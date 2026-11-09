"""Compare building-level scenario differences aggregated to legacy blocks."""
import argparse
import json
from pathlib import Path
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    for name in ('by-origin', 'origins', 'blocks', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    d = pd.read_csv(a.by_origin, encoding='utf-8-sig')
    d = d[(d.payment == 'all') & (((d.age == 7) & (d.threshold_minutes == 10)) |
                                  ((d.age == 13) & (d.threshold_minutes == 20)))]
    wide = d.pivot(index=['origin_matrix_index', 'scenario'], columns='age', values='coordinates').reset_index()
    wide['difference'] = wide[13] - wide[7]
    features = json.loads(a.origins.read_text(encoding='utf8'))['features']
    origins = pd.DataFrame({'origin_matrix_index': range(len(features)),
                            'origin_id': [f['properties']['origin_id'] for f in features]})
    blocks = pd.read_csv(a.blocks, dtype={'origin_id': str})[['origin_id', 'index_right']]
    if blocks.origin_id.duplicated().any():
        raise ValueError('Ambiguous origin-block links')
    paired = wide.merge(origins, on='origin_matrix_index', validate='many_to_one').merge(
        blocks, on='origin_id', how='left', validate='many_to_one')
    if paired.index_right.isna().any():
        raise ValueError('Origins missing block')
    grouped = paired.groupby(['index_right', 'scenario']).agg(
        buildings=('difference', 'size'), median_delta=('difference', 'median'),
        min_delta=('difference', 'min'), max_delta=('difference', 'max')).reset_index()
    grouped['sign'] = grouped.median_delta.map(lambda x: 'positive' if x > 0 else 'negative' if x < 0 else 'zero')
    cross = grouped.pivot(index='index_right', columns='scenario', values='sign')
    size = grouped.groupby('index_right').buildings.first()
    counts = pd.crosstab(cross.program_age, cross.group_evidence)
    a.output.mkdir(parents=True, exist_ok=True)
    grouped.to_csv(a.output / 'blocks.csv', index=False, encoding='utf-8-sig')
    counts.to_csv(a.output / 'sign-cross-tab.csv', encoding='utf-8-sig')
    summary = {'blocks': len(cross), 'buildings': len(origins),
               'blocks_with_fewer_than_5_buildings': int((size < 5).sum()),
               'same_median_sign_both_filters': int((cross.program_age == cross.group_evidence).sum()),
               'different_sign_both_filters': int((cross.program_age != cross.group_evidence).sum()),
               'size_min': int(size.min()), 'size_median': float(size.median()), 'size_max': int(size.max()),
               'limitations': ['Illustrative 7/10 and 13/20 scenarios, not mobility norms.',
                               'Median of buildings not weighted by residents or children.',
                               'Same signs are not proof of stable classification across other assumptions.',
                               'Same zero count is not proof of same destinations or availability.',
                               'Not a trained or validated typology.']}
    (a.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
    print(json.dumps(summary, indent=2)); print(counts.to_string())


if __name__ == '__main__':
    main()
