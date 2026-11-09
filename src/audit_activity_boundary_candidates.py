"""Inventory title-based activity candidates by location relative to a pilot boundary."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from collect_program_details import validate_card
from export_navigator_details import coordinate_state
from parse_navigator import aggregate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalogue', type=Path, required=True)
    p.add_argument('--boundary', type=Path, required=True)
    p.add_argument('--details', type=Path, nargs='*', default=[])
    p.add_argument('--term', default='шахмат')
    p.add_argument('--buffer-m', type=float, default=3000)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or not a.term or a.buffer_m <= 0:
        p.error('Use a new output, nonempty search term and positive buffer')
    raw = a.catalogue.read_bytes()
    catalog, coverage = aggregate(json.loads(raw)['pages'])
    boundary = gpd.read_file(a.boundary)
    if boundary.empty or boundary.crs is None or not boundary.geometry.is_valid.all():
        raise ValueError('Boundary needs review')
    boundary = boundary.to_crs(32636).union_all()
    rows, counts = [], Counter()
    for item in catalog:
        if a.term.casefold() not in (item.get('name') or '').casefold():
            continue
        counts['matching_titles'] += 1
        state = coordinate_state(item)
        result = {'program_id': item['id'], 'name': item.get('name'), 'organization': item.get('organization'),
                  'payment': item.get('payment'), 'catalog_latitude': item.get('latitude'),
                  'catalog_longitude': item.get('longitude'), 'coordinate_state': state,
                  'boundary_distance_m': '', 'spatial_class': 'unclassified_missing_or_invalid_coordinate',
                  'card_available': False, 'card_min_age': '', 'card_max_age': '',
                  'card_sha256': '', 'card_file': ''}
        if state == 'valid_numeric_not_venue_verified':
            point = gpd.GeoSeries([Point(float(item['longitude']), float(item['latitude']))], crs=4326).to_crs(32636).iloc[0]
            distance = point.distance(boundary)
            result['boundary_distance_m'] = round(distance, 2)
            result['spatial_class'] = ('inside_boundary' if boundary.covers(point) else
                                       'outside_within_buffer' if distance <= a.buffer_m else 'outside_buffer')
        for directory in a.details:
            file = directory / f"{item['id']}-detail.json"
            if file.is_file():
                card_raw = file.read_bytes()
                card = validate_card(card_raw, item['id'])
                result.update(card_available=True, card_min_age=card.get('min_age'), card_max_age=card.get('max_age'),
                              card_sha256=hashlib.sha256(card_raw).hexdigest(), card_file=str(file))
                break
        counts[result['spatial_class']] += 1
        rows.append(result)
    a.output.mkdir(parents=True)
    with (a.output / 'candidates.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = list(rows[0]) if rows else ['program_id']
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'term': a.term, 'buffer_m': a.buffer_m,
              'catalogue_sha256': hashlib.sha256(raw).hexdigest(), 'catalogue_coverage': coverage,
              'boundary_sha256': hashlib.sha256(a.boundary.read_bytes()).hexdigest(),
              'details_directories_in_priority_order': [str(v) for v in a.details], 'counts': dict(counts),
              'limitations': ['Title substring is an incomplete and unverified activity classifier.',
                  'Euclidean distance to boundary is not network travel time to a residence.',
                  'Programs with missing coordinates are unclassified geographically, not outside.',
                  'Card age and current enrolment may be unknown; coordinates are unverified group locations.',
                  'Programme duplicates, actual classes, access, costs and children are not inferred.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(counts), ensure_ascii=False))


if __name__ == '__main__':
    main()
