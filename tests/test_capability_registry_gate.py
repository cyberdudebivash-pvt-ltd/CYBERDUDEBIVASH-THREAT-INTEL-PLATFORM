"""
tests/test_capability_registry_gate.py

Covers scripts/capability_registry_gate.py -- the blocking CI gate added in
the sentinel-apex-transformation-8x3y26 session that (1) fails a build if a
top-level *.html page has no entry in data/quality/frontend_capability_registry.json,
and (2) fails a build if a page the registry certified as 'live' (genuinely
calling the platform's own API) is no longer dynamic per the current
frontend_api_coverage_report.json run -- the "transformed page reverted to a
static placeholder" regression the mission text asks to be guarded against
by name.

Exercises evaluate() directly against constructed fixtures (no real files
touched) so these tests stay fast and don't depend on this repo's own
149-page state matching any particular snapshot.
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import capability_registry_gate as gate  # noqa: E402


def _registry(entries):
    return {"taxonomy": ["CUSTOMER_UI", "API_ONLY", "ADMIN", "INTERNAL", "DEPRECATED"],
            "entries": entries, "customer_ui_orphan_count": sum(1 for e in entries if e.get("status") == "orphan")}


def _coverage(dynamic_files):
    return {"dynamic_pages": [{"file": f} for f in dynamic_files]}


class TestGate1UnclassifiedPage(unittest.TestCase):
    def test_every_page_classified_passes(self):
        registry = _registry([
            {"id": "a.html", "category": "CUSTOMER_UI", "status": "live"},
            {"id": "b.html", "category": "ADMIN"},
        ])
        result = gate.evaluate(registry, _coverage(["a.html"]), ["a.html", "b.html"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["unclassified_count"], 0)

    def test_new_page_with_no_registry_entry_fails(self):
        registry = _registry([{"id": "a.html", "category": "CUSTOMER_UI", "status": "live"}])
        result = gate.evaluate(registry, _coverage(["a.html"]), ["a.html", "new-unclassified-page.html"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["unclassified_count"], 1)
        finding = next(f for f in result["findings"] if f["gate"] == "unclassified_page")
        self.assertIn("new-unclassified-page.html", finding["pages"])

    def test_stale_registry_entry_for_deleted_page_does_not_fail(self):
        # A page removed from the repo but still listed in the registry is
        # not this gate's concern (a separate stale-entry cleanup, if ever
        # wanted, is not the same risk as an unclassified NEW page) --
        # actual_pages only contains what's still on disk.
        registry = _registry([
            {"id": "a.html", "category": "CUSTOMER_UI", "status": "live"},
            {"id": "removed.html", "category": "CUSTOMER_UI", "status": "live"},
        ])
        result = gate.evaluate(registry, _coverage(["a.html"]), ["a.html"])
        self.assertTrue(result["passed"])

    def test_malformed_category_fails(self):
        registry = _registry([{"id": "a.html", "category": "NOT_A_REAL_CATEGORY"}])
        result = gate.evaluate(registry, _coverage([]), ["a.html"])
        self.assertFalse(result["passed"])
        finding = next(f for f in result["findings"] if f["gate"] == "malformed_classification")
        self.assertIn("a.html", finding["pages"])


class TestGate2PlaceholderRegression(unittest.TestCase):
    def test_live_page_still_dynamic_passes(self):
        registry = _registry([{"id": "cves.html", "category": "CUSTOMER_UI", "status": "live"}])
        result = gate.evaluate(registry, _coverage(["cves.html"]), ["cves.html"])
        self.assertTrue(result["passed"])

    def test_live_page_no_longer_dynamic_fails(self):
        # The exact regression this gate exists to catch: a page previously
        # certified live (e.g. one of #336's 7 fixed pages) reverts to
        # static -- someone edits unrelated markup and a merge drops the
        # fetch() call, or reverts to a hardcoded placeholder.
        registry = _registry([{"id": "cves.html", "category": "CUSTOMER_UI", "status": "live"}])
        result = gate.evaluate(registry, _coverage([]), ["cves.html"])
        self.assertFalse(result["passed"])
        finding = next(f for f in result["findings"] if f["gate"] == "placeholder_regression")
        self.assertEqual(finding["pages"], ["cves.html"])

    def test_orphan_status_page_never_flagged_by_regression_gate(self):
        # A page the registry already knows is a static-placeholder orphan
        # (never certified live) must never trip gate 2 -- only a REGRESSION
        # from a previously-verified live state is a blocker, so unrelated
        # backlog work on other pages is never blocked by this gate.
        registry = _registry([{"id": "orphan.html", "category": "CUSTOMER_UI", "status": "orphan"}])
        result = gate.evaluate(registry, _coverage([]), ["orphan.html"])
        self.assertTrue(result["passed"])

    def test_live_non_gateway_status_never_flagged(self):
        # intelligence-archive.html's real case: genuinely dynamic via a
        # non-/api/ data source the coverage heuristic can't see. Must use
        # a distinct status from 'live' so it's structurally exempt from
        # gate 2, not merely coincidentally passing.
        registry = _registry([{"id": "intelligence-archive.html", "category": "CUSTOMER_UI", "status": "live_non_gateway"}])
        result = gate.evaluate(registry, _coverage([]), ["intelligence-archive.html"])
        self.assertTrue(result["passed"])

    def test_multiple_regressions_all_reported(self):
        registry = _registry([
            {"id": "cves.html", "category": "CUSTOMER_UI", "status": "live"},
            {"id": "ransomware.html", "category": "CUSTOMER_UI", "status": "live"},
            {"id": "still-fine.html", "category": "CUSTOMER_UI", "status": "live"},
        ])
        result = gate.evaluate(registry, _coverage(["still-fine.html"]), ["cves.html", "ransomware.html", "still-fine.html"])
        self.assertFalse(result["passed"])
        finding = next(f for f in result["findings"] if f["gate"] == "placeholder_regression")
        self.assertEqual(finding["pages"], ["cves.html", "ransomware.html"])


class TestRealRegistrySnapshot(unittest.TestCase):
    """Sanity-checks this repo's actual generated registry + coverage report
    are internally consistent, if both have been generated. Skips (not
    fails) when either artifact is missing rather than forcing every test
    run to regenerate them -- CI runs the two generator scripts as their
    own earlier stages (frontend_api_coverage_gate.py, then
    build_capability_registry.py) before this gate."""

    def test_current_repo_snapshot_passes_both_gates(self):
        import json
        registry_path = REPO_ROOT / "data/quality/frontend_capability_registry.json"
        coverage_path = REPO_ROOT / "data/quality/frontend_api_coverage_report.json"
        if not registry_path.exists() or not coverage_path.exists():
            self.skipTest("registry or coverage report not generated in this checkout")
        registry = json.loads(registry_path.read_text())
        coverage = json.loads(coverage_path.read_text())
        actual_pages = sorted(p.name for p in REPO_ROOT.glob("*.html"))
        result = gate.evaluate(registry, coverage, actual_pages)
        self.assertTrue(result["passed"], msg=str(result["findings"]))


if __name__ == "__main__":
    unittest.main()
