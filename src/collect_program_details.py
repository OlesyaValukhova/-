"""Checkpointed collection of public program cards from an explicit catalogue.

Does not certify current enrolment, venue accuracy, or complete city coverage.
Stops after consecutive failures instead of repeatedly hitting an unavailable host.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import traceback
from urllib.request import ProxyHandler, build_opener

from collect_navigator import BASE, PublicRedirect
from parse_navigator import aggregate, fetch_page


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows readers (including Get-Content/OneDrive) may briefly lock the target.
    for retry in range(8):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if retry == 7:
                raise
            time.sleep(min(1, 0.1 * 2 ** retry))


def append_jsonl(path, records):
    with path.open('a', encoding='utf-8') as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')


def validate_card(raw, item_id):
    card = json.loads(raw)
    if not isinstance(card, dict) or type(card.get('id')) is not int or card['id'] != item_id:
        raise ValueError('Card ID/schema does not match requested program')
    return card


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--limit', type=int, help='Diagnostic prefix only; omitted means all catalogue IDs')
    parser.add_argument('--ids-file', type=Path, help='Explicit JSON list of unique catalogue IDs for a spatial pilot')
    parser.add_argument('--reuse-cards', type=Path, help='Copy validated cached cards into this separate output')
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--delay', type=float, default=1)
    parser.add_argument('--failure-stop', type=int, default=3)
    args = parser.parse_args()
    if not (0 < args.timeout <= 60 and args.delay >= 1 and 1 <= args.failure_stop <= 5
            and (args.limit is None or args.limit > 0)):
        parser.error('Require timeout<=60, delay>=1, failure-stop 1..5, positive limit')
    source = args.catalogue.read_bytes()
    rows, coverage = aggregate(json.loads(source)['pages'])
    if not rows:
        parser.error('Source catalogue has no records')
    ids = [row['id'] for row in rows]
    if args.ids_file:
        selected_ids = json.loads(args.ids_file.read_text(encoding='utf-8-sig'))
        if (not isinstance(selected_ids, list) or not selected_ids
                or any(type(i) is not int for i in selected_ids)
                or len(set(selected_ids)) != len(selected_ids)
                or not set(selected_ids).issubset(ids) or args.limit is not None):
            parser.error('Explicit IDs must be unique integers from catalogue; do not combine with limit')
        ids = selected_ids
    if args.limit is not None:
        ids = ids[:args.limit]
    selection = {'source_sha256': hashlib.sha256(source).hexdigest(), 'ids': ids,
                 'selection': 'all source catalogue IDs' if args.limit is None else 'diagnostic catalogue prefix',
                 'source_catalogue_coverage': coverage}
    if args.ids_file:
        selection.update(selection='explicit spatial pilot IDs',
                         ids_file_sha256=hashlib.sha256(args.ids_file.read_bytes()).hexdigest())
    args.output.mkdir(parents=True, exist_ok=True)
    selection_path = args.output / 'selection.json'
    if selection_path.exists():
        if json.loads(selection_path.read_text(encoding='utf-8')) != selection:
            parser.error('Existing output belongs to a different source or selection')
    else:
        if any(args.output.iterdir()):
            parser.error('Nonempty output without selection manifest')
        atomic_json(selection_path, selection)
    opener = build_opener(PublicRedirect(), ProxyHandler({}))
    run = {'started_utc': datetime.now(timezone.utc).isoformat(), 'status': 'running',
           'requested': len(ids), 'saved': 0, 'attempt_count': 0, 'failure_count': 0,
           'attempts_jsonl': 'attempts.jsonl', 'failures_jsonl': 'failures.jsonl',
           'complete_city_export': False, 'current_enrolment_verified': False}
    consecutive = 0
    manifest = args.output / 'manifest.json'
    atomic_json(manifest, run)
    try:
        for item_id in ids:
            target = args.output / f'{item_id}-detail.json'
            cached = args.reuse_cards / target.name if args.reuse_cards else None
            if not target.exists() and cached and cached.is_file():
                raw = cached.read_bytes()
                validate_card(raw, item_id)
                temporary = target.with_suffix('.json.tmp')
                temporary.write_bytes(raw)
                temporary.replace(target)
            if target.exists():
                validate_card(target.read_bytes(), item_id)
                run['saved'] += 1
                continue
            if run['attempt_count']:
                time.sleep(args.delay)
            attempts = []
            try:
                raw = fetch_page(opener, BASE + f'/api/program/{item_id}/', args.timeout, 0, attempts)
                validate_card(raw, item_id)
                temporary = target.with_suffix('.json.tmp')
                temporary.write_bytes(raw)
                temporary.replace(target)
                run['saved'] += 1
                consecutive = 0
            except (OSError, ValueError) as exc:
                append_jsonl(args.output / 'failures.jsonl', [
                    {'id': item_id, 'run_started_utc': run['started_utc'],
                     'error': type(exc).__name__ + ': ' + str(exc)}])
                run['failure_count'] += 1
                consecutive += 1
            finally:
                for attempt in attempts:
                    attempt['program_id'] = item_id
                    attempt['run_started_utc'] = run['started_utc']
                append_jsonl(args.output / 'attempts.jsonl', attempts)
                run['attempt_count'] += len(attempts)
            atomic_json(manifest, run)
            print(f"saved={run['saved']}/{len(ids)} failures={run['failure_count']}", flush=True)
            if consecutive >= args.failure_stop:
                run['status'] = 'stopped_after_consecutive_failures'
                break
        else:
            run['status'] = 'complete_selection' if run['saved'] == len(ids) else 'partial_selection'
    except KeyboardInterrupt:
        run['status'] = 'interrupted'
    except Exception as exc:
        run['status'] = 'fatal_error'
        run['fatal_error'] = type(exc).__name__ + ': ' + str(exc)
        run['traceback'] = traceback.format_exc()
        print(run['traceback'], flush=True)
    finally:
        run['finished_utc'] = datetime.now(timezone.utc).isoformat()
        atomic_json(manifest, run)
    return 0 if run['status'] == 'complete_selection' else 3


if __name__ == '__main__':
    raise SystemExit(main())
