"""List textual activity mentions for review; a mention is not an activity classification."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from collect_program_details import validate_card


TERMS = {'шахматы': 'шахмат', 'баскетбол': 'баскетбол', 'футбол': 'футбол'}
FIELDS = ('description_string', 'content_string')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--details', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--review', type=Path, help='Optional explicit review decisions for this snapshot')
    a = p.parse_args()
    if a.output.exists():
        p.error('Output must be new')
    files = sorted(a.details.glob('*-detail.json'))
    results, counts = [], Counter()
    for file in files:
        raw = file.read_bytes()
        card = validate_card(raw, int(file.name.split('-')[0]))
        title = card.get('name') or ''
        for kind, term in TERMS.items():
            title_hit = term in title.casefold()
            counts[f'{kind}:title'] += title_hit
            hit = None
            for field in FIELDS:
                value = card.get(field)
                if value is None:
                    continue
                if not isinstance(value, str):
                    raise ValueError(f'Unexpected field type: {field} in {card["id"]}')
                match = re.search(re.escape(term), value, re.IGNORECASE)
                if match:
                    hit = (field, re.sub(r'\s+', ' ', value[max(0, match.start()-100):match.end()+160]))
                    break
            if hit and not title_hit:
                counts[f'{kind}:description_only'] += 1
                results.append({'program_id': card['id'], 'program_name': title, 'search_term': kind,
                    'field': hit[0], 'context': hit[1], 'classification': 'не оценено',
                    'card_sha256': hashlib.sha256(raw).hexdigest()})
    if a.review:
        decisions = json.loads(a.review.read_text(encoding='utf-8'))['decisions']
        lookup = {(str(d['program_id']), d['search_term']): d for d in decisions}
        if len(lookup) != len(decisions):
            raise ValueError('Duplicate review decisions')
        if set(lookup) != {(str(r['program_id']), r['search_term']) for r in results}:
            raise ValueError('Review decisions do not exactly match current snapshot candidates')
        for r in results:
            d = lookup[(str(r['program_id']), r['search_term'])]
            r['classification'] = d['assessment']
            r['review_reason'] = d['reason']
    a.output.mkdir(parents=True)
    with (a.output / 'description-mentions-for-review.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['program_id', 'program_name', 'search_term', 'field', 'context', 'classification', 'review_reason', 'card_sha256'])
        w.writeheader()
        w.writerows(results)
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'cards_scanned': len(files),
              'fields_searched': list(FIELDS), 'counts': dict(counts),
              'review': {'path': str(a.review), 'sha256': hashlib.sha256(a.review.read_bytes()).hexdigest()} if a.review else None,
              'scope': 'Only the saved coordinate-selected programme cards; first textual occurrence per activity and field order.',
              'limitations': ['A mention is not evidence of an actual dedicated class: it may be incidental, figurative or one part of a multi-activity programme.',
                  'Absence of a search word does not exclude an activity and does not assess the rest of the catalogue.',
                  'Current group, location, enrolment, and age suitability require independent checks.']}
    (a.output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report['counts'], ensure_ascii=True))


if __name__ == '__main__':
    main()
