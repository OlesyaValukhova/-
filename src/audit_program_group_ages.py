"""Describe program/group age intervals and reported lesson dates from saved cards."""
import argparse
from collections import Counter
import csv
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

from collect_program_details import validate_card
from nir2_demo import age_eligible, group_date_state


def eligibility(age, obj):
    try:
        return age_eligible(age, obj.get('min_age'), obj.get('max_age'))
    except (TypeError, ValueError):
        return None


def date_state(group, as_of):
    try:
        return group_date_state(group, as_of)
    except (TypeError, ValueError):
        return 'invalid_lesson_dates'


def group_eligibility(age, group):
    # The saved frontend renders the group age only when is_age_limit is true.
    # A hidden interval is unknown, not proof of either eligibility or exclusion.
    if group.get('is_age_limit') is not True:
        return None
    return eligibility(age, group)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--details', type=Path, required=True)
    p.add_argument('--as-of', type=date.fromisoformat, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    rows, totals = [], Counter()
    for path in sorted(a.details.glob('*-detail.json')):
        raw = path.read_bytes()
        card = validate_card(raw, int(path.name.split('-')[0]))
        groups = card.get('groups')
        if groups is not None and (not isinstance(groups, list) or any(not isinstance(g, dict) for g in groups)):
            raise ValueError(f'Unexpected groups schema for {card["id"]}')
        group_list = groups or []
        totals['cards'] += 1
        totals['cards_no_embedded_groups'] += not group_list
        totals['groups'] += len(group_list)
        for group in group_list:
            totals['date_' + date_state(group, a.as_of)] += 1
            totals['is_age_limit_' + str(group.get('is_age_limit'))] += 1
        for age in [7, 10, 13, 16]:
            matched = [g for g in group_list if group_eligibility(age, g) is True
                       and date_state(g, a.as_of) == 'date_interval_covers_snapshot']
            uncertain = [g for g in group_list
                         if group_eligibility(age, g) is not False
                         and date_state(g, a.as_of) not in ('ended_before_snapshot', 'starts_after_snapshot')
                         and g not in matched]
            prog_age = eligibility(age, card)
            state = ('has_matching_interval' if matched else
                     'possible_but_unknown' if uncertain else
                     'no_embedded_groups' if not group_list else 'no_matching_interval_in_embedded_groups')
            rows.append({'program_id': card['id'], 'age': age,
                         'program_age_interval_eligible': str(prog_age),
                         'groups_count': len(group_list), 'matching_group_intervals': len(matched),
                         'uncertain_group_intervals': len(uncertain), 'group_interval_state': state,
                         'source_sha256': hashlib.sha256(raw).hexdigest()})
            if prog_age is True:
                totals[f'age_{age}_program_interval_matches'] += 1
                totals[f'age_{age}_program_matches_group_{state}'] += 1
    a.output.mkdir(parents=True)
    with (a.output / 'program-age-group-comparison.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['program_id'])
        w.writeheader()
        w.writerows(rows)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'as_of': a.as_of.isoformat(),
              'source_directory': str(a.details), 'counts': dict(totals),
              'limitations': ['Partial, non-random card snapshot; counts are not representative of the district.',
                  'Group intervals count as stated only if is_age_limit is true; frontend display logic alone does not prove eligibility rules.',
                  'A lesson interval covering a date does not confirm sessions, enrolment or capacity.',
                  'No matching embedded group does not demonstrate no actual programme offering.',
                  'Current group location is not confirmed by these fields.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['counts'], ensure_ascii=True))


if __name__ == '__main__':
    main()
