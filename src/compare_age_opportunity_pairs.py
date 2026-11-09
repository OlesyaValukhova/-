"""Summarise paired age scenarios by the same residential origins."""
import argparse
import json
from pathlib import Path
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument('by_origin', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    data = pd.read_csv(a.by_origin, encoding='utf-8-sig')
    data = data[(data.payment == 'all') & data.age.isin([7, 13])]
    keys = ['origin_matrix_index', 'scenario', 'threshold_minutes', 'age']
    if data.duplicated(keys).any():
        raise ValueError('Duplicate origin, scenario, threshold, age')
    paired = data.pivot(index=keys[:-1], columns='age', values='coordinates').reset_index()
    if paired[[7, 13]].isna().any().any():
        raise ValueError('Missing paired age scenario')
    paired = paired.rename(columns={7: 'age_7', 13: 'age_13'})
    rows = []
    for (scenario, threshold), group in paired.groupby(['scenario', 'threshold_minutes']):
        x, y = group.age_7, group.age_13
        rows.append({'scenario': scenario, 'threshold_minutes': int(threshold), 'origins': len(group),
                     'both_zero': int(((x == 0) & (y == 0)).sum()),
                     'both_positive': int(((x > 0) & (y > 0)).sum()),
                     'only_7_positive': int(((x > 0) & (y == 0)).sum()),
                     'only_13_positive': int(((x == 0) & (y > 0)).sum()),
                     'more_at_7': int((x > y).sum()), 'equal_counts': int((x == y).sum()),
                     'more_at_13': int((x < y).sum())})
    a.output.mkdir(parents=True, exist_ok=True)
    paired.to_csv(a.output / 'paired-origins.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(rows).to_csv(a.output / 'paired-summary.csv', index=False, encoding='utf-8-sig')
    (a.output / 'manifest.json').write_text(json.dumps({'input': str(a.by_origin), 'origins_are_buildings_not_people': True,
        'limitations': ['Counts of reported coordinates, not distinct actual venues.',
                        'Age comparison is cross-sectional scenario, not observed changes for children.',
                        'Counts can be equal even when underlying destination sets differ.',
                        'Selected and incompletely verified Navigator records, not all city offerings.',
                        'Thresholds are scenario parameters; no safety or escort measured.']}, indent=2), encoding='utf-8')
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == '__main__':
    main()
