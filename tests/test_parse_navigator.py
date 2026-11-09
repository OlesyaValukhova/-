import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from parse_navigator import aggregate, URL, fetch_page, checkpoint
from unittest.mock import Mock
from urllib.error import URLError, HTTPError
import tempfile
import json


def page(url, count, ids, following, previous=None):
    return {"url": url, "response": {"count": count, "results": [{"id": x} for x in ids],
                                    "next": following, "previous": previous}}


class CoverageTests(unittest.TestCase):
    def test_realistic_first_page_does_not_mean_full_export(self):
        _, summary = aggregate([page(URL, 1554, range(10), URL.replace("offset=0", "offset=10"))])
        self.assertFalse(summary["complete_filtered_catalogue"])

    def test_consecutive_pages_match_total(self):
        following = URL.replace("offset=0", "offset=10")
        _, summary = aggregate([page(URL, 3, [1, 2], following),
                                page(following, 3, [3], None, URL)])
        self.assertTrue(summary["complete_filtered_catalogue"])
        self.assertFalse(summary["complete_city_export"])

    def test_overlapping_pages_not_certified(self):
        following = URL.replace("offset=0", "offset=10")
        records, summary = aggregate([page(URL, 2, [1], following),
                                     page(following, 2, [1, 2], None, URL)])
        self.assertEqual(len(records), 2)
        self.assertFalse(summary["complete_filtered_catalogue"])

    def test_unfiltered_api_coverage_is_not_market_coverage(self):
        city_url = URL.replace('district=2&', '')
        _, summary = aggregate([page(city_url, 2, [1, 2], None)])
        self.assertTrue(summary['complete_unfiltered_api_catalogue'])
        self.assertFalse(summary['complete_city_export'])
        _, district_summary = aggregate([page(URL, 2, [1, 2], None)])
        self.assertFalse(district_summary['complete_unfiltered_api_catalogue'])

    def test_filtered_and_partial_city_catalogues_are_not_city_complete(self):
        city_url = URL.replace('district=2&', '')
        _, partial = aggregate([page(city_url, 3, [1, 2], city_url.replace('offset=0', 'offset=2'))])
        self.assertFalse(partial['complete_unfiltered_api_catalogue'])
        _, filtered = aggregate([page(city_url + '&payment=free', 2, [1, 2], None)])
        self.assertFalse(filtered['complete_unfiltered_api_catalogue'])

    def test_saved_page_without_request_is_not_certified(self):
        _, summary = aggregate([page(None, 1, [1], None)])
        self.assertFalse(summary["complete_filtered_catalogue"])

    def test_different_districts_cannot_merge(self):
        with self.assertRaises(ValueError):
            aggregate([page(URL, 2, [1], URL), page(URL.replace("district=2", "district=3"), 2, [2], None)])


class RecoveryTests(unittest.TestCase):
    def test_transient_failure_retries_same_page(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{}'
        response.status, response.url = 200, URL
        opener = Mock()
        opener.open.side_effect = [URLError("timeout"), response]
        attempts, delays = [], []
        self.assertEqual(fetch_page(opener, URL, 10, 1, attempts, delays.append), b'{}')
        self.assertEqual(delays, [5])
        self.assertEqual(len(attempts), 2)

    def test_forbidden_is_not_retried(self):
        opener = Mock()
        opener.open.side_effect = HTTPError(URL, 403, "Forbidden", {}, None)
        with self.assertRaises(HTTPError):
            fetch_page(opener, URL, 10, 3, [], lambda _: self.fail("Unexpected retry"))
        self.assertEqual(opener.open.call_count, 1)

    def test_checkpoint_preserves_resumable_chain(self):
        following = URL.replace("offset=0", "offset=10")
        pages = [page(URL, 2, [1], following)]
        with tempfile.TemporaryDirectory() as folder:
            checkpoint(Path(folder), pages)
            restored = json.loads((Path(folder) / "pages.json").read_text(encoding="utf-8"))["pages"]
        _, summary = aggregate(restored + [page(following, 2, [2], None, URL)])
        self.assertTrue(summary["complete_filtered_catalogue"])


if __name__ == "__main__":
    unittest.main()
