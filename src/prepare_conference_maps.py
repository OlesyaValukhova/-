"""Generate conference-ready point maps and comparison tables from finished BlocksNet B1/B3.
Run from the nir-digital-urbanism repository root. No route calculation.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 14,
                     'figure.facecolor': 'white', 'savefig.facecolor': 'white'})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--b1', default='results/blocksnet-b1-citywide-20261111/full_observable/b1-by-origin.geojson')
    p.add_argument('--b3', default='results/blocksnet-b3-citywide-20261111/full_observable/b3-by-origin.geojson')
    p.add_argument('--output', default='results/blocksnet-conference-maps-20261111')
    args = p.parse_args()
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    print('Reading completed results...', flush=True)
    b1 = gpd.read_file(args.b1)
    b3 = gpd.read_file(args.b3)
    for tag, g in [('B1', b1), ('B3', b3)]:
        if 'origin_id' not in g or not g.origin_id.is_unique:
            raise ValueError(f'{tag}: origin_id missing or duplicated')
    if set(b1.origin_id) != set(b3.origin_id):
        raise ValueError('B1/B3 origin IDs differ; refusing to compare')
    if not b1.crs or not b3.crs:
        raise ValueError('Input GeoJSON CRS missing')
    b1 = b1.to_crs(32636)
    b3 = b3.to_crs(32636)
    b1['origin_id'] = b1.origin_id.astype(str)
    b3['origin_id'] = b3.origin_id.astype(str)
    joined = b1.merge(b3.drop(columns='geometry'), on='origin_id', suffixes=('_B1', '_B3'), validate='one_to_one')
    if len(joined) != 30611:
        print(f'WARNING: expected 30611 origins, got {len(joined)}', flush=True)
    both = joined.network_covered_B1.astype(str).str.lower().isin(['true','1']) & joined.network_covered_B3.astype(str).str.lower().isin(['true','1'])
    joined['comparison_covered'] = both
    rows = []
    for age in [7, 13]:
        for t in [10, 15, 20, 30]:
            source = f'age_{age}_N_venue_proxy_within_{t}min'
            c1, c3 = f'{source}_B1', f'{source}_B3'
            if c1 not in joined or c3 not in joined:
                raise ValueError(f'Missing column {source} in source data')
            a = pd.to_numeric(joined[c1], errors='coerce')
            b = pd.to_numeric(joined[c3], errors='coerce')
            good = both & a.notna() & b.notna()
            diff = (b-a).where(good)
            joined[f'age_{age}_gain_{t}min'] = diff
            joined[f'age_{age}_zero_B1_{t}min'] = (a.eq(0)).where(good)
            joined[f'age_{age}_zero_B3_{t}min'] = (b.eq(0)).where(good)
            if (diff.dropna() < 0).any():
                print(f'WARNING: B3 < B1 for age={age}, threshold={t}', flush=True)
            av, bv = a[good], b[good]
            rows.append({'age': age, 'threshold_min': t, 'valid_origins': int(good.sum()),
                         'mean_venues_B1': round(float(av.mean()), 3),
                         'mean_venues_B3': round(float(bv.mean()), 3),
                         'median_venues_B1': float(av.median()),
                         'median_venues_B3': float(bv.median()),
                         'mean_gain': round(float((bv-av).mean()), 3),
                         'relative_mean_gain_pct': round(float(100*(bv.mean()/av.mean()-1)), 2) if av.mean() else None,
                         'origins_improved_pct': round(float(100*(bv>av).mean()), 2),
                         'origins_zero_B1_pct': round(float(100*(av==0).mean()), 2),
                         'origins_zero_B3_pct': round(float(100*(bv==0).mean()), 2)})
    for t in [15, 30]:
        for scenario in ['B1', 'B3']:
            a = pd.to_numeric(joined[f'age_7_N_venue_proxy_within_{t}min_{scenario}'], errors='coerce')
            b = pd.to_numeric(joined[f'age_13_N_venue_proxy_within_{t}min_{scenario}'], errors='coerce')
            joined[f'age_gap_7_minus_13_{scenario}_{t}min'] = (a-b).where(both)
    summary = pd.DataFrame(rows)
    summary.to_csv(outdir/'comparison-summary.csv', index=False, encoding='utf-8-sig')
    joined.drop(columns=['geometry']).to_csv(outdir/'all-origins-comparison.csv', index=False, encoding='utf-8-sig')
    joined.to_crs(4326).to_file(outdir/'all-origins-comparison.geojson', driver='GeoJSON')
    print('Saved comparison tables and GeoJSON', flush=True)

    xy = np.column_stack((joined.geometry.x.to_numpy(), joined.geometry.y.to_numpy()))
    x, y = xy[:,0], xy[:,1]
    ext = (np.nanmin(x), np.nanmax(x), np.nanmin(y), np.nanmax(y))
    dx, dy = ext[1]-ext[0], ext[3]-ext[2]
    ext = (ext[0]-dx*.025, ext[1]+dx*.025, ext[2]-dy*.025, ext[3]+dy*.025)

    def plot_categorical(values, boundaries, colors, labels, title, filename, note):
        fig, ax = plt.subplots(figsize=(10.5, 10.5), dpi=140)
        ax.set_aspect('equal')
        ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
        ax.set_facecolor('#f7f8fa')
        valid = both.to_numpy() & np.isfinite(values)
        ax.scatter(x[~valid], y[~valid], s=1.6, color='#c7cbd1', alpha=.6, linewidths=0, rasterized=True)
        cmap = ListedColormap(colors)
        norm = BoundaryNorm(boundaries, cmap.N)
        ax.scatter(x[valid], y[valid], c=values[valid], cmap=cmap, norm=norm,
                   s=2.6, alpha=.85, linewidths=0, rasterized=True)
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values(): spine.set_visible(False)
        ax.set_title(title, loc='left', fontweight='bold', pad=18)
        handles = [Line2D([0],[0], marker='o', linestyle='', color='none', markerfacecolor=color,
                          markeredgecolor='none', markersize=8, label=label) for color,label in zip(colors,labels)]
        handles.append(Line2D([0],[0], marker='o', linestyle='', color='none', markerfacecolor='#c7cbd1',
                              markeredgecolor='none', markersize=8, label='Нет сетевого подключения / данных'))
        fig.legend(handles=handles, loc='lower center', ncol=2, bbox_to_anchor=(.5,.055), frameon=False, fontsize=9)
        fig.text(.5,.018,note,ha='center',fontsize=8,color='#555555')
        fig.subplots_adjust(top=.94,bottom=.15,left=.04,right=.96)
        fig.savefig(outdir/filename, dpi=200)
        plt.close(fig)
        print('Saved', filename, flush=True)

    availability_edges = [-.5,.5,3.5,10.5,25.5,np.inf]
    availability_colors = ['#a23b3b','#e7a366','#f3df99','#a4d4b2','#368b77']
    availability_labels = ['0 площадок','1–3','4–10','11–25','26 и более']
    gain_edges = [-.5,.5,5.5,15.5,30.5,np.inf]
    gain_colors = ['#e7e8ea','#d1e7ed','#8fc8d8','#4498b6','#12617d']
    gain_labels = ['Без прироста','+1–5','+6–15','+16–30','+31 и более']
    for age in [7,13]:
        for scenario in ['B1','B3']:
            key = f'age_{age}_N_venue_proxy_within_30min_{scenario}'
            plot_categorical(pd.to_numeric(joined[key],errors='coerce').to_numpy(dtype=float),
                             availability_edges, availability_colors, availability_labels,
                             f'{age} лет · {"пешком" if scenario=="B1" else "пешком + транспорт"} · 30 минут',
                             f'access_age{age}_{scenario}_30min.png',
                             'Точки жилой застройки · число доступных площадок, не число программ')
        plot_categorical(pd.to_numeric(joined[f'age_{age}_gain_30min'],errors='coerce').to_numpy(dtype=float),
                         gain_edges, gain_colors, gain_labels,
                         f'{age} лет · прирост выбора благодаря транспорту · 30 минут',
                         f'transport_gain_age{age}_30min.png',
                         'B3 − B1 · 5 минут на посадку в транспорт · сценарная оценка')
    # Zero-access maps for 15 and 30 minutes, both ages in one image per threshold.
    for t in [15,30]:
        for age in [7,13]:
            key = f'age_{age}_N_venue_proxy_within_{t}min_B3'
            z = pd.to_numeric(joined[key],errors='coerce').to_numpy(dtype=float)
            plot_categorical(z, [-.5,.5,np.inf], ['#b83b3b','#b8d3c8'],
                             ['Нет доступных площадок','Есть хотя бы одна'],
                             f'{age} лет · зоны без выбора · {t} минут с транспортом',
                             f'zero_access_age{age}_B3_{t}min.png',
                             'Не учитываются расписания занятий, вместимость и сопровождение')
    for t in [15,30]:
        key = f'age_gap_7_minus_13_B1_{t}min'
        gap = pd.to_numeric(joined[key],errors='coerce').to_numpy(dtype=float)
        plot_categorical(gap, [-np.inf,-.5,.5,5.5,15.5,np.inf],
                         ['#9d6aa6','#e8e8e8','#f4dca1','#e6a25d','#bd633e'],
                         ['Больше для 13 лет','Одинаково','На 1–5 больше для 7 лет',
                          'На 6–15 больше для 7 лет','На 16+ больше для 7 лет'],
                         f'Разница возрастной доступности · пешком · {t} минут',
                         f'age_gap_B1_{t}min.png',
                         'Разница числа площадок: 7 лет минус 13 лет')
    (outdir/'README.txt').write_text(
        'Карты показывают жилые точки, а не непрерывные зоны доступности.\n'
        'Знаменатель долей — только точки с корректным подключением в обоих сценариях.\n'
        'Данные не взвешены по численности детей или населения.\n'
        'B3: сценарное ожидание 5 минут на каждую посадку.\n'
        'Нормативы по видам секций НЕ применены: исходные результаты агрегированы по всем программам.\n'
        'Не учитываются фактическое сопровождение детей, расписания, качество и вместимость секций.\n',
        encoding='utf-8')
    print('DONE:', outdir.resolve(), flush=True)

if __name__ == '__main__':
    main()
