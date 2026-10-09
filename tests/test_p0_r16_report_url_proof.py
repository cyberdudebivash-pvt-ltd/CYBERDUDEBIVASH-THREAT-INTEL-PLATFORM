"""P0 R16: an HTTPS link alone cannot certify a report was published."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_reports as vr  # noqa: E402


class ReportUrlProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.tmp.name)
        self.now = datetime(2026, 10, 9, 3, 10, tzinfo=timezone.utc)

    def tearDown(self):
        os.chdir(self.previous)
        self.tmp.cleanup()

    def advisory(self, age_hours=1, **override):
        entry = {
            "id": "intel--proof-negative",
            "tlp": "TLP:CLEAR",
            "processed_at": (self.now - timedelta(hours=age_hours)).isoformat(),
            "report_url": "https://intel.cyberdudebivash.com/reports/2026/10/intel--proof-negative.html",
        }
        entry.update(override)
        return entry

    def inspect(self, entry, published_ids=None):
        return vr._validate_one(
            entry, 0, now=self.now, window_hours=24,
            published_ids=published_ids if published_ids is not None else set(),
        )

    def test_branded_https_url_without_file_is_not_automatic_pass(self):
        failures, disposition = self.inspect(self.advisory())
        self.assertEqual(disposition, "FAIL")
        self.assertTrue(any("RULE 3 FAIL" in e for e in failures))

    def test_previous_publication_receipt_is_deferred_not_falsely_passed(self):
        failures, disposition = self.inspect(
            self.advisory(), published_ids={"intel--proof-negative"}
        )
        self.assertEqual((failures, disposition), ([], "DEFERRED"))

    def test_outside_rolling_window_is_deferred_not_rebuilt(self):
        failures, disposition = self.inspect(self.advisory(age_hours=240))
        self.assertEqual((failures, disposition), ([], "DEFERRED"))

    def test_public_url_host_lookalikes_are_refused(self):
        for url in (
            "https://evil.example/cyberdudebivash/reports/a.html",
            "https://intel.cyberdudebivash.com.evil.example/reports/a.html",
            "https://intel.cyberdudebivash.com@evil.example/reports/a.html",
            "http://intel.cyberdudebivash.com/reports/a.html",
            "https://intel.cyberdudebivash.com:bad/reports/a.html",
            "https://intel.cyberdudebivash.com/evil/a.html",
            "https://intel.cyberdudebivash.com/reports/a.html?download=1",
            "//evil.example/reports/a.html",
        ):
            with self.subTest(url=url):
                failures, disposition = self.inspect(self.advisory(report_url=url))
                self.assertEqual(disposition, "FAIL")
                self.assertTrue(any("RULE 2 FAIL" in e for e in failures))

    def test_internal_report_url_also_requires_approved_origin(self):
        failures, disposition = self.inspect(self.advisory(
            internal_report_url="https://intel.cyberdudebivash.com.evil.example/reports/a.html",
        ))
        self.assertEqual(disposition, "FAIL")
        self.assertTrue(any("RULE 2 FAIL" in e for e in failures))

    def test_present_valid_html_report_can_still_pass(self):
        path = Path("reports/2026/10/intel--proof-negative.html")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<!doctype html>" + "valid content " * 80, encoding="utf-8")
        self.assertEqual(self.inspect(self.advisory()), ([], "PASS"))

    def test_present_truncated_html_report_still_fails_size_guard(self):
        path = Path("reports/2026/10/intel--proof-negative.html")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<!doctype html><body>tiny</body>", encoding="utf-8")
        failures, disposition = self.inspect(self.advisory())
        self.assertEqual(disposition, "FAIL")
        self.assertTrue(any("RULE 4 FAIL" in e for e in failures))


if __name__ == "__main__":
    unittest.main()
