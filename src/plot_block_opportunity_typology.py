"""Draw a simple map of the exploratory chess-opportunity block profiles."""
import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    blocks = gpd.read_file(a.input)
    # Labels are defined from the checked median profiles in the pilot README.
    labels = {1: "ограниченный выбор\nв обоих возрастах", 2: "близкое предложение,\nно сужение выбора"}
    colors = {1: "#D6604D", 2: "#4393C3"}
    fig, ax = plt.subplots(figsize=(8, 7.5))
    for value in sorted(labels):
        blocks[blocks.exploratory_cluster == value].plot(ax=ax, color=colors[value], edgecolor="white", linewidth=.25,
                                                         label=labels[value])
    ax.set_axis_off()
    ax.set_title("Шахматы: пилотные профили кварталов\nВасильевский остров", fontsize=15, weight="bold", pad=15)
    ax.legend(loc="lower left", frameon=True, facecolor="white", framealpha=.94, title="Профиль опубликованного\nвозрастного предложения")
    fig.text(.5, .02, "Эксплораторная типология: 142 квартала, одна деятельность; не отражает фактическую мобильность семей.",
             ha="center", fontsize=8.5)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.output, dpi=220, bbox_inches="tight")


if __name__ == "__main__":
    main()
