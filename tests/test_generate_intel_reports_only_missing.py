#!/usr/bin/env python3
"""
tests/test_generate_intel_reports_only_missing.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Report Continuity: --only-missing Regression Guard

P0 INCIDENT (2026-08-22): STAGE 5.4.1 (report_existence_validator.py) hard-failed
production CI (run #2140) because 233 entries in data/stix/feed_manifest.json
carried a /reports/ report_url whose HTML file did not exist on disk. Root cause:
generate_intel_reports.py's own render/write/validate loop never sets report_url
without first proving the file exists -- but a later pipeline stage
(stage_sync_root_feed_json()'s reconciliation step) can copy an item's report_url
field forward from another source without re-verifying the file survived into
this run's working tree.

FIX: --only-missing turns this script into a cheap, idempotent, incremental
repair pass -- it must:
  1. Regenerate a report for an item whose report_url is empty.
  2. Regenerate a report for an item whose report_url is /reports/-prefixed but
     the file does not exist ("dangling" -- the exact P0 failure signature).
  3. Never re-render (never touch) an item whose report_url already resolves to
     an existing local file -- this is the whole point of the flag: STAGE 3.6's
     normal run_pipeline.py call has already validated these once.
  4. Never touch an item whose report_url is external (http-prefixed) --
     report_existence_validator.py never checks these, and this barrier must
     not convert an intentionally-external/source-fallback item into a
     locally-rendered one as a side effect of repairing unrelated items.

These tests lock in that contract so it cannot regress.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_intel_reports.py"

_BASE_ITEM = {
    "title": "Regression Test Advisory -- Only-Missing Barrier Guard",
    "description": (
        "Synthetic advisory used by "
        "tests/test_generate_intel_reports_only_missing.py to verify the "
        "--only-missing incremental repair pass."
    ),
    "source": "TEST-FIXTURE",
    "severity": "LOW",
    "timestamp": "2026-06-01T00:00:00Z",
    "processed_at": "2026-06-01T00:00:00Z",
}


def _run_generator(manifest_path: Path, only_missing: bool = True) -> subprocess.CompletedProcess:
    args = [
        sys.executable, str(SCRIPT),
        "--manifest", str(manifest_path),
        "--public-prefix", "https://intel.cyberdudebivash.com",
        "--limit", "0",
    ]
    if only_missing:
        args.append("--only-missing")
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)


def _cleanup_reports(*item_ids):
    for item_id in item_ids:
        for p in (REPO_ROOT / "reports").rglob(f"{item_id}.html*"):
            p.unlink(missing_ok=True)


class TestOnlyMissingRepairPass(unittest.TestCase):
    def test_empty_report_url_gets_generated(self):
        item_id = "intel--testfixture0000000b01"
        item = dict(_BASE_ITEM, id=item_id, report_url="")

        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}), encoding="utf-8")
            try:
                result = _run_generator(manifest)
                self.assertEqual(result.returncode, 0, result.stderr)

                data = json.loads(manifest.read_text(encoding="utf-8"))
                persisted = data["advisories"][0]
                expected_url = f"/reports/2026/06/{item_id}.html"
                self.assertEqual(persisted.get("report_url"), expected_url)
                self.assertTrue((REPO_ROOT / expected_url.lstrip("/")).exists())
            finally:
                _cleanup_reports(item_id)

    def test_dangling_local_report_url_gets_regenerated(self):
        """The exact P0 failure signature: report_url is /reports/-prefixed but
        no file backs it. --only-missing must materialize it, not skip it."""
        item_id = "intel--testfixture0000000b02"
        dangling_url = f"/reports/2026/06/{item_id}.html"
        item = dict(_BASE_ITEM, id=item_id, report_url=dangling_url)

        report_path = REPO_ROOT / dangling_url.lstrip("/")
        self.assertFalse(report_path.exists(), "test setup invariant: file must not pre-exist")

        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}), encoding="utf-8")
            try:
                result = _run_generator(manifest)
                self.assertEqual(result.returncode, 0, result.stderr)

                self.assertTrue(
                    report_path.exists(),
                    "--only-missing must materialize a dangling report_url, not leave it broken",
                )
                self.assertGreater(report_path.stat().st_size, 1024)

                data = json.loads(manifest.read_text(encoding="utf-8"))
                persisted = data["advisories"][0]
                self.assertEqual(persisted.get("report_url"), dangling_url)
            finally:
                _cleanup_reports(item_id)

    def test_existing_valid_report_is_never_reregenerated(self):
        """Performance + correctness contract: an item whose file already
        exists must be skipped entirely -- not re-rendered, not re-written."""
        item_id = "intel--testfixture0000000b03"
        existing_url = f"/reports/2026/06/{item_id}.html"
        item = dict(_BASE_ITEM, id=item_id, report_url="")

        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}), encoding="utf-8")
            try:
                # First pass (normal mode): create the real, validated file.
                first = _run_generator(manifest, only_missing=False)
                self.assertEqual(first.returncode, 0, first.stderr)
                report_path = REPO_ROOT / existing_url.lstrip("/")
                self.assertTrue(report_path.exists())
                original_bytes = report_path.read_bytes()
                original_mtime = report_path.stat().st_mtime_ns

                # Second pass (--only-missing): must be a pure no-op for this item.
                second = _run_generator(manifest, only_missing=True)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(
                    report_path.stat().st_mtime_ns, original_mtime,
                    "--only-missing must not touch a file that already exists",
                )
                self.assertEqual(report_path.read_bytes(), original_bytes)
            finally:
                _cleanup_reports(item_id)

    def test_external_report_url_is_never_converted_to_local(self):
        """--only-missing must not treat a legitimate external/source-fallback
        report_url as 'missing' -- report_existence_validator.py never checks
        these, and converting them is an unrequested, unverified side effect."""
        item_id = "intel--testfixture0000000b04"
        external_url = "https://example-source.test/articles/some-advisory"
        item = dict(_BASE_ITEM, id=item_id, report_url=external_url)

        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": [item]}), encoding="utf-8")
            try:
                result = _run_generator(manifest, only_missing=True)
                self.assertEqual(result.returncode, 0, result.stderr)

                data = json.loads(manifest.read_text(encoding="utf-8"))
                persisted = data["advisories"][0]
                self.assertEqual(
                    persisted.get("report_url"), external_url,
                    "--only-missing must leave an external report_url completely untouched",
                )
                local_path = REPO_ROOT / "reports" / "2026" / "06" / f"{item_id}.html"
                self.assertFalse(
                    local_path.exists(),
                    "--only-missing must not fabricate a local file for an external item",
                )
            finally:
                _cleanup_reports(item_id)

    def test_mixed_batch_invariant_holds_end_to_end(self):
        """Section 14 formal invariant: LOCAL_REPORT_URL(item) => FILE_EXISTS.
        A single --only-missing pass over a realistic mixed manifest (empty,
        dangling, already-present, external) must leave every local reference
        backed by a real file, and must leave the external item untouched --
        verified with the actual report_existence_validator.py, not a re-
        implementation of its logic."""
        ids = {
            "empty": "intel--testfixture0000000b05",
            "dangling": "intel--testfixture0000000b06",
            "present": "intel--testfixture0000000b07",
            "external": "intel--testfixture0000000b08",
        }
        dangling_url = f"/reports/2026/06/{ids['dangling']}.html"
        present_url = f"/reports/2026/06/{ids['present']}.html"
        external_url = "https://example-source.test/articles/other-advisory"

        items = [
            dict(_BASE_ITEM, id=ids["empty"], report_url=""),
            dict(_BASE_ITEM, id=ids["dangling"], report_url=dangling_url),
            dict(_BASE_ITEM, id=ids["present"], report_url=""),
            dict(_BASE_ITEM, id=ids["external"], report_url=external_url),
        ]

        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "feed_manifest.json"
            manifest.write_text(json.dumps({"advisories": items}), encoding="utf-8")
            try:
                # Pre-materialize the "present" item for real via a normal pass.
                pre = json.loads(manifest.read_text(encoding="utf-8"))
                pre["advisories"] = [it for it in pre["advisories"] if it["id"] == ids["present"]]
                manifest.write_text(json.dumps(pre), encoding="utf-8")
                first = _run_generator(manifest, only_missing=False)
                self.assertEqual(first.returncode, 0, first.stderr)

                # Now run the real mixed batch through --only-missing.
                manifest.write_text(json.dumps({"advisories": items}), encoding="utf-8")
                result = _run_generator(manifest, only_missing=True)
                self.assertEqual(result.returncode, 0, result.stderr)

                validator = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "scripts" / "report_existence_validator.py"),
                     "--manifest", str(manifest)],
                    cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(
                    validator.returncode, 0,
                    f"report_existence_validator.py must pass after the repair pass:\n"
                    f"{validator.stdout}\n{validator.stderr}",
                )

                data = json.loads(manifest.read_text(encoding="utf-8"))
                by_id = {it["id"]: it for it in data["advisories"]}
                self.assertEqual(by_id[ids["external"]].get("report_url"), external_url)
                for key in ("empty", "dangling", "present"):
                    ru = by_id[ids[key]].get("report_url", "")
                    self.assertTrue(ru.startswith("/reports/"), f"{key}: {ru!r}")
                    self.assertTrue((REPO_ROOT / ru.lstrip("/")).exists(), f"{key}: {ru!r}")
            finally:
                _cleanup_reports(*ids.values())


if __name__ == "__main__":
    unittest.main()
