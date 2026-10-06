#!/usr/bin/env python3
"""
tests/test_generate_intel_reports_since_hours.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- P0 R2 Cost Incident: --since-hours regression guard.

ROOT CAUSE (docs/P0_R2_COST_CONTAINMENT.md): scripts/generate_intel_reports.py's
default mode regenerated a report for EVERY item in the manifest -- not just
new/changed ones -- on every scheduled pipeline run. Combined with a live
timestamp baked into every report's SIGMA/YARA/KQL/SPL blocks (always
different content run to run) and scripts/r2_upload.py's now-removed
whole-corpus `aws s3 sync`, this produced 3,004,147 billable R2 Class A
operations in one billing cycle.

These tests lock in the --since-hours contract so it cannot regress:
  1. An item older than the window is left COMPLETELY untouched (no field
     changed at all -- not just "no file written").
  2. An item within the window is rendered normally.
  3. The manifest save path never drops out-of-window items (they are core
     intelligence records, NOT subject to the report-retention decision).
  4. --fail-on-zero does not false-fail a genuinely empty (quiet) window --
     an empty 24h window is a valid, expected production state, not a defect.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_intel_reports.py"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(manifest_path: Path, extra_args: list[str]) -> subprocess.CompletedProcess:
    args = [
        sys.executable, str(SCRIPT),
        "--manifest", str(manifest_path),
        "--public-prefix", "https://intel.cyberdudebivash.com",
        "--limit", "0",
    ] + extra_args
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)


def _cleanup_reports(*item_ids):
    for item_id in item_ids:
        for p in (REPO_ROOT / "reports").rglob(f"{item_id}.html*"):
            p.unlink(missing_ok=True)


class TestSinceHoursWindow(unittest.TestCase):
    def test_old_item_left_completely_untouched(self):
        now = datetime.now(timezone.utc)
        old_id = "intel--sincehours0000001"
        item = {
            "id": old_id, "title": "Stale Advisory -- must not be touched",
            "description": "x" * 80, "severity": "LOW",
            "timestamp": _iso(now - timedelta(hours=100)),
            "processed_at": _iso(now - timedelta(hours=100)),
            "report_url": "", "validation_status": "", "custom_marker": "UNTOUCHED_SENTINEL",
        }
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}))
            try:
                result = _run(manifest, ["--since-hours", "24"])
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(manifest.read_text())
                persisted = data["advisories"][0]
                # Every field must be byte-identical to the input -- not
                # just report_url. This item was never entered by the loop.
                self.assertEqual(persisted, item)
                local = REPO_ROOT / "reports"
                self.assertFalse(any(local.rglob(f"{old_id}.html")), "must not render a file for an out-of-window item")
            finally:
                _cleanup_reports(old_id)

    def test_fresh_item_still_rendered(self):
        now = datetime.now(timezone.utc)
        fresh_id = "intel--sincehours0000002"
        item = {
            "id": fresh_id, "title": "Fresh Advisory", "description": "x" * 80,
            "severity": "LOW", "timestamp": _iso(now - timedelta(hours=2)),
            "processed_at": _iso(now - timedelta(hours=2)), "report_url": "",
        }
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}))
            try:
                result = _run(manifest, ["--since-hours", "24"])
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(manifest.read_text())
                persisted = data["advisories"][0]
                self.assertTrue(persisted["report_url"].startswith("/reports/"))
                self.assertTrue((REPO_ROOT / persisted["report_url"].lstrip("/")).exists())
            finally:
                _cleanup_reports(fresh_id)

    def test_mixed_batch_old_never_deleted_from_manifest(self):
        """Core safety property: filtering out-of-window items from the
        RENDER loop must never shrink the SAVED manifest -- core
        intelligence records are not subject to report retention."""
        now = datetime.now(timezone.utc)
        fresh_id = "intel--sincehours0000003"
        old_id = "intel--sincehours0000004"
        items = [
            {"id": fresh_id, "title": "Fresh", "description": "x" * 80, "severity": "LOW",
             "timestamp": _iso(now - timedelta(hours=1)), "report_url": ""},
            {"id": old_id, "title": "Old", "description": "x" * 80, "severity": "LOW",
             "timestamp": _iso(now - timedelta(days=30)), "report_url": ""},
        ]
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": items}))
            try:
                result = _run(manifest, ["--since-hours", "24"])
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(manifest.read_text())
                ids_present = {it["id"] for it in data["advisories"]}
                self.assertEqual(ids_present, {fresh_id, old_id}, "old item must NOT be dropped from the manifest")
            finally:
                _cleanup_reports(fresh_id, old_id)

    def test_without_since_hours_flag_behavior_is_unchanged(self):
        """Backward compatibility: omitting --since-hours entirely must
        still render an old item exactly as before this fix (default is
        unbounded, not silently 24h)."""
        now = datetime.now(timezone.utc)
        old_id = "intel--sincehours0000005"
        item = {"id": old_id, "title": "Old but no flag passed", "description": "x" * 80,
                "severity": "LOW", "timestamp": _iso(now - timedelta(days=30)), "report_url": ""}
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}))
            try:
                result = _run(manifest, [])  # no --since-hours at all
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(manifest.read_text())
                persisted = data["advisories"][0]
                self.assertTrue(persisted["report_url"].startswith("/reports/"), "unbounded default must still render everything")
            finally:
                _cleanup_reports(old_id)

    def test_malformed_timestamp_excluded_not_crashed(self):
        old_id = "intel--sincehours0000006"
        item = {"id": old_id, "title": "Corrupt timestamp", "description": "x" * 80,
                "severity": "LOW", "timestamp": "not-a-real-timestamp", "report_url": ""}
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}))
            try:
                result = _run(manifest, ["--since-hours", "24"])
                self.assertEqual(result.returncode, 0, f"must not crash on a malformed timestamp: {result.stderr}")
                data = json.loads(manifest.read_text())
                self.assertEqual(data["advisories"][0]["report_url"], "", "unparseable timestamp must fail safe (excluded), never fabricate a report")
            finally:
                _cleanup_reports(old_id)


class TestFailOnZeroWithWindow(unittest.TestCase):
    def test_genuinely_empty_window_does_not_trigger_fail_on_zero(self):
        """A quiet 24h period (zero new intel) is a valid, expected
        production state -- must exit 0, never hard-fail the pipeline."""
        now = datetime.now(timezone.utc)
        old_id = "intel--sincehours0000007"
        item = {"id": old_id, "title": "Only item, and it's old", "description": "x" * 80,
                "severity": "LOW", "timestamp": _iso(now - timedelta(days=10)), "report_url": ""}
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}))
            try:
                result = _run(manifest, ["--since-hours", "24", "--fail-on-zero"])
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                _cleanup_reports(old_id)

    def test_eligible_item_present_still_succeeds_with_fail_on_zero(self):
        """Contrast case for the empty-window test above: --fail-on-zero
        combined with --since-hours must not become a hair-trigger just
        because the window logic is now involved -- a window that DOES
        contain an eligible item renders it and exits 0, same as always."""
        now = datetime.now(timezone.utc)
        fresh_id = "intel--sincehours0000008"
        item = {"id": fresh_id, "title": "", "description": "", "severity": "LOW",
                "timestamp": _iso(now - timedelta(hours=1)), "report_url": ""}
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}))
            try:
                result = _run(manifest, ["--since-hours", "24", "--fail-on-zero"])
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(manifest.read_text())
                self.assertTrue(data["advisories"][0]["report_url"])
            finally:
                _cleanup_reports(fresh_id)


if __name__ == "__main__":
    unittest.main()
