"""Archive Urban API cursor pages without discarding source attributes.

Restart with the same command to resume. Records are physical objects, not
necessarily buildings: select verified object types separately after inspection.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import urlopen


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', default='https://urban-api.testing.idulab.ru')
    p.add_argument('--territory', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--page-size', type=int, default=500)
    p.add_argument('--function', type=int, help='Physical object function ID; 1 is building in the archived dictionary')
    p.add_argument('--max-pages', type=int, default=0,
                   help='Optional limit for a diagnostic run; 0 collects all pages')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    start = a.base.rstrip('/') + f'/api/v2/territory/{a.territory}/physical_objects_with_geometry?'
    query = {'include_child_territories': 'true', 'page_size': a.page_size}
    if a.function is not None:
        query['physical_object_function_id'] = a.function
    start += urlencode(query)
    url, visited, counts, pages = start, set(), [], []
    manifest = {'source': start, 'territory_id': a.territory,
                'started_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'running', 'pages': pages}
    try:
        while url:
            url = urljoin(a.base, url)
            if urlsplit(url).netloc != urlsplit(a.base).netloc:
                raise ValueError('Pagination points to a different host')
            if url in visited:
                raise ValueError('Repeated pagination URL')
            visited.add(url)
            path = a.output / f'page-{len(pages):05d}.json'
            meta = path.with_suffix('.source.json')
            if path.exists():
                if not meta.exists() or json.loads(meta.read_text())['url'] != url:
                    raise ValueError(f'Cached page source mismatch: {path}')
                raw = path.read_bytes()
            else:
                for attempt in range(3):
                    try:
                        with urlopen(url, timeout=120) as r:
                            raw = r.read()
                        break
                    except (OSError, TimeoutError) as exc:
                        if attempt == 2:
                            raise
                        print(f'Page request failed: {type(exc).__name__}; retry {attempt + 1}/2', flush=True)
                        time.sleep(10 * (attempt + 1))
                json.loads(raw)
                path.write_bytes(raw)
                meta.write_text(json.dumps({'url': url}), encoding='utf-8')
                time.sleep(0.5)
            data = json.loads(raw)
            if not isinstance(data.get('results'), list):
                raise ValueError('Expected cursor response with results list')
            counts.append(data.get('count'))
            pages.append({'file': path.name, 'rows': len(data['results']),
                          'sha256': hashlib.sha256(raw).hexdigest()})
            url = data.get('next')
            manifest.update(rows=sum(x['rows'] for x in pages),
                            declared_counts=sorted(set(x for x in counts if x is not None)),
                            next=url)
            (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            print(f"pages={len(pages)} rows={manifest['rows']} next={bool(url)}", flush=True)
            if a.max_pages and len(pages) >= a.max_pages and url:
                manifest['status'] = 'partial_page_limit'
                break
        else:
            manifest['status'] = 'pagination_finished'
    except Exception as exc:
        manifest.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (a.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
