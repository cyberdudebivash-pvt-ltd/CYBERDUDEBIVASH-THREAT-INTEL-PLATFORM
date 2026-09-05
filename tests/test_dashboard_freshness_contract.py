"""
tests/test_dashboard_freshness_contract.py

P0 regression coverage for the dashboard/backend freshness contract fix.

CONFIRMED PRODUCTION DEFECT (live evidence, 2026-09-05): the public
dashboard (https://intel.cyberdudebivash.com/) displayed "SYNC: LIVE" /
"MANIFEST VERIFIED" while its own /api/health and /api/platform/stats
endpoints reported last_sync: "2026-08-26T08:50:13Z" -- ~10 days stale at
the time of the live check (`curl https://intel.cyberdudebivash.com/api/health`).
workers/intel-gateway/src/index.js's own classifyFreshness() (added for a
PRIOR occurrence of this exact incident, per that function's comment and
workers/intel-gateway/src/__tests__/classify-freshness.test.js) already
computed the correct freshness state from feedData.generated_at, but that
signal was only ever exposed on the ADMIN-authenticated branch of
/api/health -- the public dashboard had no way to read it, and its
"SYNC: LIVE" badge was (and, without this fix, always will be) driven
purely by "did the manifest fetch succeed from the primary domain"
(isApiSource), with zero cross-check against how stale that manifest's
own content actually was.

Root cause of the underlying staleness itself (separate fix, same PR):
scripts/validate_reports.py (STAGE 3.3, Report Validation Gate) has hard-
failed every natural sentinel-blogger.yml run since PR #369/#370 landed,
which skips STAGE 3.93 (scripts/generate_api_manifests.py -- the script
that sets feedData.generated_at) on every one of those runs. See
tests/test_validate_reports_window_deferral.py for that fix's own coverage.

This file is a STATIC source-contract test, not a live/DOM/browser test --
this repository has no JS DOM test harness for index.html (see this
codebase's own documented Playwright/service-worker sandbox limitations).
It verifies the actual source text of workers/intel-gateway/src/index.js
and index.html contains the specific, load-bearing code this fix depends
on, so an unrelated future edit cannot silently regress it back to the
exact contradiction this test exists to catch. It does NOT prove live
production behavior -- see PHASE 24 in the task record for that evidence
(a direct curl of the live endpoints), which a static test cannot replay.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKER_SRC = REPO_ROOT / "workers" / "intel-gateway" / "src" / "index.js"
INDEX_HTML = REPO_ROOT / "index.html"


def _worker_source() -> str:
    return WORKER_SRC.read_text(encoding="utf-8")


def _index_html_source() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


class TestPlatformStatsExposesFreshnessPublicly:
    """GATE F/H: /api/platform/stats -- the endpoint index.html's
    fetchWorkerStats() itself documents as the single source of truth --
    must carry the same freshness signal classifyFreshness() already
    computes, unauthenticated (unlike /api/health's admin-gated
    data_freshness), so the public dashboard can actually read it."""

    def test_platform_stats_handler_computes_classify_freshness_from_generated_at(self):
        src = _worker_source()
        stats_block_start = src.index('if (path === "/api/platform/stats")')
        # Bound the search to this handler, not the whole 7000+ line file --
        # the next route registration marks its end.
        stats_block_end = src.index('if (path ===', stats_block_start + 10)
        stats_block = src[stats_block_start:stats_block_end]

        assert "classifyFreshness(feedData.generated_at)" in stats_block, (
            "/api/platform/stats must compute its freshness signal from "
            "feedData.generated_at (the pipeline's own 'last successfully "
            "wrote this file' timestamp) via the existing classifyFreshness() "
            "-- reused, not reimplemented, and NOT from stats.last_sync "
            "(source-article publish date), which can mask a silently broken "
            "pipeline per this function's own documented incident history."
        )
        assert "freshness: freshness.state" in stats_block
        assert "freshness_age_seconds: freshness.age_seconds" in stats_block
        assert "last_feed_sync_utc: feedData.generated_at" in stats_block
        # Backward compatibility: the pre-existing field must still be present
        # and unrenamed for existing consumers.
        assert "last_sync: stats.last_sync" in stats_block

    def test_freshness_fields_are_not_gated_behind_admin_auth(self):
        src = _worker_source()
        stats_block_start = src.index('if (path === "/api/platform/stats")')
        stats_block_end = src.index('if (path ===', stats_block_start + 10)
        stats_block = src[stats_block_start:stats_block_end]
        # Unlike /api/health's data_freshness, this must be unconditional --
        # no `if (healthIsAuthenticated)`-style gate anywhere in this handler.
        assert "healthIsAuthenticated" not in stats_block, (
            "/api/platform/stats' freshness fields must be public -- this "
            "route serves the public dashboard, not an admin console."
        )

    def test_health_endpoint_admin_gate_is_unchanged(self):
        """PHASE 27 / GATE O: this fix must not touch PR #371/#372's
        security hardening of /api/health -- data_freshness stays exactly
        where it was (admin-gated), this fix adds a DIFFERENT, safe
        (state + age only, no infra detail) public signal elsewhere."""
        src = _worker_source()
        assert "body.data_freshness = dataFreshness;" in src
        idx = src.index("body.data_freshness = dataFreshness;")
        # Must still be inside the `if (healthIsAuthenticated) {` block --
        # look back a short, bounded window for that guard.
        preceding = src[max(0, idx - 400):idx]
        assert "if (healthIsAuthenticated)" in preceding


class TestDashboardSyncBadgeCrossChecksFreshness:
    """GATE G (the exact screenshot defect): the dashboard must never
    render SYNC: LIVE while its own authoritative freshness signal says
    otherwise."""

    def test_fetch_worker_stats_reads_intel_freshness(self):
        src = _index_html_source()
        fn_start = src.index("function fetchWorkerStats()")
        fn_end = src.index("fetchWorkerStats();", fn_start)  # the call site right after the function
        fn_body = src[fn_start:fn_end]
        assert "intel.freshness" in fn_body, (
            "fetchWorkerStats() must read intel.freshness from its "
            "/api/platform/stats response to cross-check the SYNC badge."
        )

    def test_non_fresh_states_downgrade_the_sync_badge(self):
        src = _index_html_source()
        fn_start = src.index("function fetchWorkerStats()")
        fn_end = src.index("fetchWorkerStats();", fn_start)
        fn_body = src[fn_start:fn_end]

        assert "intel.freshness !== 'FRESH'" in fn_body
        assert "intel.freshness !== 'RECENT'" in fn_body
        # The downgrade must target the same two elements the "LIVE" path
        # (elsewhere in this file) sets, so it can actually override them.
        assert re.search(r"getElementById\('sync-val'\)", fn_body)
        assert re.search(r"getElementById\('integrity-status'\)", fn_body)
        assert "STALE" in fn_body

    def test_downgrade_runs_after_syncts_is_resolved_not_before(self):
        """Ordering matters: the cross-check must see the same intel
        payload fetchWorkerStats() just parsed, not race an unrelated
        earlier code path."""
        src = _index_html_source()
        fn_start = src.index("function fetchWorkerStats()")
        fn_end = src.index("fetchWorkerStats();", fn_start)
        fn_body = src[fn_start:fn_end]
        sync_ts_idx = fn_body.index("const _syncTs =")
        downgrade_idx = fn_body.index("intel.freshness !== 'FRESH'")
        assert sync_ts_idx < downgrade_idx


class TestAvgRiskScoreNaNGuard:
    """PHASE 23: a non-numeric risk_score/cvss_score must not silently
    poison the whole average into the literal string 'NaN'."""

    def test_fill_metrics_guards_against_nan_contribution(self):
        src = _index_html_source()
        fn_start = src.index("function fillMetrics(data){")
        fn_end = src.index("\n            }\n", fn_start)
        fn_body = src[fn_start:fn_end]
        assert "isNaN(_riskVal)" in fn_body
        # Never fabricates a score -- an unparseable value contributes 0,
        # the same as a genuinely absent field already did.
        assert "riskSum += isNaN(_riskVal) ? 0 : _riskVal;" in fn_body
