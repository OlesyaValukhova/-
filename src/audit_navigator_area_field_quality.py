"""Summarise Navigator card-field quality inside a supplied geographic boundary.

The input CSV is produced by audit_navigator_snapshot_fields.py.  Coordinates
are treated only as coordinates published on a programme card.  This script
does not geocode blank addresses or infer a group venue.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from shapely.geometry import Point, shape


def read_boundary(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") == "FeatureCollection":
        geometries = [shape(feature["geometry"]) for feature in data["features"]]
        if len(geometries) != 1:
            raise ValueError("Boundary FeatureCollection must contain exactly one geometry")
        return geometries[0]
    if data.get("type") == "Feature":
        return shape(data["geometry"])
    return shape(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fields", required=True, type=Path)
    parser.add_argument("--boundary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--area-name", required=True)
    args = parser.parse_args()

    boundary = read_boundary(args.boundary)
    selected: list[dict[str, str]] = []
    excluded_no_coordinate = 0

    with args.fields.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                longitude = float(row["longitude_raw"])
                latitude = float(row["latitude_raw"])
            except (TypeError, ValueError):
                excluded_no_coordinate += 1
                continue
            if boundary.covers(Point(longitude, latitude)):
                selected.append(row)

    args.output.mkdir(parents=True, exist_ok=True)
    fields = [
        "coordinate_state",
        "program_age_state",
        "program_address_state",
        "directivity_state",
        "study_areas_state",
        "payment_state",
        "cost_state",
    ]
    counts = {field: dict(Counter(row[field] for row in selected)) for field in fields}
    combined = Counter(
        f"coordinate={row['coordinate_state']}|age={row['program_age_state']}"
        for row in selected
    )
    districts = dict(Counter(row["district"] or "missing" for row in selected))

    summary = {
        "area_name": args.area_name,
        "boundary_file": str(args.boundary),
        "input_fields_file": str(args.fields),
        "selection_rule": (
            "A card is included when both card coordinates parse as numbers and "
            "the point is covered by the supplied boundary in CRS84 longitude/latitude."
        ),
        "selected_cards": len(selected),
        "input_rows_without_parseable_coordinate": excluded_no_coordinate,
        "field_state_counts": counts,
        "coordinate_and_age_state_counts": dict(combined),
        "district_labels_among_selected_cards": districts,
        "interpretation_limits": [
            "The point is a programme-card coordinate, not a verified group venue or entrance.",
            "Cards without coordinates cannot be spatially assigned by this audit.",
            "A known programme age interval is an eligibility field, not a measure of independent mobility.",
            "The result covers the saved Navigator snapshot, not all city provision.",
        ],
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (args.output / "selected-program-field-state.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(selected[0]) if selected else [])
        if selected:
            writer.writeheader()
            writer.writerows(selected)


if __name__ == "__main__":
    main()
