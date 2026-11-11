"""Create reproducible Navigator direction cases from the observable offer layer.

One program may carry several Navigator ``study_areas``.  It appears once in
each corresponding case; coordinate duplicates are removed only within a case.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


def slug(value: str) -> str:
    return ''.join(ch if ch.isalnum() else '_' for ch in value.lower()).strip('_')[:55]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offers', type=Path, required=True)
    parser.add_argument('--venues', type=Path, required=True)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--coverage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--min-unique-coordinates-per-age', type=int, default=10)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be a new directory')

    offers = pd.read_csv(args.offers, encoding='utf-8-sig', dtype={'program_id': str, 'coordinate_id': str})
    pairs = pd.read_csv(args.pairs, encoding='utf-8-sig', dtype={'program_id': str, 'coordinate_id': str, 'study_area_id': str})
    coverage = pd.read_csv(args.coverage, encoding='utf-8-sig', dtype={'study_area_id': str})
    venues = gpd.read_file(args.venues)
    threshold = args.min_unique_coordinates_per_age
    included = coverage[(coverage.age7_unique_coordinates >= threshold) &
                        (coverage.age13_unique_coordinates >= threshold)].copy()
    included = included.sort_values(['study_area_name', 'study_area_id'])
    keep = set(included.study_area_id)
    pairs = pairs[pairs.study_area_id.isin(keep)].drop_duplicates(['program_id', 'study_area_id'])
    assigned = offers.merge(pairs[['program_id', 'study_area_id']], on='program_id', how='inner', validate='one_to_many')
    args.output.mkdir(parents=True)
    manifest = {'rule': {'field': 'study_areas', 'min_unique_coordinates_per_age': threshold,
                         'ages': [7, 13], 'case_unit': 'Navigator study area'},
                'inputs': {'offers': str(args.offers), 'venues': str(args.venues),
                           'pairs': str(args.pairs), 'coverage': str(args.coverage)},
                'included_cases': [],
                'excluded_study_areas': coverage[~coverage.study_area_id.isin(keep)].to_dict(orient='records'),
                'limits': ['A program with several study areas is included in each relevant direction.',
                           'A coordinate is unique only within a direction; coordinates must not be summed across directions.',
                           'Cases use only published program-card coordinates with valid age intervals.']}
    for row in included.itertuples(index=False):
        # Keep filesystem and command-line paths ASCII; the Russian display name
        # remains in the manifest and outputs, keyed by the stable catalogue ID.
        case_id = f"area_{row.study_area_id}"
        sub = assigned[assigned.study_area_id == str(row.study_area_id)].drop(columns='study_area_id').copy()
        coordinate_ids = set(sub.coordinate_id)
        sub_venues = venues[venues.coordinate_id.astype(str).isin(coordinate_ids)].copy()
        folder = args.output / case_id
        folder.mkdir()
        offer_path = folder / 'offers.csv'
        venue_path = folder / 'venues.geojson'
        sub.to_csv(offer_path, index=False, encoding='utf-8-sig')
        sub_venues.to_file(venue_path, driver='GeoJSON')
        manifest['included_cases'].append({'case_id': case_id, 'study_area_id': str(row.study_area_id),
                                           'study_area_name': row.study_area_name,
                                           'offers_all_ages': int(len(sub)),
                                           'coordinates_all_ages': int(sub.coordinate_id.nunique()),
                                           'age7_offers': int(((sub.min_age <= 7) & (sub.max_age >= 7)).sum()),
                                           'age7_coordinates': int(sub.loc[(sub.min_age <= 7) & (sub.max_age >= 7), 'coordinate_id'].nunique()),
                                           'age13_offers': int(((sub.min_age <= 13) & (sub.max_age >= 13)).sum()),
                                           'age13_coordinates': int(sub.loc[(sub.min_age <= 13) & (sub.max_age >= 13), 'coordinate_id'].nunique()),
                                           'offers_file': str(offer_path), 'venues_file': str(venue_path)})
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'included_cases': len(manifest['included_cases']),
                      'assigned_program_case_rows': len(assigned),
                      'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
