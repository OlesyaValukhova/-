"""Audit candidate point offsets to a saved network; no routes or venue claims."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidates', type=Path, required=True)
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--area', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    rows = pd.read_csv(a.candidates, encoding='utf-8-sig')
    rows = rows.loc[rows.spatial_class == 'outside_within_buffer'].copy()
    if rows.empty or rows.program_id.duplicated().any():
        raise ValueError('Outside candidates missing or duplicated')
    points = gpd.GeoDataFrame(rows, geometry=gpd.points_from_xy(rows.catalog_longitude, rows.catalog_latitude), crs=4326)
    graph = ox.load_graphml(a.graph, graph_dtypes={'crs': int})
    graph = ox.convert.to_digraph(graph, weight='time_min')
    nodes = ox.graph_to_gdfs(nx.MultiDiGraph(graph), edges=False)
    points = points.to_crs(graph.graph['crs'])
    nearest = gpd.sjoin_nearest(points[['geometry']], nodes[['geometry']], how='left', distance_col='node_offset_m')
    points['node_offset_m'] = nearest.groupby(level=0).node_offset_m.min()
    area = gpd.read_file(a.area)
    if area.empty or area.crs is None or not area.geometry.is_valid.all():
        raise ValueError('Acquisition area needs valid CRS and geometry')
    area_geometry = area.to_crs(graph.graph['crs']).union_all()
    points['inside_network_acquisition_area'] = points.geometry.map(area_geometry.covers)
    points['area_edge_clearance_m'] = points.geometry.distance(area_geometry.boundary).where(
        points.inside_network_acquisition_area, other=float('nan'))
    points['within_50m_node_and_area'] = (points.node_offset_m <= 50) & points.inside_network_acquisition_area
    a.output.mkdir(parents=True)
    points.to_crs(4326).to_file(a.output / 'outside-candidates-with-offsets.geojson', driver='GeoJSON')
    points.drop(columns='geometry').to_csv(a.output / 'outside-candidates-with-offsets.csv', encoding='utf-8-sig', index=False)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'candidate_programs': len(points),
              'inside_acquisition_area': int(points.inside_network_acquisition_area.sum()),
              'node_offset_le_50m_inside_area': int(points.within_50m_node_and_area.sum()),
              'outside_acquisition_area': int((~points.inside_network_acquisition_area).sum()),
              'inside_with_clearance_lt_500m': int(((points.area_edge_clearance_m < 500) & points.inside_network_acquisition_area).sum()),
              'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [a.candidates, a.graph, a.area]},
              'limitations': ['Node proximity and area containment do not establish a safe or actual access path.',
                  'Network clipping may still affect routes; a short snap does not establish completeness.',
                  'Candidates are programme records, not unique locations, valid groups or verified venues.',
                  'Candidate list excludes records without coordinates and title matches outside 3 km from the boundary.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['candidate_programs', 'inside_acquisition_area',
                                             'node_offset_le_50m_inside_area', 'outside_acquisition_area']}))


if __name__ == '__main__':
    main()
