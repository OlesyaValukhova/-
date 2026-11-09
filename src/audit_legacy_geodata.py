"""Read-only audit/import of earlier local spatial exports for pilot feasibility.

Source platform/date are not inferred from file names or modification timestamps.
Previous modeled capacities and populations are not adopted as verified inputs.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import geopandas as gpd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    names = {'buildings': 'Здания ВР.geojson', 'schools': 'Школы ВР.geojson', 'blocks': 'Кварталы ВР.geojson'}
    sources = {key: args.source / name for key, name in names.items()}
    if not all(path.is_file() for path in sources.values()):
        parser.error('Required legacy files missing')
    if args.output.exists():
        parser.error('Output must be new')
    args.output.mkdir(parents=True)
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(),
              'source_platform_verified': False, 'export_date_verified': False,
              'purpose': 'Pilot input feasibility only, not current territorial conclusions', 'files': {}}
    frames = {}
    for key, path in sources.items():
        raw = path.read_bytes()
        copied = args.output / f'{key}-source.geojson'
        shutil.copyfile(path, copied)
        frame = gpd.read_file(copied)
        if frame.crs is None:
            raise ValueError(f'CRS is not established for {key}')
        frames[key] = frame
        report['files'][key] = {'original_path': str(path), 'copied_path': str(copied),
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'file_modified_utc_not_export_date': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            'features': len(frame), 'crs': str(frame.crs), 'bounds': frame.total_bounds.tolist(),
            'empty_geometries': int(frame.geometry.is_empty.sum()), 'missing_geometries': int(frame.geometry.isna().sum()),
            'invalid_geometries': int((~frame.geometry.is_valid).sum()),
            'geometry_types': frame.geom_type.value_counts().to_dict(), 'fields': list(frame.columns)}
    buildings, blocks = frames['buildings'], frames['blocks']
    if 'Тип физического объекта' not in buildings:
        raise ValueError('Missing explicit building type field')
    report['building_types'] = Counter(buildings['Тип физического объекта'].fillna('missing')).copy()
    residential = buildings.loc[buildings['Тип физического объекта'] == 'Жилой дом'].copy()
    valid = residential.geometry.notna() & ~residential.geometry.is_empty & residential.geometry.is_valid
    origins = residential.loc[valid, ['geometry']].copy()
    origins['legacy_source_row'] = origins.index
    origins['origin_id'] = ['legacy-residential-' + str(i) for i in origins.index]
    if 'object_geometry_id' in residential:
        origins['source_object_geometry_id'] = residential.loc[valid, 'object_geometry_id']
    origins.geometry = origins.geometry.representative_point()
    origins = origins.to_crs(blocks.crs)
    valid_blocks = blocks.loc[blocks.geometry.notna() & ~blocks.geometry.is_empty & blocks.geometry.is_valid, ['geometry']].copy()
    joined = gpd.sjoin(origins, valid_blocks, how='left', predicate='within')
    matched = joined.loc[joined['index_right'].notna()]
    multiplicity = matched.groupby('origin_id').size()
    report.update(residential_features=len(residential), usable_residential_origins=len(origins),
                  residential_excluded_geometry=int((~valid).sum()),
                  origins_in_at_least_one_valid_block=int(matched['origin_id'].nunique()),
                  origins_in_multiple_blocks=int((multiplicity > 1).sum()),
                  valid_blocks_with_origins=int(matched['index_right'].nunique()),
                  inherited_population_or_capacity_used=False,
                  representative_points_are_actual_entrances=False)
    origins.to_crs(4326).to_file(args.output / 'residential-representative-points.geojson', driver='GeoJSON')
    joined.drop(columns='geometry').to_csv(args.output / 'origin-block-links.csv', index=False, encoding='utf-8-sig')
    (args.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['residential_features', 'usable_residential_origins',
        'origins_in_at_least_one_valid_block', 'origins_in_multiple_blocks', 'valid_blocks_with_origins']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
