"""Aggregate completed B3 direction-level results to existing BlocksNet blocks.

This is deliberately an aggregation-only step: routing remains in the B3 run
and is never recomputed here.
"""
from pathlib import Path
import argparse
import hashlib
import json

import geopandas as gpd
import pandas as pd


BLOCKS = Path(r"C:\Users\olesy\PycharmProjects\blocksnet-data\cities\saint_petersburg\data\blocks_cleaned.geojson")
ORIGINS = Path("data/urban-api-spb-residential-20261110/residential.geojson")
CASES = Path("data/navigator-study-area-cases-ascii-20261111/manifest.json")
DEFAULT_INPUT = Path("results/blocksnet-b3-directions-citywide-20261112")
DEFAULT_OUT = Path("results/age-profiles-blocks-b3-20261112")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main(source: Path, out: Path):
    if not (source / "summary.json").is_file():
        raise FileNotFoundError(f"Missing completed B3 summary: {source / 'summary.json'}")
    out.mkdir(parents=True, exist_ok=True)
    blocks = gpd.read_file(BLOCKS, engine="pyogrio").to_crs(32636)
    source_block_records = len(blocks)
    blocks["blocksnet_block_id"] = blocks.geometry.map(
        lambda geom: hashlib.sha256(geom.normalize().wkb).hexdigest()[:16]
    )
    blocks = blocks.drop_duplicates("blocksnet_block_id", keep="first").copy()
    origins = gpd.read_file(ORIGINS, engine="pyogrio")[["geometry"]].reset_index(drop=True).to_crs(32636)
    origins["origin_id"] = origins.index.astype(str)
    joined = gpd.sjoin(
        origins, blocks[["blocksnet_block_id", "geometry"]], predicate="within", how="left"
    ).drop(columns="index_right")
    if joined.origin_id.duplicated().any():
        raise RuntimeError("An origin matched multiple BlocksNet polygons")

    cases = json.loads(CASES.read_text(encoding="utf-8"))["included_cases"]
    frames, layers, qa = [], [], []
    for case in cases:
        path = source / case["case_id"] / "b3-by-origin.csv"
        if not path.is_file():
            raise FileNotFoundError(path)
        data = pd.read_csv(path, dtype={"origin_id": str})
        x = joined[["origin_id", "blocksnet_block_id"]].merge(
            data, on="origin_id", how="left", validate="one_to_one"
        )
        n7 = x.age_7_N_venue_proxy_within_30min
        n13 = x.age_13_N_venue_proxy_within_30min
        valid = x.network_covered.eq(True) & n7.notna() & n13.notna()
        x["category"] = "unknown"
        x.loc[~x.network_covered.eq(True), "category"] = "uncovered"
        x.loc[valid & (n7 > 0) & (n13 > 0), "category"] = "both"
        x.loc[valid & (n7 > 0) & (n13 == 0), "category"] = "only_7"
        x.loc[valid & (n7 == 0) & (n13 > 0), "category"] = "only_13"
        x.loc[valid & (n7 == 0) & (n13 == 0), "category"] = "neither"
        x["delta_N"] = n13 - n7
        x["delta_t"] = x.age_13_nearest_minutes - x.age_7_nearest_minutes
        rows = []
        for block_id, group in x.groupby("blocksnet_block_id", dropna=True):
            observed = group[group.network_covered.eq(True) & group.delta_N.notna()]
            row = {
                "blocksnet_block_id": block_id,
                "study_area_id": case["study_area_id"],
                "study_area_name": case["study_area_name"],
                "n_origins": len(group), "n_valid": len(observed),
                "n_uncovered": int((~group.network_covered.eq(True)).sum()),
                "median_N7": observed.age_7_N_venue_proxy_within_30min.median(),
                "median_N13": observed.age_13_N_venue_proxy_within_30min.median(),
                "median_delta_N": observed.delta_N.median(),
                "median_delta_t": observed.delta_t.dropna().median(),
            }
            for category in ("both", "only_7", "only_13", "neither"):
                row[f"{category}_pct"] = (observed.category == category).mean() * 100 if len(observed) else None
            rows.append(row)
        frame = pd.DataFrame(rows)
        frames.append(frame)
        layers.append(blocks[["blocksnet_block_id", "geometry"]].merge(frame, on="blocksnet_block_id", how="inner"))
        qa.append({"study_area_id": case["study_area_id"], "study_area_name": case["study_area_name"],
                   "n_result_rows": len(x), "n_network_covered": int(x.network_covered.eq(True).sum()),
                   "n_network_uncovered": int((~x.network_covered.eq(True)).sum()),
                   "n_valid_for_age_comparison": int(valid.sum()),
                   "n_valid_unassigned_to_block": int((valid & x.blocksnet_block_id.isna()).sum())})
    result = pd.concat(frames, ignore_index=True)
    result.to_csv(out / "age_profiles_by_block.csv", index=False, encoding="utf-8-sig")
    gpd.GeoDataFrame(pd.concat(layers, ignore_index=True), crs=32636).to_crs(4326).to_file(
        out / "age_profiles_blocks.gpkg", layer="profiles", driver="GPKG"
    )
    manifest = {"scenario": "B3", "unit": "ready-made BlocksNet block", "directions": len(cases),
                "routing_repeated": False, "b3_source": str(source), "block_source": str(BLOCKS),
                "source_block_records": source_block_records, "blocks_after_exact_geometry_deduplication": len(blocks),
                "spatial_join": {"n_origins_input": len(origins),
                                 "n_origins_assigned_to_block": int(joined.blocksnet_block_id.notna().sum()),
                                 "n_origins_unassigned_to_block": int(joined.blocksnet_block_id.isna().sum()),
                                 "join_predicate": "within", "by_direction": qa}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    args = parse_args()
    main(args.input, args.out)
