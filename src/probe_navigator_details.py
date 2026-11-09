"""Small same-host probe of a known public UI and its referenced JS assets."""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import build_opener, ProxyHandler

from collect_navigator import BASE, PublicRedirect, public_url
from parse_navigator import fetch_page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--assets', action='store_true', help='Discover frontend assets instead of sampling details')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    opener = build_opener(PublicRedirect(), ProxyHandler({}))
    attempts = []
    try:
        if not args.assets:
            source = Path(__file__).resolve().parents[1] / 'data/navigator/direct-20261020-150408/catalogue/pages.json'
            bundle = json.loads(source.read_text(encoding='utf-8'))
            rows = [r for p in bundle['pages'] for r in p['response']['results']]
            # Diagnostic sample, not a representative sample of spatial accessibility.
            selected = [next(r for r in rows if r['id'] == 13702)]
            seen = {selected[0]['organization']}
            for row in rows:
                if row['organization'] not in seen:
                    selected.append(row)
                    seen.add(row['organization'])
                if len(selected) == 12:
                    break
            (args.output / 'sample.json').write_text(json.dumps(
                {'selection': 'First listed program from 12 distinct organization labels, including 13702; diagnostic only',
                 'ids': [r['id'] for r in selected], 'source': str(source)}, ensure_ascii=False, indent=2), encoding='utf-8')
            for row in selected:
                for kind, suffix in [('detail', '/'), ('groups', '/group/')]:
                    time.sleep(2)
                    url = BASE + f"/api/program/{row['id']}" + suffix
                    raw = fetch_page(opener, url, 15, 1, attempts)
                    json.loads(raw)
                    (args.output / f"{row['id']}-{kind}.json").write_bytes(raw)
                    print(f"Saved {row['id']} {kind}", flush=True)
            return
        url = BASE + '/programs/13702/groups/'
        html = fetch_page(opener, url, 15, 1, attempts).decode('utf-8')
        (args.output / 'groups.html').write_text(html, encoding='utf-8')
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)', html)
        discovered = []
        for src in scripts:
            if src.startswith('data:'):
                continue
            asset = urljoin(url, src)
            try:
                public_url(asset)
            except ValueError:
                continue
            if asset not in discovered:
                discovered.append(asset)
        print('Referenced JS files:', len(discovered), flush=True)
        snippets = []
        for index, asset in enumerate(discovered):
            time.sleep(2)
            raw = fetch_page(opener, asset, 15, 1, attempts)
            (args.output / f'asset-{index}.js').write_bytes(raw)
            text = raw.decode('utf-8', errors='replace')
            for match in re.finditer(r'list_odo|age_from|age_to|min_age|max_age|/api/|program/|group/', text):
                snippets.append({'asset': asset, 'offset': match.start(),
                                 'text': text[max(0, match.start()-150):match.end()+200]})
        (args.output / 'snippets.json').write_text(json.dumps(snippets, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Saved endpoint/schema snippets:', len(snippets), flush=True)
    finally:
        (args.output / 'requests.json').write_text(json.dumps(attempts, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
