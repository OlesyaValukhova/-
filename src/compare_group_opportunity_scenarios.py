"""Compare programme-age and conservative group-record scenarios on an existing OD matrix.

Both are descriptive counts from saved Navigator records, not observed availability.
The group scenario is a subset of known programme-age matches, not a lower bound
on real offerings. Missing cards and locations remain excluded in both scenarios.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from audit_program_group_ages import eligibility, group_eligibility, date_state
from collect_program_details import validate_card


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix', type=Path, required=True)
    p.add_argument('--links', type=Path, required=True)
    p.add_argument('--details', type=Path, required=True)
    p.add_argument('--ids-file', type=Path, help='Optional JSON ID list to reproduce a previous card snapshot')
    p.add_argument('--include-study-areas', action='store_true', help='Also report original, potentially overlapping study-area labels')
    p.add_argument('--as-of', type=date.fromisoformat, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    links = pd.read_csv(a.links, encoding='utf-8-sig', keep_default_na=False)
    matrix = pd.read_csv(a.matrix, encoding='utf-8-sig', index_col=0)
    if (links['program_id'].duplicated().any() or not matrix.index.is_unique
            or not matrix.columns.is_unique or set(links.location_id) != set(matrix.columns)):
        raise ValueError('Programme IDs or matrix indices invalid or coordinates do not match')
    times = matrix.to_numpy(dtype=float)
    if not np.isfinite(times).all() or (times < 0).any():
        raise ValueError('Expected finite nonnegative OD times')
    loc_order = {value: i for i, value in enumerate(matrix.columns)}
    snapshot_ids = None
    if a.ids_file:
        snapshot_ids = json.loads(a.ids_file.read_text(encoding='utf-8-sig'))
        if (not isinstance(snapshot_ids, list) or len(set(snapshot_ids)) != len(snapshot_ids)
                or any(type(i) is not int for i in snapshot_ids)
                or not set(snapshot_ids).issubset(set(links.program_id))):
            raise ValueError('Snapshot IDs must be unique catalogue IDs')
        snapshot_ids = set(snapshot_ids)
    records, missing = [], 0
    for row in links.to_dict('records'):
        if snapshot_ids is not None and int(row['program_id']) not in snapshot_ids:
            missing += 1
            continue
        path = a.details / f"{row['program_id']}-detail.json"
        if not path.is_file():
            if snapshot_ids is not None:
                raise ValueError(f"Snapshot card {row['program_id']} is missing")
            missing += 1
            continue
        raw = path.read_bytes()
        card = validate_card(raw, int(row['program_id']))
        groups = card.get('groups') or []
        if not isinstance(groups, list) or any(not isinstance(g, dict) for g in groups):
            raise ValueError('Unrecognized embedded group schema')
        direction = card.get('directivity')
        if isinstance(direction, dict):
            direction = direction.get('display_name') or ''
        elif direction is None:
            direction = ''
        elif not isinstance(direction, str):
            raise ValueError('Unrecognized direction schema')
        areas = card.get('study_areas') or []
        if not isinstance(areas, list):
            raise ValueError('Unrecognized study-area schema')
        labels = []
        for area in areas:
            if not isinstance(area, dict) or not isinstance(area.get('display_name'), str):
                raise ValueError('Unrecognized study-area label')
            labels.append(area['display_name'])
        base = {'program_id': card['id'], 'location_id': row['location_id'],
                'payment_label_from_catalogue': row['payment_label'], 'payment_id_from_card': card.get('payment'),
                'direction_label': direction, 'study_area_labels': json.dumps(sorted(set(labels)), ensure_ascii=False),
                'card_source_sha256': hashlib.sha256(raw).hexdigest()}
        for age in [7, 10, 13, 16]:
            is_program = eligibility(age, card) is True
            matching_groups = sum(group_eligibility(age, g) is True
                                  and date_state(g, a.as_of) == 'date_interval_covers_snapshot'
                                  for g in groups)
            records.append({**base, 'age': age, 'program_age_match': is_program,
                            'groups_matching_intervals': matching_groups,
                            'program_and_group_match': is_program and matching_groups > 0})
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError('No saved programme cards')
    categories = [('all', 'all', None)]
    categories += [('direction', label, 'direction_label') for label in sorted(frame.direction_label.unique())]
    categories += [('payment', label, 'payment_label_from_catalogue') for label in sorted(frame.payment_label_from_catalogue.unique())]
    if a.include_study_areas:
        area_labels = sorted({label for value in frame.study_area_labels for label in json.loads(value)})
        categories += [('study_area', label, 'study_area_labels') for label in area_labels]
    summaries = []
    for age in [7, 10, 13, 16]:
        age_frame = frame.loc[frame.age == age]
        for category_kind, label, field in categories:
            if field is None:
                subset = age_frame
            elif field == 'study_area_labels':
                subset = age_frame.loc[age_frame[field].map(lambda value: label in json.loads(value))]
            else:
                subset = age_frame.loc[age_frame[field] == label]
            for scenario, column in [('programme_age', 'program_age_match'),
                                     ('programme_and_group_intervals', 'program_and_group_match')]:
                selected = subset.loc[subset[column]]
                weights = np.zeros(len(loc_order), dtype=int)
                for location, count in selected.location_id.value_counts().items():
                    weights[loc_order[location]] = count
                for threshold in [10, 15, 20, 30]:
                    reachable = times <= threshold
                    programs = reachable @ weights
                    coordinates = reachable @ (weights > 0).astype(int)
                    summaries.append({'age': age, 'threshold_minutes': threshold, 'scenario': scenario,
                        'category_kind': category_kind, 'category_label': label,
                        'selected_programs_in_snapshot': len(selected),
                        'median_reachable_programs': float(np.median(programs)),
                        'p25_reachable_programs': float(np.quantile(programs, .25)),
                        'p75_reachable_programs': float(np.quantile(programs, .75)),
                        'median_reachable_coordinates': float(np.median(coordinates)),
                        'origins_without_matching_records': int((programs == 0).sum())})
    a.output.mkdir(parents=True)
    frame.to_csv(a.output / 'program-scenarios.csv', index=False, encoding='utf-8-sig')
    (a.output / 'snapshot-card-ids.json').write_text(
        json.dumps(sorted(int(i) for i in frame.program_id.unique())), encoding='utf-8')
    pd.DataFrame(summaries).to_csv(a.output / 'summary.csv', index=False, encoding='utf-8-sig')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'as_of': a.as_of.isoformat(),
              'sources': {str(path): digest(path) for path in [a.matrix, a.links]},
              'source_details_directory': str(a.details), 'matrix_origins': len(matrix),
              'catalogue_selected_programs': len(links), 'downloaded_cards': len(frame) // 4,
              'cards_not_downloaded_at_snapshot': missing,
              'payment_id_and_catalogue_labels': {str(k): int(v) for k, v in
                  Counter((str(r['payment_id_from_card']), r['payment_label_from_catalogue'])
                          for r in frame.loc[frame.age == 7].to_dict('records')).items()},
              'study_area_categories_included': a.include_study_areas,
              'cards_without_study_area_labels': int((frame.loc[frame.age == 7, 'study_area_labels'] == '[]').sum()),
              'interpretation': 'Compare sensitivity to programme versus stricter group-record evidence, not current attendance.',
              'limitations': ['Partial non-random set and catalogue missing coordinates: no inference to complete district supply.',
                  'No matching group record is not evidence of no real service; group dates do not establish sessions or enrolment.',
                  'Age flag interpretation is based on saved frontend display, not confirmed server admission rules.',
                  'Program coordinate is unverified group location, and coordinate pairs are not necessarily distinct venues.',
                  'Payment and directions are reported categories, not verified current terms; study-area labels can overlap and may remain broad.',
                  'Uniform 5km/h OD costs omit endpoint attachments; thresholds are exploratory scenarios, not norms.',
                  'Median is across buildings, not children; no assessment of escort, safety or real travel.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['matrix_origins', 'catalogue_selected_programs',
        'downloaded_cards', 'cards_not_downloaded_at_snapshot']}))


if __name__ == '__main__':
    main()
