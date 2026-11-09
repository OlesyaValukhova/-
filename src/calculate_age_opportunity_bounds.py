"""Cumulative opportunities on a precomputed library OD matrix.

Bounds concern missing age fields within the coordinate-selected catalogue only.
They do not bound true city supply, active groups, enrolment, or escort needs.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nir2_demo import age_eligible


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--links', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be new')
    links = pd.read_csv(args.links, encoding='utf-8-sig', keep_default_na=False)
    matrix = pd.read_csv(args.matrix, index_col=0, encoding='utf-8-sig')
    if links['program_id'].duplicated().any() or not matrix.index.is_unique or not matrix.columns.is_unique:
        raise ValueError('Program IDs, origin indices and destination columns must be unique')
    if set(links['location_id']) != set(matrix.columns):
        raise ValueError('Location IDs do not exactly match route matrix columns')
    times = matrix.to_numpy(dtype=float)
    if not np.isfinite(times).all() or (times < 0).any():
        raise ValueError('Route matrix must be finite and nonnegative for this pilot')
    location_order = {key: i for i, key in enumerate(matrix.columns)}
    data = links.to_dict('records')
    ages = [7, 10, 13, 16]
    thresholds = [10, 15, 20, 30]
    outputs, summaries, statuses = [], [], Counter()
    for age in ages:
        known = np.zeros(len(location_order), dtype=int)
        possible = np.zeros(len(location_order), dtype=int)
        age_states = Counter()
        for record in data:
            try:
                eligible = age_eligible(age, record['min_age'], record['max_age'])
            except (TypeError, ValueError):
                eligible = None
            loc = location_order[record['location_id']]
            age_states[str(eligible)] += 1
            if eligible is True:
                known[loc] += 1
            if eligible is not False:
                possible[loc] += 1
        statuses[str(age)] = dict(age_states)
        for minutes in thresholds:
            reachable = times <= minutes
            lower_programs = reachable @ known
            upper_programs = reachable @ possible
            lower_coords = reachable @ (known > 0).astype(int)
            upper_coords = reachable @ (possible > 0).astype(int)
            for i, origin in enumerate(matrix.index):
                outputs.append({'origin_matrix_index': origin, 'age': age, 'threshold_minutes': minutes,
                                'known_eligible_programs': int(lower_programs[i]),
                                'possibly_eligible_programs': int(upper_programs[i]),
                                'known_eligible_coordinates': int(lower_coords[i]),
                                'possibly_eligible_coordinates': int(upper_coords[i])})
            summaries.append({'age': age, 'threshold_minutes': minutes,
                'median_known_programs': float(np.median(lower_programs)),
                'median_possible_programs': float(np.median(upper_programs)),
                'median_known_coordinates': float(np.median(lower_coords)),
                'median_possible_coordinates': float(np.median(upper_coords)),
                'origins_zero_known_programs': int((lower_programs == 0).sum())})
    args.output.mkdir(parents=True)
    pd.DataFrame(outputs).to_csv(args.output / 'by-origin.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(summaries).to_csv(args.output / 'summary.csv', index=False, encoding='utf-8-sig')
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
        'sources': {k: {'path': str(p), 'sha256': digest(p)} for k, p in [('matrix', args.matrix), ('links', args.links)]},
        'origins': len(matrix), 'programs_in_coordinate_selected_catalogue': len(links),
        'reported_coordinate_pairs': len(matrix.columns),
        'card_age_states': links['card_age_state'].value_counts().to_dict(),
        'eligibility_states_by_age': dict(statuses), 'ages': ages, 'thresholds_minutes': thresholds,
        'interpretation': 'Bounds are sensitivity to missing age fields only, conditional on reported coordinates and catalogue entries.',
        'limitations': ['Partial, nonrandom card snapshot; not population-weighted.',
          'Age bands are program-level descriptions, not verified group enrolment or current classes.',
          'Coordinates may represent organisation rather than teaching address; missing coordinates excluded.',
          'Reported coordinate pair is not necessarily a unique site; count of programs is not capacity.',
          'Network-only costs exclude access to nodes and use uniform 5 km/h; thresholds are sensitivity scenarios, not child mobility norms.',
          'No parent escort, measured behaviour, route safety, citywide supply or economic impact is estimated.']}
    (args.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'origins': len(matrix), 'programs': len(links), 'card_age_states': report['card_age_states']}))


if __name__ == '__main__':
    main()
