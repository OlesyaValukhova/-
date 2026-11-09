"""Synthetic responses only; not evidence that the live Navigator is reachable."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "collector", Path(__file__).resolve().parents[1] / "src" / "collect_navigator.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class Response:
    status = 200
    headers = {"Content-Type": "application/json"}
    url = collector.DEFAULT

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return self.body[:limit]


class ProbeTests(unittest.TestCase):
    def test_cannot_follow_external_pagination(self):
        with self.assertRaises(ValueError):
            collector.next_page(collector.DEFAULT, {"next": "https://example.com/private"})

    def test_unknown_schema_is_not_empty_catalogue(self):
        with self.assertRaises(ValueError):
            collector.page_payload(b'{"message":"maintenance"}')

    def test_empty_incomplete_page_is_an_error(self):
        with self.assertRaises(ValueError):
            collector.next_page(collector.DEFAULT, {"results": [], "count": 20})

    def test_only_navigator_program_links(self):
        parser = collector.Links()
        parser.feed('<a href="/programs/123/groups/">x</a>'
                    '<a href="https://example.com/programs/456/">y</a>')
        self.assertEqual(parser.program_ids, {"123"})

    def test_html_challenge_is_preserved_without_false_success(self):
        body = b"<html>Service unavailable</html>"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "probe"
            with patch.object(collector, "build_opener") as factory:
                factory.return_value.open.return_value = Response(body)
                with patch("sys.argv", ["probe", "--output", str(output)]):
                    code = collector.main()
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(code, 2)
            self.assertEqual(manifest["status"], "blocked_or_schema_unverified")
            self.assertEqual((output / "response-001.bin").read_bytes(), body)
            self.assertFalse((output / "organizations.json").exists())


if __name__ == "__main__":
    unittest.main()
