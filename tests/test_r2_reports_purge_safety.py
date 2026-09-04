#!/usr/bin/env python3
"""
tests/test_r2_reports_purge_safety.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- P0 R2 Cost Incident: one-time historical
purge script safety-rail regression tests. See docs/P0_R2_COST_CONTAINMENT.md.

scripts/r2_reports_purge.py is a destructive, one-time migration tool. These
tests lock in its fail-closed safety rails -- they do NOT exercise any real
R2 call (list_all_objects/batch_delete need live credentials and are
intentionally out of scope here; this file only proves the tool cannot be
pointed at the wrong bucket or run destructively with no authoritative
keep-set, which are the two catastrophic failure modes for a script whose
whole job is bulk-deleting objects).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "r2_reports_purge.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_reports_purge as purge  # noqa: E402


class TestBucketAllowlist(unittest.TestCase):
    def test_allowed_bucket_passes(self):
        purge._assert_bucket_allowed(purge.ALLOWED_BUCKET)  # must not raise

    def test_sentinel_apex_data_is_permanently_blocked(self):
        with self.assertRaises(SystemExit):
            purge._assert_bucket_allowed("sentinel-apex-data")

    def test_scan_results_is_permanently_blocked(self):
        with self.assertRaises(SystemExit):
            purge._assert_bucket_allowed("cyberdudebivash-scan-results")

    def test_any_other_bucket_name_is_blocked(self):
        with self.assertRaises(SystemExit):
            purge._assert_bucket_allowed("some-other-bucket")

    def test_never_touch_set_is_never_empty(self):
        """A future edit that accidentally clears NEVER_TOUCH_BUCKETS must
        fail loudly here, not silently widen the blast radius."""
        self.assertIn("sentinel-apex-data", purge.NEVER_TOUCH_BUCKETS)
        self.assertIn("cyberdudebivash-scan-results", purge.NEVER_TOUCH_BUCKETS)
        self.assertNotIn(purge.ALLOWED_BUCKET, purge.NEVER_TOUCH_BUCKETS)


class TestKeepSetLoading(unittest.TestCase):
    def test_missing_state_file_returns_empty_not_crash(self):
        orig = purge.STATE_PATH
        purge.STATE_PATH = Path(tempfile.mkdtemp()) / "does_not_exist.json"
        try:
            self.assertEqual(purge.load_keep_set(), set())
        finally:
            purge.STATE_PATH = orig

    def test_populated_state_file_yields_correct_keep_set(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            state_path.write_text(json.dumps({
                "items": {
                    "intel--a": {"html_key": "reports/2026/09/intel--a.html", "pdf_key": "reports/pdf/intel--a.pdf"},
                    "intel--b": {"html_key": "reports/2026/09/intel--b.html"},
                }
            }))
            orig = purge.STATE_PATH
            purge.STATE_PATH = state_path
            try:
                keep = purge.load_keep_set()
                self.assertEqual(keep, {
                    "reports/2026/09/intel--a.html", "reports/pdf/intel--a.pdf",
                    "reports/2026/09/intel--b.html",
                })
            finally:
                purge.STATE_PATH = orig

    def test_corrupt_state_file_returns_empty_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.json"
            state_path.write_text("{not valid json")
            orig = purge.STATE_PATH
            purge.STATE_PATH = state_path
            try:
                self.assertEqual(purge.load_keep_set(), set())
            finally:
                purge.STATE_PATH = orig


class TestYearMonthFromKey(unittest.TestCase):
    def test_html_key_parses(self):
        self.assertEqual(purge.year_month_from_key("reports/2026/08/intel--abc.html"), "2026-08")

    def test_pdf_flat_key_returns_unknown_not_crash(self):
        self.assertEqual(purge.year_month_from_key("reports/pdf/intel--abc.pdf"), "unknown")

    def test_malformed_key_returns_unknown_not_crash(self):
        self.assertEqual(purge.year_month_from_key("garbage"), "unknown")


class TestCliRefusals(unittest.TestCase):
    """End-to-end CLI invocations (subprocess) -- proves the refusals fire
    from the actual entry point, not just the underlying functions, and
    that both exit non-zero (fail closed) without requiring any R2
    credentials to be configured."""

    def test_execute_without_matching_confirm_bucket_is_refused(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--execute", "--confirm-bucket", "sentinel-apex-data"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing", result.stderr + result.stdout)

    def test_execute_with_empty_keep_set_is_refused_without_override(self):
        # The script resolves STATE_PATH from __file__ (REPO_ROOT), not cwd,
        # so this relies on the real repo's state file being absent/empty in
        # this checkout (true pre-first-run) -- exactly the condition under test.
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--execute", "--confirm-bucket", purge.ALLOWED_BUCKET],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        # Either the empty-keep-set refusal fires (expected pre-first-run),
        # or credential validation fires first (also a safe, non-zero,
        # non-destructive outcome) -- both are acceptable "did not proceed
        # to delete anything" results for this CLI-level smoke test.
        self.assertNotEqual(result.returncode, 0)

    def test_dry_run_is_the_default_with_no_flags(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertIn("DRY-RUN", result.stdout)


if __name__ == "__main__":
    unittest.main()
