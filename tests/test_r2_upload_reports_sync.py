"""
tests/test_r2_upload_reports_sync.py

Regression test for the v184.2 P0 fix in scripts/r2_upload.py: the HTML
report sync (STAGE 3.5) must use full content comparison, not --size-only.

Root cause this guards against: --size-only skips re-uploading a report
whose content changed but whose total byte size happened to land close
enough to what was already in R2, silently leaving stale (pre-fix) report
content served from production indefinitely. Confirmed live on
intel--20282e88b1f49bf2 and intel--f43ac4fcc6f30452 after RX-PR1 merged --
the regenerated local HTML was provably correct (verified via direct CLI
reproduction), but R2 kept serving the old page.

The reports/ HTML sync call is asserted separately from the reports/pdf/
PDF sync call, which intentionally keeps size_only=True (out of scope --
no evidence of an equivalent staleness defect for PDFs).
"""
from __future__ import annotations

import inspect
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_upload  # noqa: E402


def _s3_sync_call_for(src_dir_literal: str, source: str) -> str:
    """Extract the s3_sync(...) call block whose first arg is src_dir_literal."""
    pattern = re.compile(
        r"s3_sync\(\s*" + re.escape(src_dir_literal) + r"\s*,.*?\)",
        re.DOTALL,
    )
    match = pattern.search(source)
    assert match, f"Could not find s3_sync(...) call for {src_dir_literal!r} in main()"
    return match.group(0)


class TestReportsSyncUsesFullContentComparison(unittest.TestCase):
    def setUp(self):
        self.main_source = inspect.getsource(r2_upload.main)

    def test_html_reports_sync_does_not_use_size_only(self):
        call = _s3_sync_call_for('"reports/"', self.main_source)
        self.assertIn(
            "size_only=False", call,
            "HTML report sync must use full content comparison (size_only=False). "
            "Reverting to size_only=True silently skips re-uploading changed reports "
            "that happen to match R2's stored byte size -- the exact defect that let "
            "RX-PR1's fix ship without reaching production. See the v184.2 fix note "
            "in scripts/r2_upload.py.",
        )
        self.assertNotIn("size_only=True", call)

    def test_pdf_sync_still_uses_size_only(self):
        # Out of scope for this fix -- confirm it wasn't accidentally changed too.
        call = _s3_sync_call_for('"reports/pdf/"', self.main_source)
        self.assertIn("size_only=True", call)


if __name__ == "__main__":
    unittest.main()
