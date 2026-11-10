"""Export residential records from a completed Urban API archive as GeoJSON."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.source/'manifest.json').read_text(encoding='utf8'))
    if manifest['status'] != 'pagination_finished' or manifest.get('next'):
        raise ValueError('Source archive is not finished')
    features = []
    for page in manifest['pages']:
        records = json.loads((a.source/page['file']).read_text(encoding='utf8'))['results']
        for row in records:
            if (row.get('physical_object_type') or {}).get('name') != 'Жилой дом':
                continue
            properties = {key: value for key, value in row.items() if key != 'geometry'}
            features.append({'type': 'Feature', 'geometry': row.get('geometry'), 'properties': properties})
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'residential.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features},
                                                          ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    info = {'created_utc': datetime.now(timezone.utc).isoformat(), 'source': str(a.source),
            'filter': 'physical_object_type.name == Жилой дом', 'features': len(features),
            'geometry_types': sorted({(f['geometry'] or {}).get('type', 'null') for f in features}),
            'limitations': ['Point geometries supplied by Urban API, not building footprints or verified entrances.',
                            'No modification of source pages; source attributes retained as feature properties.',
                            'Residential type is the source classification; occupancy and population not inferred.']}
    (a.output/'manifest.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
