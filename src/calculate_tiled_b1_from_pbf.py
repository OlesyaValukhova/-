"""Calculate B1 sequentially from a local OSM PBF in buffered core tiles.

Each residential origin belongs to exactly one non-overlapping core tile.  For
that tile only, the script builds a walk graph from PBF ways intersecting a
buffer.  The buffer equals the largest reported walking radius by default.
Thus every route whose total length is within the reported maximum is contained
in the buffered region; no city-wide NetworkX graph is held in memory.

The script uses Transport Frames for the OD matrix.  It does not estimate
actual journeys, accompaniment, safety, capacity or independent mobility.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box
from transport_frames.indicators import get_adj_matrix_gdf_to_gdf


# Kept local so the graph-free island validator needs only Transport Frames,
# not the PBF reader installed in the BlocksNet environment.
WALK_SPEED_M_PER_MIN = 5_000 / 60


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def make_tiles(origins: gpd.GeoDataFrame, tile_size: float) -> list[tuple[int, int, gpd.GeoDataFrame, tuple[float, float, float, float]]]:
    minx, miny, _, _ = origins.total_bounds
    keys_x = np.floor((origins.geometry.x.to_numpy() - minx) / tile_size).astype(int)
    keys_y = np.floor((origins.geometry.y.to_numpy() - miny) / tile_size).astype(int)
    keyed = origins.assign(_tile_x=keys_x, _tile_y=keys_y)
    result = []
    for (ix, iy), group in keyed.groupby(["_tile_x", "_tile_y"], sort=True):
        x0, y0 = minx + ix * tile_size, miny + iy * tile_size
        result.append((int(ix), int(iy), group.drop(columns=["_tile_x", "_tile_y"]).copy(),
                       (x0, y0, x0 + tile_size, y0 + tile_size)))
    return result


def calculate_tile(graph, origins: gpd.GeoDataFrame, venues: gpd.GeoDataFrame, offers: pd.DataFrame,
                   ages: list[float], thresholds: list[float]) -> tuple[pd.DataFrame, list[dict]]:
    if not graph or graph.number_of_edges() == 0:
        raise RuntimeError("Tile has no usable walking graph")
    result = pd.DataFrame({"origin_id": origins.origin_id.astype(str).to_numpy()})
    audit = []
    max_threshold = max(thresholds)
    for age in ages:
        eligible = offers[(offers.min_age <= age) & (offers.max_age >= age)].copy()
        ids = eligible.coordinate_id.drop_duplicates().astype(str).tolist()
        prefix = f"age_{age:g}"
        if not ids:
            # No destination can be reached inside the maximum reporting
            # radius.  Zero counts are a result, not a tile-processing error.
            result[f"{prefix}_nearest_minutes"] = np.nan
            for threshold in thresholds:
                result[f"{prefix}_N_venue_proxy_within_{threshold:g}min"] = 0
                result[f"{prefix}_N_program_card_proxy_within_{threshold:g}min"] = 0
            audit.append({"age": age, "eligible_program_card_coordinate_proxies": 0,
                          "eligible_unique_coordinate_venue_proxies": 0, "finite_nearest_origins": 0})
            continue
        local = venues.set_index("coordinate_id").loc[ids]
        matrix = get_adj_matrix_gdf_to_gdf(origins[["geometry"]], local[["geometry"]], graph,
                                           weight="time_min", dtype=np.float32)
        matrix.columns = ids
        nearest = matrix.min(axis=1).replace(np.inf, np.nan)
        # A shortest path longer than the buffer cannot be interpreted from a
        # local tile.  Counts at all reported thresholds remain exact.
        result[f"{prefix}_nearest_minutes"] = nearest.where(nearest <= max_threshold, np.nan).to_numpy()
        venue_weights = np.ones(len(ids), dtype=np.int16)
        offer_weights = eligible.groupby("coordinate_id").size().reindex(ids).to_numpy(dtype=np.int16)
        for threshold in thresholds:
            reachable = matrix.to_numpy() <= threshold
            result[f"{prefix}_N_venue_proxy_within_{threshold:g}min"] = reachable @ venue_weights
            result[f"{prefix}_N_program_card_proxy_within_{threshold:g}min"] = reachable @ offer_weights
        audit.append({"age": age, "eligible_program_card_coordinate_proxies": int(len(eligible)),
                      "eligible_unique_coordinate_venue_proxies": len(ids),
                      "finite_nearest_origins": int(np.isfinite(result[f"{prefix}_nearest_minutes"]).sum())})
    return result, audit


def uncovered_tile(origins: gpd.GeoDataFrame, ages: list[float], thresholds: list[float]) -> pd.DataFrame:
    """Keep an explicit missing-data row; never recode absent network as zero access."""
    result = pd.DataFrame({"origin_id": origins.origin_id.astype(str).to_numpy(), "network_covered": False})
    for age in ages:
        prefix = f"age_{age:g}"
        result[f"{prefix}_nearest_minutes"] = np.nan
        for threshold in thresholds:
            result[f"{prefix}_N_venue_proxy_within_{threshold:g}min"] = np.nan
            result[f"{prefix}_N_program_card_proxy_within_{threshold:g}min"] = np.nan
    return result


def main() -> int:
    from build_walk_graph_from_osm_pbf import WalkGraphHandler
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pbf", type=Path, required=True)
    p.add_argument("--origins", type=Path, required=True)
    p.add_argument("--offers", type=Path, required=True)
    p.add_argument("--venues", type=Path, required=True)
    p.add_argument("--activity", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--ages", type=float, nargs="+", default=[7, 13])
    p.add_argument("--thresholds", type=float, nargs="+", default=[10, 15, 20, 30])
    p.add_argument("--tile-size-m", type=float, default=4_000)
    p.add_argument("--buffer-m", type=float, help="Default: max threshold × 5 km/h")
    p.add_argument("--crs", type=int, default=32636)
    p.add_argument("--max-tiles", type=int, help="Stop after this many tiles; useful only for a smoke test")
    args = p.parse_args()
    if args.output.exists(): p.error("Output directory must be new")
    if not args.pbf.is_file() or args.tile_size_m <= 0: p.error("PBF must exist and tile size must be positive")
    buffer_m = args.buffer_m if args.buffer_m is not None else max(args.thresholds) * WALK_SPEED_M_PER_MIN
    if buffer_m + 1e-6 < max(args.thresholds) * WALK_SPEED_M_PER_MIN:
        p.error("Buffer must be at least the maximum threshold times walking speed")
    args.output.mkdir(parents=True)
    manifest_path = args.output / "manifest.json"
    manifest = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
                "scenario": "B1 ordinary OSM walking network in sequential buffered core tiles",
                "activity": args.activity, "ages": args.ages, "thresholds_minutes": args.thresholds,
                "tile_size_m": args.tile_size_m, "buffer_m": buffer_m, "crs": args.crs,
                "sources": {str(x): sha(x) for x in (args.pbf, args.origins, args.offers, args.venues)},
                "primary_measure": "N_venue_proxy", "secondary_measure": "N_program_card_proxy",
                "limitations": [
                    "Tile buffer proves containment only for routes no longer than the largest reported threshold; values beyond it are not interpreted.",
                    "Navigator coordinates are published-card coordinate proxies, not verified group venues.",
                    "Age is published eligibility, not independent-mobility ability or parental permission.",
                    "No entrances, safety, schedules, capacity, participation, accompaniment, car travel or parental time are estimated."]}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    try:
        origins = gpd.read_file(args.origins).to_crs(args.crs)
        origins["origin_id"] = origins.get("origin_id", pd.Series(origins.index, index=origins.index)).astype(str)
        if not origins.origin_id.is_unique: raise ValueError("origin_id must be unique")
        offers = pd.read_csv(args.offers, encoding="utf-8-sig", dtype={"program_id": str, "coordinate_id": str})
        venues = gpd.read_file(args.venues).to_crs(args.crs)
        venues["coordinate_id"] = venues.coordinate_id.astype(str)
        if not venues.coordinate_id.is_unique or not offers.program_id.is_unique: raise ValueError("Input proxy IDs must be unique")
        if not set(offers.coordinate_id.astype(str)).issubset(set(venues.coordinate_id)): raise ValueError("Offer references missing venue")
        tiles = make_tiles(origins, args.tile_size_m)
        completed, audits, tile_rows = [], [], []
        for ordinal, (ix, iy, tile_origins, core_bounds) in enumerate(tiles, start=1):
            if args.max_tiles and ordinal > args.max_tiles: break
            minx, miny, maxx, maxy = core_bounds
            buffered = box(minx, miny, maxx, maxy).buffer(buffer_m)
            # Any destination reachable within the maximum threshold from a core
            # origin lies in this buffer by the straight-line lower bound.
            local_venues = venues.loc[venues.geometry.intersects(buffered)].copy()
            local_offers = offers[offers.coordinate_id.astype(str).isin(set(local_venues.coordinate_id))].copy()
            handler = WalkGraphHandler(args.crs, tuple(buffered.bounds))
            handler.apply_file(str(args.pbf), locations=True)
            graph = handler.graph
            row = {"tile": ordinal, "tile_x": ix, "tile_y": iy, "core_bounds": list(core_bounds),
                   "origins": len(tile_origins), "venues_in_buffer": len(local_venues),
                   "graph_nodes": graph.number_of_nodes(), "graph_edges": graph.number_of_edges()}
            if not graph or graph.number_of_edges() == 0:
                row["status"] = "uncovered_no_usable_pbf_network"
                values = uncovered_tile(tile_origins, args.ages, args.thresholds)
                audit = []
            else:
                row["status"] = "computed"
                values, audit = calculate_tile(graph, tile_origins, local_venues, local_offers, args.ages, args.thresholds)
                values.insert(1, "network_covered", True)
            completed.append(values); audits.extend([{**x, "tile": ordinal} for x in audit]); tile_rows.append(row)
            del graph, handler, values
            pd.DataFrame(tile_rows).to_json(args.output / "tile-progress.json", orient="records", force_ascii=False, indent=2)
        if len(completed) != len(tiles):
            raise RuntimeError(f"Stopped after {len(completed)} of {len(tiles)} tiles; no partial city result is exported")
        out = pd.concat(completed, ignore_index=True)
        if not out.origin_id.is_unique or len(out) != len(origins): raise RuntimeError("Tiling did not produce exactly one row per origin")
        out = origins[["origin_id"]].merge(out, on="origin_id", validate="one_to_one")
        out.to_csv(args.output / "b1-by-origin.csv", index=False, encoding="utf-8-sig")
        geo = origins[["origin_id", "geometry"]].merge(out, on="origin_id", validate="one_to_one")
        geo.to_crs(4326).to_file(args.output / "b1-by-origin.geojson", driver="GeoJSON")
        uncovered = int((~out.network_covered).sum())
        manifest.update(status="computed" if uncovered == 0 else "computed_with_uncovered_origins", origins=len(origins), tiles=len(tiles), tile_audit=tile_rows,
                        origins_without_usable_network=uncovered,
                        age_tile_audit=audits, versions={x: importlib.metadata.version(x) for x in ("transport_frames", "networkx", "osmnx", "osmium")})
    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({k: v for k, v in manifest.items() if k not in {"sources", "tile_audit"}}, ensure_ascii=False))
    return int(manifest["status"] not in {"computed", "computed_with_uncovered_origins"})


if __name__ == "__main__":
    raise SystemExit(main())
