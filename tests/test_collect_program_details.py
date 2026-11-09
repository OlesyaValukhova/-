import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import collect_program_details as collector
from parse_navigator import URL


class DetailsRecoveryTests(unittest.TestCase):
    def test_checkpoint_retries_temporary_windows_file_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'manifest.json'
            target.write_text('{"status":"old"}', encoding='utf-8')
            original = Path.replace
            calls = []

            def locked_replace(temporary, destination):
                calls.append(str(destination))
                if len(calls) < 3:
                    raise PermissionError('Temporary reader lock')
                return original(temporary, destination)

            with patch.object(Path, 'replace', new=locked_replace), patch.object(collector.time, 'sleep'):
                collector.atomic_json(target, {'status': 'new'})
            self.assertEqual(len(calls), 3)
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['status'], 'new')

    def test_fatal_checkpoint_error_is_recorded_as_terminal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'pages.json'
            source.write_text(json.dumps({'pages': [{'url': URL, 'response': {
                'count': 1, 'results': [{'id': 1}], 'next': None, 'previous': None}}]}), encoding='utf-8')
            output = root / 'details'
            argv = ['collector', '--catalogue', str(source), '--output', str(output)]
            original = collector.atomic_json
            checkpoints = []

            def fail_one_checkpoint(path, value):
                if path.name == 'manifest.json':
                    checkpoints.append(1)
                    if len(checkpoints) == 2:
                        raise RuntimeError('Unexpected checkpoint failure')
                return original(path, value)

            with patch.object(sys, 'argv', argv), patch.object(collector, 'fetch_page', return_value=b'{"id":1}'), patch.object(collector, 'atomic_json', side_effect=fail_one_checkpoint), patch('builtins.print'):
                self.assertEqual(collector.main(), 3)
            manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'], 'fatal_error')
            self.assertIn('Unexpected checkpoint failure', manifest['fatal_error'])
            self.assertTrue((output / '1-detail.json').exists())

    def test_failed_run_resumes_without_redownloading_saved_cards(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'pages.json'
            source.write_text(json.dumps({'pages': [{'url': URL, 'response': {
                'count': 3, 'results': [{'id': i} for i in [1, 2, 3]],
                'next': None, 'previous': None}}]}), encoding='utf-8')
            output = root / 'details'
            argv = ['collector', '--catalogue', str(source), '--output', str(output), '--failure-stop', '1']
            calls = []

            def first_fetch(opener, url, timeout, retries, attempts):
                item_id = int(url.rstrip('/').split('/')[-1])
                calls.append(item_id)
                attempts.append({'url': url})
                if item_id == 2:
                    raise URLError('temporary connection failure')
                return json.dumps({'id': item_id}).encode()

            with patch.object(sys, 'argv', argv), patch.object(collector, 'fetch_page', first_fetch), patch.object(collector.time, 'sleep'):
                self.assertEqual(collector.main(), 3)
            self.assertEqual(calls, [1, 2])
            self.assertTrue((output / '1-detail.json').exists())

            def resumed_fetch(opener, url, timeout, retries, attempts):
                item_id = int(url.rstrip('/').split('/')[-1])
                calls.append(item_id)
                attempts.append({'url': url})
                return json.dumps({'id': item_id}).encode()

            with patch.object(sys, 'argv', argv), patch.object(collector, 'fetch_page', resumed_fetch), patch.object(collector.time, 'sleep'):
                self.assertEqual(collector.main(), 0)
            self.assertEqual(calls, [1, 2, 2, 3])
            manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['saved'], 3)
            self.assertEqual(manifest['attempt_count'], 2)
            self.assertNotIn('attempts', manifest)
            attempts = [json.loads(line) for line in (output / 'attempts.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([a['program_id'] for a in attempts], [1, 2, 2, 3])

    def test_wrong_card_id_is_rejected(self):
        for raw in [b'{"id": 2}', b'{"id": true}', b'[]']:
            with self.assertRaises(ValueError):
                collector.validate_card(raw, 1)


if __name__ == '__main__':
    unittest.main()
