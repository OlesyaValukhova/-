"""Analyse paired 7-to-13 age differences from already-computed network results.

This does not rerun routing. It keeps the same residential origins, graph and
thresholds used by the existing Transport Frames outputs and makes the pairing
explicit: every delta is calculated before any summary or block aggregation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


AGES = (7, 13)
THRESHOLDS = (10, 15, 20, 30)


def read_activity(name: str, csv_path: Path, tolerance: float) -> pd.DataFrame:
    frame = pd.read_csv(csv_path, encoding="utf-8-sig")
    required = {"origin_id", *(f"age_{age}_nearest_minutes" for age in AGES)}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{csv_path} lacks columns: {sorted(missing)}")
    if frame.origin_id.duplicated().any():
        raise ValueError(f"{csv_path} has duplicate origin_id values")

    out = pd.DataFrame({"activity": name, "origin_id": frame.origin_id})
    out["t7_minutes"] = frame["age_7_nearest_minutes"]
    out["t13_minutes"] = frame["age_13_nearest_minutes"]
    out["both_reachable"] = np.isfinite(out.t7_minutes) & np.isfinite(out.t13_minutes)
    out["t13_minus_t7_minutes"] = np.where(
        out.both_reachable, out.t13_minutes - out.t7_minutes, np.nan
    )
    out["direction"] = np.select(
        [
            ~out.both_reachable,
            out.t13_minus_t7_minutes > tolerance,
            out.t13_minus_t7_minutes < -tolerance,
        ],
        ["not_reachable_both", "older_farther", "older_closer"],
        default="same_within_tolerance",
    )
    for threshold in THRESHOLDS:
        c7 = frame[f"age_7_locations_within_{threshold}min"]
        c13 = frame[f"age_13_locations_within_{threshold}min"]
        out[f"locations_{threshold}min_age7"] = c7
        out[f"locations_{threshold}min_age13"] = c13
        out[f"locations_{threshold}min_delta"] = c13 - c7
    return out


def summary_table(data: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    records = []
    structured = {}
    for activity, d in data.groupby("activity", sort=False):
        finite = d[d.both_reachable].copy()
        direction = d.direction.value_counts(dropna=False)
        record = {
            "activity": activity,
            "origins": int(len(d)),
            "both_reachable": int(len(finite)),
            "median_t7_minutes": float(finite.t7_minutes.median()),
            "median_t13_minutes": float(finite.t13_minutes.median()),
            "median_paired_delta_minutes": float(finite.t13_minus_t7_minutes.median()),
            "mean_paired_delta_minutes": float(finite.t13_minus_t7_minutes.mean()),
            "older_farther_origins": int(direction.get("older_farther", 0)),
            "same_within_tolerance_origins": int(direction.get("same_within_tolerance", 0)),
            "older_closer_origins": int(direction.get("older_closer", 0)),
            "not_reachable_both_origins": int(direction.get("not_reachable_both", 0)),
        }
        for label in ("older_farther", "same_within_tolerance", "older_closer"):
            record[f"share_{label}"] = float(direction.get(label, 0) / len(d))
        for threshold in THRESHOLDS:
            record[f"median_locations_{threshold}min_delta"] = float(
                finite[f"locations_{threshold}min_delta"].median()
            )
            record[f"share_fewer_locations_{threshold}min_at13"] = float(
                (finite[f"locations_{threshold}min_delta"] < 0).mean()
            )
            record[f"share_more_locations_{threshold}min_at13"] = float(
                (finite[f"locations_{threshold}min_delta"] > 0).mean()
            )
        records.append(record)
        structured[activity] = record
    return pd.DataFrame(records), structured


def aggregate_blocks(data: pd.DataFrame, origins_path: Path, blocks_path: Path) -> gpd.GeoDataFrame:
    origins = gpd.read_file(origins_path)[["source_row", "geometry"]].copy()
    origins["origin_id"] = "origin-source-" + origins.source_row.astype(str)
    blocks = gpd.read_file(blocks_path)[["fid", "geometry"]].copy()
    joined = gpd.sjoin(origins, blocks, how="inner", predicate="within").drop(columns="index_right")
    long = joined.merge(data, on="origin_id", how="inner", validate="one_to_many")
    rows = []
    for (activity, fid), d in long.groupby(["activity", "fid"], sort=False):
        rows.append({
            "activity": activity,
            "fid": int(fid),
            "origin_count": int(d.origin_id.nunique()),
            "median_paired_delta_minutes": float(d.t13_minus_t7_minutes.median()),
            "share_older_farther": float((d.direction == "older_farther").mean()),
            "median_15min_location_delta": float(d.locations_15min_delta.median()),
        })
    stats = pd.DataFrame(rows)
    return blocks.merge(stats, on="fid", how="inner")


def plot_pairs(data: pd.DataFrame, blocks: gpd.GeoDataFrame, output: Path) -> None:
    activities = list(data.activity.drop_duplicates())
    fig, axes = plt.subplots(2, len(activities), figsize=(7 * len(activities), 9), constrained_layout=True)
    if len(activities) == 1:
        axes = np.array([[axes[0]], [axes[1]]])
    for index, activity in enumerate(activities):
        d = data[data.activity == activity]
        b = blocks[blocks.activity == activity]
        ax = axes[0, index]
        ax.hist(d.t13_minus_t7_minutes, bins=26, color="#3B6EA5", edgecolor="white")
        ax.axvline(0, color="#E0684F", linewidth=2)
        ax.set_title(f"{activity}: парная разница t13 − t7")
        ax.set_xlabel("минуты до ближайшей опубликованной точки")
        ax.set_ylabel("жилых точек")
        ax = axes[1, index]
        b.plot(
            column="median_paired_delta_minutes", cmap="RdBu_r", legend=True,
            vmin=-30, vmax=30, linewidth=.25, edgecolor="white", ax=ax,
            legend_kwds={"label": "медиана t13 − t7, минут"},
        )
        ax.set_title(f"{activity}: квартальная агрегация\n(число исходов показано в таблице)")
        ax.set_axis_off()
    fig.suptitle(
        "Возрастные различия опубликованного предложения: парный пилот Васильевского острова",
        fontsize=15, fontweight="bold",
    )
    fig.savefig(output, dpi=220, bbox_inches="tight")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chess", type=Path, required=True)
    parser.add_argument("--robotics", type=Path, required=True)
    parser.add_argument("--origins", type=Path, required=True)
    parser.add_argument("--blocks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=0.001)
    args = parser.parse_args()
    chess = read_activity("Шахматы", args.chess, args.tolerance)
    robotics = read_activity("Робототехника", args.robotics, args.tolerance)
    if set(chess.origin_id) != set(robotics.origin_id):
        raise ValueError("Activities do not use the same origins; pairing is invalid")
    data = pd.concat([chess, robotics], ignore_index=True)
    summary, structured = summary_table(data)
    block_data = aggregate_blocks(data, args.origins, args.blocks)
    args.output.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.output / "paired-age-difference-by-origin.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(args.output / "paired-age-difference-summary.csv", index=False, encoding="utf-8-sig")
    block_data.to_file(args.output / "paired-age-difference-by-block.geojson", driver="GeoJSON")
    plot_pairs(data, block_data, args.output / "paired-age-difference.png")
    manifest = {
        "status": "computed",
        "purpose": "paired age difference using existing compatible Transport Frames results",
        "ages": list(AGES),
        "thresholds_minutes": list(THRESHOLDS),
        "comparison_tolerance_minutes": args.tolerance,
        "inputs": {
            "chess": str(args.chess), "robotics": str(args.robotics),
            "origins": str(args.origins), "blocks": str(args.blocks),
        },
        "same_origin_ids": True,
        "summary": structured,
        "limitations": [
            "Age is published programme eligibility, not observed child age, ability or permission.",
            "Destination coordinates are programme-card coordinates, not verified group venues or entrances.",
            "All results are for a compact pilot and published coordinates only.",
            "Block aggregation follows origin-level paired differences and is exploratory, not a city typology.",
        ],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
