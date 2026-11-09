"""Compare frozen catalogue coordinates with saved programme-card coordinates."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import geopandas as gpd
from pyproj import Geod
from shapely.geometry import Point

from collect_program_details import validate_card
from export_navigator_details import coordinate_state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--links', type=Path, required=True)
    p.add_argument('--boundary', type=Path, required=True)
    p.add_argument('--details', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    with a.links.open(encoding='utf-8-sig', newline='') as f:
        links = list(csv.DictReader(f))
    if len({r['program_id'] for r in links}) != len(links):
        raise ValueError('Programme IDs must be unique')
    boundary = gpd.read_file(a.boundary)
    if boundary.crs is None or boundary.empty or not boundary.geometry.is_valid.all():
        raise ValueError('Boundary needs review')
    polygon = boundary.to_crs(4326).union_all()
    geod, counts, rows = Geod(ellps='WGS84'), Counter(), []
    for r in links:
        path = a.details / f"{r['program_id']}-detail.json"
        if not path.is_file():
            counts['card_not_available'] += 1
            continue
        raw = path.read_bytes()
        card = validate_card(raw, int(r['program_id']))
        catalog_state, card_state = coordinate_state(r), coordinate_state(card)
        row = {'program_id': r['program_id'], 'catalog_location_id': r['location_id'],
               'catalog_latitude': r['latitude'], 'catalog_longitude': r['longitude'],
               'card_latitude': card.get('latitude'), 'card_longitude': card.get('longitude'),
               'card_coordinate_state': card_state, 'distance_m': '', 'card_inside_boundary': '',
               'card_source_sha256': hashlib.sha256(raw).hexdigest()}
        counts['cards_compared'] += 1
        if catalog_state != 'valid_numeric_not_venue_verified':
            raise ValueError('Coordinate-selected catalogue must have valid numerical coordinates')
        if card_state != 'valid_numeric_not_venue_verified':
            counts['card_coords_missing_or_invalid'] += 1
        else:
            lat, lon = float(card['latitude']), float(card['longitude'])
            _, _, distance = geod.inv(float(r['longitude']), float(r['latitude']), lon, lat)
            row['distance_m'] = round(distance, 3)
            row['card_inside_boundary'] = polygon.covers(Point(lon, lat))
            counts['same_numeric_pair' if lat == float(r['latitude']) and lon == float(r['longitude']) else 'different_numeric_pair'] += 1
            counts['distance_gt_1m'] += distance > 1
            counts['distance_gt_50m'] += distance > 50
            counts['card_outside_boundary'] += not row['card_inside_boundary']
        rows.append(row)
    a.output.mkdir(parents=True)
    with (a.output / 'coordinate-comparison.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['program_id'])
        w.writeheader()
        w.writerows(rows)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'counts': dict(counts),
              'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [a.links, a.boundary]},
              'details_directory': str(a.details),
              'limitations': ['Catalogue and card were saved at different times; differences need investigation, not automatic correction.',
                  'The selection includes only programmes whose catalogue coordinates were inside the district.',
                  'Identical coordinates do not confirm that a group meets at that point.',
                  'A partial nonrandom download cannot establish results for all programmes.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['counts']))


if __name__ == '__main__':
    main()
