"""Offline regression coverage for unavailable URLhaus feed retry amplification."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "real_osint_ioc_enricher.py"
CSV = '1,2026-10-07,https://malicious.example/payload,online,,malware_download,loader,,researcher\n'


class UrlhausCacheTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("offline_urlhaus_enricher", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module.IOC_CACHE_DIR = Path(self.temp.name)
        self.now = 10000.0
        patcher = mock.patch.object(self.module.time, "time", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_outage_is_one_request_across_thirty_advisories(self):
        def unavailable(*args, **kwargs):
            self.now += 20
            return None

        started = self.now
        with mock.patch.object(self.module, "_http_get", side_effect=unavailable) as fetch:
            for _ in range(30):
                self.assertEqual(self.module.fetch_urlhaus_iocs_for_threat_type("malware", []), [])
        self.assertEqual(fetch.call_count, 1)
        self.assertLess(self.now - started, 8 * 60)
        self.assertFalse((self.module.IOC_CACHE_DIR / "urlhaus_recent.json").exists())

    def test_unavailable_response_types_are_memoized_without_indicators(self):
        for response in (None, "", {"error": "source unavailable"}):
            with self.subTest(response=response):
                self.module._urlhaus_cache = None
                self.module._urlhaus_cache_ts = 0
                with mock.patch.object(self.module, "_http_get", return_value=response) as fetch:
                    self.assertEqual(self.module._load_urlhaus_feed(), [])
                    self.assertEqual(self.module._load_urlhaus_feed(), [])
                self.assertEqual(fetch.call_count, 1)

    def test_source_is_retried_at_existing_ttl_and_can_recover(self):
        with mock.patch.object(self.module, "_http_get", side_effect=[None, CSV]) as fetch:
            self.assertEqual(self.module._load_urlhaus_feed(), [])
            self.now += self.module.URLHAUS_CACHE_TTL - 1
            self.assertEqual(self.module._load_urlhaus_feed(), [])
            self.assertEqual(fetch.call_count, 1)
            self.now += 1
            recovered = self.module._load_urlhaus_feed()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(recovered[0]["value"], "https://malicious.example/payload")
        self.assertEqual(recovered[0]["source"], "URLhaus")

    def test_failed_fetch_does_not_refresh_or_overwrite_expired_disk_evidence(self):
        cache_file = self.module.IOC_CACHE_DIR / "urlhaus_recent.json"
        original = '[{"value":"old evidence"}]'
        cache_file.write_text(original)
        stale = self.now - self.module.URLHAUS_CACHE_TTL - 1
        os.utime(cache_file, (stale, stale))
        with mock.patch.object(self.module, "_http_get", return_value=None) as fetch:
            self.assertEqual(self.module._load_urlhaus_feed(), [])
            self.assertEqual(self.module._load_urlhaus_feed(), [])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(cache_file.read_text(), original)
        self.assertEqual(cache_file.stat().st_mtime, stale)

    def test_fresh_disk_cache_needs_no_network(self):
        cache_file = self.module.IOC_CACHE_DIR / "urlhaus_recent.json"
        cache_file.write_text(json.dumps([{"value": "existing measured indicator"}]))
        os.utime(cache_file, (self.now, self.now))
        with mock.patch.object(self.module, "_http_get", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.module._load_urlhaus_feed()[0]["value"], "existing measured indicator")

    def test_successful_csv_is_unchanged_and_cached(self):
        with mock.patch.object(self.module, "_http_get", return_value=CSV) as fetch:
            entries = self.module._load_urlhaus_feed()
            self.assertEqual(self.module._load_urlhaus_feed(), entries)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["confidence"], 80)
        self.assertEqual(json.loads((self.module.IOC_CACHE_DIR / "urlhaus_recent.json").read_text()), entries)


if __name__ == "__main__":
    unittest.main()
