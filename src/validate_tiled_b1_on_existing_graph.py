"""Validate buffered core tiling against one already-calculated whole graph.

This is an accuracy test for the tile boundary rule.  It intentionally uses
the same origins, published-coordinate proxies, thresholds and Transport
Frames matrix on (a) the full graph and (b) induced buffered subgraphs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

from calculate_tiled_b1_from_pbf import WALK_SPEED_M_PER_MIN, calculate_tile, make_tiles


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--origins", type=Path, required=True)
    p.add_argument("--offers", type=Path, required=True)
    p.add_argument("--venues", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--ages", type=float, nargs="+", default=[7, 13])
    p.add_argument("--thresholds", type=float, nargs="+", default=[10, 15, 20, 30])
    p.add_argument("--tile-size-m", type=float, default=2_000)
    p.add_argument("--buffer-m", type=float)
    p.add_argument("--tolerance", type=float, default=1e-5)
    args = p.parse_args()
    if args.output.exists(): p.error("Output must be new")
    args.output.mkdir(parents=True)
    buffer_m = args.buffer_m if args.buffer_m is not None else max(args.thresholds) * WALK_SPEED_M_PER_MIN
    report = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
              "tile_size_m": args.tile_size_m, "buffer_m": buffer_m,
              "thresholds_minutes": args.thresholds, "ages": args.ages}
    try:
        graph = nx.MultiDiGraph(ox.load_graphml(args.graph, edge_dtypes={"time_min": float, "length_meter": float},
                                                graph_dtypes={"crs": int, "walk_speed": float}))
        crs = graph.graph["crs"]
        origins = gpd.read_file(args.origins).to_crs(crs)
        origins["origin_id"] = origins.get("origin_id", pd.Series(origins.index, index=origins.index)).astype(str)
        offers = pd.read_csv(args.offers, encoding="utf-8-sig", dtype={"program_id": str, "coordinate_id": str})
        venues = gpd.read_file(args.venues).to_crs(crs)
        venues["coordinate_id"] = venues.coordinate_id.astype(str)
        whole, _ = calculate_tile(graph, origins, venues, offers, args.ages, args.thresholds)
        tiled = []
        rows = []
        for ordinal, (_, _, tile_origins, bounds) in enumerate(make_tiles(origins, args.tile_size_m), start=1):
            minx, miny, maxx, maxy = bounds
            expanded = (minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m)
            node_ids = [n for n, d in graph.nodes(data=True)
                        if expanded[0] <= float(d["x"]) <= expanded[2] and expanded[1] <= float(d["y"]) <= expanded[3]]
            subgraph = nx.MultiDiGraph(graph.subgraph(node_ids).copy())
            local_venues = venues.loc[(venues.geometry.x >= expanded[0]) & (venues.geometry.x <= expanded[2]) &
                                      (venues.geometry.y >= expanded[1]) & (venues.geometry.y <= expanded[3])].copy()
            local_offers = offers[offers.coordinate_id.astype(str).isin(set(local_venues.coordinate_id))].copy()
            values, _ = calculate_tile(subgraph, tile_origins, local_venues, local_offers, args.ages, args.thresholds)
            tiled.append(values)
            rows.append({"tile": ordinal, "origins": len(tile_origins), "nodes": subgraph.number_of_nodes(),
                         "edges": subgraph.number_of_edges(), "venues": len(local_venues)})
        tiled = pd.concat(tiled, ignore_index=True).sort_values("origin_id").reset_index(drop=True)
        whole = whole.sort_values("origin_id").reset_index(drop=True)
        if not whole.origin_id.equals(tiled.origin_id): raise RuntimeError("Tile output lost or duplicated origin IDs")
        numeric = [c for c in whole.columns if c not in {"origin_id", "network_covered"}]
        if "network_covered" in whole and not whole.network_covered.equals(tiled.network_covered):
            raise RuntimeError("Tiling changed network coverage flags")
        diff = (whole[numeric] - tiled[numeric]).abs()
        summary = pd.DataFrame({"column": numeric, "max_absolute_difference": diff.max().to_numpy(),
                                "different_origins": (diff > args.tolerance).sum().to_numpy()})
        summary.to_csv(args.output / "comparison-by-field.csv", index=False, encoding="utf-8-sig")
        whole.to_csv(args.output / "whole-graph-b1-by-origin.csv", index=False, encoding="utf-8-sig")
        tiled.to_csv(args.output / "tiled-b1-by-origin.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(rows).to_csv(args.output / "tile-audit.csv", index=False, encoding="utf-8-sig")
        mismatch = int((diff > args.tolerance).sum().sum())
        report.update(status="validated" if mismatch == 0 else "not_validated", origins=len(origins), tiles=len(rows),
                      graph_nodes=graph.number_of_nodes(), graph_edges=graph.number_of_edges(),
                      tolerance=args.tolerance, differing_cells=mismatch,
                      maximum_absolute_difference=float(diff.max().max()))
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (args.output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(report, ensure_ascii=False))
    return int(report["status"] != "validated")


if __name__ == "__main__":
    raise SystemExit(main())
