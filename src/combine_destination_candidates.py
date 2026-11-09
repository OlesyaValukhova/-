"""Merge coordinate points while preserving programme-to-coordinate provenance."""
import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


def coordinate_id(point):
    token = f'{point.y:.17g},{point.x:.17g}'
    return 'coordinate-' + hashlib.sha256(token.encode()).hexdigest()[:16]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inside', type=Path, required=True)
    p.add_argument('--outside', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    inside, outside = gpd.read_file(a.inside), gpd.read_file(a.outside)
    if inside.crs is None or outside.crs is None:
        raise ValueError('Both inputs need CRS')
    inside, outside = inside.to_crs(4326), outside.to_crs(4326)
    if not inside.location_id.is_unique or outside.program_id.duplicated().any():
        raise ValueError('Coordinate IDs and external programme IDs must be unique')
    if any(g is None or g.geom_type != 'Point' or not g.is_valid for g in list(inside.geometry) + list(outside.geometry)):
        raise ValueError('Expected valid point geometries')
    for _, row in inside.iterrows():
        if coordinate_id(row.geometry) != row.location_id:
            raise ValueError('Original coordinate ID does not match original point')
    records = {row.location_id: row.geometry for _, row in inside.iterrows()}
    mapping = []
    for _, row in outside.iterrows():
        key = coordinate_id(row.geometry)
        if key in records and not records[key].equals_exact(row.geometry, 0):
            raise ValueError('Coordinate hash collision')
        records[key] = row.geometry
        mapping.append({'program_id': int(row.program_id), 'location_id': key,
                        'boundary_distance_m': row.boundary_distance_m})
    a.output.mkdir(parents=True)
    gpd.GeoDataFrame([{'location_id': key, 'geometry': value} for key, value in records.items()],
                     crs=4326).to_file(a.output / 'destinations.geojson', driver='GeoJSON')
    pd.DataFrame(mapping).to_csv(a.output / 'outside-program-links.csv', index=False, encoding='utf-8-sig')
    result = {'inside_coordinates': len(inside), 'outside_programs': len(outside),
              'combined_unique_coordinates': len(records),
              'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [a.inside, a.outside]},
              'note': 'Exact coordinate pairs are not verified venues; outside records do not establish current eligible groups.'}
    (a.output / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
