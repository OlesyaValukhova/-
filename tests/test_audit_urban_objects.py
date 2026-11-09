import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audit_urban_objects import audit


class UrbanAuditTests(unittest.TestCase):
    def sample(self, folder, records, status='pagination_finished', count=None):
        raw = json.dumps({'count': len(records) if count is None else count,
                          'results': records}).encode()
        (folder / 'page.json').write_bytes(raw)
        manifest = {'source': 'https://example.test/api', 'status': status,
                    'next': None if status == 'pagination_finished' else '/next',
                    'pages': [{'file': 'page.json', 'rows': len(records),
                               'sha256': hashlib.sha256(raw).hexdigest()}]}
        (folder / 'manifest.json').write_text(json.dumps(manifest))

    def object(self, geometry_id=10):
        return {'physical_object_id': 1, 'object_geometry_id': geometry_id,
                'geometry': {'type': 'Point', 'coordinates': [30, 60]}}

    def test_running_and_truncated_exports_are_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for status, count in [('running', 1), ('pagination_finished', 2)]:
                self.sample(folder, [self.object()], status, count)
                self.assertFalse(audit(folder)['complete_api_traversal_verified'])

    def test_geometry_pairs_distinguish_multiple_geometries_from_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.sample(folder, [self.object(), self.object(11)])
            r = audit(folder)
            self.assertEqual(r['repeated_physical_object_rows'], 1)
            self.assertTrue(r['complete_api_traversal_verified'])
            self.sample(folder, [self.object(), self.object()])
            self.assertFalse(audit(folder)['complete_api_traversal_verified'])

    def test_modified_page_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.sample(folder, [self.object()])
            (folder / 'page.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                audit(folder)
