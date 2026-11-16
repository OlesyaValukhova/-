#!/usr/bin/env python3
"""Build two B1 direction-level charts from the published 43-direction CSV.

Run from any directory:
    python presentation/map_sources/build_direction_charts_v38.py

Only the standard library is required. No routing or spatial reconstruction is done.
"""
from __future__ import annotations
import csv
import json
import math
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRESENTATION = HERE.parent
SOURCE = HERE / "b1-direction-summary.csv"
OUT = PRESENTATION / "assets_v38"
AUDIT = HERE / "direction_distribution_audit_v38.json"
EXPECTED_DIRECTIONS = 43
EXPECTED_ORIGINS = 30224
THRESHOLDS = ("15", "20", "30")
COLORS = {"age7": "#b86c5d", "age13": "#315b78"}


def read_source():
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != EXPECTED_DIRECTIONS:
        raise ValueError(f"Expected {EXPECTED_DIRECTIONS} directions, got {len(rows)}")
    ids = [row["study_area_id"] for row in rows]
    if len(set(ids)) != EXPECTED_DIRECTIONS:
        raise ValueError("Duplicate study_area_id values")
    denominators = {int(row["origins_network_covered"]) for row in rows}
    if denominators != {EXPECTED_ORIGINS}:
        raise ValueError(f"Unexpected direction denominators: {denominators}")
    for row in rows:
        for age in ("age7", "age13"):
            for threshold in THRESHOLDS:
                value = 100 - float(row[f"{age}_zero_pct_{threshold}min"])
                if not math.isfinite(value) or not 0 <= value <= 100:
                    raise ValueError(f"Invalid accessibility value in {row['study_area_id']}")
    return rows


def quantile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    fraction = position - lower
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def fmt(value, digits=1):
    return f"{value:.{digits}f}".replace(".", ",")


def build_direction_chart(rows):
    data = [{
        "id": row["study_area_id"],
        "name": row["study_area_name"],
        "age7": 100 - float(row["age7_zero_pct_30min"]),
        "age13": 100 - float(row["age13_zero_pct_30min"]),
    } for row in rows]
    data.sort(key=lambda item: item["age13"] - item["age7"], reverse=True)
    deltas = [item["age13"] - item["age7"] for item in data]
    positive = sum(value > 0 for value in deltas)
    negative = sum(value < 0 for value in deltas)
    zero = sum(value == 0 for value in deltas)
    if (positive, negative, zero) != (24, 19, 0):
        raise ValueError(f"Unexpected direction signs: {(positive, negative, zero)}")

    width, height = 1800, 1012
    left, right, top, bottom = 485, 1440, 220, 930
    row_height = (bottom - top) / len(data)
    x = lambda value: left + value / 100 * (right - left)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Доля жилых точек с хотя бы одной опубликованной координатой по 43 направлениям, отдельно для 7 и 13 лет</title>',
        '<desc id="desc">Парная диаграмма: терракотовая точка — 7 лет, синяя — 13 лет, соединяющая линия — разница между возрастами. Направления отсортированы по разнице от преимущества 13 лет к преимуществу 7 лет. В 24 направлениях доля выше для 13 лет, в 19 — для 7 лет.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="36" y="58" font-family="Arial,sans-serif" font-size="38" font-weight="650" fill="#263e48">Возрастное преимущество зависит от направления</text>',
        '<text x="36" y="92" font-family="Arial,sans-serif" font-size="20" fill="#5e6d73">24 из 43 направлений: выше доля для 13 лет · 19: выше для 7 лет · B1, 30 минут пешком</text>',
        '<circle cx="40" cy="145" r="7" fill="#b86c5d"/><text x="58" y="151" font-family="Arial,sans-serif" font-size="17" fill="#344e57">7 лет</text>',
        '<circle cx="160" cy="145" r="7" fill="#315b78"/><text x="178" y="151" font-family="Arial,sans-serif" font-size="17" fill="#344e57">13 лет</text>',
        '<text x="36" y="190" font-family="Arial,sans-serif" font-size="14" font-weight="700" fill="#60727b">НАПРАВЛЕНИЕ</text>',
        f'<text x="{left}" y="190" font-family="Arial,sans-serif" font-size="14" font-weight="700" fill="#60727b">ДОЛЯ ЖИЛЫХ ТОЧЕК С ≥1 КООРДИНАТОЙ</text>',
        '<text x="1540" y="190" font-family="Arial,sans-serif" font-size="14" font-weight="700" fill="#60727b">Δ, п.п.</text>',
    ]
    for tick in (0, 25, 50, 75, 100):
        px = x(tick)
        stroke = "#9aa8ac" if tick == 0 else "#e8edee"
        parts.append(f'<line x1="{px}" y1="{top-12}" x2="{px}" y2="{bottom+4}" stroke="{stroke}" stroke-width="1"/>')
        parts.append(f'<text x="{px}" y="211" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" fill="#69777c">{tick}%</text>')
    for index, item in enumerate(data):
        y = top + (index + .5) * row_height
        x7, x13 = x(item["age7"]), x(item["age13"])
        delta = item["age13"] - item["age7"]
        if index == positive:
            parts.append(f'<line x1="28" y1="{top + index*row_height}" x2="1690" y2="{top + index*row_height}" stroke="#8d9da2" stroke-width="1.5" stroke-dasharray="5 4"/>')
        parts.append(f'<line x1="28" y1="{top + (index+1)*row_height}" x2="1690" y2="{top + (index+1)*row_height}" stroke="#f0f2f2" stroke-width=".8"/>')
        parts.append(f'<text x="36" y="{y+4.2}" font-family="Arial,sans-serif" font-size="13.2" fill="#33474f">{escape(item["name"])}</text>')
        parts.append(f'<line x1="{min(x7,x13)}" y1="{y}" x2="{max(x7,x13)}" y2="{y}" stroke="#aebbc0" stroke-width="2.2" stroke-linecap="round"/>')
        parts.append(f'<circle cx="{x7}" cy="{y}" r="4.4" fill="{COLORS["age7"]}" stroke="#ffffff" stroke-width="1"/>')
        parts.append(f'<circle cx="{x13}" cy="{y}" r="4.4" fill="{COLORS["age13"]}" stroke="#ffffff" stroke-width="1"/>')
        sign = "+" if delta > 0 else ""
        text_color = COLORS["age13"] if delta > 0 else "#a65d4f"
        parts.append(f'<text x="1550" y="{y+4.2}" font-family="Arial,sans-serif" font-size="13" font-weight="600" fill="{text_color}">{sign}{fmt(delta)}</text>')
    parts.extend([
        '<text x="36" y="976" font-family="Arial,sans-serif" font-size="14" fill="#607078">Знаменатель каждого направления: 30 224 сетево-покрытые жилые точки. Δ = доступность для 13 лет − доступность для 7 лет.</text>',
        '<text x="36" y="997" font-family="Arial,sans-serif" font-size="12" fill="#7b878b">Координата — прокси предложения, не число групп или мест.</text>',
        '</svg>',
    ])
    return "\n".join(parts), data, deltas


def build_threshold_chart(rows):
    stats = {}
    for age in ("age7", "age13"):
        stats[age] = {}
        for threshold in THRESHOLDS:
            values = [100 - float(row[f"{age}_zero_pct_{threshold}min"]) for row in rows]
            stats[age][threshold] = {
                "min": min(values), "q1": quantile(values, .25),
                "median": quantile(values, .5), "q3": quantile(values, .75),
                "max": max(values),
            }

    width, height = 1600, 900
    x0, x1 = 340, 1350
    x = lambda value: x0 + value / 100 * (x1 - x0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Распределение доли жилых точек с хотя бы одной координатой по 43 направлениям и трём временным порогам</title>',
        '<desc id="desc">Шесть горизонтальных boxplot. Коробки показывают межквартильный размах по 43 направлениям, вертикальная линия — медиану, усики — минимум и максимум. Для обоих возрастов медиана повышается при увеличении времени пешком.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="38" y="58" font-family="Arial,sans-serif" font-size="38" font-weight="650" fill="#263e48">Распределение по направлениям, а не одна городская доля</text>',
        '<text x="38" y="92" font-family="Arial,sans-serif" font-size="19" fill="#5e6d73">Доля жилых точек с ≥1 опубликованной координатой · 43 направления · B1</text>',
        '<rect x="40" y="128" width="18" height="18" rx="2" fill="#b86c5d"/><text x="68" y="143" font-family="Arial,sans-serif" font-size="16" fill="#344e57">7 лет</text>',
        '<rect x="145" y="128" width="18" height="18" rx="2" fill="#315b78"/><text x="173" y="143" font-family="Arial,sans-serif" font-size="16" fill="#344e57">13 лет</text>',
        '<line x1="320" y1="137" x2="370" y2="137" stroke="#607078" stroke-width="2"/><rect x="336" y="129" width="18" height="16" fill="#dce4e5" stroke="#607078"/><line x1="345" y1="128" x2="345" y2="146" stroke="#263e48" stroke-width="2"/>',
        '<text x="382" y="143" font-family="Arial,sans-serif" font-size="15" fill="#52636b">усики: min–max · коробка: Q1–Q3 · линия: медиана</text>',
    ]
    for tick in (0, 25, 50, 75, 100):
        px = x(tick)
        parts.append(f'<line x1="{px}" y1="210" x2="{px}" y2="790" stroke="#e7ecec" stroke-width="1"/>')
        parts.append(f'<text x="{px}" y="817" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" fill="#69777c">{tick}%</text>')
    layout = {
        "age7": ("7 лет", COLORS["age7"], (270, 345, 420), 198),
        "age13": ("13 лет", COLORS["age13"], (590, 665, 740), 518),
    }
    for age, (label, color, y_values, group_y) in layout.items():
        parts.append(f'<text x="40" y="{group_y}" font-family="Arial,sans-serif" font-size="25" font-weight="700" fill="{color}">{label}</text>')
        for threshold, y in zip(THRESHOLDS, y_values):
            item = stats[age][threshold]
            parts.append(f'<text x="40" y="{y+6}" font-family="Arial,sans-serif" font-size="18" fill="#344e57">{threshold} минут</text>')
            parts.append(f'<line x1="{x(item["min"])}" y1="{y}" x2="{x(item["max"])}" y2="{y}" stroke="{color}" stroke-width="2.2"/>')
            parts.append(f'<line x1="{x(item["min"])}" y1="{y-9}" x2="{x(item["min"])}" y2="{y+9}" stroke="{color}" stroke-width="2"/>')
            parts.append(f'<line x1="{x(item["max"])}" y1="{y-9}" x2="{x(item["max"])}" y2="{y+9}" stroke="{color}" stroke-width="2"/>')
            box_x = x(item["q1"])
            box_width = max(2, x(item["q3"]) - box_x)
            parts.append(f'<rect x="{box_x}" y="{y-13}" width="{box_width}" height="26" rx="2" fill="{color}" fill-opacity=".22" stroke="{color}" stroke-width="2"/>')
            parts.append(f'<line x1="{x(item["median"])}" y1="{y-15}" x2="{x(item["median"])}" y2="{y+15}" stroke="#263e48" stroke-width="3"/>')
            parts.append(f'<text x="1390" y="{y+6}" font-family="Arial,sans-serif" font-size="17" font-weight="700" fill="{color}">Me {fmt(item["median"])}%</text>')
    parts.extend([
        '<text x="38" y="866" font-family="Arial,sans-serif" font-size="14" fill="#607078">n=43 на каждом пороге. Для каждого направления знаменатель — 30 224 сетево-покрытые жилые точки.</text>',
        '<text x="38" y="887" font-family="Arial,sans-serif" font-size="12" fill="#7b878b">Квартильный размах рассчитан линейной интерполяцией; медиана — по направлениям, не по всем точкам города.</text>',
        '</svg>',
    ])
    return "\n".join(parts), stats


def main():
    rows = read_source()
    OUT.mkdir(parents=True, exist_ok=True)
    direction_svg, ordered, deltas = build_direction_chart(rows)
    threshold_svg, stats = build_threshold_chart(rows)
    (OUT / "directions_dumbbell_b1.svg").write_text(direction_svg, encoding="utf-8")
    (OUT / "threshold_distribution_b1.svg").write_text(threshold_svg, encoding="utf-8")
    audit = {
        "version": "v38",
        "source": "presentation/map_sources/b1-direction-summary.csv",
        "source_date": "2026-11-09",
        "scenario": {"name": "B1", "mode": "walking", "ages": [7, 13], "threshold_minutes": 30, "directions": 43, "network_covered_origins_per_direction": EXPECTED_ORIGINS},
        "direction_comparison": {
            "metric": "100 - age*_zero_pct_30min",
            "delta": "age13_accessibility_pct - age7_accessibility_pct",
            "positive_age13": sum(v > 0 for v in deltas),
            "negative_age7": sum(v < 0 for v in deltas),
            "zero": sum(v == 0 for v in deltas),
            "min_delta_pp": round(min(deltas), 2),
            "max_delta_pp": round(max(deltas), 2),
            "sort": "descending delta; positive values first",
            "rows": [{"study_area_id": d["id"], "name": d["name"], "age7_access_pct": round(d["age7"], 2), "age13_access_pct": round(d["age13"], 2), "delta_pp": round(d["age13"] - d["age7"], 2)} for d in ordered],
        },
        "threshold_distributions": stats,
        "quantile_method": "Linear interpolation at h=(n-1)*p for p=0.25, 0.50 and 0.75; min and max are observed extrema.",
        "interpretation_limits": [
            "The 43 study areas are directions in the B1 summary, not a population-weighted sample of all possible activities.",
            "Each direction uses 30,224 network-covered residential origins; block assignment is not required.",
            "A reachable published coordinate is a proxy for observed offer, not a confirmed group, vacancy, enrolment or trip.",
            "Medians and quartiles describe variation across directions, not pooled citywide shares.",
        ],
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"directions": len(rows), "positive_age13": audit["direction_comparison"]["positive_age13"], "negative_age7": audit["direction_comparison"]["negative_age7"], "delta_range_pp": [audit["direction_comparison"]["min_delta_pp"], audit["direction_comparison"]["max_delta_pp"]], "threshold_distributions": stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
