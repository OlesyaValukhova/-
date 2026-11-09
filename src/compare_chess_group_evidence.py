"""Compare reported programme versus group evidence on the same route matrix."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['matrix', 'programs', 'groups', 'inside-links', 'outside-links', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    matrix = pd.read_csv(a.matrix, index_col=0, encoding='utf-8-sig').astype(float)
    programs = pd.read_csv(a.programs, encoding='utf-8-sig', dtype=str, keep_default_na=False)
    groups = pd.read_csv(a.groups, encoding='utf-8-sig', dtype=str, keep_default_na=False)
    inside = pd.read_csv(a.inside_links, encoding='utf-8-sig', dtype=str, keep_default_na=False)
    outside = pd.read_csv(a.outside_links, encoding='utf-8-sig', dtype=str, keep_default_na=False)
    if programs.program_id.duplicated().any() or groups.group_id.duplicated().any():
        raise ValueError('Programme and group IDs must be unique')
    links = pd.concat([inside[['program_id', 'location_id']], outside[['program_id', 'location_id']]], ignore_index=True)
    if links.program_id.duplicated().any():
        raise ValueError('Ambiguous programme-to-coordinate mapping')
    if not matrix.index.is_unique or not matrix.columns.is_unique or not np.isfinite(matrix.to_numpy()).all():
        raise ValueError('Route matrix requires unique, finite values')
    programs = programs.merge(links, on='program_id', how='left', validate='one_to_one')
    if programs.location_id.isna().any() or not set(programs.location_id).issubset(matrix.columns):
        raise ValueError('Programme coordinate missing from matrix')
    times = matrix.to_numpy()
    positions = {key: i for i, key in enumerate(matrix.columns)}
    scenario_rows, summaries, origins = [], [], []
    for age in [7, 13]:
        matched_groups = groups.loc[(groups[f'displayed_interval_matches_{age}'] == 'True') &
                                    (groups.lesson_date_state == 'date_interval_covers_snapshot')]
        matched_ids = set(matched_groups.program_id)
        selected_age = programs[f'program_matches_age_{age}'] == 'True'
        scenario = programs.copy()
        scenario['age'] = age
        scenario['program_age_match'] = selected_age
        scenario['program_and_group_match'] = selected_age & scenario.program_id.isin(matched_ids)
        scenario_rows.append(scenario[['program_id', 'scope', 'program_name', 'location_id',
            'payment_label_from_catalogue', 'age', 'program_age_match', 'program_and_group_match', 'card_sha256']])
        for pay in ['all', 'Бесплатно', 'Только платно']:
            subset = scenario if pay == 'all' else scenario.loc[scenario.payment_label_from_catalogue == pay]
            for label, col in [('program_age', 'program_age_match'), ('group_evidence', 'program_and_group_match')]:
                picked = subset.loc[subset[col]]
                coordinate_ids = sorted(set(picked.location_id))
                weights = np.zeros(len(positions), dtype=int)
                for location in coordinate_ids:
                    weights[positions[location]] = 1
                for threshold in [10, 15, 20, 30]:
                    count = (times <= threshold) @ weights
                    summaries.append({'age': age, 'payment': pay, 'scenario': label,
                        'threshold_minutes': threshold, 'selected_programs': len(picked),
                        'selected_coordinates': len(coordinate_ids),
                        'median_coordinates_per_building': float(np.median(count)),
                        'buildings_without_matching_coordinates': int((count == 0).sum())})
                    origins.extend({'origin_matrix_index': int(i), 'age': age, 'payment': pay,
                                    'scenario': label, 'threshold_minutes': threshold, 'coordinates': int(value)}
                                   for i, value in zip(matrix.index, count))
    a.output.mkdir(parents=True)
    pd.concat(scenario_rows, ignore_index=True).to_csv(a.output / 'program-scenarios.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(summaries).to_csv(a.output / 'summary.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(origins).to_csv(a.output / 'by-origin.csv', index=False, encoding='utf-8-sig')
    paths = [a.matrix, a.programs, a.groups, a.inside_links, a.outside_links]
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(), 'programs': len(programs),
        'groups': len(groups), 'origins': len(matrix), 'source_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
        'limitations': ['Incomplete title-based selection and geographical coverage, not census of chess opportunities.',
            'Group evidence is a conservative record filter, not a lower bound on actual provision.',
            'Program coordinate is not independently verified group venue; group age display flag does not establish admission.',
            'Lesson dates including the snapshot do not establish actual sessions or enrolment.',
            'Payment label is unverified source metadata; selected categories can omit records with missing labels.',
            'Thresholds use network edge time at 5 km/h with no endpoint attachments; not mobility norms.',
            'Buildings are proxies; results do not represent number of children, parental escort or route safety.']}
    (a.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'programs': len(programs), 'groups': len(groups), 'origins': len(matrix)}))


if __name__ == '__main__':
    main()
