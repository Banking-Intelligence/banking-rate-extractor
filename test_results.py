import datetime as dt
import tempfile
import unittest
from pathlib import Path

from extractor import ReviewRequired
from run_extract import build_result, result_path, source_is_publishable


SOURCE = {"id": "src-test", "url": "https://example.com/rates", "group": "bank"}
NOW = dt.datetime(2026, 9, 11, 1, 2, 3, tzinfo=dt.timezone.utc)


class ResultContractTests(unittest.TestCase):
    def test_success_contract(self):
        result = build_result(SOURCE, lambda _: {"status": "ok", "records": [{"id": "r1"}], "fingerprint": "abc", "source_url": SOURCE["url"]}, NOW)
        self.assertEqual(1, result["schema_version"])
        self.assertEqual("src-test", result["source_id"])
        self.assertEqual("ok", result["status"])
        self.assertEqual("2026-09-11T01:02:03+00:00", result["checked_at"])

    def test_review_retains_empty_records(self):
        def review(_):
            raise ReviewRequired("ambiguous table")
        result = build_result(SOURCE, review, NOW)
        self.assertEqual("review", result["status"])
        self.assertEqual([], result["records"])

    def test_failure_retains_empty_records(self):
        def fail(_):
            raise RuntimeError("network unavailable")
        result = build_result(SOURCE, fail, NOW)
        self.assertEqual("failed", result["status"])
        self.assertEqual([], result["records"])

    def test_result_path_cannot_escape_results(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                result_path("../secret", Path(directory))

    def test_bank_review_sources_are_not_scheduled(self):
        source = {"id": "directory-only", "group": "bank", "enabled": True, "adapter": "review"}
        self.assertFalse(source_is_publishable(source, "bank"))

    def test_mapped_bank_sources_are_scheduled(self):
        source = {"id": "mapped-bank", "group": "bank", "enabled": True, "adapter": "html-table"}
        self.assertTrue(source_is_publishable(source, "bank"))


if __name__ == "__main__":
    unittest.main()
