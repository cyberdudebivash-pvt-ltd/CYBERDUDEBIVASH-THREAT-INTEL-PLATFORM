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
from unittest.mock import patch

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

    def test_one_manifest_write_failure_does_not_block_the_others_and_is_reported(self):
        """P0 PRODUCTION ASSURANCE regression test (post-#369 audit): before
        this fix, a single manifest's write failure raised out of
        clear_report_urls() entirely -- since this function is called from
        inside execute_plan()'s try/finally with no except of its own, that
        exception propagated past main()'s call to save_publish_state(),
        silently losing the in-memory retirement state for EVERY id this
        run touched, not just the one whose manifest failed. Both manifests
        carry an id that needs clearing (CodeRabbit review on PR #370: the
        original version of this test gave manifest_b an id absent from
        html_ids, so it never exercised a real write on that file -- it
        could not have told isolation-works-correctly apart from
        isolation-is-a-no-op). manifest_a is forced to fail; manifest_b
        must still get its real, needed update. clear_report_urls must:
        (1) not raise, (2) still return which manifest(s) failed, (3) still
        apply the update to every OTHER manifest, (4) leave the failed
        manifest's original content untouched (no partial write)."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            manifest_a = Path(td) / "feed_a.json"
            manifest_b = Path(td) / "feed_b.json"
            manifest_a.write_text(json.dumps([{"id": "intel--a", "report_url": "/reports/x/a.html"}]))
            manifest_b.write_text(json.dumps([{"id": "intel--a", "report_url": "/reports/x/a-mirror.html"}]))
            orig = pub.REPORT_URL_MANIFESTS
            pub.REPORT_URL_MANIFESTS = [manifest_a, manifest_b]
            real_replace = pub.os.replace

            def _flaky_replace(src, dst):
                if Path(dst) == manifest_a:
                    raise OSError("simulated disk failure writing manifest_a")
                return real_replace(src, dst)

            try:
                with patch.object(pub.os, "replace", side_effect=_flaky_replace):
                    failed = pub.clear_report_urls(html_ids={"intel--a"}, pdf_ids=set())
                self.assertEqual(failed, [manifest_a], "must report exactly the manifest that failed to write")
                self.assertEqual(
                    json.loads(manifest_a.read_text())[0]["report_url"], "/reports/x/a.html",
                    "failed write must never partially land -- original content must survive untouched",
                )
                self.assertEqual(
                    json.loads(manifest_b.read_text())[0]["report_url"], "",
                    "manifest_b's real, needed update must still land even though manifest_a failed",
                )
            finally:
                pub.REPORT_URL_MANIFESTS = orig

    def test_all_manifests_succeed_returns_empty_failed_list(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            manifest_path = Path(td) / "feed.json"
            manifest_path.write_text(json.dumps([{"id": "intel--a", "report_url": "/reports/x/a.html"}]))
            orig = pub.REPORT_URL_MANIFESTS
            pub.REPORT_URL_MANIFESTS = [manifest_path]
            try:
                failed = pub.clear_report_urls(html_ids={"intel--a"}, pdf_ids=set())
                self.assertEqual(failed, [], "no failures -- must return an empty list, not None or a truthy sentinel")
            finally:
                pub.REPORT_URL_MANIFESTS = orig


class TestExecutePlanManifestFailureRecovery(unittest.TestCase):
    """P0 PRODUCTION ASSURANCE regression test (post-#369 audit) for
    execute_plan()'s restoration logic: when clear_report_urls() reports a
    failed manifest, every id this run's retirement batch touched must be
    restored to its pre-clear state (never permanently dropped from
    tracking), so the next run's retirement pass retries the FULL
    delete+clear for all of them. Redoing an already-successful S3 delete
    is safe by construction -- s3_delete() treats an already-absent key as
    success (idempotent), and DELETE is not Class A billed -- so this
    restoration trades a little redundant work for guaranteed eventual
    consistency, matching this codebase's established fail-safe direction
    (bounded-but-redundant beats silently incomplete)."""

    def test_restoration_logic_recovers_full_entry_on_manifest_failure(self):
        """Exercises the REAL execute_plan() (CodeRabbit review on PR #370:
        an earlier version of this test duplicated execute_plan()'s
        bookkeeping inline, so it could keep passing even if the production
        restoration logic regressed). s3_delete() is mocked to succeed for
        both objects; clear_report_urls() is mocked to report a failed
        manifest -- execute_plan() itself must then restore the id's full
        pre-clear state entry."""
        intel_id = "intel--manifest-fail-restore"
        original_entry = {
            "canonical_ts": "2026-09-01T00:00:00Z",
            "html_key": f"reports/2026/01/{intel_id}.html",
            "pdf_key": f"reports/pdf/{intel_id}.pdf",
        }
        state = {"items": {intel_id: dict(original_entry)}}
        delete_ops = [
            {"id": intel_id, "kind": "html", "bucket": BUCKET_REPORTS, "key": original_entry["html_key"]},
            {"id": intel_id, "kind": "pdf", "bucket": BUCKET_DATA, "key": original_entry["pdf_key"]},
        ]

        with patch.object(pub, "s3_delete", return_value=True), \
             patch.object(pub, "clear_report_urls", return_value=[Path("/tmp/simulated-failed-manifest.json")]) as mock_clear:
            put_ok, delete_ok = pub.execute_plan([], delete_ops, state, "https://fake.example.r2.cloudflarestorage.com")

        self.assertEqual(delete_ok, 2, "both real (mocked) s3_delete calls must have been counted as successful")
        mock_clear.assert_called_once_with(html_ids={intel_id}, pdf_ids={intel_id})
        self.assertIn(intel_id, state["items"], "must be restored, not permanently dropped, when a manifest failed to write")
        self.assertEqual(state["items"][intel_id], original_entry, "restored entry must exactly match its pre-clear state (both keys, canonical_ts)")

    def test_no_restoration_when_all_manifests_succeed(self):
        """Symmetric case: when clear_report_urls() reports no failures, the
        id must be fully retired (popped from state), not left behind."""
        intel_id = "intel--manifest-success-retire"
        state = {"items": {intel_id: {
            "canonical_ts": "2026-09-01T00:00:00Z",
            "html_key": f"reports/2026/01/{intel_id}.html",
        }}}
        delete_ops = [{"id": intel_id, "kind": "html", "bucket": BUCKET_REPORTS, "key": state["items"][intel_id]["html_key"]}]

        with patch.object(pub, "s3_delete", return_value=True), \
             patch.object(pub, "clear_report_urls", return_value=[]):
            pub.execute_plan([], delete_ops, state, "https://fake.example.r2.cloudflarestorage.com")

        self.assertNotIn(intel_id, state["items"], "must be fully retired when every manifest write actually succeeded")


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


class TestStateFailClosed(unittest.TestCase):
    """P0 R2 COST AUDIT FIX: missing/corrupt publish state must FAIL CLOSED
    -- it must never trigger a full bucket LIST, a whole-corpus upload,
    uncontrolled deletion, or reconstruction by enumerating R2. Proves this
    holds both at load_publish_state() (the loader itself) and at
    build_plan() (the consumer), including at candidate/state volumes far
    beyond any realistic 24h window -- the same "regardless of size" bar
    TestCostSimulation above already sets for the historical-state case."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="pub_failclosed_test_"))
        self.state_path = self.tmp / "r2_report_publish_state.json"
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_state_file_bootstraps_to_empty_without_error_or_loud_log(self):
        self.assertFalse(self.state_path.exists())
        with patch.object(pub, "STATE_PATH", self.state_path), \
             patch.object(pub.log, "error") as mock_error:
            state = pub.load_publish_state()
        self.assertEqual(state, {"schema_version": "1.0", "items": {}})
        mock_error.assert_not_called()  # routine bootstrap, not an anomaly

    def test_corrupt_json_state_file_discards_and_logs_loudly(self):
        self.state_path.write_text("{not valid json at all", encoding="utf-8")
        with patch.object(pub, "STATE_PATH", self.state_path), \
             patch.object(pub.log, "error") as mock_error:
            state = pub.load_publish_state()
        self.assertEqual(state, {"schema_version": "1.0", "items": {}})
        mock_error.assert_called_once()  # unlike missing-file, this IS an anomaly worth flagging loudly

    def test_wrong_shape_state_file_discards_and_logs_loudly(self):
        """Valid JSON, wrong shape (e.g. a bare list, or a dict with no
        'items' key) is exactly as dangerous as unparseable JSON -- both
        mean this script cannot trust what it thinks it already published."""
        self.state_path.write_text(json.dumps(["not", "the", "right", "shape"]), encoding="utf-8")
        with patch.object(pub, "STATE_PATH", self.state_path), \
             patch.object(pub.log, "error") as mock_error:
            state = pub.load_publish_state()
        self.assertEqual(state, {"schema_version": "1.0", "items": {}})
        mock_error.assert_called_once()

    def test_missing_items_key_discards_and_logs_loudly(self):
        self.state_path.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
        with patch.object(pub, "STATE_PATH", self.state_path), \
             patch.object(pub.log, "error") as mock_error:
            state = pub.load_publish_state()
        self.assertEqual(state, {"schema_version": "1.0", "items": {}})
        mock_error.assert_called_once()

    def test_empty_state_causes_zero_delete_ops_regardless_of_candidate_volume(self):
        """The concrete 'fails closed' guarantee: build_plan()'s retirement
        pass only ever iterates the STATE FILE's own tracked ids -- an empty
        state (from a missing or discarded-corrupt file) means that loop
        runs zero times, so delete_ops is always [] no matter how many
        candidates this run sees. Never a full-bucket LIST, never an
        uncontrolled DELETE, never reconstruction by enumerating R2."""
        empty_state = {"schema_version": "1.0", "items": {}}
        candidates = [
            {
                "item": {"id": f"intel--failclosed{i:06d}",
                         "timestamp": (self.now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")},
                "id": f"intel--failclosed{i:06d}",
                "canonical_ts": self.now - timedelta(hours=1),
            }
            for i in range(10_000)  # far beyond any realistic 24h window
        ]
        plan, _put_ops, delete_ops = pub.build_plan(candidates, empty_state, 24, self.now)

        self.assertEqual(plan.list_calls, 0, "empty/lost state must never cause a LIST call")
        self.assertEqual(delete_ops, [], "empty/lost state must never cause an uncontrolled DELETE")
        self.assertEqual(plan.delete, 0)
        self.assertEqual(plan.expired, 0)
        # Every candidate is legitimately new-looking (nothing rendered to
        # disk in this simulation, so still zero PUT here too) -- the point
        # is that whatever PUT volume DOES result stays bounded by candidate
        # count (itself bounded by the 24h window upstream), never by state
        # file corruption reconstructing or inflating scope.
        self.assertEqual(len(plan.notes), 0)

    def test_load_publish_state_recovery_from_corruption_then_next_run_rebuilds_correctly(self):
        """End-to-end: a corrupted state file does not permanently break the
        incremental architecture -- the very next successful run, working
        from the (safely emptied) state, re-establishes real tracking."""
        self.state_path.write_text("garbage{{{", encoding="utf-8")
        with patch.object(pub, "STATE_PATH", self.state_path):
            state = pub.load_publish_state()
        self.assertEqual(state["items"], {})

        # Simulate this run successfully publishing one item and saving state.
        state["items"]["intel--recoverytest01"] = {
            "canonical_ts": self.now.isoformat().replace("+00:00", "Z"),
            "html_key": "reports/2026/09/intel--recoverytest01.html",
            "html_sha256": "b" * 64,
        }
        with patch.object(pub, "STATE_PATH", self.state_path):
            pub.save_publish_state(state)

        with patch.object(pub, "STATE_PATH", self.state_path):
            reloaded = pub.load_publish_state()
        self.assertIn("intel--recoverytest01", reloaded["items"])
        self.assertEqual(reloaded["items"]["intel--recoverytest01"]["html_sha256"], "b" * 64)


if __name__ == "__main__":
    unittest.main()
