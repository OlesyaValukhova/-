"""Extract manually identified Urban API address candidates without asserting venue."""
import argparse
import json
from pathlib import Path

MATCHES = {561170: [13378, 13379], 561144: [13602], 561150: [34986]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads((a.source/'manifest.json').read_text(encoding='utf8'))
    if manifest['status'] != 'pagination_finished':
        raise ValueError('Urban archive is incomplete')
    features = []
    for page in manifest['pages']:
        for row in json.loads((a.source/page['file']).read_text(encoding='utf8'))['results']:
            object_id = row['physical_object_id']
            if object_id in MATCHES:
                features.append({'type': 'Feature', 'geometry': row['geometry'], 'properties': {
                    'location_id': f'urban-candidate-{object_id}', 'urban_object_id': object_id,
                    'program_ids': ','.join(str(x) for x in MATCHES[object_id]),
                    'name': row.get('name'), 'address': row.get('address'), 'source_page': page['file'],
                    'verified_venue': False}})
    if len(features) != len(MATCHES):
        raise ValueError('Expected unique source records for three candidates')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False), encoding='utf8')
    print(f'candidate_locations={len(features)}')


if __name__ == '__main__':
    main()
