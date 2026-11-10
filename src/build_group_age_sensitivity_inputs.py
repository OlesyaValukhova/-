"""Build a group-age sensitivity input without replacing programme-age inputs.

One retained row represents a saved group with numeric min/max ages. Its
coordinate remains the programme-card coordinate, so this is a sensitivity
analysis of the stored catalogue fields, not validation of a venue or schedule.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--programmes", type=Path, required=True)
    parser.add_argument("--destinations", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output directory must be new")
    source = pd.read_csv(args.programmes, encoding="utf-8-sig", dtype={"program_id": str, "location_id": str})
    records = []
    excluded_no_numeric_groups = []
    for row in source.itertuples(index=False):
        card_path = args.details / f"{row.program_id}-detail.json"
        card = json.loads(card_path.read_text(encoding="utf-8"))
        numeric_groups = []
        for group in card.get("groups") or []:
            if group.get("min_age") not in (None, "") and group.get("max_age") not in (None, ""):
                numeric_groups.append(group)
        if not numeric_groups:
            excluded_no_numeric_groups.append(row.program_id)
        for group in numeric_groups:
            record = row._asdict()
            record.update({
                "programme_card_id": row.program_id,
                "program_id": f"{row.program_id}-group-{group.get('id')}",
                "group_id": group.get("id"),
                "min_age": float(group["min_age"]),
                "max_age": float(group["max_age"]),
                "group_status_raw": (group.get("status") or {}).get("id"),
                "group_lesson_start": group.get("lesson_start"),
                "group_lesson_end": group.get("lesson_end"),
                "group_open_request_raw": group.get("requests_from_public"),
            })
            records.append(record)
    if not records:
        raise ValueError("No saved groups with numeric age ranges")
    args.output.mkdir(parents=True)
    pd.DataFrame(records).to_csv(args.output / "groups-as-age-filter-rows.csv", index=False, encoding="utf-8-sig")
    gpd.read_file(args.destinations).to_file(args.output / "destinations.geojson", driver="GeoJSON")
    report = {
        "source_program_cards": len(source),
        "source_unique_coordinates": int(source.location_id.nunique()),
        "saved_groups_with_numeric_age": len(records),
        "programme_cards_without_numeric_group_age": len(excluded_no_numeric_groups),
        "programme_card_ids_without_numeric_group_age": excluded_no_numeric_groups,
        "limitations": [
            "Saved group fields may be stale and do not prove a currently available group.",
            "Group records retain their programme-card coordinate; this does not verify the group venue.",
            "This is a sensitivity variant, not a replacement for programme-level published eligibility.",
        ],
    }
    (args.output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
