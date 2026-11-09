"""Summarise tags in an existing OSMnx Overpass cache; no completeness inference."""
import argparse
import collections
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cache', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.cache.read_text(encoding='utf-8'))
    elements = source['elements']
    result = {'source': str(args.cache), 'osm3s': source.get('osm3s'), 'types': {}}
    for kind in ('node', 'way', 'relation'):
        rows = [element for element in elements if element['type'] == kind]
        keys = collections.Counter(key for element in rows for key in element.get('tags', {}))
        highways = collections.Counter(element['tags']['highway'] for element in rows
                                       if 'highway' in element.get('tags', {}))
        result['types'][kind] = {'total': len(rows), 'tagged': sum('tags' in e for e in rows),
                                 'tag_counts': dict(sorted(keys.items())),
                                 'highway_values': dict(sorted(highways.items()))}
    result['interpretation'] = ('Counts only elements returned by the original pedestrian-network query; '
                                'not a census of OSM features or evidence of crossing safety.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
