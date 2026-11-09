"""Offline integration check on an explicitly synthetic three-node network.

Tests installed library calls/units, not accessibility or independent mobility in SPb.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', choices=['blocksnet', 'transport_frames'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'library': args.library, 'python': sys.version, 'input_kind': 'synthetic_integration_check',
              'checked_utc': datetime.now(timezone.utc).isoformat(), 'status': 'failed',
              'real_territory_accessibility_computed': False}
    try:
        import geopandas as gpd
        import networkx as nx
        import numpy as np
        from shapely.geometry import Point, LineString
        report['versions'] = {name: importlib.metadata.version(name)
                              for name in [args.library, 'iduedu', 'pandera', 'geopandas', 'numpy', 'networkx']}
        graph = nx.MultiDiGraph(crs=3857)
        for node, x in enumerate([0., 100., 200.]):
            graph.add_node(node, x=x, y=0., geometry=Point(x, 0.))
        for u, v, minutes in [(0, 1, 2.), (1, 0, 2.), (1, 2, 3.), (2, 1, 3.)]:
            graph.add_edge(u, v, time_min=minutes, length_meter=100.,
                           geometry=LineString([(u*100., 0.), (v*100., 0.)]))
        points = gpd.GeoDataFrame(geometry=[Point(x, 0.) for x in [0., 100., 200.]], crs=3857)
        if args.library == 'blocksnet':
            from blocksnet.relations.accessibility import calculate_accessibility_matrix
            from blocksnet.analysis.network.accessibility.basic import accessibility
            matrix = calculate_accessibility_matrix(points, graph)
            expected = np.array([[0., 2., 5.], [2., 0., 3.], [5., 3., 0.]])
            np.testing.assert_allclose(matrix.values, expected)
            opportunities = accessibility(matrix.iloc[:2, 2:],
                agg_func=lambda values, axis: (values <= 3).sum(axis=axis), accessibility_column='count')
            np.testing.assert_array_equal(opportunities['count'].values, [0, 1])
            report.update(matrix_minutes=matrix.values.tolist(), opportunities_within_3_minutes=[0, 1])
        else:
            from transport_frames.indicators import calculate_distances
            nearest = calculate_distances(points.iloc[:2].copy(), points.iloc[2:].copy(), graph,
                                          weight='time_min', unit_div=1)
            np.testing.assert_allclose(nearest.values, [5., 3.])
            report['nearest_minutes'] = nearest.values.tolist()
        report['status'] = 'passed'
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
