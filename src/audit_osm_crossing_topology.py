"""Describe OSM road/crossing topology within an existing Overpass response."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

ROAD = {'primary', 'secondary', 'tertiary', 'residential', 'unclassified',
        'primary_link', 'secondary_link', 'tertiary_link', 'living_street'}
WALK = {'footway', 'path', 'pedestrian', 'steps'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.source.read_text(encoding='utf8'))
    ways = [e for e in raw['elements'] if e['type'] == 'way' and e.get('tags', {}).get('highway')]
    refs = defaultdict(set)
    for way in ways:
        for node in way['nodes']:
            refs[node].add(way['tags']['highway'])
    nodes = [e for e in raw['elements'] if e['type'] == 'node' and
             e.get('tags', {}).get('highway') == 'crossing']
    counts = Counter()
    crossing_values = Counter()
    for node in nodes:
        kinds = refs[node['id']]
        road, walk = bool(kinds & ROAD), bool(kinds & WALK)
        counts['road_and_explicit_walk' if road and walk else 'road_only' if road else
               'explicit_walk_only' if walk else 'neither'] += 1
        crossing_values[node.get('tags', {}).get('crossing', '<missing>')] += 1
    road_ways = [w for w in ways if w['tags']['highway'] in ROAD]
    per_class = {}
    for highway in sorted(ROAD):
        group = [w for w in road_ways if w['tags']['highway'] == highway]
        per_class[highway] = {'ways': len(group),
                              'maxspeed_tagged': sum('maxspeed' in w['tags'] for w in group),
                              'lanes_tagged': sum('lanes' in w['tags'] for w in group)}
    result = {'source': str(args.source), 'timestamp_osm_base': raw.get('osm3s', {}).get('timestamp_osm_base'),
              'crossing_nodes': len(nodes), 'shared_osm_node_topology': dict(counts),
              'crossing_tag_values': dict(crossing_values), 'road_way_tag_counts': per_class,
              'limitations': ['Bounding box, not administrative district; line segments not road length.',
                              'Only nodes returned as members of requested ways; standalone crossing nodes can be absent.',
                              'Shared IDs are strict topology, not geometric proximity or a validated crossing.',
                              'OSM missing tag is unknown, not absence; no completeness or safety validation.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
