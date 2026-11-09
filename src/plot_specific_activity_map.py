"""Plot a small diagnostic map from library routes and reviewed programme IDs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix', type=Path, required=True)
    p.add_argument('--origin-rows', type=Path, required=True)
    p.add_argument('--origins', type=Path, required=True)
    p.add_argument('--blocks', type=Path, required=True)
    p.add_argument('--locations', type=Path, required=True)
    p.add_argument('--programs', type=Path, required=True)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    matrix = pd.read_csv(a.matrix, index_col=0, encoding='utf-8-sig')
    rows = pd.read_csv(a.origin_rows, encoding='utf-8-sig')
    origins = gpd.read_file(a.origins)
    blocks = gpd.read_file(a.blocks)
    locations = gpd.read_file(a.locations)
    programs = pd.read_csv(a.programs, encoding='utf-8-sig')
    selection = json.loads(a.selection.read_text(encoding='utf-8'))['categories']['Шахматы']
    if (not np.array_equal(matrix.index.to_numpy(), np.arange(len(matrix)))
            or len(rows) != len(matrix) or len(origins) != len(matrix)
            or not rows.origin_id.equals(origins.origin_id)
            or not locations.location_id.is_unique
            or set(locations.location_id) != set(matrix.columns)):
        raise ValueError('Origin order or destination IDs do not match the route matrix')
    if set(selection) - set(programs.program_id):
        raise ValueError('Reviewed programme IDs missing from scenario snapshot')
    if any(g.crs is None for g in (origins, blocks, locations)):
        raise ValueError('All geometries need a CRS')
    origins = origins.to_crs(32636)
    locations = locations.to_crs(32636)
    blocks = blocks.loc[blocks.geometry.notna() & blocks.geometry.is_valid].to_crs(32636)
    matrix = matrix.astype(float)
    if not np.isfinite(matrix.to_numpy()).all() or (matrix.to_numpy() < 0).any():
        raise ValueError('Invalid route matrix')
    counts = {}
    chosen_locations = {}
    for age in [7, 13]:
        eligible = programs.loc[(programs.program_id.isin(selection)) & (programs.age == age)
                                & (programs.program_age_match == True)]
        if eligible.program_id.duplicated().any():
            raise ValueError('Duplicate programme-age records')
        ids = sorted(set(eligible.location_id))
        if not set(ids).issubset(matrix.columns):
            raise ValueError('Missing destination coordinate in route matrix')
        chosen_locations[age] = ids
        counts[age] = (matrix[ids].to_numpy() <= 15).sum(axis=1) if ids else np.zeros(len(matrix), dtype=int)
        origins[f'age_{age}_reachable_coordinates'] = counts[age]
    a.output.mkdir(parents=True)
    origins.to_crs(4326).to_file(a.output / 'residential-points-with-counts.geojson', driver='GeoJSON')
    origins.drop(columns='geometry').to_csv(a.output / 'residential-points-with-counts.csv', index=False, encoding='utf-8-sig')
    cmap = ListedColormap(['#d6dce1', '#9dc6db', '#4e93ba', '#205a86'])
    norm = BoundaryNorm([-.5, .5, 1.5, 2.5, 100], cmap.N)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11})
    fig, axes = plt.subplots(1, 2, figsize=(13, 8), constrained_layout=True)
    minx, miny, maxx, maxy = origins.total_bounds
    for ax, age in zip(axes, [7, 13]):
        blocks.plot(ax=ax, facecolor='#f7f8f8', edgecolor='#d8dee2', linewidth=.3, zorder=1)
        ax.scatter(origins.geometry.x, origins.geometry.y, c=np.minimum(counts[age], 3),
                   cmap=cmap, norm=norm, s=11, linewidths=0, zorder=2)
        sites = locations.loc[locations.location_id.isin(chosen_locations[age])]
        ax.scatter(sites.geometry.x, sites.geometry.y, marker='*', color='#d77a32',
                   edgecolor='white', linewidth=.4, s=90, zorder=3)
        ax.set_xlim(minx-250, maxx+250)
        ax.set_ylim(miny-250, maxy+250)
        ax.set_aspect('equal')
        ax.set_title(f'{age} лет', fontsize=16, weight='bold')
        ax.set_axis_off()
    fig.suptitle('Шахматы: что показывают записи Навигатора рядом с домом', fontsize=17, weight='bold')
    handles = [Line2D([0], [0], marker='o', linestyle='', color=c, label=l, markersize=8)
               for c, l in zip(cmap.colors, ['0', '1', '2', '3 и более'])]
    handles.append(Line2D([0], [0], marker='*', linestyle='', color='#d77a32',
                          label='Координата программы', markersize=11))
    fig.legend(handles=handles, title='Разных координат в 15 минутах по сети',
               loc='lower center', bbox_to_anchor=(.5, -.005), ncol=5, frameon=False)
    subset = set(chosen_locations[13]).issubset(chosen_locations[7])
    subset_note = ('Точки для 13 лет входят в набор точек для 7 лет; сравнение зависит от состава выборки.'
                   if subset else 'Наборы точек различаются; сравнение зависит от состава выборки.')
    fig.text(.04, -.08, 'Василеостровский район · возраст программы · 9 ноября 2026\n'
             + subset_note + '\n'
             + 'Подходы к узлам не учтены. Точки и работа групп не подтверждены; ноль — отсутствие записей в выборке.',
             fontsize=10, color='#46535c', va='top')
    fig.savefig(a.output / 'chess-age-map.png', dpi=170, bbox_inches='tight', facecolor='white')
    fig.savefig(a.output / 'chess-age-map.svg', bbox_inches='tight', facecolor='white')
    plt.close(fig)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'activity': 'Шахматы',
              'scenario': 'known programme age only', 'ages': [7, 13], 'threshold_minutes': 15,
              'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
                          [a.matrix, a.origin_rows, a.origins, a.blocks, a.locations, a.programs, a.selection]},
              'buildings': len(origins), 'coordinates_by_age': {str(k): len(v) for k, v in chosen_locations.items()},
              'age13_coordinate_set_is_subset_of_age7': subset,
              'building_count_distribution': {str(age): {str(k): int(v) for k, v in
                  pd.Series(counts[age]).value_counts().sort_index().items()} for age in [7, 13]},
              'limitations': ['Reported programme coordinates, not independently verified class venues.',
                'Title-based chess selection is incomplete; unknown ages are not included.',
                'Records without catalogue coordinates or outside the district were excluded.',
                'Network costs omit links to nodes; 15 minutes is a scenario, not a child mobility norm.',
                'Points are representative residential building locations, not children or building entrances.',
                'Results do not measure parental accompaniment, actual participation or route safety.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'coordinates_by_age': report['coordinates_by_age'], 'buildings': len(origins)}))


if __name__ == '__main__':
    main()
