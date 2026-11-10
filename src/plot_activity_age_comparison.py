"""Compare age profiles of two narrowly selected activities."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def metrics(path):
    d = pd.read_csv(path, encoding="utf-8-sig")
    return {
        "nearest": [d[f"age_{age}_nearest_minutes"].median() for age in (7, 13)],
        "two15": [(d[f"age_{age}_locations_within_15min"] >= 2).mean() * 100 for age in (7, 13)],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chess", type=Path, required=True)
    p.add_argument("--robotics", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    series = {"Шахматы": metrics(a.chess), "Робототехника": metrics(a.robotics)}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
    colors = ["#3B6EA5", "#E68A2E"]
    x = [0, 1]
    for i, (activity, result) in enumerate(series.items()):
        axes[0].plot(x, result["nearest"], marker="o", linewidth=2.5, label=activity, color=colors[i])
        axes[1].plot(x, result["two15"], marker="o", linewidth=2.5, label=activity, color=colors[i])
    for ax in axes:
        ax.set_xticks(x, ["7 лет", "13 лет"]); ax.grid(axis="y", alpha=.25); ax.legend(frameon=False)
    axes[0].set_title("Медиана до ближайшей площадки"); axes[0].set_ylabel("минут пешком")
    axes[1].set_title("Есть ≥2 площадки за 15 минут"); axes[1].set_ylabel("доля жилых точек, %")
    fig.suptitle("Возрастной профиль зависит от конкретной деятельности", fontsize=13, weight="bold")
    fig.supxlabel(
        "Пилот Васильевского острова; опубликованные возрастные допуски программ, не фактическая мобильность.",
        fontsize=8.5,
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.output, dpi=220, bbox_inches="tight")


if __name__ == "__main__":
    main()
