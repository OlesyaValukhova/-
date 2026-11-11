"""Calculate city-wide B1 accessibility from Navigator coordinate proxies.

Uses Transport Frames' public matrix function, not a custom router.  A
Navigator card's coordinate is a *published-coordinate proxy*, not a verified
group venue.  Thus ``N_venue_proxy`` is the principal output; the separate
``N_program_card_proxy`` is a sensitivity/control count, never a count of
confirmed programme-place offers.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from transport_frames.indicators import get_adj_matrix_gdf_to_gdf


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--origins", type=Path, required=True)
    p.add_argument("--offers", type=Path, required=True)
    p.add_argument("--venues", type=Path, required=True)
    p.add_argument("--activity", required=True)
    p.add_argument("--ages", type=float, nargs="+", default=[7, 13])
    p.add_argument("--thresholds", type=float, nargs="+", default=[10, 15, 20, 30])
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("Output directory must be new")
    a.output.mkdir(parents=True)
    manifest = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
                "scenario": "B1: normal OSM walking network; no road-barrier modification",
                "activity": a.activity, "ages": a.ages, "thresholds_minutes": a.thresholds,
                "sources": {str(x): sha(x) for x in (a.graph, a.origins, a.offers, a.venues)},
                "primary_measure": "N_venue_proxy", "secondary_measure": "N_program_card_proxy",
                "limitations": [
                    "Navigator coordinates are published-card coordinate proxies, not verified factual group venues.",
                    "Age is published eligibility; it does not encode independent-mobility ability or parental permission.",
                    "Times attach geometric points to the network and do not verify entrances, safety, capacity, schedules or participation.",
                    "This B1 result does not estimate accompaniment, car use, or parental time."]}
    path_manifest = a.output / "manifest.json"
    path_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    try:
        graph = ox.load_graphml(a.graph, edge_dtypes={"time_min": float, "length_meter": float},
                                graph_dtypes={"crs": int, "walk_speed": float})
        graph = nx.MultiDiGraph(graph)
        origins = gpd.read_file(a.origins).to_crs(graph.graph["crs"])
        origins["origin_id"] = origins.get("origin_id", pd.Series(origins.index, index=origins.index)).astype(str)
        offers = pd.read_csv(a.offers, encoding="utf-8-sig", dtype={"program_id": str, "coordinate_id": str})
        venues = gpd.read_file(a.venues).to_crs(graph.graph["crs"])
        if not venues.coordinate_id.is_unique:
            raise ValueError("Venue proxy coordinate IDs must be unique")
        if not offers.program_id.is_unique:
            raise ValueError("Programme-card IDs must be unique before calculating proxy counts")
        venues = venues.set_index("coordinate_id", drop=False)
        if not set(offers.coordinate_id).issubset(set(venues.coordinate_id)):
            raise ValueError("Every offer must refer to a venue-proxy coordinate")
        # One complete matrix supports every age and threshold; Transport Frames
        # internally reverses the calculation so the smaller venue set is source.
        matrix = get_adj_matrix_gdf_to_gdf(origins[["geometry"]], venues[["geometry"]], graph,
                                           weight="time_min", dtype=np.float32)
        matrix.columns = matrix.columns.astype(str)
        out = pd.DataFrame({"origin_id": origins["origin_id"].to_numpy()})
        audit = []
        for age in a.ages:
            eligible = offers[(offers.min_age <= age) & (offers.max_age >= age)].copy()
            ids = eligible.coordinate_id.drop_duplicates().astype(str).tolist()
            if not ids:
                raise ValueError(f"No eligible coordinate proxies for age {age}")
            sub = matrix.loc[:, ids]
            finite = np.isfinite(sub.to_numpy())
            prefix = f"age_{age:g}"
            nearest = sub.min(axis=1).replace(np.inf, np.nan)
            out[f"{prefix}_nearest_minutes"] = nearest.to_numpy()
            venue_weights = np.ones(len(ids), dtype=np.int16)
            offer_weights = eligible.groupby("coordinate_id").size().reindex(ids).to_numpy(dtype=np.int16)
            for threshold in a.thresholds:
                reachable = sub.to_numpy() <= threshold
                out[f"{prefix}_N_venue_proxy_within_{threshold:g}min"] = reachable @ venue_weights
                out[f"{prefix}_N_program_card_proxy_within_{threshold:g}min"] = reachable @ offer_weights
            audit.append({"age": age, "eligible_program_card_coordinate_proxies": int(len(eligible)),
                          "eligible_unique_coordinate_venue_proxies": len(ids),
                          "finite_nearest_origins": int(np.isfinite(nearest).sum())})
        out.to_csv(a.output / "b1-by-origin.csv", index=False, encoding="utf-8-sig")
        geo = origins[["origin_id", "geometry"]].copy().merge(out, on="origin_id", validate="one_to_one")
        geo.to_crs(4326).to_file(a.output / "b1-by-origin.geojson", driver="GeoJSON")
        manifest.update(status="computed", origins=len(origins), graph_nodes=graph.number_of_nodes(),
                        graph_edges=graph.number_of_edges(), age_sets=audit,
                        versions={x: importlib.metadata.version(x) for x in ("transport_frames", "osmnx", "networkx")})
    except Exception as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    path_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "sources"}, ensure_ascii=False))
    return 0 if manifest["status"] == "computed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
