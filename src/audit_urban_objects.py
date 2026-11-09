"""Audit only pages committed to a collector manifest, including partial runs."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from shapely.geometry import shape


def audit(folder):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    ids, pairs, types, geometries, dates = Counter(), Counter(), Counter(), Counter(), Counter()
    declared, rows, bad_geometry, missing_ids = set(), 0, 0, 0
    for page in manifest['pages']:
        raw = (folder / page['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != page['sha256']:
            raise ValueError(f"Page checksum mismatch: {page['file']}")
        data = json.loads(raw)
        if data.get('count') is not None:
            declared.add(data['count'])
        if len(data['results']) != page['rows']:
            raise ValueError('Page row count mismatch')
        for obj in data['results']:
            rows += 1
            pid, gid = obj.get('physical_object_id'), obj.get('object_geometry_id')
            if pid is None or gid is None:
                missing_ids += 1
            else:
                ids[pid] += 1
                pairs[(pid, gid)] += 1
            t = obj.get('physical_object_type') or {}
            types[f"{t.get('physical_object_type_id')}: {t.get('name')}"] += 1
            dates[str(obj.get('updated_at', 'missing'))[:10]] += 1
            try:
                geom = shape(obj['geometry'])
                geometries[geom.geom_type] += 1
                if geom.is_empty or not geom.is_valid:
                    bad_geometry += 1
            except (ValueError, TypeError, KeyError, AttributeError):
                bad_geometry += 1
    exact = len(declared) == 1 and rows == next(iter(declared))
    return {
        'audited_utc': datetime.now(timezone.utc).isoformat(),
        'source_manifest_status': manifest['status'], 'source': manifest['source'],
        'pages': len(manifest['pages']), 'rows': rows, 'declared_counts': sorted(declared),
        'unique_physical_object_ids': len(ids), 'unique_object_geometry_pairs': len(pairs),
        'repeated_physical_object_rows': sum(n-1 for n in ids.values()),
        'duplicate_object_geometry_pairs': sum(n-1 for n in pairs.values()),
        'missing_identifiers': missing_ids, 'object_types': dict(types),
        'geometry_types': dict(geometries), 'invalid_empty_or_unreadable_geometry': bad_geometry,
        'api_update_dates': dict(sorted(dates.items())),
        'complete_api_traversal_verified': (
            manifest['status'] == 'pagination_finished' and not manifest.get('next')
            and exact and not missing_ids and len(pairs) == rows),
        'limitations': [
            'A running collector yields a partial, nonrandom snapshot.',
            'API completeness is not completeness of real buildings in the city.',
            'Repeated physical IDs may represent multiple geometries; pairs are audited separately.',
            'API update dates are not confirmed field observation dates.',
            'Geometry validity does not establish accurate footprints or residential entrances.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = audit(a.input)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['pages', 'rows', 'duplicate_object_geometry_pairs',
        'invalid_empty_or_unreadable_geometry', 'complete_api_traversal_verified']}))


if __name__ == '__main__':
    main()
