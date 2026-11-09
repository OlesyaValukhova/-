"""Offline, loss-aware tabulation of saved public cards and embedded groups.

No venue inference, deduplication by address, capacity imputation, or GIS calculation.
"""
import argparse
from collections import Counter
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path

from collect_program_details import validate_card
from nir2_demo import age_eligible, group_date_state


def age_state(record):
    lower, upper = record.get('min_age'), record.get('max_age')
    try:
        age_eligible(0, lower, upper)
    except (ValueError, TypeError):
        return 'invalid'
    return 'missing_or_partial' if lower in (None, '') or upper in (None, '') else 'known_interval'


def coordinate_state(record):
    latitude, longitude = record.get('latitude'), record.get('longitude')
    if latitude in (None, '') or longitude in (None, ''):
        return 'missing_or_partial'
    try:
        lat, lon = float(latitude), float(longitude)
        valid = (not isinstance(latitude, bool) and not isinstance(longitude, bool)
                 and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180)
    except (ValueError, TypeError):
        valid = False
    return 'valid_numeric_not_venue_verified' if valid else 'invalid'


def write_table(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})


def export(source, output, as_of):
    programs, groups, sources = [], [], []
    program_fields = ['id', 'name', 'min_age', 'max_age', 'address', 'latitude', 'longitude',
                      'payment', 'cost', 'directivity', 'study_areas', 'profiles', 'activity_status']
    group_fields = ['id', 'name', 'min_age', 'max_age', 'is_age_limit', 'date_start', 'date_end',
                    'lesson_start', 'lesson_end', 'status', 'members_limit']
    for path in sorted(source.glob('*-detail.json')):
        raw = path.read_bytes()
        program_id = int(path.name.split('-')[0])
        card = validate_card(raw, program_id)
        organization = card.get('organization')
        embedded = card.get('groups')
        if embedded is not None and not isinstance(embedded, list):
            raise ValueError(f'Unrecognized groups schema for {program_id}')
        row = {key: card.get(key) for key in program_fields}
        row.update(organization_id=organization.get('id') if isinstance(organization, dict) else None,
                   organization_name=organization.get('name') if isinstance(organization, dict) else organization,
                   age_state=age_state(card), coordinate_state=coordinate_state(card),
                   group_count=len(embedded) if embedded is not None else None,
                   source_file=str(path), source_sha256=hashlib.sha256(raw).hexdigest())
        programs.append(row)
        sources.append({'file': str(path), 'sha256': row['source_sha256']})
        for group in embedded or []:
            if not isinstance(group, dict):
                raise ValueError(f'Non-object group in {program_id}')
            record = {key: group.get(key) for key in group_fields}
            try:
                date_state = group_date_state(group, as_of)
            except (ValueError, TypeError):
                date_state = 'invalid_lesson_dates'
            record.update(program_id=program_id, age_state=age_state(group),
                          lesson_date_state=date_state, source_file=str(path))
            groups.append(record)
    output.mkdir(parents=True, exist_ok=False)
    write_table(output / 'programs.csv', programs, program_fields + [
        'organization_id', 'organization_name', 'age_state', 'coordinate_state', 'group_count', 'source_file', 'source_sha256'])
    write_table(output / 'groups.csv', groups, group_fields + ['program_id', 'age_state', 'lesson_date_state', 'source_file'])
    report = {'as_of': as_of.isoformat(), 'programs': len(programs), 'group_rows': len(groups),
              'program_age_states': dict(Counter(r['age_state'] for r in programs)),
              'coordinate_states': dict(Counter(r['coordinate_state'] for r in programs)),
              'group_age_states': dict(Counter(r['age_state'] for r in groups)),
              'group_lesson_date_states': dict(Counter(r['lesson_date_state'] for r in groups)),
              'programs_with_nonempty_address': sum(bool((r['address'] or '').strip()) for r in programs),
              'selection_manifest': json.loads((source / 'selection.json').read_text(encoding='utf-8'))
              if (source / 'selection.json').exists() else None,
              'sources': sources, 'complete_city_export': False, 'venue_link_verified': False,
              'note': 'Rows describe saved cards only. Lesson interval coverage is not confirmed activity/enrolment. '
                      'members_limit is a raw field, not validated capacity; no use of free_places_count.'}
    (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if not args.input.is_dir():
        parser.error('Input directory does not exist')
    report = export(args.input, args.output, args.as_of)
    print(json.dumps({key: report[key] for key in ['programs', 'group_rows', 'program_age_states', 'group_lesson_date_states']}))


if __name__ == '__main__':
    main()
