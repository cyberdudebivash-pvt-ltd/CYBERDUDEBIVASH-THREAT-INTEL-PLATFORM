#!/usr/bin/env python3
"""
tests/test_report_materialization_barrier.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Report Continuity: Pipeline-Order Barrier Guard

P0 INCIDENT (2026-08-22): scripts/run_pipeline.py's stage_sync_root_feed_json()
runs a SECOND time at the very end of the pipeline and can persist a manifest
item's report_url field forward (via its reconciliation step) without
re-verifying the file it names still exists on disk. This is the pipeline-order
defect behind STAGE 5.4.1's hard failure on production run #2140 (233 dangling
report_url entries in data/stix/feed_manifest.json).

scripts.run_pipeline.apply_report_materialization_barrier(manifest_path) is the
fix: called last in stage_sync_root_feed_json(), it scans the manifest as it
stands at that point and, if anything is dangling, re-invokes
generate_intel_reports.py --only-missing to close the gap (or clear report_url
if generation genuinely fails). These tests exercise that function directly
(not via a full pipeline run) to lock in its pipeline-order and atomicity
contract.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("CDB_JWT_SECRET", "pytest-dummy-secret-not-for-production")

import scripts.run_pipeline as run_pipeline  # noqa: E402


def _cleanup_reports(*item_ids):
    for item_id in item_ids:
        for p in (REPO_ROOT / "reports").rglob(f"{item_id}.html*"):
            p.unlink(missing_ok=True)


class TestMaterializationBarrierAtomicity(unittest.TestCase):
    """Late-mutation guard: an item appended to the manifest AFTER Stage 3.6
    (simulating stage_sync_root_feed_json()'s reconciliation step carrying a
    report_url forward from another source) must not survive the barrier with
    a dangling reference."""

    def test_late_mutation_dangling_item_gets_closed(self):
        item_id = "intel--testfixture0000000c01"
        dangling_url = f"/reports/2026/06/{item_id}.html"
        item = {
            "id": item_id,
            "title": "Late-mutation reconciliation test item",
            "description": "Simulates an item reconciled into the manifest after "
                            "Stage 3.6, carrying forward a report_url whose file "
                            "was never generated in this run's working tree.",
            "source": "TEST-FIXTURE",
            "severity": "LOW",
            "timestamp": "2026-06-01T00:00:00Z",
            "processed_at": "2026-06-01T00:00:00Z",
            "report_url": dangling_url,
        }
        report_path = REPO_ROOT / dangling_url.lstrip("/")
        self.assertFalse(report_path.exists(), "test setup invariant: file must not pre-exist")

        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "feed_manifest.json"
            manifest_path.write_text(json.dumps({"advisories": [item]}), encoding="utf-8")
            try:
                run_pipeline.apply_report_materialization_barrier(manifest_path)

                self.assertTrue(
                    report_path.exists(),
                    "barrier must materialize a dangling report_url introduced by late mutation",
                )
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(data["advisories"][0].get("report_url"), dangling_url)
            finally:
                _cleanup_reports(item_id)

    def test_clean_manifest_never_invokes_the_subprocess(self):
        """Performance contract: when nothing is dangling, the barrier must not
        spawn generate_intel_reports.py at all -- verified by mocking
        run_script and asserting it is never called."""
        item = {
            "id": "intel--testfixture0000000c02",
            "title": "Clean item, no report yet",
            "description": "No report_url at all -- nothing dangling for this item.",
            "source": "TEST-FIXTURE",
            "severity": "LOW",
            "timestamp": "2026-06-01T00:00:00Z",
            "processed_at": "2026-06-01T00:00:00Z",
            "report_url": "",
        }
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "feed_manifest.json"
            manifest_path.write_text(json.dumps({"advisories": [item]}), encoding="utf-8")

            with mock.patch.object(run_pipeline, "run_script") as mocked:
                run_pipeline.apply_report_materialization_barrier(manifest_path)
                mocked.assert_not_called()

    def test_bare_list_manifest_is_re_enveloped_before_repair(self):
        """P0 format-drift guard: data/stix/feed_manifest.json was found on
        committed main to have drifted to a bare JSON list instead of its
        intended {"advisories": [...]} envelope. generate_intel_reports.py's
        own save path applies a publish-filter to list-shaped input that drops
        every external (non-/reports/) item -- so the barrier must re-envelope
        BEFORE invoking it, or repairing local items would silently delete
        unrelated external ones. This proves both halves: the envelope is
        restored, and an external item survives untouched."""
        dangling_id = "intel--testfixture0000000c03"
        external_id = "intel--testfixture0000000c04"
        dangling_url = f"/reports/2026/06/{dangling_id}.html"
        external_url = "https://example-source.test/articles/some-advisory"

        items = [
            {
                "id": dangling_id, "title": "Dangling item in a bare list",
                "description": "x" * 60, "source": "TEST-FIXTURE", "severity": "LOW",
                "timestamp": "2026-06-01T00:00:00Z", "processed_at": "2026-06-01T00:00:00Z",
                "report_url": dangling_url,
            },
            {
                "id": external_id, "title": "External item in a bare list",
                "description": "x" * 60, "source": "TEST-FIXTURE", "severity": "LOW",
                "timestamp": "2026-06-01T00:00:00Z", "processed_at": "2026-06-01T00:00:00Z",
                "report_url": external_url,
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "feed_manifest.json"
            manifest_path.write_text(json.dumps(items), encoding="utf-8")  # bare list, matches prod drift
            try:
                run_pipeline.apply_report_materialization_barrier(manifest_path)

                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertIsInstance(
                    data, dict,
                    "barrier must re-envelope a bare-list manifest before repairing it",
                )
                self.assertIn("advisories", data)
                by_id = {it["id"]: it for it in data["advisories"]}
                self.assertEqual(
                    len(by_id), 2,
                    "re-enveloping must not drop the external item as a side effect",
                )
                self.assertEqual(by_id[external_id].get("report_url"), external_url)
                dangling_ru = by_id[dangling_id].get("report_url", "")
                self.assertTrue(dangling_ru.startswith("/reports/"))
                self.assertTrue((REPO_ROOT / dangling_ru.lstrip("/")).exists())
            finally:
                _cleanup_reports(dangling_id, external_id)

    def test_missing_manifest_file_does_not_raise(self):
        """Defensive: the barrier is called unconditionally at the end of
        stage_sync_root_feed_json(); it must never itself crash the pipeline."""
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "does_not_exist.json"
            try:
                run_pipeline.apply_report_materialization_barrier(manifest_path)
            except Exception as exc:  # pragma: no cover - failure path under test
                self.fail(f"barrier must never raise, got: {exc!r}")


if __name__ == "__main__":
    unittest.main()
