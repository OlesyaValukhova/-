"""Plot empirical coverage curves for nearest programme times by age scenario."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--times", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = pd.read_csv(args.times, encoding="utf-8-sig")
    columns = [column for column in data if column.startswith("tf_default_nearest_minutes_age_")]
    if not columns:
        raise ValueError("No nearest-time columns found")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, ax = plt.subplots(figsize=(8.2, 5.0), constrained_layout=True)
    for column, color in zip(columns, ["#2a6fbb", "#c85720", "#5a8f29", "#7e5aa6"]):
        age = column.rsplit("_", 1)[-1]
        values = data[column].sort_values().to_numpy()
        coverage = (range(1, len(values) + 1))
        ax.step(values, [value / len(values) for value in coverage], where="post", label=f"{age} лет", color=color, linewidth=2.4)
    for threshold in (10, 15, 20, 30):
        ax.axvline(threshold, color="#9a9a9a", linewidth=0.8, linestyle="--", zorder=0)
        ax.text(threshold + 0.25, 0.02, f"{threshold} мин", color="#666666", fontsize=9, rotation=90, va="bottom")
    ax.set(xlim=(0, max(data[columns].max()) + 2), ylim=(0, 1.02),
           xlabel="Расчётное время до ближайшей опубликованной координаты, мин",
           ylabel="Доля 1 265 жилых точек", title="Шахматные программы: покрытие по возрастному допуску")
    ax.grid(axis="y", color="#dddddd", linewidth=0.8)
    ax.legend(title="Возраст сценария", frameon=False, loc="lower right")
    fig.savefig(args.output, dpi=220, facecolor="white")


if __name__ == "__main__":
    main()
