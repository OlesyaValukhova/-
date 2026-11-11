"""Create city-wide Navigator offer proxies for fixed activity-title rules.

The Navigator card coordinate is published with a programme card but is not a
verified venue of every group.  The primary rows are therefore deliberately
called ``program_card_coordinate_offer`` (one card id × coordinate), while a
separate coordinate-deduplicated layer is a venue proxy for concentration
checks.  Age is published programme eligibility, not mobility capability.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point


ACTIVITIES = {
    "chess": ("Шахматы: название содержит «шахмат»", re.compile(r"шахмат", re.I)),
    "robotics": ("Робототехника: название содержит «робот»", re.compile(r"робот", re.I)),
}


def number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def coord_id(lon: float, lat: float) -> str:
    value = f"{lon:.12f},{lat:.12f}"
    return "coordinate-" + hashlib.sha256(value.encode()).hexdigest()[:16]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--details", type=Path, required=True)
    p.add_argument("--catalogue", type=Path, required=True,
                   help="Navigator catalogue CSV used to preselect title candidates before opening detail cards")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--activity", choices=sorted(ACTIVITIES), action="append")
    a = p.parse_args()
    if a.output.exists():
        p.error("Output directory must be new")
    requested = a.activity or sorted(ACTIVITIES)
    selected = {key: [] for key in requested}
    candidate_keys: dict[str, set[str]] = {key: set() for key in requested}
    with a.catalogue.open(encoding="utf-8-sig", newline="") as f:
        catalogue_rows = list(csv.DictReader(f))
    for row in catalogue_rows:
        title = str(row.get("name") or "")
        identifier = str(row.get("id") or "")
        for key in requested:
            if ACTIVITIES[key][1].search(title):
                candidate_keys[key].add(identifier)
    candidate_ids = set().union(*candidate_keys.values())
    cards_read = 0
    for identifier in sorted(candidate_ids, key=lambda x: int(x) if x.isdigit() else x):
        path = a.details / f"{identifier}-detail.json"
        if not path.is_file():
            continue
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cards_read += 1
        title = str(card.get("name") or "")
        lon, lat = number(card.get("longitude")), number(card.get("latitude"))
        min_age, max_age = number(card.get("min_age")), number(card.get("max_age"))
        if None in (lon, lat, min_age, max_age) or min_age > max_age:
            continue
        for key in requested:
            label, pattern = ACTIVITIES[key]
            if str(card.get("id")) not in candidate_keys[key] or not pattern.search(title):
                continue
            selected[key].append({
                "program_id": str(card.get("id")),
                "program_name": title,
                "organization": ((card.get("organization") or {}).get("name") or ""),
                "activity_key": key,
                "activity_rule": label,
                "offer_unit": "program_card_coordinate_offer_proxy",
                "coordinate_id": coord_id(lon, lat),
                "longitude": lon,
                "latitude": lat,
                "min_age": min_age,
                "max_age": max_age,
                "published_address": str(card.get("address") or ""),
                "card_file": str(path),
            })
    a.output.mkdir(parents=True)
    summary = {"created_utc": datetime.now(timezone.utc).isoformat(), "details_directory": str(a.details),
               "details_directory_sha256_note": "Individual raw cards retained; directory hash not computed.",
               "catalogue": str(a.catalogue), "catalogue_rows": len(catalogue_rows),
               "title_candidates_in_catalogue": {k: len(v) for k, v in candidate_keys.items()},
               "detail_cards_opened_after_catalogue_preselection": cards_read, "activities": {},
               "unit_of_analysis": "program_card_coordinate_offer_proxy",
               "venue_control": "unique published coordinates; neither layer confirms factual group venue",
               "limits": ["A Navigator programme-card coordinate is not a verified address of a particular group.",
                          "One card may aggregate several groups; group schedules, enrolment, capacity and actual attendance are not modelled.",
                          "Title rules identify transparent activity candidates and may omit or misclassify programmes.",
                          "Published age eligibility is not a child mobility threshold."]}
    for key, rows in selected.items():
        rows.sort(key=lambda row: (int(row["program_id"]) if row["program_id"].isdigit() else row["program_id"]))
        with (a.output / f"{key}-program-card-coordinate-offers.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["program_id"])
            writer.writeheader(); writer.writerows(rows)
        venues = {}
        for row in rows:
            venues.setdefault(row["coordinate_id"], {"coordinate_id": row["coordinate_id"],
                "geometry": Point(row["longitude"], row["latitude"]), "cards_at_coordinate": 0})
            venues[row["coordinate_id"]]["cards_at_coordinate"] += 1
        gpd.GeoDataFrame(list(venues.values()), crs=4326).to_file(a.output / f"{key}-coordinate-venue-proxy.geojson", driver="GeoJSON")
        summary["activities"][key] = {"program_card_coordinate_offer_proxies": len(rows),
            "unique_coordinate_venue_proxies": len(venues),
            "eligible_at_age_7": sum(row["min_age"] <= 7 <= row["max_age"] for row in rows),
            "eligible_at_age_13": sum(row["min_age"] <= 13 <= row["max_age"] for row in rows),
            "card_coordinates_per_venue_proxy": dict(Counter(v["cards_at_coordinate"] for v in venues.values()))}
    (a.output / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
