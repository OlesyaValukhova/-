"""Measure coordinate alignment of explicitly tagged OSM crossings and walking nodes."""
import argparse
import json
from pathlib import Path
import networkx as nx
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree


def main():
    p = argparse.ArgumentParser()
    p.add_argument('osm', type=Path)
    p.add_argument('graph', type=Path)
    p.add_argument('--bbox', nargs=4, type=float, required=True, metavar=('S', 'W', 'N', 'E'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raw = json.loads(a.osm.read_text(encoding='utf8'))
    s, w, n, e = a.bbox
    points = [x for x in raw['elements'] if x['type'] == 'node' and
              x.get('tags', {}).get('highway') == 'crossing' and
              s <= x['lat'] <= n and w <= x['lon'] <= e]
    g = nx.read_graphml(a.graph)
    xy = np.array([(float(x['x']), float(x['y'])) for _, x in g.nodes(data=True)])
    project = Transformer.from_crs(4326, 32636, always_xy=True)
    xx, yy = project.transform([x['lon'] for x in points], [x['lat'] for x in points])
    distances, indices = cKDTree(xy).query(np.column_stack((xx, yy)))
    result = {'osm_source': str(a.osm), 'graph_source': str(a.graph), 'bbox_s_w_n_e': a.bbox,
              'crossings_in_bbox': len(points), 'graph_nodes': len(xy),
              'nearest_node_distance_m': {'median': float(np.median(distances)),
                                           'p90': float(np.quantile(distances, .9)),
                                           'max': float(np.max(distances))},
              'within_m': {str(t): int(np.sum(distances <= t)) for t in (0.1, 1, 5, 10, 20, 50)},
              'distinct_graph_nodes_within_1m': len(set(indices[distances <= 1].tolist())),
              'limitations': ['Only crossing nodes present in the source extract, within its requested bounding box.',
                              'Coordinate proximity is not proof of shared topology or a crossing along a route.',
                              'Graph node identifiers are regenerated; original OSM node IDs are unavailable.',
                              'No inference about safety, tag completeness, or real-world validation.']}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
