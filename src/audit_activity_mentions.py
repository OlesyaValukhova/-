"""Find title-absent activity mentions in programme content for manual review."""
import argparse
import csv
import html
import json
import re
from pathlib import Path

TERMS = {'chess': re.compile(r'шахмат', re.I), 'basketball': re.compile(r'баскетбол', re.I)}
FIELDS = ('description_string', 'content_string', 'skills_string', 'competence_string',
          'material_technical_base_string', 'classes_requirements_string')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('directory', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rows, checked = [], 0
    for path in sorted(a.directory.glob('*-detail.json')):
        card = json.loads(path.read_text(encoding='utf8')); checked += 1
        title = html.unescape(str(card.get('name') or ''))
        for activity, pattern in TERMS.items():
            if pattern.search(title):
                continue
            for field in FIELDS:
                content = html.unescape(str(card.get(field) or ''))
                match = pattern.search(content)
                if match:
                    snippet = re.sub(r'\s+', ' ', content[max(0, match.start()-90):match.end()+140]).strip()
                    rows.append({'activity': activity, 'program_id': card['id'], 'title': title,
                                 'field': field, 'snippet': snippet, 'card_file': str(path)})
    a.output.mkdir(parents=True, exist_ok=True)
    with (a.output/'candidates.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['activity', 'program_id', 'title', 'field', 'snippet', 'card_file']); w.writeheader(); w.writerows(rows)
    (a.output/'summary.json').write_text(json.dumps({'cards_checked': checked, 'candidate_field_mentions': len(rows),
        'unique_candidate_programmes_by_activity': {a: len({r['program_id'] for r in rows if r['activity']==a}) for a in TERMS},
        'interpretation': 'Text matches are candidates only; they may describe equipment, examples or other activities.'}, indent=2), encoding='utf8')
    print((a.output/'summary.json').read_text(encoding='utf8'))


if __name__ == '__main__':
    main()
