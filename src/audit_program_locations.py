"""Compare reported programme and organisation addresses; never geocode or assert venues."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from collect_program_details import validate_card
from export_navigator_details import coordinate_state


def normalized(value):
    return ' '.join((value or '').casefold().split())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--details', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    files = sorted(a.details.glob('*-detail.json'))
    rows, group_fields = [], Counter()
    for path in files:
        raw = path.read_bytes()
        card = validate_card(raw, int(path.name.split('-')[0]))
        org = card.get('organization') or {}
        addresses = org.get('addresses') if isinstance(org, dict) else None
        addresses = addresses if isinstance(addresses, list) else []
        addresses = [v for v in addresses if isinstance(v, dict)]
        program_address = card.get('address') or ''
        matches = [v for v in addresses if normalized(program_address)
                   and normalized(program_address) == normalized(v.get('address'))]
        groups = card.get('groups') or []
        for group in groups:
            if isinstance(group, dict):
                group_fields.update(group.keys())
        comparable = [v for v in addresses if coordinate_state(v) == 'valid_numeric_not_venue_verified']
        valid_program_coords = coordinate_state(card) == 'valid_numeric_not_venue_verified'
        coord_matches = [v for v in comparable if valid_program_coords
                         and abs(float(v['latitude']) - float(card['latitude'])) < 1e-6
                         and abs(float(v['longitude']) - float(card['longitude'])) < 1e-6]
        rows.append({'program_id': card['id'], 'organization_id': org.get('id') if isinstance(org, dict) else None,
            'program_address': program_address, 'latitude': card.get('latitude'), 'longitude': card.get('longitude'),
            'organization_addresses_count': len(addresses), 'exact_text_matching_org_addresses': len(matches),
            'matching_address_types': json.dumps([v.get('address_type') for v in matches], ensure_ascii=False),
            'org_addresses_with_coordinates': len(comparable), 'org_coordinate_matches': len(coord_matches),
            'group_count_loaded': len(groups), 'source_sha256': hashlib.sha256(raw).hexdigest()})
    a.output.mkdir(parents=True)
    with (a.output / 'address-comparison.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['program_id'])
        writer.writeheader()
        writer.writerows(rows)
    counts = {'cards': len(rows), 'nonempty_program_address': sum(bool(r['program_address']) for r in rows),
              'with_org_addresses': sum(r['organization_addresses_count'] > 0 for r in rows),
              'program_address_matches_org_text': sum(r['exact_text_matching_org_addresses'] > 0 for r in rows),
              'program_address_differs_from_all_org_text': sum(bool(r['program_address']) and r['organization_addresses_count'] > 0 and not r['exact_text_matching_org_addresses'] for r in rows),
              'org_coordinate_comparable': sum(r['org_addresses_with_coordinates'] > 0 and r['latitude'] not in (None, '') and r['longitude'] not in (None, '') for r in rows),
              'coordinate_matches_org': sum(r['org_coordinate_matches'] > 0 for r in rows),
              'embedded_groups': sum(r['group_count_loaded'] for r in rows)}
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'source_directory': str(a.details),
              'counts': counts, 'group_field_presence': dict(group_fields),
              'limitations': ['Partial, nonrandom snapshot; counts concern program records, not unique organisations.',
                  'Exact normalized-text comparison misses equivalent differently written addresses; differences do not establish a different place.',
                  'Coordinate equality is not independent verification of address or entrance.',
                  'Fields absent from embedded groups may be available elsewhere; do not infer that no location information exists.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(counts, ensure_ascii=True))


if __name__ == '__main__':
    main()
