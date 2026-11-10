"""Calculate nearest age-eligible programme location with Transport Frames.

This is intentionally a nearest-location indicator. It avoids unsupported
capacity, demand, price, safety, or observed-travel claims and does not treat
programme age eligibility as a mobility threshold.
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
    parser.add_argument("--ages", type=float, nargs="+", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output directory must be new")
    args.output.mkdir(parents=True)
    manifest_path = args.output / "manifest.json"
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "indicator": "Transport Frames default nearest network time to one published coordinate",
        "programme_accessibility_computed": False,
        "sources": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (args.graph, args.origins, args.destinations, args.programmes)
        },
    }
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        graph = ox.load_graphml(args.graph, edge_dtypes={"time_min": float, "length_meter": float},
                                graph_dtypes={"crs": int, "walk_speed": float})
        graph = ox.convert.to_digraph(graph, weight="time_min")
        graph = nx.MultiDiGraph(graph)
        origins = gpd.read_file(args.origins).to_crs(graph.graph["crs"])
        if "origin_id" not in origins.columns:
            if "source_row" not in origins.columns:
                raise ValueError("Origins require origin_id or source_row")
            origins["origin_id"] = "origin-source-" + origins["source_row"].astype(str)
        destinations = gpd.read_file(args.destinations).to_crs(graph.graph["crs"])
        programmes = pd.read_csv(args.programmes, encoding="utf-8-sig", dtype={"program_id": str, "location_id": str})
        if not destinations.location_id.is_unique or not set(programmes.location_id).issubset(set(destinations.location_id)):
            raise ValueError("Destination IDs do not match programme-location mapping")
        rows = origins[["origin_id"]].copy()
        details = []
        for age in args.ages:
            eligible = programmes[(programmes.min_age <= age) & (programmes.max_age >= age)]
            location_ids = sorted(eligible.location_id.unique())
            if not location_ids:
                raise ValueError(f"No eligible locations for age {age}")
            target = destinations[destinations.location_id.isin(location_ids)].copy()
            nearest = calculate_distances(origins.copy(), target, graph, weight="time_min", unit_div=1)
            column = f"tf_default_nearest_minutes_age_{age:g}"
            rows[column] = nearest.values
            details.append({"age": age, "eligible_programmes": int(len(eligible)), "eligible_locations": int(len(target)),
                            "finite_origins": int(np.isfinite(nearest).sum())})
        rows.to_csv(args.output / "nearest-times.csv", index=False, encoding="utf-8-sig")
        report.update(
            status="computed", programme_accessibility_computed=True, origins=len(origins), age_sets=details,
            graph_nodes=graph.number_of_nodes(), graph_edges=graph.number_of_edges(),
            versions={name: importlib.metadata.version(name) for name in ["transport_frames", "osmnx", "networkx"]},
            limitations=[
                "Transport Frames default distance includes straight-line attachments; it is not a verified entrance-to-entrance walk.",
                "Coordinates are published programme-card points, not confirmed group venues.",
                "Programme eligibility does not establish actual participation, age-specific walking capability, safety, or accompaniment.",
                "The saved walking graph is dated by its metadata to 31.05.2026 and was not refreshed.",
            ],
        )
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"sources", "traceback"}}, ensure_ascii=True))
    return 0 if report["status"] == "computed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
