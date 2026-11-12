"""Render comparable B1 maps from the published age_profiles_blocks.gpkg.

Requires GDAL's ogr2ogr and matplotlib. No routing or metric recalculation.
"""
import argparse, collections, json, pathlib, subprocess, tempfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import PathPatch, Patch
from matplotlib.path import Path

COLORS = ['#526F85', '#CB9A5A', '#6E8C78', '#BFCAD0', '#EDEDE9', '#9F8D7D']
LABELS = ['Для обоих возрастов', 'Только для 7 лет', 'Только для 13 лет',
          'Ни для одного возраста', 'Менее 3 точек с сетью', 'Равенство состояний']
FIELDS = ['both_pct', 'only_7_pct', 'only_13_pct', 'neither_pct']

def polygon_path(rings):
    vertices, codes = [], []
    for i, ring in enumerate(rings):
        # Enforce opposite winding for holes under the nonzero fill rule.
        area = sum(a[0]*b[1] - b[0]*a[1] for a,b in zip(ring, ring[1:]))
        if (area > 0) != (i == 0):
            ring = ring[::-1]
        vertices.extend(ring)
        codes.extend([Path.MOVETO] + [Path.LINETO]*(len(ring)-2) + [Path.CLOSEPOLY])
    return PathPatch(Path(vertices, codes))

def category(p):
    if p['n_valid'] is None or p['n_valid'] < 3:
        return 4
    values = [p[x] for x in FIELDS]
    if any(v is None for v in values):
        raise ValueError('Missing state percentages for eligible block')
    maximum = max(values)
    winners = [i for i, value in enumerate(values) if abs(value - maximum) < 1e-7]
    return winners[0] if len(winners) == 1 else 5

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('gpkg'); parser.add_argument('output', type=pathlib.Path)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / 'blocks.geojson'
        subprocess.run(['ogr2ogr', '-f', 'GeoJSON', '-t_srs', 'EPSG:32636', str(target),
                        args.gpkg, 'profiles', '-where', "study_area_id IN ('81','38')"], check=True)
        features = json.loads(target.read_text())['features']
    groups = collections.defaultdict(list)
    for feature in features:
        groups[str(feature['properties']['study_area_id'])].append(feature)
    if set(groups) != {'81', '38'} or any(len(x) != 3330 for x in groups.values()):
        raise ValueError('Expected 3,330 blocks for each direction')
    all_coords = []
    for feature in groups['81']:
        for polygon in feature['geometry']['coordinates']:
            all_coords.extend(polygon[0])
    xs, ys = zip(*all_coords); bounds = (min(xs), max(xs), min(ys), max(ys))
    for code in ['81', '38']:
        buckets = [[] for _ in COLORS]; counts = collections.Counter()
        for f in groups[code]:
            idx = category(f['properties']); counts[idx] += 1
            for poly in f['geometry']['coordinates']:
                buckets[idx].append(polygon_path(poly))
        fig = plt.figure(figsize=(16, 9), facecolor='white')
        ax = fig.add_axes([.035,.10,.60,.78])
        for i, patches in enumerate(buckets):
            ax.add_collection(PatchCollection(patches, facecolor=COLORS[i], edgecolor='white', linewidth=.12))
        ax.set_xlim(bounds[0],bounds[1]); ax.set_ylim(bounds[2],bounds[3]); ax.set_aspect('equal'); ax.axis('off')
        fig.text(.055,.92,groups[code][0]['properties']['study_area_name'], fontsize=23, color='#25313A')
        fig.text(.65,.77,'Преобладающее состояние', fontsize=17, color='#25313A')
        fig.text(.65,.73,'среди жилых точек квартала', fontsize=14, color='#566771')
        handles = [Patch(facecolor=COLORS[i], edgecolor='none', label=LABELS[i]) for i in range(6)]
        fig.legend(handles=handles, loc='upper left', frameon=False, fontsize=14,
                   bbox_to_anchor=(.65,.69), labelspacing=.8, handlelength=1.4)
        fig.text(.65,.30,'Пешком за 30 минут',fontsize=14,color='#25313A')
        fig.text(.65,.265,'Опубликованные координаты Navigator.\nОтсутствие координаты не доказывает\nотсутствие занятий.',fontsize=11,color='#566771',linespacing=1.5,va='top')
        fig.text(.055,.04,'BlocksNet · сценарий B1 · не фактические поездки и не наличие мест',fontsize=10,color='#64737C')
        # UTM 36N has metre units; the bar represents 10,000 m on the map.
        x0=bounds[0]+(bounds[1]-bounds[0])*.05; y0=bounds[2]+(bounds[3]-bounds[2])*.04
        ax.plot([x0,x0+10000],[y0,y0],color='#33454f',lw=2)
        ax.text(x0+5000,y0+(bounds[3]-bounds[2])*.012,'10 км',ha='center',fontsize=9,color='#33454f')
        fig.savefig(args.output / f'blocks_state_{code}.png', dpi=120, facecolor='white')
        plt.close(fig)
        print(code, dict(sorted(counts.items())))

if __name__ == '__main__': main()
