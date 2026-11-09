"""Prepare a pedestrian graph through BlocksNet/IduEdu, not a custom router.

Residential representatives are geometric proxies, not verified building entrances.
The network supports technical feasibility checks, not child-safety assessment.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--buildings', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--buffer-metres', type=float, default=1000)
    parser.add_argument('--overpass-url', default='https://overpass-api.de/api',
                        choices=['https://overpass-api.de/api', 'https://overpass.private.coffee/api',
                                 'https://overpass.kumi.systems/api'])
    args = parser.parse_args()
    if not args.buildings.is_file() or not 0 < args.buffer_metres <= 3000:
        parser.error('Require existing buildings and buffer 0..3000m')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(), 'status': 'running',
              'source_buildings': str(args.buildings),
              'source_sha256': hashlib.sha256(args.buildings.read_bytes()).hexdigest(),
              'source_export_date_verified': False, 'programme_accessibility_computed': False,
              'actual_entrances_verified': False, 'buffer_metres': args.buffer_metres,
              'overpass_url': args.overpass_url,
              'limitations': ['Geometric origins are not verified entrances.',
                  'IduEdu 0.4.1 removes weakly connected components; missing network links are not proof of inaccessibility.',
                  'Default walking speed is a technical baseline, not an age-specific independent mobility threshold.']}
    manifest = args.output / 'manifest.json'
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        import geopandas as gpd
        import osmnx as ox
        import importlib.metadata
        from blocksnet.relations.accessibility import get_accessibility_graph
        buildings = gpd.read_file(args.buildings)
        if buildings.crs is None:
            raise ValueError('Source CRS is missing')
        buildings = buildings.loc[buildings['Тип физического объекта'] == 'Жилой дом'].copy()
        if buildings.empty or buildings.geometry.isna().any() or not buildings.geometry.is_valid.all():
            raise ValueError('Residential building geometry needs review')
        origins = buildings[['geometry']].copy()
        origins['source_row'] = origins.index
        origins.geometry = origins.geometry.representative_point()
        origins.to_crs(4326).to_file(args.output / 'origins.geojson', driver='GeoJSON')
        metric = origins.to_crs(32636)
        area = gpd.GeoDataFrame(geometry=[metric.union_all().convex_hull.buffer(args.buffer_metres)], crs=32636).to_crs(4326)
        area.to_file(args.output / 'acquisition-area.geojson', driver='GeoJSON')
        ox.settings.use_cache = True
        ox.settings.cache_folder = str(args.output / 'osmnx-cache')
        ox.settings.requests_timeout = 60
        ox.settings.overpass_rate_limit = False
        ox.settings.overpass_url = args.overpass_url
        report.update(origins=len(origins), acquisition_bounds=area.total_bounds.tolist(),
                      versions={name: importlib.metadata.version(name) for name in ['blocksnet','iduedu','osmnx']})
        manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        graph = get_accessibility_graph(area, 'walk')
        ox.save_graphml(graph, args.output / 'walk.graphml')
        report.update(status='prepared', nodes=graph.number_of_nodes(), edges=graph.number_of_edges(),
                      graph_crs=graph.graph.get('crs'), walk_speed_metres_per_minute=graph.graph.get('walk_speed'))
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True), flush=True)
    return 0 if report['status'] == 'prepared' else 1


if __name__ == '__main__':
    sys.exit(main())
