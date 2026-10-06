"""
tests/test_r2_upload_reports_sync.py

Regression test for scripts/r2_upload.py's reports/ keyspace ownership.

HISTORY: this test originally asserted (v184.2) that main()'s HTML report
sync used `size_only=False` full-content comparison rather than
`size_only=True`. PR #369 (2026-09 P0 R2 cost incident fix) removed that
whole-corpus `aws s3 sync reports/ -> s3://sentinel-apex-reports/reports/`
call from main() entirely -- not flag-gated, structurally deleted -- because
it was the confirmed root cause of a 3,004,147-Class-A-operation billing
cycle (docs/P0_R2_COST_CONTAINMENT.md). scripts/r2_report_publisher.py is
now the sole writer/retirer for both the HTML reports keyspace
(sentinel-apex-reports) and reports/pdf/ (sentinel-apex-data): deterministic
keys, sha256-diffed, bounded to a rolling window, fail-closed budget before
any mutation (see tests/test_r2_report_publisher.py for that coverage).

This test now guards the opposite, durable invariant: main() must NEVER
reintroduce a whole-corpus `s3_sync(...)` call against the reports/
directories -- doing so would resurrect the exact incident #369 fixed.
Mirrors scripts/regression_tests.py's T26_no_whole_corpus_r2_report_sync at
the r2_upload.py-source level specifically.
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_upload  # noqa: E402


class TestMainNeverReintroducesWholeCorpusReportsSync(unittest.TestCase):
    def setUp(self):
        self.main_source = inspect.getsource(r2_upload.main)

    def test_main_does_not_sync_reports_directory(self):
        self.assertNotIn(
            's3_sync("reports/"', self.main_source,
            "main() must not resurrect the whole-corpus `reports/` sync -- "
            "removed in PR #369 as the confirmed root cause of the P0 R2 "
            "billing incident (docs/P0_R2_COST_CONTAINMENT.md). "
            "scripts/r2_report_publisher.py owns this keyspace now.",
        )

    def test_main_does_not_sync_reports_pdf_directory(self):
        self.assertNotIn(
            's3_sync("reports/pdf/"', self.main_source,
            "main() must not resurrect the whole-corpus `reports/pdf/` sync "
            "-- see PR #369 / docs/P0_R2_COST_CONTAINMENT.md.",
        )

    def test_main_does_not_call_bucket_reports_at_all(self):
        # BUCKET_REPORTS is documented as "written/retired only by
        # scripts/r2_report_publisher.py now" (see r2_upload.py module
        # docstring) -- main() referencing it at all would mean a new
        # writer crept back into the reports keyspace.
        self.assertNotIn("BUCKET_REPORTS", self.main_source)


if __name__ == "__main__":
    unittest.main()
