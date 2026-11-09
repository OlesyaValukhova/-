"""Identify district hints in saved cards for chess programmes missing catalogue coordinates."""
import argparse
import csv
import json
import re
from pathlib import Path

DISTRICT = re.compile(r'василеостров', re.I)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--candidates', type=Path, required=True)
    p.add_argument('--details', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    with a.candidates.open(encoding='utf-8-sig', newline='') as f:
        selected = [r for r in csv.DictReader(f) if r['spatial_class'] == 'unclassified_missing_or_invalid_coordinate']
    rows = []
    for r in selected:
        path = a.details/f"{r['program_id']}-detail.json"
        if not path.exists():
            continue
        card = json.loads(path.read_text(encoding='utf8'))
        org = card.get('organization') or {}
        address_list = org.get('addresses') or []
        values = {'catalogue_organization': r.get('organization', ''), 'program_district': card.get('district') or '',
                  'program_address': card.get('address') or '', 'organization_name': org.get('name') or '',
                  'organization_addresses': ' | '.join(str(v.get('address') or '') for v in address_list),
                  'organization_districts': ' | '.join(str(v.get('district') or '') for v in address_list)}
        hints = [k for k, v in values.items() if DISTRICT.search(str(v))]
        if hints:
            rows.append({'program_id': r['program_id'], 'program_name': r['name'], 'hint_fields': '|'.join(hints),
                         **values, 'program_latitude': card.get('latitude'), 'program_longitude': card.get('longitude'),
                         'detail_file': str(path)})
    a.output.mkdir(parents=True, exist_ok=True)
    fields = ['program_id', 'program_name', 'hint_fields', 'catalogue_organization', 'program_district',
              'program_address', 'organization_name', 'organization_addresses', 'organization_districts',
              'program_latitude', 'program_longitude', 'detail_file']
    with (a.output/'candidates.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    summary = {'missing_catalogue_coordinate_chess_records': len(selected),
               'available_detail_cards': sum((a.details/f"{r['program_id']}-detail.json").exists() for r in selected),
               'records_with_textual_district_hint': len(rows),
               'limitations': ['District text hint is not verified teaching location.',
                               'Missing detail cards and unrecognised address formats can hide candidates.',
                               'Catalogue and details are collected at different times.']}
    (a.output/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
