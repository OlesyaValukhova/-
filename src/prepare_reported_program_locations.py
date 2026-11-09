"""Prepare catalogue-reported coordinate candidates, never infer verified venues.

Missing coordinates are geographically unclassified, not outside the study area.
An incomplete card collection does not imply absence of age-appropriate supply.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from collect_program_details import validate_card
from export_navigator_details import coordinate_state, age_state, write_table
from parse_navigator import aggregate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue', type=Path, required=True)
    parser.add_argument('--districts', type=Path, required=True)
    parser.add_argument('--details', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be new')
    raw = args.catalogue.read_bytes()
    rows, coverage = aggregate(json.loads(raw)['pages'])
    if any(w != 'API count changed during collection' for w in coverage['warnings']):
        raise ValueError('Inspect catalogue duplicates/chain before spatial selection')
    districts = gpd.read_file(args.districts)
    if districts.crs is None:
        raise ValueError('District CRS missing')
    selected = districts.loc[districts['Наименование'] == 'Василеостровский район'].to_crs(4326)
    if selected.empty or not selected.geometry.is_valid.all():
        raise ValueError('District boundary needs review')
    boundary = selected.union_all()
    mapping, locations, detail_sources = [], {}, []
    states = Counter()
    for row in rows:
        quality = coordinate_state(row)
        if quality != 'valid_numeric_not_venue_verified':
            states[quality] += 1
            continue
        latitude, longitude = float(row['latitude']), float(row['longitude'])
        point = Point(longitude, latitude)
        if not boundary.covers(point):
            states['reported_coordinate_outside_boundary'] += 1
            continue
        states['reported_coordinate_inside_boundary'] += 1
        token = f'{latitude:.17g},{longitude:.17g}'
        location_id = 'coordinate-' + hashlib.sha256(token.encode()).hexdigest()[:16]
        if location_id in locations and locations[location_id]['coordinate_token'] != token:
            raise ValueError('Coordinate ID hash collision')
        locations.setdefault(location_id, {'location_id': location_id, 'coordinate_token': token,
            'latitude': latitude, 'longitude': longitude, 'program_count': 0,
            'venue_verified': False, 'geometry': point})['program_count'] += 1
        card_path = args.details / f"{row['id']}-detail.json" if args.details else None
        card = None
        if card_path and card_path.is_file():
            card_raw = card_path.read_bytes()
            card = validate_card(card_raw, row['id'])
            detail_sources.append({'program_id': row['id'], 'file': str(card_path),
                                   'sha256': hashlib.sha256(card_raw).hexdigest()})
        record = {'program_id': row['id'], 'name': row.get('name'),
            'organization_label': row.get('organization'), 'payment_label': row.get('payment'),
            'profiles_raw': row.get('profiles'), 'study_areas_raw': row.get('study_areas'),
            'location_id': location_id, 'latitude': latitude, 'longitude': longitude,
            'detail_available': card is not None,
            'min_age': card.get('min_age') if card else None,
            'max_age': card.get('max_age') if card else None,
            'card_age_state': age_state(card) if card else 'card_not_yet_available',
            'card_address': card.get('address') if card else None,
            'detail_source_file': str(card_path) if card else None}
        mapping.append(record)
    args.output.mkdir(parents=True)
    selected.to_file(args.output / 'study-boundary.geojson', driver='GeoJSON')
    if locations:
        gpd.GeoDataFrame(list(locations.values()), crs=4326).to_file(args.output / 'reported-locations.geojson', driver='GeoJSON')
    fields = ['program_id','name','organization_label','payment_label','profiles_raw','study_areas_raw',
              'location_id','latitude','longitude','detail_available','min_age','max_age','card_age_state',
              'card_address','detail_source_file']
    write_table(args.output / 'program-location-links.csv', mapping, fields)
    report = {'prepared_utc': datetime.now(timezone.utc).isoformat(),
        'catalogue_file': str(args.catalogue), 'catalogue_sha256': hashlib.sha256(raw).hexdigest(),
        'catalogue_coverage': coverage, 'boundary_file': str(args.districts),
        'boundary_sha256': hashlib.sha256(args.districts.read_bytes()).hexdigest(),
        'selected_boundary_name': 'Василеостровский район', 'selected_boundary_features': len(selected),
        'source_programs': len(rows), 'coordinate_classification': dict(states),
        'programs_with_reported_coordinate_inside': len(mapping), 'reported_coordinate_locations': len(locations),
        'card_age_states': dict(Counter(r['card_age_state'] for r in mapping)), 'detail_sources': detail_sources,
        'age_accessibility_computed': False, 'venue_verified': False,
        'limitations': ['Scope is reported coordinates inside boundary, not all real programmes offered there.',
            'Missing coordinates remain geographically unclassified; no absence inferred.',
            'Coordinate pairs are deduplicated exactly, not rounded or geocoded; one pair is not one organisation or capacity.',
            'Available cards are a partial, nonrandom collection. No age counts interpreted as complete supply.',
            'Boundary source date and catalogue coordinate-to-venue correspondence are not independently verified.']}
    (args.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['source_programs','coordinate_classification',
        'programs_with_reported_coordinate_inside','reported_coordinate_locations','card_age_states']}))


if __name__ == '__main__':
    main()
