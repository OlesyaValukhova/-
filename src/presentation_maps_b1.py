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

COLORS = ['#526F85', '#D0A56B', '#708C78', '#D7DDE0', '#F2F2F0', '#B9AC9A']
LABELS = ['Для обоих возрастов', 'Только для 7 лет', 'Только для 13 лет',
          'Ни для одного возраста', 'Менее 3 жилых точек с сетью', 'Равенство наиболее частых состояний']
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
        fig, ax = plt.subplots(figsize=(10, 8), facecolor='white')
        for i, patches in enumerate(buckets):
            ax.add_collection(PatchCollection(patches, facecolor=COLORS[i], edgecolor='white', linewidth=.12))
        ax.set_xlim(bounds[0],bounds[1]); ax.set_ylim(bounds[2],bounds[3]); ax.set_aspect('equal'); ax.axis('off')
        ax.set_title(groups[code][0]['properties']['study_area_name'], loc='left', fontsize=17, color='#25313A', pad=9)
        handles = [Patch(facecolor=COLORS[i], edgecolor='none', label=LABELS[i]) for i in range(6)]
        fig.legend(handles=handles, loc='lower center', ncol=2, frameon=False, fontsize=9, bbox_to_anchor=(.5,.085))
        fig.text(.08,.055,'Преобладающее состояние среди жилых точек квартала · пешком за 30 минут',fontsize=9,color='#3D4A52')
        fig.text(.08,.03,'Опубликованные координаты Navigator · BlocksNet · B1; не фактические поездки и не наличие мест',fontsize=8,color='#64737C')
        fig.subplots_adjust(left=.05,right=.95,top=.91,bottom=.22)
        fig.savefig(args.output / f'blocks_state_{code}.png', dpi=180, facecolor='white')
        plt.close(fig)
        print(code, dict(sorted(counts.items())))

if __name__ == '__main__': main()
