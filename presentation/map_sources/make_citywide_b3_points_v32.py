#!/usr/bin/env python3
"""Build comparable point maps from the published B3 by-origin GeoJSON.

This is a point-level map: no grid or BlocksNet aggregation is performed.
Origins without network coverage remain a separate gray category.
"""
import argparse
import json
import math
import statistics
from html import escape
from pathlib import Path

N7 = "age_7_N_venue_proxy_within_30min"
N13 = "age_13_N_venue_proxy_within_30min"
SOURCE_COMMIT = "72bcbd10b88e1b417ef372f1a08fd649805e0d63"

PALETTE_N = {
    "0": "#edf2f0", "1–10": "#c9ddd6", "11–30": "#91b7ab",
    "31–60": "#5d9084", ">60": "#2f655d", "нет покрытия": "#c5ccce",
}
PALETTE_D = {
    "≤−20": "#355f72", "−19…−10": "#6f9ba4", "−9…−1": "#b6cdcc",
    "0": "#ecefed", ">0": "#c87868", "нет покрытия": "#c5ccce",
}
LEGEND_N = [("0", PALETTE_N["0"]), ("1–10", PALETTE_N["1–10"]),
            ("11–30", PALETTE_N["11–30"]), ("31–60", PALETTE_N["31–60"]),
            (">60", PALETTE_N[">60"]), ("без сети", PALETTE_N["нет покрытия"])]
LEGEND_D = [("≤−20", PALETTE_D["≤−20"]), ("−19…−10", PALETTE_D["−19…−10"]),
            ("−9…−1", PALETTE_D["−9…−1"]), ("0", PALETTE_D["0"]),
            (">0", PALETTE_D[">0"]), ("без сети", PALETTE_D["нет покрытия"])]


def project_utm36(lon, lat):
    """WGS84 lon/lat to UTM zone 36N (EPSG:32636)."""
    a, e2, k0 = 6378137.0, 0.00669437999014, 0.9996
    ep2, lon0 = e2 / (1.0 - e2), math.radians(33.0)
    p, l = math.radians(lat), math.radians(lon)
    s, c, t = math.sin(p), math.cos(p), math.tan(p)
    n, tt, cc = a / math.sqrt(1.0 - e2 * s * s), t * t, ep2 * c * c
    aa = c * (l - lon0)
    m = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * p
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * p)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * p)
        - (35 * e2**3 / 3072) * math.sin(6 * p)
    )
    x = 500000 + k0 * n * (
        aa + (1 - tt + cc) * aa**3 / 6
        + (5 - 18 * tt + tt**2 + 72 * cc - 58 * ep2) * aa**5 / 120
    )
    y = k0 * (
        m + n * t * (
            aa**2 / 2 + (5 - tt + 9 * cc + 4 * cc**2) * aa**4 / 24
            + (61 - 58 * tt + tt**2 + 600 * cc - 330 * ep2) * aa**6 / 720
        )
    )
    return x, y


def classify_count(value):
    if value == 0:
        return "0"
    if value <= 10:
        return "1–10"
    if value <= 30:
        return "11–30"
    if value <= 60:
        return "31–60"
    return ">60"


def classify_delta(value):
    if value <= -20:
        return "≤−20"
    if value <= -10:
        return "−19…−10"
    if value < 0:
        return "−9…−1"
    if value == 0:
        return "0"
    return ">0"


def classify_origin(covered, n7, n13):
    if not covered:
        return "нет покрытия", "нет покрытия", "нет покрытия", None
    for value in (n7, n13):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Covered origin has missing/non-numeric N7 or N13")
    delta = n13 - n7
    return classify_count(n7), classify_count(n13), classify_delta(delta), delta


def load_points(path):
    geo = json.loads(path.read_text(encoding="utf-8"))
    crs = geo.get("crs", {}).get("properties", {}).get("name", "")
    if "CRS84" not in crs and "4326" not in crs:
        raise ValueError("Expected CRS84/4326 GeoJSON input")
    ids, points = set(), []
    n7_values, n13_values, deltas = [], [], []
    counts7 = {k: 0 for k in ("0", "1–10", "11–30", "31–60", ">60", "нет покрытия")}
    counts13 = dict(counts7)
    counts_delta = {k: 0 for k in ("≤−20", "−19…−10", "−9…−1", "0", ">0", "нет покрытия")}
    covered = uncovered = 0

    for feature in geo["features"]:
        if feature.get("geometry", {}).get("type") != "Point":
            raise ValueError("Expected Point geometry for every origin")
        props = feature.get("properties") or {}
        origin_id = str(props.get("origin_id"))
        if origin_id in ids:
            raise ValueError("Duplicate origin_id: " + origin_id)
        ids.add(origin_id)
        lon, lat = feature["geometry"]["coordinates"]
        x, y = project_utm36(float(lon), float(lat))
        is_covered = props.get("network_covered") is True
        n7, n13 = props.get(N7), props.get(N13)
        c7, c13, cd, delta = classify_origin(is_covered, n7, n13)
        if is_covered:
            covered += 1
            n7_values.append(float(n7))
            n13_values.append(float(n13))
            deltas.append(float(delta))
        else:
            uncovered += 1
            n7 = n13 = None
        counts7[c7] += 1
        counts13[c13] += 1
        counts_delta[cd] += 1
        points.append({"x": x, "y": y, "c7": c7, "c13": c13, "cd": cd})

    if len(points) != 30611 or covered != 30224 or uncovered != 387:
        raise ValueError("Unexpected source coverage; expected 30611 / 30224 / 387")
    summary = {
        "source_commit": SOURCE_COMMIT,
        "origins": {"total": len(points), "network_covered": covered, "network_uncovered": uncovered},
        "point_summary": {
            "mean_N7": statistics.mean(n7_values),
            "mean_N13": statistics.mean(n13_values),
            "mean_delta_N13_minus_N7": statistics.mean(deltas),
            "median_N7": statistics.median(n7_values),
            "median_N13": statistics.median(n13_values),
            "median_delta_N13_minus_N7": statistics.median(deltas),
            "zero_access_share_pct": {
                "age7": counts7["0"] / covered * 100,
                "age13": counts13["0"] / covered * 100,
            },
        },
        "category_counts": {"age7": counts7, "age13": counts13, "delta": counts_delta},
    }
    return points, summary


def legend_svg(items, x, y):
    out = []
    for i, (label, color) in enumerate(items):
        out.append(
            f'<g transform="translate({x + i * 74},{y})">'
            f'<rect width="12" height="11" rx="2" fill="{color}"/>'
            f'<text x="17" y="10" font-size="11" fill="#4c6068">{escape(label)}</text></g>'
        )
    return "".join(out)


def render_svg(points, output):
    min_x = min(p["x"] for p in points) - 1200
    max_x = max(p["x"] for p in points) + 1200
    min_y = min(p["y"] for p in points) - 1200
    max_y = max(p["y"] for p in points) + 1200
    width, height, panel_width, gap = 1500, 670, 480, 20
    map_width, map_height, map_y = 440, 400, 92
    scale = min(map_width / (max_x - min_x), map_height / (max_y - min_y))

    def panel(index, title, subtitle, field, legend):
        px, mx = 10 + index * (panel_width + gap), 30 + index * 500
        groups = {}
        for point in points:
            groups.setdefault(point[field], []).append(
                "M{} {}h0".format(
                    round(mx + (point["x"] - min_x) * scale),
                    round(map_y + (max_y - point["y"]) * scale),
                )
            )
        palette = PALETTE_D if field == "cd" else PALETTE_N
        paths = []
        for label, _ in legend:
            category = "нет покрытия" if label == "без сети" else label
            commands = groups.get(category, [])
            if commands:
                paths.append(
                    '<path d="{}" fill="none" stroke="{}" stroke-width="1.45" '
                    'stroke-linecap="round" opacity="0.78"/>'.format(
                        "".join(commands), palette[category]
                    )
                )
        grid = []
        tick = math.ceil(min_x / 10000) * 10000
        while tick < max_x:
            sx = mx + (tick - min_x) * scale
            grid.append(
                f'<line x1="{sx:.1f}" y1="{map_y}" x2="{sx:.1f}" '
                f'y2="{map_y + map_height}" stroke="#e8edeb" stroke-width="0.7"/>'
            )
            tick += 10000
        tick = math.ceil(min_y / 10000) * 10000
        while tick < max_y:
            sy = map_y + (max_y - tick) * scale
            grid.append(
                f'<line x1="{mx}" y1="{sy:.1f}" x2="{mx + map_width}" '
                f'y2="{sy:.1f}" stroke="#e8edeb" stroke-width="0.7"/>'
            )
            tick += 10000
        bar = 10000 * scale
        return (
            f'<g><text x="{px + 16}" y="36" font-size="19" font-weight="700" fill="#263e48">{escape(title)}</text>'
            f'<text x="{px + 16}" y="58" font-size="12" fill="#62747a">{escape(subtitle)}</text>'
            f'<rect x="{mx}" y="{map_y}" width="{map_width}" height="{map_height}" fill="#fbfcfb" stroke="#dce4e1"/>'
            + "".join(grid) + "".join(paths)
            + f'<g transform="translate({px + 450},{map_y + 20})"><text x="0" y="0" text-anchor="middle" font-size="11" font-weight="700" fill="#52666d">N</text><path d="M0 7 L-5 22 L0 19 L5 22 Z" fill="#52666d"/></g>'
            + f'<g transform="translate({mx + 8},{map_y + map_height + 10})"><line x1="0" y1="0" x2="{bar:.1f}" y2="0" stroke="#435b63" stroke-width="2"/><line x1="0" y1="-4" x2="0" y2="4" stroke="#435b63"/><line x1="{bar:.1f}" y1="-4" x2="{bar:.1f}" y2="4" stroke="#435b63"/><text x="{bar + 8:.1f}" y="4" font-size="11" fill="#52666d">10 км</text></g>'
            + legend_svg(legend, px + 14, 540) + "</g>"
        )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="#fff"/>'
        '<text x="28" y="20" font-size="12" font-weight="600" fill="#6b7b80">САНКТ-ПЕТЕРБУРГ · ЖИЛЫЕ ТОЧКИ URBAN API · ОДИНАКОВЫЙ ЭКСТЕНТ И МАСШТАБ</text>'
        + panel(0, "7 лет · N7", "Достижимые уникальные координаты за 30 минут", "c7", LEGEND_N)
        + panel(1, "13 лет · N13", "Достижимые уникальные координаты за 30 минут", "c13", LEGEND_N)
        + panel(2, "Возрастная разница · N13 − N7", "Парная разница для каждой жилой точки", "cd", LEGEND_D)
        + '<line x1="28" y1="570" x2="1472" y2="570" stroke="#e0e6e3"/>'
        + '<text x="28" y="592" font-size="12" fill="#4f6269">N — число уникальных опубликованных координат программ, не число карточек или свободных мест. Серый — 387 точек без сетевого покрытия, не нулевой результат.</text>'
        + '<text x="28" y="613" font-size="12" fill="#4f6269">Точки могут перекрываться; карта показывает жилые начала маршрутов, не население и не кварталы BlocksNet. B3 — дополнительный модельный сценарий.</text>'
        + '<text x="28" y="644" font-size="11" fill="#78868a">B3 · пешком + общественный транспорт · 30 минут · ожидание 5 минут на каждую посадку · расчёт 11.11.2026</text></svg>'
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    return svg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-svg", type=Path, default=Path("citywide_b3_points_v32.svg"))
    parser.add_argument("--output-summary", type=Path, default=Path("citywide_b3_points_v32_summary.json"))
    args = parser.parse_args()
    points, summary = load_points(args.input)
    svg = render_svg(points, args.output_svg)
    summary["map"] = {
        "type": "point-level; no spatial aggregation",
        "crs": "EPSG:32636",
        "same_extent_and_scale": True,
        "panels": ["N7", "N13", "N13-N7"],
        "points_per_panel": len(points),
        "svg_bytes": len(svg.encode("utf-8")),
    }
    summary["limitations"] = [
        "N counts unique published coordinate proxies, not cards, seats or attendance.",
        "387 origins without network coverage are shown in gray and are not treated as zero.",
        "B3 is a modelled walk + public-transport scenario with a five-minute wait per boarding, not observed journeys.",
        "Origin points are not children or population counts; point overlap can hide observations.",
        "This is not a BlocksNet block choropleth and does not replace B1 block analysis or the uncompleted B2 barrier scenario.",
    ]
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
