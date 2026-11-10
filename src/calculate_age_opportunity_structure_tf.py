"""Calculate age-filtered proximity, alternatives and backup access with Transport Frames.

The script treats programme-card coordinates as published candidate locations.
It deliberately does not infer enrolment, safety, capacity, independent travel,
or observed accompaniment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import traceback

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from transport_frames.indicators import calculate_distances


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--origins", required=True, type=Path)
    parser.add_argument("--destinations", required=True, type=Path)
    parser.add_argument("--programmes", required=True, type=Path)
    parser.add_argument("--ages", type=float, required=True, nargs="+")
    parser.add_argument("--thresholds", type=float, required=True, nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be a new directory")
    args.output.mkdir(parents=True)
    manifest_path = args.output / "manifest.json"
    report = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
              "indicator": "age-filtered published-location proximity and choice structure",
              "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (args.graph, args.origins, args.destinations, args.programmes)}}
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    try:
        graph = ox.load_graphml(args.graph, edge_dtypes={"time_min": float, "length_meter": float},
                                graph_dtypes={"crs": int, "walk_speed": float})
        graph = nx.MultiDiGraph(ox.convert.to_digraph(graph, weight="time_min"))
        origins = gpd.read_file(args.origins).to_crs(graph.graph["crs"])
        if "origin_id" not in origins:
            origins["origin_id"] = "origin-source-" + origins["source_row"].astype(str)
        destinations = gpd.read_file(args.destinations).to_crs(graph.graph["crs"])
        programmes = pd.read_csv(args.programmes, encoding="utf-8-sig", dtype={"program_id": str, "location_id": str})
        if not destinations.location_id.is_unique:
            raise ValueError("Destination location IDs must be unique")
        base = origins[["origin_id"]].copy()
        details = []
        for age in args.ages:
            eligible = programmes[(programmes.min_age <= age) & (programmes.max_age >= age)]
            ids = sorted(eligible.location_id.unique())
            target = destinations.set_index("location_id").loc[ids].reset_index()
            times = []
            for location_id in ids:
                one = target[target.location_id == location_id]
                times.append(calculate_distances(origins.copy(), one, graph, weight="time_min", unit_div=1).to_numpy())
            matrix = np.column_stack(times)
            ordered = np.sort(matrix, axis=1)
            prefix = f"age_{age:g}"
            base[f"{prefix}_nearest_minutes"] = ordered[:, 0]
            base[f"{prefix}_second_nearest_minutes"] = ordered[:, 1] if len(ids) > 1 else np.nan
            base[f"{prefix}_backup_gap_minutes"] = ordered[:, 1] - ordered[:, 0] if len(ids) > 1 else np.nan
            for threshold in args.thresholds:
                base[f"{prefix}_locations_within_{threshold:g}min"] = (matrix <= threshold).sum(axis=1)
            details.append({"age": age, "eligible_programmes": int(len(eligible)), "eligible_locations": len(ids),
                            "finite_nearest_origins": int(np.isfinite(ordered[:, 0]).sum())})
        base.to_csv(args.output / "opportunity-structure-by-origin.csv", encoding="utf-8-sig", index=False)
        report.update(status="computed", origins=len(origins), age_sets=details, thresholds_minutes=args.thresholds,
                      graph_nodes=graph.number_of_nodes(), graph_edges=graph.number_of_edges(),
                      versions={x: importlib.metadata.version(x) for x in ("transport_frames", "osmnx", "networkx")},
                      limitations=["Times use Transport Frames default straight-line network attachments, not verified entrances.",
                                   "A destination is a published programme-card coordinate, not a confirmed group venue.",
                                   "The count is a number of distinct coordinate locations, not programmes, seats, quality, participation or choice.",
                                   "Age filters published programme eligibility only; they do not model ability or permission to travel independently."])
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"sources", "traceback"}}, ensure_ascii=False))
    return int(report["status"] != "computed")


if __name__ == "__main__":
    raise SystemExit(main())
