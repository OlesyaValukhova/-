"""Prepare age-filterable destination coordinates from title-search candidates.

This deliberately preserves one row per programme and a separate deduplicated
location layer.  A title substring is a transparent candidate rule, not a claim
that every programme is interchangeable or currently open for enrolment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point


def location_id(longitude: float, latitude: float) -> str:
    token = f"{longitude:.12f},{latitude:.12f}"
    return "coordinate-" + hashlib.sha256(token.encode()).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--activity-label", required=True)
    parser.add_argument("--include-spatial-class", action="append", required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output directory must be new")

    with args.candidates.open(encoding="utf-8-sig", newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    selected = [
        row for row in all_rows
        if row["spatial_class"] in set(args.include_spatial_class)
        and row["card_available"] == "True"
        and row["card_min_age"] != ""
        and row["card_max_age"] != ""
    ]
    programmes = []
    locations: dict[str, dict] = {}
    for row in selected:
        longitude, latitude = float(row["catalog_longitude"]), float(row["catalog_latitude"])
        key = location_id(longitude, latitude)
        programmes.append({
            "program_id": row["program_id"],
            "program_name": row["name"],
            "organization": row["organization"],
            "activity_label": args.activity_label,
            "location_id": key,
            "min_age": float(row["card_min_age"]),
            "max_age": float(row["card_max_age"]),
            "spatial_class": row["spatial_class"],
            "boundary_distance_m": float(row["boundary_distance_m"]),
            "coordinate_state": row["coordinate_state"],
            "card_file": row["card_file"],
            "card_sha256": row["card_sha256"],
        })
        locations.setdefault(key, {"location_id": key, "geometry": Point(longitude, latitude)})

    if not programmes:
        raise ValueError("No candidates passed the stated selection rule")
    args.output.mkdir(parents=True)
    fields = list(programmes[0])
    with (args.output / "programmes.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(programmes)
    gpd.GeoDataFrame(list(locations.values()), crs=4326).to_file(
        args.output / "destinations.geojson", driver="GeoJSON"
    )
    summary = {
        "activity_label": args.activity_label,
        "candidate_file": str(args.candidates),
        "candidate_file_sha256": hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
        "selection_rule": {
            "spatial_classes": args.include_spatial_class,
            "requires_saved_detail_card": True,
            "requires_numeric_program_min_and_max_age": True,
        },
        "candidate_rows_total": len(all_rows),
        "selected_programmes": len(programmes),
        "unique_coordinate_locations": len(locations),
        "selected_by_spatial_class": dict(Counter(row["spatial_class"] for row in programmes)),
        "limits": [
            "Programme title matching happened upstream and is an incomplete candidate classifier.",
            "A coordinate is not a verified group venue or entrance.",
            "Programme age is a published eligibility field, not a mobility threshold.",
            "Location deduplication prevents co-located programmes from counting as several physical destinations.",
        ],
    }
    (args.output / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
