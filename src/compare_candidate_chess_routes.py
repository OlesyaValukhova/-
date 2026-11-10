"""Sensitivity to three manually identified, unverified school-location candidates."""
import argparse
from pathlib import Path
import pandas as pd

CANDIDATES = {7: ['urban-candidate-561170', 'urban-candidate-561144', 'urban-candidate-561150'],
              13: ['urban-candidate-561144']}


def main():
    p = argparse.ArgumentParser()
    for key in ('base-matrix', 'candidate-matrix', 'scenarios', 'output'):
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    base = pd.read_csv(a.base_matrix, index_col=0, encoding='utf-8-sig')
    extra = pd.read_csv(a.candidate_matrix, index_col=0, encoding='utf-8-sig')
    scenarios = pd.read_csv(a.scenarios, encoding='utf-8-sig')
    if not base.index.equals(extra.index):
        raise ValueError('Origin order differs between route matrices')
    rows = []
    for age, added in CANDIDATES.items():
        loc = sorted(set(scenarios[(scenarios.age == age) & scenarios.program_age_match].location_id))
        for candidate in added:
            if ((base[loc].sub(extra[candidate], axis=0)).abs().max() == 0).any():
                raise ValueError('Candidate shares a snapped node with an already selected destination: review deduplication')
        for threshold in [10, 15, 20, 30]:
            old = (base[loc] <= threshold).sum(axis=1)
            new = old + (extra[added] <= threshold).sum(axis=1)
            rows.append({'age': age, 'threshold_minutes': threshold, 'origin_count': len(old),
                         'no_coordinate_before': int((old == 0).sum()),
                         'no_coordinate_after': int((new == 0).sum()),
                         'origins_with_added_coordinate': int((new > old).sum()),
                         'median_before': float(old.median()), 'median_after': float(new.median())})
    a.output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(a.output/'summary.csv', index=False, encoding='utf-8-sig')
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == '__main__':
    main()
