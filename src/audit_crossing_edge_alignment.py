"""Compare tagged crossing coordinates with walking edge geometry, not safety."""
import argparse
import json
from pathlib import Path
import networkx as nx
import numpy as np
from pyproj import Transformer
from shapely import from_wkt
from shapely.geometry import Point
from shapely.strtree import STRtree


def main():
    p = argparse.ArgumentParser()
    p.add_argument('osm', type=Path)
    p.add_argument('graph', type=Path)
    p.add_argument('--bbox', nargs=4, type=float, required=True, metavar=('S', 'W', 'N', 'E'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raw = json.loads(a.osm.read_text(encoding='utf8'))
    s, w, n, e = a.bbox
    crossings = [x for x in raw['elements'] if x['type'] == 'node' and
                 x.get('tags', {}).get('highway') == 'crossing' and
                 s <= x['lat'] <= n and w <= x['lon'] <= e]
    graph = nx.read_graphml(a.graph)
    edges = [from_wkt(d['geometry']) for *_, d in graph.edges(data=True) if 'geometry' in d]
    tree = STRtree(edges)
    transformer = Transformer.from_crs(4326, 32636, always_xy=True)
    xx, yy = transformer.transform([x['lon'] for x in crossings], [x['lat'] for x in crossings])
    points = [Point(x, y) for x, y in zip(xx, yy)]
    distances = np.array([point.distance(edges[int(tree.nearest(point))]) for point in points])
    output = {'osm_source': str(a.osm), 'graph_source': str(a.graph), 'bbox_s_w_n_e': a.bbox,
              'crossings_in_bbox': len(points), 'directed_edges_with_geometry': len(edges),
              'nearest_edge_distance_m': {'median': float(np.median(distances)),
                                          'p90': float(np.quantile(distances, .9)),
                                          'max': float(np.max(distances))},
              'within_m': {str(t): int(np.sum(distances <= t)) for t in (0.1, 1, 5, 10, 20, 50)},
              'limitations': ['Only crossing nodes in a limited OSM extract and bounding box.',
                              'A close geometry is not proof the crossing lies on that route or crosses that road.',
                              'Overlapping, opposing and grade-separated edges may be equally close.',
                              'No observation of actual safety or network completeness.']}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
