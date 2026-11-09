"""Read-only ten-minute watchdog for a running Navigator collection on Windows."""
import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import time


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


def process_alive(pid):
    result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                            capture_output=True, timeout=20)
    if result.returncode:
        return None
    for row in csv.reader(io.StringIO(result.stdout.decode(errors='replace'))):
        if len(row) > 1 and row[1] == str(pid):
            return True
    return False


def snapshot(root, pid):
    pages = sorted((root / 'catalogue').glob('page-*.json'))
    count = 0
    declared = None
    newest = None
    for page in pages:
        data = load_json(page)
        if data is not None:
            count += len(data.get('results', []))
            declared = data.get('count', declared)
            newest = max(newest or 0, page.stat().st_mtime)
    catalogue = load_json(root / 'catalogue' / 'manifest.json')
    details = load_json(root / 'program-details' / 'manifest.json')
    alive = process_alive(pid)
    state = 'collecting_catalogue'
    if details:
        state = 'collecting_details'
        newest = max(newest or 0, (root / 'program-details' / 'manifest.json').stat().st_mtime)
    if catalogue and catalogue.get('status') == 'error':
        state = 'catalogue_error'
    if details and details.get('status') == 'complete_selection':
        state = 'complete'
    elif details and details.get('status') in ('stopped_after_consecutive_failures', 'partial_selection'):
        state = 'details_incomplete'
    elif alive is False:
        state = 'process_stopped_check_results'
    age = time.time() - newest if newest is not None else None
    return {'checked_utc': datetime.now(timezone.utc).isoformat(), 'collector_pid': pid,
            'process_alive': alive, 'state': state, 'saved_page_records_not_unique_audit': count,
            'api_declared_count': declared, 'saved_pages': len(pages),
            'details_saved': details.get('saved') if details else None,
            'details_requested': details.get('requested') if details else None,
            'details_failures_this_run': details.get('failure_count') if details else None,
            'catalogue_status': catalogue.get('status') if catalogue else None,
            'details_status': details.get('status') if details else None,
            'seconds_since_latest_write': age,
            'stalled_warning': alive is True and age is not None and age > 1200}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--interval', type=int, default=600)
    parser.add_argument('--hours', type=float, default=72)
    args = parser.parse_args()
    if args.interval < 60 or not 0 < args.hours <= 168 or not args.run.is_dir():
        parser.error('Require existing run, interval>=60s, hours<=168')
    deadline = time.monotonic() + args.hours * 3600
    while time.monotonic() < deadline:
        try:
            report = snapshot(args.run, args.pid)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            report = {'checked_utc': datetime.now(timezone.utc).isoformat(),
                      'state': 'observation_error', 'error': str(exc)}
        with (args.run / 'monitor.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(report, ensure_ascii=False) + '\n')
        temporary = args.run / 'monitor-status.json.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(args.run / 'monitor-status.json')
        if report['state'] in ('complete', 'catalogue_error', 'details_incomplete', 'process_stopped_check_results'):
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
