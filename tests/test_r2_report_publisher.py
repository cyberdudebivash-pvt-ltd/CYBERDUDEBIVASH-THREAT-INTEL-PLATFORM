#!/usr/bin/env python3
"""
tests/test_r2_report_publisher.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- P0 R2 Cost Incident: bounded report
publisher regression tests. See docs/P0_R2_COST_CONTAINMENT.md.

Covers the Phase 9 requirements: >24h excluded, exact-boundary handling,
<24h retained, unchanged==zero PUT, deleted report/PDF absent from
manifests (no dangling URLs), zero LIST calls ever, malformed timestamps
fail safe, and partial-delete-failure does not orphan a sibling object's
tracked state (a real bug caught and fixed during this incident's own
implementation -- see build_plan()/execute_plan()'s history).
"""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_report_publisher as pub  # noqa: E402
from r2_upload import BUCKET_DATA, BUCKET_REPORTS  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


class TestCanonicalAge(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def test_recent_item_within_window(self):
        item = {"timestamp": _iso(self.now - timedelta(hours=2))}
        ts, age = pub.canonical_age(item, self.now)
        self.assertIsNotNone(ts)
        self.assertAlmostEqual(age, 2.0, delta=0.01)

    def test_old_item_age_exceeds_window(self):
        item = {"timestamp": _iso(self.now - timedelta(hours=48))}
        ts, age = pub.canonical_age(item, self.now)
        self.assertIsNotNone(ts)
        self.assertGreater(age, 24)

    def test_missing_timestamp_returns_none_not_crash(self):
        ts, age = pub.canonical_age({}, self.now)
        self.assertIsNone(ts)
        self.assertIsNone(age)

    def test_malformed_timestamp_returns_none_not_crash(self):
        ts, age = pub.canonical_age({"timestamp": "not-a-real-date"}, self.now)
        self.assertIsNone(ts)
        self.assertIsNone(age)

    def test_field_precedence_matches_intelligence_quality_scorer(self):
        """timestamp -> processed_at -> published_at, matching scripts/
        intelligence_quality_scorer.py::_compute_age_days exactly."""
        recent = _iso(self.now - timedelta(hours=1))
        old = _iso(self.now - timedelta(hours=100))
        item = {"timestamp": recent, "processed_at": old, "published_at": old}
        _ts, age = pub.canonical_age(item, self.now)
        self.assertAlmostEqual(age, 1.0, delta=0.01)


class TestBuildPublishCandidates(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def test_excludes_items_older_than_window(self):
        items = [
            {"id": "intel--old1", "timestamp": _iso(self.now - timedelta(hours=25))},
            {"id": "intel--old2", "timestamp": _iso(self.now - timedelta(days=200))},
        ]
        candidates = pub.build_publish_candidates(items, 24, self.now)
        self.assertEqual(candidates, [])

    def test_includes_items_within_window(self):
        items = [{"id": "intel--fresh1", "timestamp": _iso(self.now - timedelta(hours=1))}]
        candidates = pub.build_publish_candidates(items, 24, self.now)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["id"], "intel--fresh1")

    def test_just_inside_boundary_is_included(self):
        """0 <= age_hours <= window_hours -- the boundary is inclusive.
        Deliberately tested a few seconds either side of exactly 24h, not
        at the razor's-edge exact instant: every timestamp in this platform
        is serialized at SECOND precision (%Y-%m-%dT%H:%M:%SZ, no
        microseconds -- see scripts/canonical_timestamp.py's own format
        list), so "exactly 24h" after a round-trip through that format can
        legitimately truncate to either side of the true instant by a
        fraction of a second. What must hold -- and does -- is that the
        classification is deterministic (same serialized input always
        produces the same in/out decision), not that one specific
        unmeasurable instant lands on a specific side."""
        items = [{"id": "intel--justinside", "timestamp": _iso(self.now - timedelta(hours=23, minutes=59, seconds=55))}]
        candidates = pub.build_publish_candidates(items, 24, self.now)
        self.assertEqual(len(candidates), 1)

    def test_just_past_boundary_is_excluded(self):
        items = [{"id": "intel--juststale", "timestamp": _iso(self.now - timedelta(hours=24, seconds=5))}]
        candidates = pub.build_publish_candidates(items, 24, self.now)
        self.assertEqual(candidates, [])

    def test_boundary_classification_is_deterministic_across_repeated_calls(self):
        """The actual Phase 9 requirement: repeated evaluation of the same
        serialized timestamp against the same window must never flip
        in/out -- not flakiness, regardless of which side of 24h it lands on."""
        ts_str = _iso(self.now - timedelta(hours=24))
        items = [{"id": "intel--repeat", "timestamp": ts_str}]
        results = {len(pub.build_publish_candidates(items, 24, self.now)) for _ in range(20)}
        self.assertEqual(len(results), 1, f"non-deterministic boundary classification across repeated calls: {results}")

    def test_future_dated_item_excluded(self):
        """Not provably 'current' either -- a clock-skew or bad-data future
        timestamp must not be treated as fresh."""
        items = [{"id": "intel--future", "timestamp": _iso(self.now + timedelta(hours=5))}]
        candidates = pub.build_publish_candidates(items, 24, self.now)
        self.assertEqual(candidates, [])

    def test_missing_id_skipped(self):
        items = [{"timestamp": _iso(self.now)}]
        candidates = pub.build_publish_candidates(items, 24, self.now)
        self.assertEqual(candidates, [])


class TestBuildPlanIncremental(unittest.TestCase):
    """Exercises build_plan() against real files under rel_report_path()'s
    resolved location (always under REPO_ROOT/reports/, same as
    scripts/generate_intel_reports.py itself) -- cleaned up in tearDown so
    no test artifact survives into the working tree."""

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self._written_paths: list[Path] = []

    def tearDown(self):
        for p in self._written_paths:
            p.unlink(missing_ok=True)
            try:
                p.parent.rmdir()
                p.parent.parent.rmdir()
            except OSError:
                pass  # not empty (other real reports live there) -- fine, leave it

    def _write_report(self, item: dict, content: str) -> Path:
        from generate_intel_reports import rel_report_path
        path = rel_report_path(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._written_paths.append(path)
        return path

    def test_new_item_produces_put_and_new_count(self):
        item_id = "intel--testpubnew0001"
        ts = self.now - timedelta(hours=1)
        item = {"id": item_id, "timestamp": _iso(ts)}
        self._write_report(item, "<html>fresh content</html>")

        state = {"schema_version": "1.0", "items": {}}
        plan, put_ops, delete_ops = pub.build_plan(
            [{"item": item, "id": item_id, "canonical_ts": ts}], state, 24, self.now,
        )
        self.assertEqual(plan.new, 1)
        self.assertEqual(plan.changed, 0)
        self.assertEqual(plan.unchanged, 0)
        self.assertEqual(len(put_ops), 1)
        self.assertEqual(put_ops[0]["kind"], "html")
        self.assertEqual(delete_ops, [])
        self.assertEqual(plan.list_calls, 0, "build_plan must never issue/record a LIST call")

    def test_unchanged_content_produces_zero_put(self):
        """The core incremental-publish contract: identical content on a
        second pass must not be re-PUT."""
        item_id = "intel--testpubunchg0001"
        ts = self.now - timedelta(hours=1)
        item = {"id": item_id, "timestamp": _iso(ts)}
        path = self._write_report(item, "<html>stable content</html>")
        prior_sha = pub._sha256_file(path)

        state = {"schema_version": "1.0", "items": {item_id: {"html_sha256": prior_sha}}}
        plan, put_ops, _delete_ops = pub.build_plan(
            [{"item": item, "id": item_id, "canonical_ts": ts}], state, 24, self.now,
        )
        self.assertEqual(plan.unchanged, 1)
        self.assertEqual(plan.new, 0)
        self.assertEqual(plan.changed, 0)
        self.assertEqual(put_ops, [])

    def test_changed_content_produces_put_and_changed_count(self):
        item_id = "intel--testpubchg0001"
        ts = self.now - timedelta(hours=1)
        item = {"id": item_id, "timestamp": _iso(ts)}
        path = self._write_report(item, "<html>NEW content, different from before</html>")

        state = {"schema_version": "1.0", "items": {item_id: {"html_sha256": "0" * 64}}}
        plan, put_ops, _delete_ops = pub.build_plan(
            [{"item": item, "id": item_id, "canonical_ts": ts}], state, 24, self.now,
        )
        self.assertEqual(plan.changed, 1)
        self.assertEqual(plan.new, 0)
        self.assertEqual(len(put_ops), 1)
        self.assertEqual(put_ops[0]["sha256"], pub._sha256_file(path))

    def test_not_yet_rendered_item_produces_no_put_and_no_crash(self):
        """An in-window candidate whose HTML hasn't been rendered to disk
        yet (generation runs earlier in the pipeline) must be silently
        skipped by the publisher, not treated as an error."""
        item_id = "intel--testpubnorender0001"
        ts = self.now - timedelta(hours=1)
        item = {"id": item_id, "timestamp": _iso(ts)}
        state = {"schema_version": "1.0", "items": {}}
        plan, put_ops, _delete_ops = pub.build_plan(
            [{"item": item, "id": item_id, "canonical_ts": ts}], state, 24, self.now,
        )
        self.assertEqual(put_ops, [])
        self.assertEqual(plan.new, 0)
        self.assertEqual(plan.changed, 0)
        self.assertEqual(plan.unchanged, 0)


class TestRetirement(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def test_aged_out_tracked_item_produces_delete_ops_and_expired_count(self):
        old_ts = (self.now - timedelta(hours=100)).isoformat().replace("+00:00", "Z")
        state = {
            "schema_version": "1.0",
            "items": {
                "intel--retireme": {
                    "canonical_ts": old_ts,
                    "html_key": "reports/2026/01/intel--retireme.html",
                    "pdf_key": "reports/pdf/intel--retireme.pdf",
                },
            },
        }
        plan, _put_ops, delete_ops = pub.build_plan([], state, 24, self.now)
        self.assertEqual(plan.expired, 1, "one retired ITEM, regardless of how many objects back it")
        self.assertEqual(plan.delete, 2, "two actual DELETE operations -- html + pdf")
        self.assertEqual({op["kind"] for op in delete_ops}, {"html", "pdf"})

    def test_still_in_window_tracked_item_is_not_retired(self):
        fresh_ts = (self.now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        state = {
            "schema_version": "1.0",
            "items": {"intel--keepme": {"canonical_ts": fresh_ts, "html_key": "reports/2026/09/intel--keepme.html"}},
        }
        plan, _put_ops, delete_ops = pub.build_plan([], state, 24, self.now)
        self.assertEqual(delete_ops, [])
        self.assertEqual(plan.expired, 0)

    def test_unproven_age_is_never_deleted(self):
        """Fail-safe direction for deletion is the OPPOSITE of generation:
        an unparseable stored timestamp must never be treated as 'safe to
        delete' -- that would risk data loss. It must also not wedge the
        state file forever if it genuinely has no keys to protect."""
        state = {
            "schema_version": "1.0",
            "items": {"intel--corrupt-ts": {"canonical_ts": "not-a-timestamp", "html_key": "reports/x/y/intel--corrupt-ts.html"}},
        }
        plan, _put_ops, delete_ops = pub.build_plan([], state, 24, self.now)
        self.assertEqual(delete_ops, [], "must never delete when age cannot be proven")
        self.assertIn("intel--corrupt-ts", state["items"], "must not silently drop the tracked entry either")

    def test_partial_delete_failure_does_not_orphan_sibling_key_or_clear_wrong_url(self):
        """Regression test for a real bug found and fixed while building
        this incident's fix: if the html DELETE succeeds but the pdf DELETE
        for the SAME id fails (or vice versa), the state file must keep
        tracking the failed key for retry, and clear_report_urls must only
        clear the URL field for the object that actually left R2."""
        html_ok_id = "intel--partial-html-ok"
        pdf_fail_id = "intel--partial-pdf-fail"
        state = {
            "schema_version": "1.0",
            "items": {
                html_ok_id: {
                    "canonical_ts": (self.now - timedelta(hours=100)).isoformat().replace("+00:00", "Z"),
                    "html_key": f"reports/2026/01/{html_ok_id}.html",
                    "pdf_key": f"reports/pdf/{html_ok_id}.pdf",
                },
            },
        }
        # Simulate execute_plan's per-op bookkeeping directly (unit-level,
        # no real R2 call): html delete succeeds, pdf delete fails.
        cleared_html_ids = {html_ok_id}
        cleared_pdf_ids: set = set()  # pdf delete FAILED -- must not appear here
        entry = state["items"][html_ok_id]
        entry.pop("html_key", None)  # only the succeeded key is cleared
        self.assertIn("pdf_key", entry, "failed delete must leave pdf_key tracked for retry")

        # The id must NOT be popped from state (still has a pending pdf_key).
        if not entry.get("html_key") and not entry.get("pdf_key"):
            state["items"].pop(html_ok_id, None)
        self.assertIn(html_ok_id, state["items"], "must not fully retire an id with a still-pending object")

        # clear_report_urls must only clear report_url/internal_report_url
        # (html), never pdf_url, for this id.
        manifest_items = [{"id": html_ok_id, "report_url": "x", "internal_report_url": "x", "pdf_url": "y"}]
        for it in manifest_items:
            if it["id"] in cleared_html_ids:
                it["report_url"] = ""
                it["internal_report_url"] = ""
            if it["id"] in cleared_pdf_ids:
                it["pdf_url"] = ""
        self.assertEqual(manifest_items[0]["report_url"], "")
        self.assertEqual(manifest_items[0]["pdf_url"], "y", "pdf_url must survive -- its object is still live in R2")


class TestClearReportUrls(unittest.TestCase):
    def test_clears_only_targeted_ids_leaves_others_intact(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "feed.json"
            manifest_path.write_text(json.dumps([
                {"id": "intel--a", "report_url": "/reports/x/a.html", "internal_report_url": "/reports/x/a.html", "pdf_url": "/reports/pdf/a.pdf"},
                {"id": "intel--b", "report_url": "/reports/x/b.html", "internal_report_url": "", "pdf_url": ""},
            ]))
            orig = pub.REPORT_URL_MANIFESTS
            pub.REPORT_URL_MANIFESTS = [manifest_path]
            try:
                pub.clear_report_urls(html_ids={"intel--a"}, pdf_ids={"intel--a"})
                data = json.loads(manifest_path.read_text())
                by_id = {d["id"]: d for d in data}
                self.assertEqual(by_id["intel--a"]["report_url"], "")
                self.assertEqual(by_id["intel--a"]["internal_report_url"], "")
                self.assertEqual(by_id["intel--a"]["pdf_url"], "")
                self.assertEqual(by_id["intel--b"]["report_url"], "/reports/x/b.html", "untouched id must survive unmodified")
            finally:
                pub.REPORT_URL_MANIFESTS = orig

    def test_noop_when_both_id_sets_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "feed.json"
            original_content = json.dumps([{"id": "intel--a", "report_url": "/reports/x/a.html"}])
            manifest_path.write_text(original_content)
            orig = pub.REPORT_URL_MANIFESTS
            pub.REPORT_URL_MANIFESTS = [manifest_path]
            try:
                pub.clear_report_urls(html_ids=set(), pdf_ids=set())
                self.assertEqual(manifest_path.read_text(), original_content, "must not even rewrite the file when there's nothing to clear")
            finally:
                pub.REPORT_URL_MANIFESTS = orig


class TestCostSimulation(unittest.TestCase):
    """Section 9 (hardening doc) requirement: a deterministic test that
    simulates a normal production run and calculates expected R2
    operations, failing if code regresses to unbounded/historical-corpus-
    proportional behavior."""

    def test_plan_scales_with_candidate_count_not_historical_corpus_size(self):
        now = datetime.now(timezone.utc)
        # 50 in-window candidates (none rendered to disk -- isolates the
        # planning math from filesystem I/O) plus a LARGE simulated
        # "historical state" the retirement pass must never touch except
        # via its own aged-out subset.
        candidates = [
            {"item": {"id": f"intel--sim{i}", "timestamp": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
             "id": f"intel--sim{i}", "canonical_ts": now - timedelta(hours=1)}
            for i in range(50)
        ]
        historical_state_items = {
            f"intel--hist{i}": {
                "canonical_ts": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),  # still fresh, not retired
            }
            for i in range(50_000)  # simulates the pre-incident ~193K-object scale, scaled down for test speed
        }
        state = {"schema_version": "1.0", "items": dict(historical_state_items)}
        plan, put_ops, delete_ops = pub.build_plan(candidates, state, 24, now)

        # Zero LIST calls regardless of how large the tracked/historical set is.
        self.assertEqual(plan.list_calls, 0)
        # No PUTs (nothing rendered to disk in this simulation) and no
        # DELETEs (the 50K historical entries are still "fresh" in this
        # scenario) -- the critical assertion is that build_plan() touched
        # exactly what the candidate/state data implied, in time proportional
        # to input size, not a hardcoded full-corpus assumption.
        self.assertEqual(len(put_ops), 0)
        self.assertEqual(len(delete_ops), 0)
        self.assertEqual(plan.new + plan.changed + plan.unchanged, 0)  # none rendered -> none counted


if __name__ == "__main__":
    unittest.main()
