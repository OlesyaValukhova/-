"""Separate programme age eligibility from a hypothetical walking-time budget."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument('by_origin', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    d = pd.read_csv(a.by_origin, encoding='utf-8-sig')
    d = d[(d.payment == 'all') & (d.scenario == 'program_age') & d.age.isin([7, 13])]
    if d.duplicated(['origin_matrix_index', 'age', 'threshold_minutes']).any():
        raise ValueError('Non-unique scenario origin')
    wide = d.pivot(index='origin_matrix_index', columns=['age', 'threshold_minutes'], values='coordinates')
    if wide.isna().any().any():
        raise ValueError('Incomplete origin scenarios')
    comparisons = [('age_7_10_vs_age_13_10', (7, 10), (13, 10)),
                   ('age_7_20_vs_age_13_20', (7, 20), (13, 20)),
                   ('age_7_10_vs_age_13_20', (7, 10), (13, 20)),
                   ('age_13_10_vs_age_13_20', (13, 10), (13, 20))]
    rows = []
    for label, first, second in comparisons:
        x, y = wide[first], wide[second]
        rows.append({'comparison': label, 'origins': len(wide), 'first_more': int((x > y).sum()),
                     'equal': int((x == y).sum()), 'second_more': int((x < y).sum()),
                     'median_first': float(x.median()), 'median_second': float(y.median()),
                     'median_paired_difference_second_minus_first': float((y-x).median())})
    a.output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(a.output / 'summary.csv', index=False, encoding='utf-8-sig')
    (a.output / 'manifest.json').write_text(json.dumps({'source': str(a.by_origin),
        'limitations': ['Times are arbitrary sensitivity scenarios, not age-specific norms.',
                        'Age-specific programme availability is incomplete and unvalidated.',
                        'No observed children, escorting, actual venues, safety, or population weights.',
                        'Age and time changes together are illustrative, not causal decomposition.']}, indent=2), encoding='utf8')
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == '__main__':
    main()
