"""Describe within-building age differences and aggregate by existing blocks.

Intervals only address unknown programme age bounds in a fixed catalogue subset;
they are not uncertainty bounds for actual destinations or child mobility.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bounds', type=Path, required=True)
    p.add_argument('--origin-rows', type=Path, required=True)
    p.add_argument('--block-links', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    bounds = pd.read_csv(a.bounds, encoding='utf-8-sig')
    origins = pd.read_csv(a.origin_rows, encoding='utf-8-sig')
    links = pd.read_csv(a.block_links, encoding='utf-8-sig')
    if not origins.origin_id.is_unique or not links.origin_id.is_unique:
        raise ValueError('Origins must map uniquely to blocks')
    origins = origins[['origin_id']].copy()
    origins['origin_matrix_index'] = np.arange(len(origins))
    mapping = origins.merge(links[['origin_id', 'index_right']], on='origin_id', how='left', validate='one_to_one')
    if mapping.index_right.isna().any() or set(bounds.origin_matrix_index.unique()) != set(mapping.origin_matrix_index):
        raise ValueError('Missing origin-block mapping or inconsistent matrix indices')
    parts = []
    for threshold in sorted(bounds.threshold_minutes.unique()):
        selected = bounds.loc[bounds.threshold_minutes == threshold]
        young = selected.loc[selected.age == 7].set_index('origin_matrix_index')
        older = selected.loc[selected.age == 16].set_index('origin_matrix_index')
        if (not young.index.is_unique or not older.index.is_unique
                or set(young.index) != set(mapping.origin_matrix_index)
                or set(older.index) != set(mapping.origin_matrix_index)):
            raise ValueError('Missing or duplicate age/origin rows')
        young = young.sort_index()
        older = older.sort_index()
        d = pd.DataFrame({'origin_matrix_index': young.index,
            'age16_minus_age7_known_programs': (older.known_eligible_programs - young.known_eligible_programs).to_numpy(),
            'delta_low_from_unknown_age': (older.known_eligible_programs - young.possibly_eligible_programs).to_numpy(),
            'delta_high_from_unknown_age': (older.possibly_eligible_programs - young.known_eligible_programs).to_numpy()})
        d['threshold_minutes'] = threshold
        d['sign_given_unknown_age'] = np.select(
            [d.delta_low_from_unknown_age > 0, d.delta_high_from_unknown_age < 0],
            ['positive', 'negative'], default='uncertain_or_zero')
        parts.append(d.merge(mapping, on='origin_matrix_index', validate='one_to_one'))
    by_origin = pd.concat(parts, ignore_index=True)
    by_block = by_origin.groupby(['threshold_minutes', 'index_right'], as_index=False).agg(
        residential_buildings=('origin_id', 'size'),
        median_difference_known_programs=('age16_minus_age7_known_programs', 'median'),
        median_delta_low=('delta_low_from_unknown_age', 'median'),
        median_delta_high=('delta_high_from_unknown_age', 'median'))
    by_block['sign_given_unknown_age'] = np.select(
        [by_block.median_delta_low > 0, by_block.median_delta_high < 0],
        ['positive', 'negative'], default='uncertain_or_zero')
    summary = []
    for threshold, group in by_origin.groupby('threshold_minutes'):
        blocks = by_block.loc[by_block.threshold_minutes == threshold]
        summary.append({'threshold_minutes': int(threshold), 'buildings': len(group), 'blocks': len(blocks),
                        'building_sign_counts': group.sign_given_unknown_age.value_counts().to_dict(),
                        'block_sign_counts': blocks.sign_given_unknown_age.value_counts().to_dict(),
                        'median_building_difference_known_programs': float(group.age16_minus_age7_known_programs.median())})
    a.output.mkdir(parents=True)
    by_origin.to_csv(a.output / 'age-differences-by-building.csv', encoding='utf-8-sig', index=False)
    by_block.to_csv(a.output / 'age-differences-by-block.csv', encoding='utf-8-sig', index=False)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'comparison': 'age 16 minus age 7',
              'sources': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [a.bounds, a.origin_rows, a.block_links]}, 'thresholds': summary,
              'limitations': ['Sign intervals cover only missing programme age values in the coordinate-selected catalogue.',
                  'Bounds are deliberately conservative and may combine incompatible assignments of the same unknown programme.',
                  'Results are counts of program records, not confirmed groups, attendance, safety or parental escort.',
                  'Programme coordinates are unverified locations; unlocated catalogue records are excluded.',
                  'Median by building is not weighted by population or number of children.',
                  'Block index comes from saved blocks; omitted invalid blocks and boundary effects require review.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
