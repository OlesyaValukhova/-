"""Compare inside-only and inside-plus-nearby destinations on one walking graph."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from audit_program_group_ages import eligibility
from collect_program_details import validate_card
from export_navigator_details import coordinate_state


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix', type=Path, required=True)
    p.add_argument('--inside-programs', type=Path, required=True)
    p.add_argument('--selection', type=Path, required=True)
    p.add_argument('--outside-links', type=Path, required=True)
    p.add_argument('--outside-catalogue', type=Path, required=True)
    p.add_argument('--outside-cards', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    matrix = pd.read_csv(a.matrix, encoding='utf-8-sig', index_col=0).astype(float)
    inside = pd.read_csv(a.inside_programs, encoding='utf-8-sig')
    selected = json.loads(a.selection.read_text(encoding='utf-8'))['categories']['Шахматы']
    links = pd.read_csv(a.outside_links, encoding='utf-8-sig')
    catalog = pd.read_csv(a.outside_catalogue, encoding='utf-8-sig')
    if links.program_id.duplicated().any() or catalog.program_id.duplicated().any():
        raise ValueError('Outside programme IDs must be unique')
    if not matrix.index.is_unique or not matrix.columns.is_unique or not np.isfinite(matrix.to_numpy()).all():
        raise ValueError('Expected unique and finite matrix')
    catalog = catalog.set_index('program_id')
    outside = []
    for row in links.to_dict('records'):
        raw = (a.outside_cards / f"{row['program_id']}-detail.json").read_bytes()
        card = validate_card(raw, row['program_id'])
        src = catalog.loc[row['program_id']]
        if coordinate_state(card) != 'valid_numeric_not_venue_verified' or (
            float(card['latitude']) != float(src.catalog_latitude) or float(card['longitude']) != float(src.catalog_longitude)):
            raise ValueError(f"Catalogue/card coordinates differ for {row['program_id']}")
        outside.append({'program_id': row['program_id'], 'location_id': row['location_id'],
                        'card_sha256': hashlib.sha256(raw).hexdigest(),
                        **{f'age_{age}_eligible': str(eligibility(age, card)) for age in [7, 13]}})
    outputs, summaries = [], []
    for age in [7, 13]:
        filtered = inside.loc[(inside.age == age) & inside.program_id.isin(selected) & (inside.program_age_match == True)]
        internal = set(filtered.location_id)
        external = {r['location_id'] for r in outside if r[f'age_{age}_eligible'] == 'True'}
        if not (internal | external).issubset(matrix.columns):
            raise ValueError('Destination missing from expanded route matrix')
        for minutes in [10, 15, 20, 30]:
            old = (matrix[sorted(internal)].to_numpy() <= minutes).sum(axis=1) if internal else np.zeros(len(matrix), dtype=int)
            all_locations = internal | external
            new = (matrix[sorted(all_locations)].to_numpy() <= minutes).sum(axis=1) if all_locations else np.zeros(len(matrix), dtype=int)
            if (new < old).any():
                raise ValueError('Expanded set cannot reduce opportunity counts')
            increase = new - old
            summaries.append({'age': age, 'threshold_minutes': minutes,
                'inside_eligible_coordinates': len(internal), 'outside_eligible_coordinates': len(external),
                'median_inside_coordinates': float(np.median(old)), 'median_combined_coordinates': float(np.median(new)),
                'buildings_with_added_coordinate': int((increase > 0).sum()),
                'buildings_without_inside_but_with_combined': int(((old == 0) & (new > 0)).sum())})
            outputs.extend({'origin_matrix_index': int(index), 'age': age, 'threshold_minutes': minutes,
                            'inside_coordinates': int(v), 'combined_coordinates': int(w)}
                           for index, v, w in zip(matrix.index, old, new))
    a.output.mkdir(parents=True)
    pd.DataFrame(outputs).to_csv(a.output / 'by-origin.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(summaries).to_csv(a.output / 'summary.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(outside).to_csv(a.output / 'outside-card-ages.csv', index=False, encoding='utf-8-sig')
    paths = [a.matrix, a.inside_programs, a.selection, a.outside_links, a.outside_catalogue]
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'origins': len(matrix),
              'source_sha256': {str(path): sha(path) for path in paths},
              'outside_cards': outside, 'summary': summaries,
              'limitations': ['Both scenarios use the same 9 November 2026 expanded walking network and the same building proxies.',
                'Only four nearby outside title matches were considered; this is not the entire 3 km set.',
                'Missing/partial programme ages excluded; group status, admissions and specific venue are unverified.',
                'No endpoint attachments or child-specific safety considered; finite network extent can affect routes.',
                'Programmes outside the catalogue or without coordinates remain missing.',
                'Counts are distinct reported coordinate pairs, not actual premises or seats.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summaries))


if __name__ == '__main__':
    main()
