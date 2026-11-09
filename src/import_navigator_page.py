"""Import a user-saved public program catalogue response without network access."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from collect_navigator import page_payload, public_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    data = page_payload(raw.decode("utf-8-sig"))
    following = data.get("next")
    if following:
        public_url(following)
        if urlsplit(following).path.rstrip("/") != "/api/program/list_odo":
            raise ValueError("Not a verified program catalogue response")
    records = data["results"]
    ids = [r.get("id") for r in records]
    if any(not isinstance(x, int) or isinstance(x, bool) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("Missing or duplicate program IDs; inspect input")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "source-response.json").write_bytes(raw)
    fields = sorted({key for row in records for key in row})
    with (args.output / "programs.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict))
                             else value for key, value in row.items()})
    coords = lambda r: r.get("latitude") is not None and r.get("longitude") is not None
    summary = {
        "imported_utc": datetime.now(timezone.utc).isoformat(),
        "origin": "user_supplied_response; request not executed by importer",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "declared_filtered_count": data["count"], "imported_records": len(records),
        "next": following, "previous": data.get("previous"),
        "query_of_next_page": dict(parse_qsl(urlsplit(following).query)) if following else None,
        "complete_city_export": False, "fields": fields,
        "records_with_coordinate_pair": sum(coords(r) for r in records),
        "records_with_profiles": sum(bool(r.get("profiles")) for r in records),
        "records_with_study_areas": sum(bool(r.get("study_areas")) for r in records),
        "age_group_venue_link_verified": False,
        "note": "Coordinates in list response are not yet verified as actual group venues; no age inferred.",
    }
    (args.output / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
