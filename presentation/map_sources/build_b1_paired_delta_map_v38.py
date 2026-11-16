#!/usr/bin/env python3
"""Build a paired B1 delta map for programming and visual arts from source data.

Uses the existing BlocksNet geometry and the two published block CSVs.
No routing, centroids, new grid or spatial aggregation is performed.
"""
from __future__ import annotations

import base64
import gzip
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.collections import PatchCollection
from matplotlib.patches import Patch

from make_research_maps import polygon_path

HERE = Path(__file__).resolve().parent
PRESENTATION = HERE.parent
OUT = PRESENTATION / "assets_v38"
GEOMETRY = HERE / "blocks_v22.json.gz.b64"
SOURCES = {
    "programming": ("Программирование", HERE / "b1_81.csv"),
    "art": ("Изобразительное искусство", HERE / "b1_38.csv"),
}
EXPECTED_BLOCKS = 3330
EXPECTED_ORIGINS = (30609, 30222, 387)
EXPECTED_CLASSES = {
    "programming": {
        "lt_minus2": 6, "minus2_to_zero": 207, "zero": 971,
        "zero_to_2": 709, "gt2": 353, "low": 1020, "nocover": 64,
    },
    "art": {
        "lt_minus2": 864, "minus2_to_zero": 549, "zero": 597,
        "zero_to_2": 229, "gt2": 7, "low": 1020, "nocover": 64,
    },
}
COLORS = {
    "lt_minus2": "#A94F3E",
    "minus2_to_zero": "#D18C7D",
    "zero": "#D8DEDD",
    "zero_to_2": "#8FB4C2",
    "gt2": "#315B78",
    "low": "#AAB6BB",
    "nocover": "#5D686E",
    "noresult": "#29343A",
}
LABELS = {
    "lt_minus2": "Меньше −2",
    "minus2_to_zero": "От −2 до <0",
    "zero": "0",
    "zero_to_2": "Больше 0 до 2",
    "gt2": "Больше 2",
    "low": "1–2 валидные точки",
    "nocover": "Нет сетевого покрытия",
    "noresult": "Нет результата",
}
ORDER = ("lt_minus2", "minus2_to_zero", "zero", "zero_to_2", "gt2", "low", "nocover", "noresult")


def load_geometry():
    if not GEOMETRY.is_file() or GEOMETRY.stat().st_size == 0:
        raise FileNotFoundError(GEOMETRY)
    packed = base64.b64decode(GEOMETRY.read_text(encoding="ascii").strip(), validate=True)
    geo = json.loads(gzip.decompress(packed).decode("utf-8"))
    crs = geo.get("crs", {}).get("properties", {}).get("name")
    if crs != "urn:ogc:def:crs:EPSG::32636":
        raise ValueError(f"Expected EPSG:32636, got {crs}")
    features = geo.get("features", [])
    ids = [str(f["properties"]["blocksnet_block_id"]) for f in features]
    if len(features) != EXPECTED_BLOCKS or len(set(ids)) != EXPECTED_BLOCKS:
        raise ValueError("Expected 3,330 unique BlocksNet polygons")
    return features


def load_tables(features):
    geometry_ids = {str(f["properties"]["blocksnet_block_id"]) for f in features}
    frames = {}
    summaries = {}
    for key, (_, path) in SOURCES.items():
        df = pd.read_csv(path, dtype={"blocksnet_block_id": str})
        if len(df) != EXPECTED_BLOCKS or df.blocksnet_block_id.duplicated().any():
            raise ValueError(f"{key}: expected 3,330 unique block rows")
        if set(df.blocksnet_block_id) != geometry_ids:
            raise ValueError(f"{key}: block IDs differ from geometry")
        if not (df.n_origins == df.n_valid + df.n_uncovered).all():
            raise ValueError(f"{key}: origin accounting mismatch")
        totals = tuple(int(df[col].sum()) for col in ("n_origins", "n_valid", "n_uncovered"))
        if totals != EXPECTED_ORIGINS:
            raise ValueError(f"{key}: unexpected origin totals {totals}")
        classes = Counter()
        for row in df.to_dict("records"):
            n = int(row["n_valid"])
            value = row["median_delta_N"]
            if n == 0:
                label = "nocover"
            elif n < 3:
                label = "low"
            elif pd.isna(value):
                label = "noresult"
            elif value < -2:
                label = "lt_minus2"
            elif value < 0:
                label = "minus2_to_zero"
            elif value == 0:
                label = "zero"
            elif value <= 2:
                label = "zero_to_2"
            else:
                label = "gt2"
            classes[label] += 1
        if dict(classes) != EXPECTED_CLASSES[key]:
            raise ValueError(f"{key}: unexpected delta classes {dict(classes)}")
        if sum(classes.values()) != EXPECTED_BLOCKS:
            raise ValueError(f"{key}: classes do not sum to 3,330")
        frames[key] = df.set_index("blocksnet_block_id", verify_integrity=True)
        negative = classes["lt_minus2"] + classes["minus2_to_zero"]
        positive = classes["zero_to_2"] + classes["gt2"]
        summaries[key] = {
            "rows": len(df), "origin_totals": dict(zip(("n_origins", "n_valid", "n_uncovered"), totals)),
            "class_counts": dict(classes),
            "delta_sign": {"negative": negative, "zero": classes["zero"], "positive": positive},
            "eligible_blocks": negative + classes["zero"] + positive,
        }
    return frames, summaries


def geometry_polygons(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    raise ValueError(f"Unsupported geometry type: {geometry['type']}")


def render(features, frames, summaries):
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["svg.fonttype"] = "none"
    fig = plt.figure(figsize=(16, 9), facecolor="white")
    fig.text(.04, .955, "Возрастная разница зависит от направления занятий",
             fontsize=20, weight="bold", color="#263E48")
    fig.text(.04, .925, "Медиана парной разницы N13 − N7 по кварталам BlocksNet · B1, пешком, 30 минут",
             fontsize=11, color="#60727B")
    bounds = []
    xs, ys = [], []
    for feature in features:
        for polygon in geometry_polygons(feature["geometry"]):
            for ring in polygon:
                for x, y in ring:
                    xs.append(x); ys.append(y)
    bounds = (min(xs), max(xs), min(ys), max(ys))
    x0, x1, y0, y1 = bounds

    panels = [
        ("programming", "Программирование", [.035, .205, .445, .665]),
        ("art", "Изобразительное искусство", [.52, .205, .445, .665]),
    ]
    for key, title, rect in panels:
        ax = fig.add_axes(rect)
        by_id = frames[key]
        buckets = {label: [] for label in ORDER}
        for feature in features:
            block_id = str(feature["properties"]["blocksnet_block_id"])
            row = by_id.loc[block_id]
            n, value = int(row.n_valid), row.median_delta_N
            if n == 0:
                label = "nocover"
            elif n < 3:
                label = "low"
            elif pd.isna(value):
                label = "noresult"
            elif value < -2:
                label = "lt_minus2"
            elif value < 0:
                label = "minus2_to_zero"
            elif value == 0:
                label = "zero"
            elif value <= 2:
                label = "zero_to_2"
            else:
                label = "gt2"
            for polygon in geometry_polygons(feature["geometry"]):
                buckets[label].append(polygon_path(polygon))
        for label in ORDER:
            if buckets[label]:
                ax.add_collection(PatchCollection(
                    buckets[label], facecolor=COLORS[label], edgecolor="white", linewidth=.13
                ))
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color="#263E48", pad=9)
        scale_x = x0 + (x1 - x0) * .06
        scale_y = y0 + (y1 - y0) * .045
        ax.plot([scale_x, scale_x + 10000], [scale_y, scale_y], color="#33454F", lw=2)
        ax.text(scale_x + 5000, scale_y + (y1-y0)*.012, "10 км",
                ha="center", fontsize=8, color="#33454F")
        summary = summaries[key]["delta_sign"]
        caption = (f"n ≥ 3: {summaries[key]['eligible_blocks']:,} кварталов · "
                   f"− {summary['negative']:,} · 0 {summary['zero']:,} · "
                   f"+ {summary['positive']:,}").replace(",", " ")
        fig.text(rect[0], .175, caption, fontsize=9, color="#52636B")

    present = {k for summary in summaries.values() for k, count in summary["class_counts"].items() if count}\n    handles = [Patch(facecolor=COLORS[k], edgecolor="none", label=LABELS[k]) for k in ORDER if k in present]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .105),
               ncol=4, frameon=False, fontsize=9, columnspacing=1.6, handlelength=1.2)
    fig.text(.04, .045,
             "Отрицательная Δ: меньше координат для 13 лет; положительная: больше. "
             "Медиана сначала рассчитывается по-точечно, затем по кварталу.",
             fontsize=9, color="#52636B")
    fig.text(.04, .023,
             "Серые классы: 1–2 валидные точки или отсутствие сетевого покрытия. "
             "Квартальный цвет не описывает каждый адрес; N — опубликованные координаты Navigator.",
             fontsize=8, color="#748187")
    fig.savefig(OUT / "paired_delta_programming_art_b1.svg", format="svg", facecolor="white")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    features = load_geometry()
    frames, summaries = load_tables(features)
    render(features, frames, summaries)
    audit = {
        "version": "v38",
        "source_geometry": "blocks_v22.json.gz.b64",
        "source_tables": {"programming": "b1_81.csv", "art": "b1_38.csv"},
        "crs": "EPSG:32636",
        "feature_count": len(features),
        "scenario": {"name": "B1", "mode": "walking", "threshold_minutes": 30, "ages": [7, 13]},
        "method": "median of point-level paired differences N13-N7 within each BlocksNet block",
        "directions": summaries,
        "limitations": [
            "Block medians summarize residential origins and do not imply within-block homogeneity.",
            "N counts unique published Navigator coordinates, not groups, vacancies or participants.",
            "A zero difference can occur when both ages have zero reachable coordinates or equal positive counts.",
            "Blocks with 1-2 valid origins and blocks with no network-covered origins are separate classes.",
        ],
    }
    (HERE / "paired_delta_map_audit_v38.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
