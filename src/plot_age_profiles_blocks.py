"""Render the conference block maps from the completed B1 aggregation.

No routing or recalculation of access metrics is performed here.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


def plot_category(frame: gpd.GeoDataFrame, title: str, path: Path) -> None:
    states = ['both', 'only_7', 'only_13', 'neither', 'insufficient']
    labels = {
        'both': 'предложение есть для 7 и 13 лет',
        'only_7': 'только для 7 лет',
        'only_13': 'только для 13 лет',
        'neither': 'нет наблюдаемой площадки ≤30 мин',
        'insufficient': 'менее 3 сетево-покрытых жилых точек',
    }
    colors = ['#2a9d8f', '#e9c46a', '#f4a261', '#e76f51', '#d9d9d9']
    q = frame.copy()
    state_cols = ['both_pct', 'only_7_pct', 'only_13_pct', 'neither_pct']
    q['state'] = 'insufficient'
    observed = q[state_cols].notna().any(axis=1)
    q.loc[observed, 'state'] = q.loc[observed, state_cols].idxmax(axis=1).str.replace('_pct', '', regex=False)
    q.loc[q.n_valid < 3, 'state'] = 'insufficient'
    q['state'] = q.state.astype('category').cat.set_categories(states, ordered=True)
    fig, ax = plt.subplots(figsize=(10, 9))
    q.to_crs(32636).plot(column='state', categorical=True, cmap=ListedColormap(colors),
                          linewidth=0, legend=True, legend_kwds={'labels': [labels[x] for x in states]}, ax=ax)
    ax.set_axis_off(); ax.set_title(title, loc='left', fontsize=13, weight='bold')
    fig.tight_layout(); fig.savefig(path, dpi=220, bbox_inches='tight'); plt.close(fig)


def plot_delta(frame: gpd.GeoDataFrame, title: str, path: Path) -> None:
    q = frame[frame.n_valid >= 3].copy()
    fig, ax = plt.subplots(figsize=(10, 9))
    q.to_crs(32636).plot(column='median_delta_N', cmap='RdBu_r', linewidth=0,
                          legend=True, legend_kwds={'label': 'медиана N13 − N7, координат'},
                          ax=ax, vmin=-10, vmax=10)
    ax.set_axis_off(); ax.set_title(title + '\nкварталы с ≥3 сетево-покрытыми жилыми точками', loc='left', fontsize=13, weight='bold')
    fig.tight_layout(); fig.savefig(path, dpi=220, bbox_inches='tight'); plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('data_dir', type=Path)
    args = parser.parse_args()
    out = args.data_dir / 'maps'; out.mkdir(exist_ok=True)
    layer = gpd.read_file(args.data_dir / 'age_profiles_blocks.gpkg', layer='profiles')
    cases = {'81': 'Программирование', '38': 'Изобразительное искусство'}
    for area_id, name in cases.items():
        q = layer[layer.study_area_id.astype(str) == area_id].copy()
        if q.empty:
            raise RuntimeError(f'No profile rows for study_area_id={area_id}')
        plot_category(q, f'{name}: преобладающий возрастной профиль, B1, ≤30 минут пешком', out / f'blocks_dominant_state_{area_id}.png')
    programming = layer[layer.study_area_id.astype(str) == '81'].copy()
    plot_delta(programming, 'Программирование: изменение числа доступных координат, B1, ≤30 минут пешком', out / 'blocks_delta_N_81.png')


if __name__ == '__main__':
    main()
