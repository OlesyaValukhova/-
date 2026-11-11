"""Summarise completed B1 results at existing 15/20/30-minute thresholds.

This is a descriptive sensitivity check only.  It consumes existing per-origin
tables and never calls the routing pipeline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path('results/blocksnet-b1-study-areas-citywide-20261111')
CASES = Path('data/navigator-study-area-cases-ascii-20261111/manifest.json')


def main(out: Path) -> None:
    cases = json.loads(CASES.read_text(encoding='utf-8'))['included_cases']
    rows: list[dict] = []
    for case in cases:
        data = pd.read_csv(ROOT / case['case_id'] / 'b1-by-origin.csv')
        covered = data.network_covered.eq(True)
        for age in (7, 13):
            for threshold in (15, 20, 30):
                n = data[f'age_{age}_N_venue_proxy_within_{threshold}min']
                valid = covered & n.notna()
                rows.append({
                    'study_area_id': case['study_area_id'],
                    'study_area_name': case['study_area_name'],
                    'age': age,
                    'threshold_minutes': threshold,
                    'n_network_covered_origins': int(covered.sum()),
                    'n_valid_origins': int(valid.sum()),
                    'share_origins_with_venue_pct': float(100 * (n[valid] > 0).mean()),
                    'median_reachable_venue_coordinates': float(n[valid].median()),
                    'mean_reachable_venue_coordinates': float(n[valid].mean()),
                })
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False, encoding='utf-8-sig')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path,
                        default=Path('results/age-profiles-blocks-b1-20261112-r2/threshold_sensitivity_by_direction.csv'))
    main(parser.parse_args().out)
