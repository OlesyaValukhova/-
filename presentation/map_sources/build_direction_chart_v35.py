#!/usr/bin/env python3
"""Build the 43-direction B1 age-difference chart as standalone SVG."""
import csv
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRESENTATION = HERE.parent
SOURCE = HERE / "b1-direction-summary.csv"
OUTPUT = PRESENTATION / "assets_v35" / "directions_chart_b1.svg"

def main():
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 43 or len({r["study_area_id"] for r in rows}) != 43:
        raise ValueError("Expected 43 unique study areas")
    if {int(r["origins_network_covered"]) for r in rows} != {30224}:
        raise ValueError("Expected 30,224 network-covered origins per direction")
    for row in rows:
        row["diff"] = float(row["age7_zero_pct_30min"]) - float(row["age13_zero_pct_30min"])
    rows.sort(key=lambda r: r["diff"])
    negative = sum(r["diff"] < 0 for r in rows)
    positive = sum(r["diff"] > 0 for r in rows)
    zero = sum(r["diff"] == 0 for r in rows)
    if (negative, positive, zero) != (19, 24, 0):
        raise ValueError(f"Unexpected sign counts: {(negative, positive, zero)}")

    width, height = 1600, 900
    plot_x, plot_y, plot_w, plot_h = 160, 185, 1300, 565
    low, high = -20, 50
    def y(value):
        return plot_y + (high - value) / (high - low) * plot_h
    bar_w = 19
    gap = (plot_w - 43 * bar_w) / 42
    zero_y = y(0)
    bars = []
    for i, row in enumerate(rows):
        value = row["diff"]
        x = plot_x + i * (bar_w + gap)
        top = min(y(value), zero_y)
        bar_h = abs(zero_y - y(value))
        color = "#C08A4B" if value < 0 else "#315B78"
        tip = f'{row["study_area_name"]}: {value:+.1f} п.п.'
        bars.append(
            f'<rect x="{x:.2f}" y="{top:.2f}" width="{bar_w}" height="{bar_h:.2f}" '
            f'rx="2" fill="{color}"><title>{escape(tip)}</title></rect>'
        )
    grid = []
    for tick in range(-20, 51, 10):
        yy = y(tick)
        stroke = "#64737C" if tick == 0 else "#E6EBED"
        sw = 2 if tick == 0 else 1
        grid.append(
            f'<line x1="{plot_x}" y1="{yy:.2f}" x2="{plot_x+plot_w}" y2="{yy:.2f}" '
            f'stroke="{stroke}" stroke-width="{sw}"/>'
            f'<text x="{plot_x-20}" y="{yy+6:.2f}" text-anchor="end" font-size="16" fill="#64737C">{tick}</text>'
        )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">'
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#25313A}.title{font-size:30px;font-weight:700}'
        '.subtitle{font-size:17px;fill:#64737C}.top7{font-size:19px;font-weight:700;fill:#A66C34}'
        '.top13{font-size:19px;font-weight:700;fill:#315B78}.axis{font-size:16px;fill:#64737C}'
        '.foot{font-size:13px;fill:#7A858A}</style><rect width="1600" height="900" fill="#FFFFFF"/>'
        '<text x="160" y="65" class="title">Возрастное различие по 43 направлениям</text>'
        '<text x="160" y="98" class="subtitle">Δ доли жилых точек с ≥1 координатой: 13 лет − 7 лет · B1 · 30 минут пешком</text>'
        f'<text x="160" y="145" class="top7">{negative} направлений: выше для 7 лет</text>'
        f'<text x="1460" y="145" text-anchor="end" class="top13">{positive} направления: выше для 13 лет</text>'
        + "".join(grid) + "".join(bars)
        + '<text x="810" y="805" text-anchor="middle" class="axis">43 направления, отсортированы по разнице</text>'
        + '<text x="52" y="470" transform="rotate(-90 52 470)" text-anchor="middle" class="axis">Разница, процентные пункты</text>'
        + '<text x="160" y="855" class="foot">Положительное значение — выше для 13 лет; отрицательное — выше для 7 лет. Знаменатель каждого направления: 30 224 сетево-покрытые жилые точки.</text>'
        + '<text x="160" y="880" class="foot">Источник: Navigator, выгрузка 09.11.2026 · B1 · пешком, 30 минут</text></svg>'
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(svg, encoding="utf-8")
    print(f"Wrote {OUTPUT}; {negative} negative, {positive} positive, {zero} zero.")

if __name__ == "__main__":
    main()
