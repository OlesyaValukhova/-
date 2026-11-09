"""Compare programme coordinates with organisation addresses in saved cards."""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path


def distance_m(a, b, c, d):
    r = math.pi / 180
    h = math.sin((c-a)*r/2)**2 + math.cos(a*r)*math.cos(c*r)*math.sin((d-b)*r/2)**2
    return 12742017.6 * math.asin(min(1, math.sqrt(h)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('inventory', type=Path)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rows = list(csv.DictReader(a.inventory.open(encoding='utf-8-sig', newline='')))
    results, group_keys = [], Counter()
    for row in rows:
        card = json.loads((a.workspace / row['card_file']).read_text(encoding='utf8'))
        coords = (card.get('latitude'), card.get('longitude'))
        distances = []
        for addr in (card.get('organization') or {}).get('addresses') or []:
            if all(v is not None for v in (*coords, addr.get('latitude'), addr.get('longitude'))):
                distances.append((distance_m(float(coords[0]), float(coords[1]),
                                             float(addr['latitude']), float(addr['longitude'])), addr))
        matches = [addr for dist, addr in distances if dist <= 1]
        for group in card.get('groups') or []:
            group_keys.update(group.keys())
        results.append({'program_id': row['program_id'], 'scope': row['scope'],
                        'organization_addresses_with_coordinates': len(distances),
                        'nearest_organization_address_m': round(min((dist for dist, _ in distances), default=-1), 3),
                        'matching_address_types_within_1m': '|'.join(str(x.get('address_type', '')) for x in matches),
                        'exact_match_count': len(matches), 'embedded_groups': len(card.get('groups') or [])})
    a.output.mkdir(parents=True, exist_ok=True)
    with (a.output / 'program-address-comparison.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys()); writer.writeheader(); writer.writerows(results)
    summary = {'programs': len(results), 'matched_organization_coordinate_within_1m': sum(r['exact_match_count'] > 0 for r in results),
               'nearest_over_1m': sum(r['nearest_organization_address_m'] > 1 for r in results),
               'no_comparable_organization_coordinates': sum(r['nearest_organization_address_m'] < 0 for r in results),
               'group_fields': dict(group_keys),
               'limitations': ['Coordinate matches do not establish a group teaching venue or current accuracy.',
                               'Addresses and coordinates are from one provider, not independent confirmation.',
                               'Sample limited to selected chess programmes.']}
    (a.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
