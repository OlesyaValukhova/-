"""Create *candidate* Urban API points for Navigator cards without coordinates.

This is address reconciliation, not venue verification or blind geocoding.  A
candidate is emitted only where the normalized Navigator address has exactly
one matching normalized Urban API address.  Ambiguous matches stay explicit in
the CSV and are never silently converted into a point.
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def norm_address(value):
    """Conservative Russian address key; preserves house and building numbers."""
    if not isinstance(value, str) or not value.strip():
        return ""
    value = unicodedata.normalize("NFKC", value).lower().replace("ё", "е")
    value = re.sub(r"^\s*\d{6}\s*,?\s*", "", value)
    value = re.sub(r"\b(санкт[ -]?петербург|спб|г\.?\s*санкт[ -]?петербург)\b\s*,?", "", value)
    replacements = {
        r"\bпроспект\b|\bпр-?кт\.?": "пр", r"\bулица\b|\bул\.?": "ул",
        r"\bнабережная\b|\bнаб\.?": "наб", r"\bпереулок\b|\bпер\.?": "пер",
        r"\bшоссе\b|\bш\.?м?\b": "ш", r"\bплощадь\b|\bпл\.?": "пл",
        r"\bкорпус\b|\bкорп\.?": "к", r"\bлитера\b|\bлит\.?": "лит",
        r"\bдом\b|\bд\.?": "д",
    }
    for pattern, replacement in replacements.items():
        value = re.sub(pattern, replacement, value)
    # Keep a compact house component comparable whether a provider wrote
    # "10к2", "10 к. 2" or "10, корпус 2".
    value = re.sub(r"(?<=\d)(?=[a-zа-я])|(?<=[a-zа-я])(?=\d)", " ", value)
    value = re.sub(r"[^0-9a-zа-я]+", " ", value)
    return " ".join(value.split())


def relaxed_address(value):
    """Second-tier key: ignores building liter but keeps street and house/corpus."""
    key = norm_address(value)
    key = re.sub(r"\bлит\s+[a-zа-я]\b", " ", key)
    key = re.sub(r"\bд\s+(?=\d)", "", key)
    return " ".join(key.split())


def parse_point(row):
    geometry = row.get("geometry") or {}
    point = geometry.get("coordinates") if geometry.get("type") == "Point" else None
    if not isinstance(point, list) or len(point) < 2:
        return None
    try:
        lon, lat = float(point[0]), float(point[1])
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def card_has_coordinate(card):
    """Navigator cards keep their point as top-level latitude/longitude."""
    try:
        lat, lon = float(card.get("latitude")), float(card.get("longitude"))
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def card_addresses(card):
    yielded = set()
    values = [("program_address", card.get("address"))]
    org = card.get("organization") or {}
    values += [("organization_address", item.get("address")) for item in org.get("addresses", []) if isinstance(item, dict)]
    for source, raw in values:
        key = norm_address(raw)
        if key and (source, key) not in yielded:
            yielded.add((source, key))
            yield source, raw, key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--urban", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.urban / "manifest.json").read_text(encoding="utf8"))
    if manifest.get("status") != "pagination_finished":
        raise ValueError("Urban archive must be complete")

    index, relaxed_index = defaultdict(list), defaultdict(list)
    for page in manifest["pages"]:
        data = json.loads((args.urban / page["file"]).read_text(encoding="utf8"))
        for row in data.get("results", []):
            key, point = norm_address(row.get("address")), parse_point(row)
            if key and point:
                index[key].append(row)
                relaxed_index[relaxed_address(row.get("address"))].append(row)

    args.output.mkdir(parents=True, exist_ok=True)
    rows, candidates, states = [], [], Counter()
    for path in sorted(args.cards.glob("*-detail.json")):
        card = json.loads(path.read_text(encoding="utf8"))
        if card_has_coordinate(card):
            continue
        card_id = card.get("id")
        addresses = list(card_addresses(card))
        if not addresses:
            rows.append({"program_id": card_id, "state": "no_published_address"})
            states["no_published_address"] += 1
            continue
        seen_objects, match_levels = {}, {}
        source_rows = []
        for source, raw, key in addresses:
            matched = index.get(key, [])
            level = "strict"
            if not matched:
                matched, level = relaxed_index.get(relaxed_address(raw), []), "relaxed_no_liter"
            source_rows.append((source, raw, key, matched, level))
            for item in matched:
                seen_objects[item["physical_object_id"]] = item
                match_levels[item["physical_object_id"]] = level
        point_rows = defaultdict(list)
        for item in seen_objects.values():
            point_rows[parse_point(item)].append(item)
        if len(point_rows) == 1:
            state = "unique_urban_address_candidate"
            point, objects = next(iter(point_rows.items()))
            item, (lon, lat) = objects[0], point
            candidates.append({"program_id": card_id, "program_name": card.get("name"),
                               "program_address": card.get("address"), "organization_name": (card.get("organization") or {}).get("name"),
                               "urban_object_ids": ";".join(str(x["physical_object_id"]) for x in objects), "urban_address": item.get("address"),
                               "longitude": lon, "latitude": lat,
                               "address_match_sources": ";".join(source for source, _, _, found, _ in source_rows if found),
                               "address_match_level": ";".join(sorted({match_levels[x["physical_object_id"]] for x in objects})),
                               "candidate_status": "address_match_not_verified_venue"})
        elif len(point_rows) > 1:
            state = "ambiguous_urban_address_candidates"
        else:
            state = "no_exact_urban_address_match"
        rows.append({"program_id": card_id, "state": state, "program_address": card.get("address"),
                     "organization_address_count": sum(1 for source, *_ in source_rows if source == "organization_address"),
                     "matched_urban_objects": len(seen_objects), "matched_urban_points": len(point_rows)})
        states[state] += 1

    fields = ["program_id", "state", "program_address", "organization_address_count", "matched_urban_objects", "matched_urban_points"]
    with (args.output / "all-missing-coordinate-address-states.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)
    candidate_fields = ["program_id", "program_name", "program_address", "organization_name", "urban_object_ids", "urban_address", "longitude", "latitude", "address_match_sources", "address_match_level", "candidate_status"]
    with (args.output / "unique-urban-address-candidates.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=candidate_fields); writer.writeheader(); writer.writerows(candidates)
    report = {"cards_input_without_card_coordinate": sum(states.values()), "states": dict(states),
              "unique_address_candidates": len(candidates), "urban_source_rows": manifest.get("rows"),
              "limitations": ["An exact normalized address is not confirmation of a programme-group venue or entrance.",
                              "Ambiguous and unmatched cards remain unlocated.",
                              "This local reconciliation does not query an external geocoder or the web."]}
    (args.output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    (args.output / "README.md").write_text("# Address-recovery candidates\n\n"
        "This is a reproducible **candidate** layer for Navigator programme cards lacking their own coordinates. "
        "It matches published addresses against the completed Urban API archive only when the normalized address maps to exactly one source object. "
        "The CSV must not be merged into the primary analysis as verified programme venues.\n\n"
        f"Cards assessed: {report['cards_input_without_card_coordinate']}; unique candidates: {len(candidates)}.\n", encoding="utf8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
