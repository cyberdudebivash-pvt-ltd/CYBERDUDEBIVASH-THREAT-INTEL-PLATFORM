#!/usr/bin/env python3
"""
tests/test_direct_push_inventory.py

Regression coverage for scripts/direct_push_inventory.py -- the P0 RUNTIME
INTELLIGENCE STATE RECOVERY mission's repository-wide OBSERVABILITY
inventory (Section 17/18). This is deliberately NOT a completeness gate:
it does not assert the remaining count is zero (that would require the
34-workflow repo-wide migration this mission explicitly scoped out --
"DO NOT EXPAND TO ALL 34 WORKFLOWS"). It asserts the tool itself works and
that the 2 workflows this mission DID migrate are correctly reflected.
"""
import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import direct_push_inventory as dpi  # noqa: E402


class TestDirectPushInventory(unittest.TestCase):
    def test_scan_runs_and_returns_well_formed_report(self):
        report = dpi.scan()
        self.assertIn("workflows_with_direct_runtime_push", report)
        self.assertIn("findings", report)
        self.assertIsInstance(report["findings"], list)
        self.assertGreater(report["total_workflows_scanned"], 0)

    def test_migrated_workflows_are_not_in_the_findings(self):
        """The 2 workflows this mission fixed must no longer appear in the
        remaining-direct-push findings -- proving the fix actually reduced
        the count, not just relabeled it."""
        report = dpi.scan()
        flagged = {f["workflow"] for f in report["findings"]}
        self.assertNotIn("genesis-powerhouse.yml", flagged)
        self.assertNotIn("sovereign-platform.yml", flagged)

    def test_report_does_not_claim_the_repo_wide_class_is_solved(self):
        """This mission's own explicit instruction: never silently claim
        the repo-wide 34-workflow class is solved. The report's own note
        must say so plainly, and other, unmigrated workflows must still be
        visible (proving this is a real scan, not a rigged empty result)."""
        report = dpi.scan()
        self.assertIn("not claimed as solved", report["note"])
        self.assertGreater(
            report["workflows_with_direct_runtime_push"], 0,
            "expected other, out-of-scope workflows to still be flagged -- "
            "if this is ever 0, verify the scan itself still works rather "
            "than assuming the 34-workflow class was solved",
        )

    def test_main_writes_report_file_and_exits_zero(self):
        rc = dpi.main()
        self.assertEqual(rc, 0)
        self.assertTrue(dpi.REPORT_PATH.exists())


if __name__ == "__main__":
    unittest.main()
