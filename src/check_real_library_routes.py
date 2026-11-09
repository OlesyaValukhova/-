"""Offline library OD calculation: residential proxies to reported destinations.

Uses Transport Frames routing. No actual school assignment/escort/OOSA inference.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import traceback

import geopandas as gpd
import numpy as np
import networkx as nx
import osmnx as ox
from transport_frames.indicators import calculate_distances
from iduedu import get_adj_matrix_gdf_to_gdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', type=Path, required=True)
    parser.add_argument('--origins', type=Path, required=True)
    parser.add_argument('--schools', '--destinations', dest='destinations', type=Path, required=True)
    parser.add_argument('--destination-kind', choices=['school_control', 'reported_program_coordinate'], default='school_control')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(), 'status': 'running',
              'scope': 'technical real-data routing integration check',
              'destination_kind': args.destination_kind,
              'programme_accessibility_computed': False, 'actual_school_assignment_known': False,
              'parent_time_computed': False, 'periodic_monitor_started': False,
              'sources': {key: {'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                          for key, path in [('graph', args.graph), ('origins', args.origins), ('destinations', args.destinations)]}}
    manifest = args.output / 'manifest.json'
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        graph = ox.load_graphml(args.graph, edge_dtypes={'time_min': float, 'length_meter': float},
                               graph_dtypes={'crs': int, 'walk_speed': float})
        original_edges = graph.number_of_edges()
        parallel_pairs = sum(len(edges) > 1 for neighbors in graph.adj.values() for edges in neighbors.values())
        # IduEdu coerces MultiDiGraph to DiGraph without selecting the minimum.
        # Use OSMnx's existing minimum-weight conversion explicitly before routing.
        graph = ox.convert.to_digraph(graph, weight='time_min')
        ox.save_graphml(nx.MultiDiGraph(graph), args.output / 'minimum-weight-routing-graph.graphml')
        origins = gpd.read_file(args.origins).to_crs(graph.graph['crs'])
        schools = gpd.read_file(args.destinations).to_crs(graph.graph['crs'])
        if args.destination_kind == 'reported_program_coordinate':
            if 'location_id' not in schools or not schools['location_id'].is_unique:
                raise ValueError('Reported coordinate IDs must be unique')
            schools = schools.set_index('location_id', drop=False)
        schools.geometry = schools.geometry.representative_point()
        if origins.empty or schools.empty or not schools.geometry.is_valid.all():
            raise ValueError('Input geometries need review')
        nodes = ox.graph_to_gdfs(nx.MultiDiGraph(graph), edges=False)
        destination_snaps = gpd.sjoin_nearest(schools[['geometry']], nodes[['geometry']],
            how='left', distance_col='destination_node_offset_m')
        schools['destination_node_offset_m'] = destination_snaps.groupby(level=0)['destination_node_offset_m'].min()
        components = sorted((len(c) for c in nx.strongly_connected_components(graph)), reverse=True)
        nearest = calculate_distances(origins.copy(), schools.copy(), graph, weight='time_min', unit_div=1)
        matrix = get_adj_matrix_gdf_to_gdf(origins.copy(), schools.copy(), graph,
            weight='time_min', dtype=np.float64, add_dist_tofrom_node=False)
        network_nearest = matrix.min(axis=1)
        if len(nearest) != len(origins) or (nearest.dropna() < 0).any():
            raise ValueError('Invalid route results')
        table = origins[['origin_id', 'source_row', 'nearest_node_offset_m']].copy()
        destination_label = 'school' if args.destination_kind == 'school_control' else 'reported_location'
        table[f'tf_default_nearest_{destination_label}_minutes'] = nearest
        table[f'network_only_nearest_{destination_label}_minutes'] = network_nearest
        table['origin_offset_review_gt_50m'] = table['nearest_node_offset_m'] > 50
        table['finite_route_in_saved_graph'] = np.isfinite(network_nearest)
        table['zero_network_path_review'] = network_nearest == 0
        table.to_csv(args.output / f'network-times-to-{destination_label}s.csv', index=False, encoding='utf-8-sig')
        matrix.to_csv(args.output / 'network-only-od-matrix.csv', encoding='utf-8-sig')
        schools.drop(columns='geometry').to_csv(args.output / f'{destination_label}-source-rows.csv', index_label='matrix_column_id', encoding='utf-8-sig')
        finite = network_nearest[np.isfinite(network_nearest)]
        report.update(status='computed', origins=len(origins), destination_geometries=len(schools),
                      destinations_offset_gt_50m=int((schools['destination_node_offset_m'] > 50).sum()),
                      destination_offset_max_m=float(schools['destination_node_offset_m'].max()),
                      parallel_directed_pairs=parallel_pairs,
                      original_edges=original_edges, routing_edges=graph.number_of_edges(),
                      parallel_edge_policy='OSMnx convert.to_digraph minimum time_min before IduEdu',
                      finite_network_routes=int(np.isfinite(network_nearest).sum()),
                      zero_network_routes=int((network_nearest == 0).sum()),
                      source_graph_strong_components=len(components),
                      nodes_pruned_by_library=len(graph)-components[0],
                      tf_default_adds_straight_line_attachments=True,
                      network_matrix_add_dist_tofrom_node=False,
                      attachment_comparison_median_minutes=float((nearest-network_nearest).median()),
                      origin_offset_review_gt_50m=int(table['origin_offset_review_gt_50m'].sum()),
                      network_time_quantiles_minutes={str(k): float(v) for k, v in finite.quantile([0,.5,.9,.95,1]).items()},
                      walk_kmh=graph.graph['walk_speed'] * 60 / 1000,
                      versions={name: importlib.metadata.version(name) for name in ['transport_frames','iduedu','osmnx']},
                      limitations=['Network dated by its metadata to 2026-05-31, not refreshed.',
                          'Reported coordinates are unverified destinations; school assignment/programme participation and enrolment eligibility are not inferred.',
                          'Network-only column excludes attachments. TF-default column adds straight-line proxy attachments at 5 km/h only for positive paths; neither verifies entrances.',
                          'IduEdu prunes to largest strongly connected component and quantizes edge costs to 0.01 minutes; pruning/zero paths require review.',
                          'Uniform walking speed is a technical scenario, not evidence about children by age.',
                          'Finite route does not establish safe access or completeness of the walking graph.'])
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__ + ': ' + str(exc), traceback=traceback.format_exc())
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ['sources','traceback']}, ensure_ascii=True))
    return 0 if report['status'] == 'computed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
