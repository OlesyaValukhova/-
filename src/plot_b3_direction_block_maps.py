"""Render B3 block maps for the two directions used in the conference deck."""
from pathlib import Path
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


ROOT = Path("results/age-profiles-blocks-b3-20261112")


def render(frame, direction_id, title, output):
    q = frame[frame.study_area_id.astype(str) == str(direction_id)].copy()
    states = ["both", "only_7", "only_13", "neither", "insufficient"]
    labels = ["7 + 13 \u043b\u0435\u0442", "\u0442\u043e\u043b\u044c\u043a\u043e 7 \u043b\u0435\u0442", "\u0442\u043e\u043b\u044c\u043a\u043e 13 \u043b\u0435\u0442", "\u043d\u0435\u0442 \u2264 30 \u043c\u0438\u043d", "< 3 \u0436\u0438\u043b\u044b\u0445 \u0442\u043e\u0447\u0435\u043a"]
    q["state"] = "insufficient"
    observed = q[["both_pct", "only_7_pct", "only_13_pct", "neither_pct"]].notna().any(axis=1)
    q.loc[observed, "state"] = q.loc[observed, ["both_pct", "only_7_pct", "only_13_pct", "neither_pct"]].idxmax(axis=1).str.replace("_pct", "", regex=False)
    q.loc[q.n_valid < 3, "state"] = "insufficient"
    q["state"] = q.state.astype("category").cat.set_categories(states, ordered=True)
    fig, ax = plt.subplots(figsize=(12, 7), facecolor="white")
    q.to_crs(32636).plot(column="state", categorical=True, cmap=ListedColormap(["#2a9d8f", "#e9c46a", "#f4a261", "#e76f51", "#d9d9d9"]), linewidth=.1, edgecolor="white", legend=True, legend_kwds={"labels": labels, "loc": "center left", "bbox_to_anchor": (1.01, .5), "frameon": False, "fontsize": 10}, ax=ax)
    ax.set_axis_off(); ax.set_title(title, loc="left", fontsize=16, weight="bold", pad=12)
    fig.subplots_adjust(left=.01, right=.76, top=.91, bottom=.02)
    fig.savefig(output, dpi=220, facecolor="white"); plt.close(fig)


if __name__ == "__main__":
    maps = ROOT / "maps"; maps.mkdir(exist_ok=True)
    layer = gpd.read_file(ROOT / "age_profiles_blocks.gpkg", layer="profiles", engine="pyogrio")
    render(layer, "81", "Программирование: возрастной профиль, B3, ≤30 минут", maps / "blocks_dominant_state_81_b3.png")
    render(layer, "38", "Изобразительное искусство: возрастной профиль, B3, ≤30 минут", maps / "blocks_dominant_state_38_b3.png")
