"""Export raw chess programme/group evidence for spatial pilot review."""
import argparse
from collections import Counter
import csv
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from audit_program_group_ages import date_state, eligibility, group_eligibility
from collect_program_details import validate_card


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--outside-ids', type=Path, required=True)
    p.add_argument('--inside-cards', type=Path, required=True)
    p.add_argument('--outside-cards', type=Path, required=True)
    p.add_argument('--catalogue-candidates', type=Path, required=True)
    p.add_argument('--as-of', type=date.fromisoformat, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    inside = json.loads(a.selection.read_text(encoding='utf-8'))['categories']['Шахматы']
    outside = json.loads(a.outside_ids.read_text(encoding='utf-8'))
    with a.catalogue_candidates.open(encoding='utf-8-sig', newline='') as f:
        catalog_rows = list(csv.DictReader(f))
    if len({int(r['program_id']) for r in catalog_rows}) != len(catalog_rows):
        raise ValueError('Catalogue candidate IDs must be unique')
    catalog = {int(r['program_id']): r for r in catalog_rows}
    if len(set(inside)) != len(inside) or len(set(outside)) != len(outside) or set(inside) & set(outside):
        raise ValueError('Input IDs must be unique and groups disjoint')
    if not (set(inside) | set(outside)).issubset(catalog):
        raise ValueError('Selected programme missing from catalogue candidate file')
    programs, groups, totals = [], [], Counter()
    for kind, ids, folder in [('inside', inside, a.inside_cards), ('outside', outside, a.outside_cards)]:
        for program_id in ids:
            file = folder / f'{program_id}-detail.json'
            raw = file.read_bytes()
            card = validate_card(raw, program_id)
            source_hash = hashlib.sha256(raw).hexdigest()
            embedded = card.get('groups')
            if embedded is not None and (not isinstance(embedded, list) or any(not isinstance(g, dict) for g in embedded)):
                raise ValueError(f'Unexpected groups in {program_id}')
            embedded = embedded or []
            organization = card.get('organization') or {}
            declared = card.get('group_count')
            row = {'program_id': program_id, 'scope': kind, 'program_name': card.get('name'),
                   'organization': organization.get('name') if isinstance(organization, dict) else organization,
                   'program_address': card.get('address'), 'latitude': card.get('latitude'), 'longitude': card.get('longitude'),
                   'program_min_age': card.get('min_age'), 'program_max_age': card.get('max_age'),
                   'program_matches_age_7': str(eligibility(7, card)), 'program_matches_age_13': str(eligibility(13, card)),
                   'payment_code': card.get('payment'), 'payment_label_from_catalogue': catalog[program_id]['payment'],
                   'cost_raw': card.get('cost'), 'study_form_raw': card.get('study_form'),
                   'declared_group_count': declared, 'embedded_groups': len(embedded),
                   'declared_matches_embedded': declared == len(embedded),
                   'navigator_page': f'https://dopobr.petersburgedu.ru/programs/{program_id}/groups/',
                   'card_file': str(file), 'card_sha256': source_hash}
            programs.append(row)
            totals['cards'] += 1
            totals[f'cards_{kind}'] += 1
            totals['cards_without_embedded_groups'] += not embedded
            totals['group_count_mismatch'] += declared != len(embedded)
            for group in embedded:
                status = group.get('status')
                status_id = status.get('id') if isinstance(status, dict) else status
                status_label = status.get('display_name') if isinstance(status, dict) else None
                group_row = {'program_id': program_id, 'scope': kind, 'group_id': group.get('id'),
                    'group_name': group.get('name'), 'min_age': group.get('min_age'), 'max_age': group.get('max_age'),
                    'is_age_limit': group.get('is_age_limit'),
                    'displayed_interval_matches_7': str(group_eligibility(7, group)),
                    'displayed_interval_matches_13': str(group_eligibility(13, group)),
                    'lesson_start': group.get('lesson_start'), 'lesson_end': group.get('lesson_end'),
                    'lesson_date_state': date_state(group, a.as_of), 'status_id_raw': status_id,
                    'status_label_raw': status_label, 'access_to_creating_request_raw': group.get('access_to_creating_request'),
                    'members_limit_raw': group.get('members_limit'), 'card_sha256': source_hash}
                groups.append(group_row)
                totals['groups'] += 1
                totals['date_' + group_row['lesson_date_state']] += 1
                totals['status_' + str(status_id)] += 1
    a.output.mkdir(parents=True)
    write_csv(a.output / 'programs.csv', programs, list(programs[0]))
    write_csv(a.output / 'groups.csv', groups, list(groups[0]) if groups else ['program_id'])
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'as_of': a.as_of.isoformat(),
              'selection_sha256': hashlib.sha256(a.selection.read_bytes()).hexdigest(),
              'outside_ids_sha256': hashlib.sha256(a.outside_ids.read_bytes()).hexdigest(),
              'catalogue_candidates_sha256': hashlib.sha256(a.catalogue_candidates.read_bytes()).hexdigest(),
              'counts': dict(totals),
              'limitations': ['Names and candidate locations are selected, not a census of chess programmes.',
                  'Raw group counts may omit groups not returned by the API; equal counts do not prove completeness.',
                  'Age interval and lesson dates are recorded attributes, not proof of actual activity or admission.',
                  'Displayed group age logic is inferred from a saved frontend; server admission rules remain unverified.',
                  'Programme address and coordinates are not independently verified as the place for every group.',
                  'Payment and participant limit fields are raw data, not verified current cost or free capacity.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(totals), ensure_ascii=False))


if __name__ == '__main__':
    main()
