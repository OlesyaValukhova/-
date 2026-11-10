"""Audit fields in saved Navigator cards without inferring unreported venues or eligibility.

The script works entirely offline on a frozen directory of ``*-detail.json`` files.
It describes field availability and raw value distributions; it does not establish
that a programme is current, has vacancies, or is held at the card coordinate.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from collect_program_details import validate_card
from export_navigator_details import age_state, coordinate_state
from nir2_demo import group_date_state


def label(value):
    """Return a stable display label from Navigator's object-or-string fields."""
    if isinstance(value, dict):
        return value.get('display_name') or value.get('name') or json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value in (None, ''):
        return '(missing)'
    return str(value)


def group_age_state(group):
    if group.get('is_age_limit') is not True:
        return 'not_displayed_as_age_limited'
    return age_state(group)


def increment(counter, prefix, value):
    counter[f'{prefix}:{label(value)}'] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--details', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path,
                        help='New directory for summary.json and program-field-state.csv')
    parser.add_argument('--as-of', required=True, help='Snapshot date YYYY-MM-DD used only for group date state')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be a new directory')
    try:
        snapshot_date = datetime.strptime(args.as_of, '%Y-%m-%d').date()
    except ValueError as exc:
        parser.error(f'Invalid --as-of date: {exc}')
    if not args.details.is_dir():
        parser.error('Details directory does not exist')

    files = sorted(args.details.glob('*-detail.json'))
    if not files:
        parser.error('No saved detail cards found')
    counts, raw_values = Counter(), Counter()
    rows, source_hashes = [], []
    samples = {name: [] for name in (
        'missing_program_age', 'invalid_or_missing_coordinate', 'missing_program_address',
        'missing_directivity', 'missing_study_area', 'missing_payment', 'missing_cost',
    )}

    for path in files:
        expected_id = int(path.name.split('-', 1)[0])
        raw = path.read_bytes()
        card = validate_card(raw, expected_id)
        groups = card.get('groups')
        if groups is None:
            groups = []
        if not isinstance(groups, list) or any(not isinstance(group, dict) for group in groups):
            raise ValueError(f'Unexpected embedded group schema for {expected_id}')

        program_age = age_state(card)
        coordinates = coordinate_state(card)
        address_present = bool(str(card.get('address') or '').strip())
        directivity_present = isinstance(card.get('directivity'), dict)
        study_areas = card.get('study_areas')
        study_area_present = isinstance(study_areas, list) and bool(study_areas)
        payment_present = card.get('payment') is not None
        cost_present = bool(str(card.get('cost') or '').strip())
        sha256 = hashlib.sha256(raw).hexdigest()

        counts['cards'] += 1
        counts[f'program_age:{program_age}'] += 1
        counts[f'coordinate:{coordinates}'] += 1
        counts[f'program_address:{"nonempty" if address_present else "missing"}'] += 1
        counts[f'directivity:{"present" if directivity_present else "missing"}'] += 1
        counts[f'study_areas:{"present" if study_area_present else "missing"}'] += 1
        counts[f'payment:{"present" if payment_present else "missing"}'] += 1
        counts[f'cost:{"nonempty" if cost_present else "missing_or_empty"}'] += 1
        counts[f'groups:{"nonempty" if groups else "none"}'] += 1
        increment(raw_values, 'payment_value', card.get('payment'))
        increment(raw_values, 'activity_status', card.get('activity_status'))
        increment(raw_values, 'directivity_value', card.get('directivity'))
        for area in study_areas if isinstance(study_areas, list) else []:
            increment(raw_values, 'study_area_value', area)

        state_flags = {
            'program_age_state': program_age,
            'coordinate_state': coordinates,
            'program_address_state': 'nonempty' if address_present else 'missing',
            'directivity_state': 'present' if directivity_present else 'missing',
            'study_areas_state': 'present' if study_area_present else 'missing',
            'payment_state': 'present' if payment_present else 'missing',
            'cost_state': 'nonempty' if cost_present else 'missing_or_empty',
        }
        rows.append({
            'program_id': card['id'], 'program_name': card.get('name'), 'district': card.get('district'),
            'program_address_raw': card.get('address'), 'latitude_raw': card.get('latitude'),
            'longitude_raw': card.get('longitude'),
            'payment_raw': card.get('payment'), 'cost_raw': card.get('cost'),
            'group_count': len(groups), 'source_sha256': sha256, **state_flags,
        })
        for sample_name, condition in (
            ('missing_program_age', program_age != 'known_interval'),
            ('invalid_or_missing_coordinate', coordinates != 'valid_numeric_not_venue_verified'),
            ('missing_program_address', not address_present),
            ('missing_directivity', not directivity_present),
            ('missing_study_area', not study_area_present),
            ('missing_payment', not payment_present),
            ('missing_cost', not cost_present),
        ):
            if condition and len(samples[sample_name]) < 20:
                samples[sample_name].append(card['id'])

        for group in groups:
            counts['groups'] += 1
            counts[f'group_age:{group_age_state(group)}'] += 1
            try:
                date_state = group_date_state(group, snapshot_date)
            except (TypeError, ValueError):
                date_state = 'invalid_lesson_dates'
            counts[f'group_lesson_date:{date_state}'] += 1
            increment(raw_values, 'group_status', group.get('status'))

        source_hashes.append({'file': str(path), 'sha256': sha256})

    args.output.mkdir(parents=True)
    fields = list(rows[0])
    with (args.output / 'program-field-state.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    selection = args.details / 'selection.json'
    collector_manifest = args.details / 'manifest.json'
    report = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'as_of': args.as_of,
        'source_directory': str(args.details),
        'saved_card_files': len(files),
        'counts': dict(sorted(counts.items())),
        'raw_value_counts': dict(sorted(raw_values.items())),
        'examples_up_to_20_ids': samples,
        'selection_manifest': json.loads(selection.read_text(encoding='utf-8')) if selection.exists() else None,
        'collector_manifest_at_audit': json.loads(collector_manifest.read_text(encoding='utf-8')) if collector_manifest.exists() else None,
        'sources': source_hashes,
        'interpretation_limits': [
            'The audit covers only card files present when it was run; a live collector may still be incomplete.',
            'A numeric coordinate is the programme card coordinate, not a verified group venue or entrance.',
            'A nonempty date interval does not prove a lesson occurred or enrolment was open.',
            'payment and cost are raw public fields, not a validated price or affordability measure.',
            'No capacity, demand, actual travel, escorting, safety, or independent mobility is inferred.',
        ],
    }
    (args.output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'saved_card_files': len(files), 'counts': report['counts']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
