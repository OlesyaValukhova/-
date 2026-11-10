"""Plot a compact, publication-ready summary of an age-opportunity pilot."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    d = pd.read_csv(a.input, encoding="utf-8-sig")
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), constrained_layout=True)
    blue, orange = "#3B6EA5", "#E68A2E"
    ages = ["7 лет", "13 лет"]
    nearest = [d["age_7_nearest_minutes"].median(), d["age_13_nearest_minutes"].median()]
    second = [d["age_7_second_nearest_minutes"].median(), d["age_13_second_nearest_minutes"].median()]
    x = [0, 1]
    width = .34
    axes[0].bar([z-width/2 for z in x], nearest, width, label="ближайшая", color="#547da9")
    axes[0].bar([z+width/2 for z in x], second, width, label="вторая ближайшая", color="#bac8d8")
    axes[0].set_xticks(x, ages); axes[0].set_ylabel("минут пешком")
    axes[0].set_title("Медианное время до площадок")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    for i, value in enumerate(nearest):
        axes[0].text(i-width/2, value + .5, f"{value:.1f}", ha="center", fontsize=10, weight="bold")
        axes[0].text(i+width/2, second[i] + .5, f"{second[i]:.1f}", ha="center", fontsize=10)
    thresholds = [10, 15, 20, 30]
    v7 = [(d[f"age_7_locations_within_{t}min"] >= 2).mean() * 100 for t in thresholds]
    v13 = [(d[f"age_13_locations_within_{t}min"] >= 2).mean() * 100 for t in thresholds]
    positions = range(len(thresholds))
    axes[1].bar([z - width/2 for z in positions], v7, width, label="7 лет", color=blue)
    axes[1].bar([z + width/2 for z in positions], v13, width, label="13 лет", color=orange)
    axes[1].set_xticks(list(positions), [f"{t} мин" for t in thresholds])
    axes[1].set_ylim(0, 100); axes[1].set_ylabel("доля жилых точек, %")
    axes[1].set_title("Есть как минимум две площадки")
    axes[1].legend(frameon=False, fontsize=9)
    fig.suptitle("Шахматы: опубликованные возрастно-допустимые площадки, пилот Васильевского острова", fontsize=11, weight="bold")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.output, dpi=200, bbox_inches="tight")


if __name__ == "__main__":
    main()
