#!/usr/bin/env python3
"""Rebuild vector B1 maps from existing BlocksNet geometry and block CSVs.

No routing is performed. Run from any working directory:
    python presentation/map_sources/maps_b1_v24.py
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
ASSET_DIR = PRESENTATION / "assets_v40"
GEOMETRY_B64 = HERE / "blocks_v22.json.gz.b64"
PROGRAMMING_CSV = HERE / "b1_81.csv"
ART_CSV = HERE / "b1_38.csv"

EXPECTED_BLOCKS = 3330
EXPECTED_ORIGINS_ASSIGNED = 30609
EXPECTED_COVERED = 30224
EXPECTED_UNCOVERED = 387
EXPECTED_COVERED_ASSIGNED = 30222
EXPECTED_UNASSIGNED = 2

STATE_COLORS = {
    "both": "#315B78", "only7": "#C08A4B", "only13": "#6F8F82",
    "neither": "#D7E0E2", "tie": "#8A776B", "low": "#AAB6BB",
    "nocover": "#5D686E", "noresult": "#29343A",
}
STATE_LABELS = {
    "both": "Есть ≥1 координата для каждого возраста",
    "only7": "Только для 7 лет", "only13": "Только для 13 лет",
    "neither": "Не найдено ни для одного",
    "tie": "Равные максимальные доли",
    "low": "1–2 валидные точки",
    "nocover": "Нет точек с сетевым покрытием",
    "noresult": "Нет результата",
}
DELTA_COLORS = ["#A94F3E", "#D18C7D", "#D8DEDD", "#8FB4C2", "#315B78"]
DELTA_LABELS = ["Меньше −2", "От −2 до меньше 0", "0", "Больше 0 до 2", "Больше 2"]
COVERAGE_COLORS = {"full": "#DCE7E4", "partial": "#C08A4B", "none": "#5D686E", "noresult": "#29343A"}

def load_geometry():
    if not GEOMETRY_B64.exists() or GEOMETRY_B64.stat().st_size == 0:
        raise FileNotFoundError(f"Missing BlocksNet geometry: {GEOMETRY_B64}")
    raw = base64.b64decode(GEOMETRY_B64.read_text(encoding="ascii").strip(), validate=True)
    geo = json.loads(gzip.decompress(raw).decode("utf-8"))
    crs = geo.get("crs", {}).get("properties", {}).get("name")
    if crs != "urn:ogc:def:crs:EPSG::32636":
        raise ValueError(f"Expected EPSG:32636, got {crs}")
    features = geo.get("features", [])
    ids = [str(f["properties"]["blocksnet_block_id"]) for f in features]
    if len(features) != EXPECTED_BLOCKS or len(set(ids)) != EXPECTED_BLOCKS:
        raise ValueError("BlocksNet geometry must contain 3,330 unique IDs")
    return features

def load_and_validate(features):
    frames = {
        "programming": pd.read_csv(PROGRAMMING_CSV, dtype={"blocksnet_block_id": str}),
        "art": pd.read_csv(ART_CSV, dtype={"blocksnet_block_id": str}),
    }
    geom_ids = {str(f["properties"]["blocksnet_block_id"]) for f in features}
    summaries = {}
    coverage_signature = None
    coverage_by_block = None
    if EXPECTED_ORIGINS_ASSIGNED + EXPECTED_UNASSIGNED != 30611 or EXPECTED_COVERED_ASSIGNED + EXPECTED_UNASSIGNED != EXPECTED_COVERED:
        raise ValueError("Origin accounting constants are inconsistent")
    for name, df in frames.items():
        if len(df) != EXPECTED_BLOCKS or df["blocksnet_block_id"].duplicated().any():
            raise ValueError(f"{name}: expected 3,330 unique block rows")
        if set(df["blocksnet_block_id"]) != geom_ids:
            raise ValueError(f"{name}: CSV IDs do not match geometry")
        if (df[["n_origins", "n_valid", "n_uncovered"]] < 0).any().any():
            raise ValueError(f"{name}: negative origin count")
        if not (df["n_origins"] == df["n_valid"] + df["n_uncovered"]).all():
            raise ValueError(f"{name}: n_origins != n_valid + n_uncovered")
        totals = tuple(int(df[k].sum()) for k in ("n_origins", "n_valid", "n_uncovered"))
        if totals != (EXPECTED_ORIGINS_ASSIGNED, EXPECTED_COVERED_ASSIGNED, EXPECTED_UNCOVERED):
            raise ValueError(f"{name}: unexpected totals {totals}")
        coverage = {
            "no_uncovered_origins": int((df.n_uncovered == 0).sum()),
            "partial": int(((df.n_uncovered > 0) & (df.n_uncovered < df.n_origins)).sum()),
            "all_origins_uncovered": int((df.n_uncovered == df.n_origins).sum()),
        }
        if coverage != {"no_uncovered_origins": 3265, "partial": 1, "all_origins_uncovered": 64}:
            raise ValueError(f"{name}: unexpected coverage classes {coverage}")
        partial = df.loc[(df.n_uncovered > 0) & (df.n_uncovered < df.n_origins)]
        partial_rate = (partial.n_uncovered / partial.n_origins * 100).round(1).tolist()
        if partial_rate != [5.3]:
            raise ValueError(f"{name}: expected one 5.3% partial-coverage block, got {partial_rate}")
        coverage_rows = df.set_index("blocksnet_block_id")[["n_origins", "n_valid", "n_uncovered"]].sort_index()
        if coverage_by_block is None:
            coverage_by_block = coverage_rows
        elif not coverage_by_block.equals(coverage_rows):
            raise ValueError("Per-block network coverage differs between directions")
        state_counts = Counter()
        delta_bins = Counter()
        delta_sign = Counter()
        weighted7 = weighted13 = 0.0
        for row in df.to_dict("records"):
            n = int(row["n_valid"])
            vals = [row[k] for k in ("both_pct", "only_7_pct", "only_13_pct", "neither_pct")]
            if n > 0:
                if any(pd.isna(v) for v in vals):
                    raise ValueError(f"{name}: missing age-state shares for a covered block")
                weighted7 += (vals[0] + vals[1]) * n / 100
                weighted13 += (vals[0] + vals[2]) * n / 100
            if n == 0:
                state_counts["nocover"] += 1
            elif n < 3:
                state_counts["low"] += 1
            else:
                m = max(vals)
                winners = [i for i, v in enumerate(vals) if abs(v - m) < 1e-7]
                key = "tie" if len(winners) > 1 else ("both", "only7", "only13", "neither")[winners[0]]
                state_counts[key] += 1
                d = row["median_delta_N"]
                if pd.isna(d):
                    delta_sign["noresult"] += 1
                elif d < 0:
                    delta_sign["negative"] += 1
                    delta_bins["lt_minus2" if d < -2 else "minus2_to_zero"] += 1
                elif d == 0:
                    delta_sign["zero"] += 1
                    delta_bins["zero"] += 1
                else:
                    delta_sign["positive"] += 1
                    delta_bins["zero_to_2" if d <= 2 else "gt2"] += 1
        if sum(state_counts.values()) != EXPECTED_BLOCKS:
            raise ValueError(f"{name}: state classes do not sum to 3,330")
        expected_states = ({"both": 975, "only7": 55, "only13": 459, "neither": 749, "tie": 8, "low": 1020, "nocover": 64}
                           if name == "programming" else
                           {"both": 1818, "only7": 113, "only13": 26, "neither": 283, "tie": 6, "low": 1020, "nocover": 64})
        if dict(state_counts) != expected_states:
            raise ValueError(f"{name}: unexpected modal-state counts {dict(state_counts)}")
        if int((df.n_valid == 0).sum()) != 64 or int(((df.n_valid > 0) & (df.n_valid < 3)).sum()) != 1020:
            raise ValueError(f"{name}: unexpected low-sample classes")
        if sum(delta_sign.values()) != 2246 or delta_sign["noresult"]:
            raise ValueError(f"{name}: delta denominator is not 2,246")
        expected_delta = ({"lt_minus2": 6, "minus2_to_zero": 207, "zero": 971, "zero_to_2": 709, "gt2": 353}
                          if name == "programming" else
                          {"lt_minus2": 864, "minus2_to_zero": 549, "zero": 597, "zero_to_2": 229, "gt2": 7})
        if dict(delta_bins) != expected_delta:
            raise ValueError(f"{name}: unexpected paired-difference bins {dict(delta_bins)}")
        signature = (totals, coverage)
        if coverage_signature is None:
            coverage_signature = signature
        elif coverage_signature != signature:
            raise ValueError("Network coverage differs between directions")
        expected_access = (46.4132, 63.2486) if name == "programming" else (85.4047, 80.9841)
        actual_access = (weighted7 / EXPECTED_COVERED_ASSIGNED * 100, weighted13 / EXPECTED_COVERED_ASSIGNED * 100)
        if any(abs(a - e) > 0.01 for a, e in zip(actual_access, expected_access)):
            raise ValueError(f"{name}: weighted access shares do not match source control values {actual_access}")
        summaries[name] = {
            "n_origins": totals[0], "n_valid": totals[1], "n_uncovered": totals[2],
            "state_counts": dict(state_counts), "delta_bins": dict(delta_bins),
            "delta_sign": dict(delta_sign),
            "weighted_access_pct": {
                "age7": round(weighted7 / EXPECTED_COVERED_ASSIGNED * 100, 4),
                "age13": round(weighted13 / EXPECTED_COVERED_ASSIGNED * 100, 4),
            },
            "coverage_classes": coverage,
        }
    return frames, summaries

def geometry_bounds(features):
    xs, ys = [], []
    for f in features:
        g = f["geometry"]
        polygons = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polygons:
            for ring in poly:
                for x, y in ring:
                    xs.append(x); ys.append(y)
    return min(xs), max(xs), min(ys), max(ys)

def classify(row, kind):
    n = int(row["n_valid"])
    if kind == "coverage":
        origins, uncovered = int(row["n_origins"]), int(row["n_uncovered"])
        if origins == 0: return "noresult"
        if uncovered == 0: return "full"
        if uncovered == origins: return "none"
        return "partial"
    if n == 0: return "nocover"
    if n < 3: return "low"
    if kind == "state":
        vals = [row[k] for k in ("both_pct", "only_7_pct", "only_13_pct", "neither_pct")]
        if any(pd.isna(v) for v in vals): return "noresult"
        m = max(vals)
        winners = [i for i, v in enumerate(vals) if abs(v - m) < 1e-7]
        return "tie" if len(winners) > 1 else ("both", "only7", "only13", "neither")[winners[0]]
    d = row["median_delta_N"]
    if pd.isna(d): return "noresult"
    return "d0" if d < -2 else "d1" if d < 0 else "d2" if d == 0 else "d3" if d <= 2 else "d4"

def render_map(kind, direction, slug, df, features, bounds, summary):
    x0, x1, y0, y1 = bounds
    fig = plt.figure(figsize=(16, 9), facecolor="white")
    ax = fig.add_axes([0.02, 0.07, 0.63, 0.86])
    scale = min(1010 / (x1 - x0), 770 / (y1 - y0))
    left = x0 + ((1010 / scale) - (x1 - x0)) / 2
    bottom = y0 + ((770 / scale) - (y1 - y0)) / 2
    by_id = df.set_index("blocksnet_block_id", verify_integrity=True)
    keys = [classify(by_id.loc[str(f["properties"]["blocksnet_block_id"])], kind) for f in features]
    counts = Counter(keys)
    order = (["both", "only7", "only13", "neither", "tie", "low", "nocover", "noresult"] if kind == "state"
             else ["d0", "d1", "d2", "d3", "d4", "low", "nocover", "noresult"] if kind == "delta"
             else ["full", "partial", "none", "noresult"])
    buckets = {k: [] for k in order}
    for feature, key in zip(features, keys):
        geom = feature["geometry"]
        polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for polygon in polygons:
            buckets[key].append(polygon_path(polygon))
    def color_for(key):
        if kind == "coverage":
            return COVERAGE_COLORS[key]
        if kind == "state":
            return STATE_COLORS[key]
        return DELTA_COLORS[int(key[1])] if key.startswith("d") else STATE_COLORS[key]
    for key in order:
        if buckets[key]:
            ax.add_collection(PatchCollection(buckets[key], facecolor=color_for(key), edgecolor="white", linewidth=0.15))
    ax.set_xlim(left, left + 1010 / scale)
    ax.set_ylim(bottom, bottom + 770 / scale)
    ax.set_aspect("equal"); ax.axis("off")
    ax.plot([left + 2200, left + 12200], [bottom + 3000, bottom + 3000], color="#33454F", lw=2)
    ax.text(left + 7200, bottom + 5200, "10 км", ha="center", fontsize=9, color="#33454F")

    if kind == "state":
        title = "Возрастные состояния по кварталам"
        subtitle = f"{direction} · преобладающий класс среди жилых точек · B1"
        labels = STATE_LABELS
        note = "N — уникальные опубликованные координаты. «Оба возраста» не означает одну и ту же площадку."
        p7, p13 = summary["weighted_access_pct"]["age7"], summary["weighted_access_pct"]["age13"]
        n = EXPECTED_COVERED_ASSIGNED
        fig.text(0.68, 0.51, "ДОЛЯ ТОЧЕК С ≥1 КООРДИНАТОЙ", fontsize=11, color="#64737C")
        fig.text(0.68, 0.45, f"{p7:.1f}%", fontsize=27, weight="bold", color="#315B78")
        fig.text(0.81, 0.45, f"{p13:.1f}%", fontsize=27, weight="bold", color="#315B78")
        fig.text(0.68, 0.42, "7 лет", fontsize=11, color="#566771")
        fig.text(0.81, 0.42, "13 лет", fontsize=11, color="#566771")
        fig.text(0.68, 0.38, f"Взвешено по {n:,} валидным жилым точкам".replace(",", " "), fontsize=9, color="#64737C")
    elif kind == "delta":
        title = "Медиана парной разницы N13 − N7"
        subtitle = f"{direction} · B1, пешком, 30 минут"
        labels = {**STATE_LABELS, **{f"d{i}": DELTA_LABELS[i] for i in range(5)}}
        note = "0 означает равное число координат; в том числе возможно 0 для обоих возрастов."
        signs = summary["delta_sign"]; n = 2246
        neg, zero, pos = signs["negative"], signs["zero"], signs["positive"]
        fig.text(0.68, 0.51, "КВАРТАЛЫ С n_valid ≥ 3 · n=2 246", fontsize=11, color="#64737C")
        fig.text(0.68, 0.46, f"− {neg:,}".replace(",", " "), fontsize=13, color="#A94F3E")
        fig.text(0.82, 0.46, f"0 {zero:,}".replace(",", " "), fontsize=13, color="#566771")
        fig.text(0.68, 0.42, f"+ {pos:,}".replace(",", " "), fontsize=13, color="#315B78")
    else:
        title = "Сетевое покрытие жилых точек"
        subtitle = "Доля непокрытых точек по кварталам · порог привязки 250 м"
        labels = {"full": "0% без покрытия", "partial": "5,3% без покрытия",
                  "none": "100% без покрытия", "noresult": "Нет результата"}
        note = "387 точек без сетевого покрытия исключены; 2 покрытые точки не попали в кварталы."
        fig.text(0.68, 0.62, "ИСХОДНЫЙ НАБОР", fontsize=10, color="#64737C")
        fig.text(0.68, 0.57, "30 611", fontsize=25, weight="bold", color="#315B78")
        fig.text(0.68, 0.54, "жилых точек", fontsize=10, color="#566771")
        fig.text(0.68, 0.49, "СЕТЕВОЕ ПОКРЫТИЕ", fontsize=10, color="#64737C")
        fig.text(0.68, 0.44, "30 224", fontsize=25, weight="bold", color="#315B78")
        fig.text(0.81, 0.44, "с покрытием", fontsize=10, color="#566771")
        fig.text(0.68, 0.41, "387 без покрытия · 1,26% всех", fontsize=10, color="#566771")
        fig.text(0.68, 0.36, "ПРИСОЕДИНЕНИЕ К BLOCKSNET", fontsize=10, color="#64737C")
        fig.text(0.68, 0.31, "30 609", fontsize=25, weight="bold", color="#315B78")
        fig.text(0.81, 0.31, "внутри кварталов", fontsize=10, color="#566771")
        fig.text(0.68, 0.28, "2 не присоединены · 0,0065% всех", fontsize=10, color="#566771")
        fig.text(0.68, 0.23, "ПЕРЕСЕЧЕНИЕ ДВУХ УСЛОВИЙ", fontsize=10, color="#64737C")
        fig.text(0.68, 0.18, "30 222", fontsize=25, weight="bold", color="#315B78")
        fig.text(0.68, 0.15, "покрыты сетью и присоединены к кварталу", fontsize=9, color="#566771")
        fig.text(0.68, 0.12, "Знаменатель квартальных показателей B1", fontsize=9, color="#64737C")

    fig.text(0.68, 0.91, title, fontsize=17, weight="bold", color="#25313A")
    fig.text(0.68, 0.88, subtitle, fontsize=10, color="#64737C")
    handles = [Patch(facecolor=color_for(k), label=f"{labels[k]} · n={counts[k]:,}".replace(",", " "))
               for k in order if counts[k]]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.68, 0.84),
               frameon=False, fontsize=9, labelspacing=0.65, handlelength=1.3)
    fig.text(0.68, 0.055, note, fontsize=8.5, color="#64737C", wrap=True)
    fig.text(0.02, 0.02, "Санкт-Петербург · BlocksNet · EPSG:32636 · B1 · пешком, 30 минут · Navigator, 09.11.2026",
             fontsize=8, color="#7A858A")
    out = ASSET_DIR / (f"{slug}_states_b1.svg" if kind == "state" else f"{slug}_delta_b1.svg" if kind == "delta" else "network_coverage_b1.svg")
    fig.savefig(out, format="svg", facecolor="white")
    plt.close(fig)
    return out.name, dict(counts)

def main():
    features = load_geometry()
    frames, summaries = load_and_validate(features)
    bounds = geometry_bounds(features)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name, df in frames.items():
        direction = "Программирование" if name == "programming" else "Изобразительное искусство"
        for kind in ("state", "delta"):
            outputs.append(render_map(kind, direction, name, df, features, bounds, summaries[name]))
    outputs.append(render_map("coverage", "Покрытие", "network", frames["programming"], features, bounds, summaries["programming"]))
    audit = {
        "scenario": {"name": "B1", "mode": "walking", "threshold_minutes": 30, "ages": [7, 13],
                     "origin_snap_limit_m": 250, "crs": "EPSG:32636"},
        "source_date": "2026-11-09",
        "geometry": {"feature_count": len(features), "crs": "EPSG:32636"},
        "origin_accounting": {"input_origins": EXPECTED_ORIGINS, "network_covered": EXPECTED_COVERED,
                              "network_uncovered": EXPECTED_UNCOVERED, "assigned_to_blocks": EXPECTED_ORIGINS_ASSIGNED,
                              "unassigned_to_blocks": EXPECTED_ORIGINS - EXPECTED_ORIGINS_ASSIGNED,
                              "covered_and_assigned": EXPECTED_COVERED_ASSIGNED},
        "directions": summaries,
        "outputs": [x[0] for x in outputs],
        "map_class_counts": {x[0]: x[1] for x in outputs},
        "limitations": [
            "N is the number of unique published Navigator coordinates, not groups, available places or participants.",
            "The modal state is aggregated from residential origins in each block and requires at least three valid origins.",
            "The 'both ages' state does not require the same coordinate for both ages.",
            "A zero paired difference means equal N13 and N7; it can be zero for both ages or equal positive counts.",
            "The network map is a diagnostic of origin snapping within 250 m, not an accessibility result.",
            "Uncovered or unassigned origins are excluded from the relevant denominators, not coded as zero.",
        ],
    }
    (HERE / "coverage_audit_v40.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"outputs": audit["outputs"], "directions": summaries}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
