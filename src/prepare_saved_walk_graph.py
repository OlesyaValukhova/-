"""Adapt the user's existing OSMnx walking graph to library weight conventions.

No shortest-path algorithm is implemented here. Preserves dated source evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import pickle
import shutil

import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely.geometry import box
from blocksnet.relations.accessibility import validate_accessibility_graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', type=Path, required=True, help="User-owned trusted local OSMnx pickle")
    parser.add_argument('--buildings', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--walk-kmh', type=float, default=5)
    args = parser.parse_args()
    if not 0 < args.walk_kmh <= 8 or args.output.exists():
        parser.error('Require positive speed<=8 and a new output directory')
    with args.graph.open('rb') as stream:
        graph = pickle.load(stream)
    if not isinstance(graph, nx.MultiDiGraph):
        raise ValueError('Expected saved OSMnx MultiDiGraph')
    metadata = {k: str(v) for k, v in graph.graph.items()}
    if any(not math.isfinite(float(d['length'])) or float(d['length']) <= 0 for _, _, d in graph.edges(data=True)):
        raise ValueError('Missing/invalid source edge length')
    graph = ox.project_graph(graph, to_crs=32636)
    graph.graph.update(crs=32636, type='walk', walk_speed=args.walk_kmh * 1000 / 60)
    for _, _, data in graph.edges(data=True):
        data['length_meter'] = float(data['length'])
        data['time_min'] = data['length_meter'] / graph.graph['walk_speed']
        data['type'] = 'walk'
    validate_accessibility_graph(graph)
    buildings = gpd.read_file(args.buildings)
    residential = buildings.loc[buildings['Тип физического объекта'] == 'Жилой дом'].copy()
    if not residential.geometry.is_valid.all() or residential.geometry.isna().any():
        raise ValueError('Residential geometry needs review')
    origins = residential[['geometry']].copy()
    origins['origin_id'] = ['legacy-residential-' + str(i) for i in origins.index]
    origins['source_row'] = origins.index
    origins.geometry = origins.geometry.representative_point()
    origins = origins.to_crs(32636)
    nodes = ox.graph_to_gdfs(graph, edges=False)
    nearest = gpd.sjoin_nearest(origins, nodes[['geometry']], how='left', distance_col='snap_distance_m')
    snap = nearest.groupby('origin_id')['snap_distance_m'].min()
    counts = nearest.groupby('origin_id').size()
    origins['nearest_node_offset_m'] = origins['origin_id'].map(snap)
    origins['nearest_node_ties'] = origins['origin_id'].map(counts)
    args.output.mkdir(parents=True)
    shutil.copyfile(args.graph, args.output / 'source-walk-graph.pkl')
    ox.save_graphml(graph, args.output / 'walk.graphml')
    origins.to_crs(4326).to_file(args.output / 'origins.geojson', driver='GeoJSON')
    origins.drop(columns='geometry').to_csv(args.output / 'origin-snap-audit.csv', index=False, encoding='utf-8-sig')
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'status': 'prepared_offline',
        'source_graph': str(args.graph), 'source_graph_sha256': hashlib.sha256(args.graph.read_bytes()).hexdigest(),
        'source_graph_metadata': metadata, 'source_buildings': str(args.buildings),
        'source_buildings_sha256': hashlib.sha256(args.buildings.read_bytes()).hexdigest(),
        'versions': {name: importlib.metadata.version(name) for name in ['blocksnet','iduedu','osmnx','networkx']},
        'nodes': graph.number_of_nodes(), 'edges': graph.number_of_edges(), 'graph_crs': 32636,
        'weak_components': nx.number_weakly_connected_components(graph),
        'origins': len(origins), 'origins_offset_gt_50m': int((snap > 50).sum()),
        'origins_offset_gt_100m': int((snap > 100).sum()), 'origins_with_nearest_node_ties': int((counts > 1).sum()),
        'origins_outside_node_bbox': int((~origins.geometry.covered_by(box(*nodes.total_bounds))).sum()),
        'offset_quantiles_m': {str(k): float(v) for k, v in snap.quantile([0, .5, .9, .95, 1]).items()},
        'walk_kmh': args.walk_kmh, 'edge_weight': 'time_min', 'edge_weight_unit': 'minutes',
        'actual_entrances_verified': False, 'new_network_downloaded': False,
        'programme_accessibility_computed': False,
        'limitations': ['Source network metadata dates its creation to 2026-05-31; not refreshed to November.',
            'Node offset is straight-line attachment uncertainty, not an observed walk or verified access path.',
            'No synthetic connector edges added; large offsets require review before interpreting routes.',
            'Uniform walking speed is a technical scenario, not a validated age-specific capability.',
            'Source pedestrian filtering and missing crossings/access restrictions need separate audit.']}
    (args.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['status','nodes','edges','origins','origins_offset_gt_50m','origins_offset_gt_100m','origins_outside_node_bbox','offset_quantiles_m']}))


if __name__ == '__main__':
    main()
