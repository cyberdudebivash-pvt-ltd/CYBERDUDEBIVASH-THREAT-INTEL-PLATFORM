#!/usr/bin/env python3
"""
tests/test_dashboard_single_source.py
SENTINEL APEX v175.1 -- SINGLE-SOURCE ARCHITECTURE REGRESSION TESTS
====================================================================
Root cause fixed: dashboard EICC engine used api/v1/intel/latest.json as PRIMARY
while GOC engine used api/feed.json, creating dual-source divergence.

Evidence of the bug (from forensic audit 2026-06-07):
  - Stage 67 (Generate API Manifests) runs BEFORE Stage 71 (Source Diversity Enforcer)
  - latest.json was written pre-diversity-enforcement: could have 102 items
  - api/feed.json R2 had post-diversity count: 64 items
  - On R2 failure, GitHub fallback served different item counts per endpoint
  - Customers saw the same intel in both EICC sections AND main GOC grid
    (ticker, preview pane showing items from latest.json; grid showing api/feed.json)

Fix:
  - EICC_DATA_URLS[0] changed from 'api/v1/intel/latest.json' to 'api/feed.json'
  - api/v1/intel/latest.json removed from EICC_DATA_URLS entirely
  - dashboard_frontend_guard.py CHECK 2d enforces this contract permanently

2026-09-27 (after #513): the EICC engine no longer declares EICC_DATA_URLS.
It renders one snapshot built by js/apex-dashboard-snapshot.js from exactly
two same-origin reads -- /api/health (freshness contract) and /api/feed.json
(the only feed source) -- and the raw.githubusercontent.com fallback was
removed on purpose (a frozen mirror must never be shown as current intel).
The EICC tests below assert the same single-source mandate against that
module; T-SSRC-06 is inverted accordingly (no GitHub fallback).

Tests:
  T-SSRC-01: EICC_DATA_URLS does NOT contain api/v1/intel/latest.json
  T-SSRC-02: EICC_DATA_URLS[0] (PRIMARY) is api/feed.json
  T-SSRC-03: GOC MANIFEST_URLS[0] (PRIMARY) is api/feed.json
  T-SSRC-04: Both EICC and GOC have api/feed.json as their PRIMARY source
  T-SSRC-05: api/v1/intel/latest.json is only in GOC MANIFEST_URLS (not EICC)
  T-SSRC-06: EICC has NO raw.githubusercontent.com fallback (frozen mirror)
  T-SSRC-07: Guard CHECK 2d is present and tests for single-source mandate
  T-SSRC-08: CHECK 2d inline logic correctly FAILs a regressed index
  T-SSRC-09: CHECK 2d inline logic correctly PASSes the fixed index.html
  T-SSRC-10: EICC snapshot makes exactly 2 reads (/api/health + /api/feed.json)
  T-SSRC-11: single-source rationale documented in the EICC snapshot module
"""

import re
import os
from scripts.homepage_source import read_homepage_source  # index.html + extracted css/js
import sys
import unittest

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INDEX_HTML = os.path.join(REPO_ROOT, 'index.html')
GUARD_PY   = os.path.join(REPO_ROOT, 'scripts', 'dashboard_frontend_guard.py')
SNAPSHOT_JS = os.path.join(REPO_ROOT, 'js', 'apex-dashboard-snapshot.js')


# ── Helpers ───────────────────────────────────────────────────────────────────
def _load_index():
    """Return index.html content (full file)."""
    return read_homepage_source()


def _get_eicc_block(content):
    """Return the raw content of the EICC_DATA_URLS array block (between brackets)."""
    m = re.search(r'var EICC_DATA_URLS\s*=\s*\[(.*?)\];', content, re.DOTALL)
    return m.group(1) if m else None


def _load_snapshot():
    with open(SNAPSHOT_JS, 'r', encoding='utf-8') as f:
        return f.read()


def _snapshot_urls(snapshot_src):
    """Every `var <NAME>_URL = '<url>';` the EICC snapshot module declares, in order."""
    return re.findall(r"var ([A-Z_]+_URL)\s*=\s*'([^']+)';", snapshot_src)


def _snapshot_code(snapshot_src):
    """Snapshot source with comments stripped (so documentation that names a
    removed source does not count as using it)."""
    no_block = re.sub(r'/\*.*?\*/', '', snapshot_src, flags=re.DOTALL)
    return '\n'.join(l for l in no_block.split('\n') if not l.strip().startswith('//'))


def _get_manifest_block(content):
    """Return the LARGEST MANIFEST_URLS array block (GOC engine's block)."""
    blocks = re.findall(r'var MANIFEST_URLS\s*=\s*\[(.*?)\];', content, re.DOTALL)
    return max(blocks, key=len) if blocks else None


def _get_ordered_url_lines(block):
    """Extract ordered non-comment URL entries from an array block."""
    lines = [l.strip() for l in block.split('\n')
             if l.strip() and not l.strip().startswith('//')]
    return [l for l in lines if '.json' in l or 'URL' in l.upper()]


def _check_2d_failures(html_content):
    """
    Inline CHECK 2d detection logic (mirrors dashboard_frontend_guard.py CHECK 2d).
    Returns list of (severity, message) tuples for single-source mandate violations.
    """
    failures = []
    eicc_blocks = re.findall(r'var EICC_DATA_URLS\s*=\s*\[(.*?)\];', html_content, re.DOTALL)
    if not eicc_blocks:
        return failures
    block = eicc_blocks[0]
    src_lines = [l.strip() for l in block.split('\n')
                 if l.strip() and not l.strip().startswith('//')]
    url_lines = [l for l in src_lines if '.json' in l or 'URL' in l.upper()]
    first = url_lines[0] if url_lines else ''
    if 'latest.json' in first and "'api/feed.json'" not in first and '"api/feed.json"' not in first:
        failures.append(('FAIL', 'DUAL-SOURCE BUG: EICC PRIMARY = api/v1/intel/latest.json (pre-diversity data)'))
    if 'latest.json' in block:
        failures.append(('FAIL', 'REGRESSION: api/v1/intel/latest.json present in EICC_DATA_URLS'))
    return failures


# ── Test Cases ────────────────────────────────────────────────────────────────
class TestDashboardSingleSource(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.content = _load_index()
        cls.eicc_block     = _get_eicc_block(cls.content)
        cls.manifest_block = _get_manifest_block(cls.content)
        cls.snapshot_src   = _load_snapshot()
        cls.snapshot_urls  = _snapshot_urls(cls.snapshot_src)
        cls.snapshot_code  = _snapshot_code(cls.snapshot_src)

    def _assert_eicc_uses_snapshot(self):
        self.assertIn('<script src="/js/apex-dashboard-snapshot.js"></script>', self.content,
                      "index.html must load the EICC snapshot module")
        self.assertIn('var SNAP = window.ApexDashboardSnapshot;', self.content,
                      "the EICC engine must render from ApexDashboardSnapshot")
        self.assertIsNone(self.eicc_block,
                          "EICC_DATA_URLS is back in index.html: EICC must read only via the snapshot")

    # ── T-SSRC-01 ─────────────────────────────────────────────────────────────
    def test_01_latest_json_absent_from_eicc(self):
        """T-SSRC-01: api/v1/intel/latest.json must NOT be an EICC source.

        ROOT CAUSE: latest.json is generated by Stage 67 BEFORE Stage 71 diversity
        enforcement. Serving it to EICC caused item-count divergence vs GOC.
        """
        self._assert_eicc_uses_snapshot()
        self.assertNotIn('latest.json', self.snapshot_code,
                         "REGRESSION: the EICC snapshot reads api/v1/intel/latest.json. "
                         "EICC must read ONLY from api/feed.json.")

    # ── T-SSRC-02 ─────────────────────────────────────────────────────────────
    def test_02_eicc_primary_is_feed_json(self):
        """T-SSRC-02: the EICC feed source is api/feed.json."""
        self._assert_eicc_uses_snapshot()
        self.assertIn(('FEED_URL', '/api/feed.json'), self.snapshot_urls,
                      f"EICC feed source is not /api/feed.json. Found: {self.snapshot_urls!r}")

    # ── T-SSRC-03 ─────────────────────────────────────────────────────────────
    def test_03_goc_primary_is_feed_json(self):
        """T-SSRC-03: GOC MANIFEST_URLS first entry (PRIMARY) must be api/feed.json."""
        self.assertIsNotNone(self.manifest_block, "MANIFEST_URLS block not found in index.html")
        url_lines = _get_ordered_url_lines(self.manifest_block)
        self.assertTrue(url_lines, "MANIFEST_URLS has no URL entries")
        first = url_lines[0]
        self.assertIn(
            'api/feed.json',
            first,
            f"GOC MANIFEST_URLS PRIMARY is not api/feed.json. Found: {first!r}."
        )

    # ── T-SSRC-04 ─────────────────────────────────────────────────────────────
    def test_04_eicc_and_goc_share_same_primary(self):
        """T-SSRC-04: EICC and GOC must both have api/feed.json as their PRIMARY source.

        This is the core single-source mandate. When both engines read from the same
        source, dashboard sections cannot show divergent item counts regardless of
        pipeline stage ordering or R2 availability.
        """
        self.assertIsNotNone(self.manifest_block, "MANIFEST_URLS block not found")
        manifest_first = _get_ordered_url_lines(self.manifest_block)[0]
        feed_urls = [u for n, u in self.snapshot_urls if n == 'FEED_URL']
        self.assertTrue(
            feed_urls and feed_urls[0].lstrip('/') == 'api/feed.json' and 'api/feed.json' in manifest_first,
            f"EICC and GOC primary sources diverge.\n"
            f"  EICC FEED_URL:    {feed_urls!r}\n"
            f"  MANIFEST PRIMARY: {manifest_first!r}\n"
            "Both must be api/feed.json for single-source architecture."
        )

    # ── T-SSRC-05 ─────────────────────────────────────────────────────────────
    def test_05_latest_json_only_in_goc_not_eicc(self):
        """T-SSRC-05: api/v1/intel/latest.json may appear in GOC MANIFEST_URLS (fallback)
        but never as an EICC source."""
        self.assertIsNotNone(self.manifest_block)
        self.assertNotIn('latest.json', self.snapshot_code,
                         "api/v1/intel/latest.json must not be an EICC source")
        # GOC should have it (as secondary/fallback) — WARN only, not hard fail
        if 'latest.json' not in self.manifest_block:
            import warnings
            warnings.warn(
                "api/v1/intel/latest.json absent from GOC MANIFEST_URLS — "
                "ensure Worker /api/v1/intel/latest.json endpoint still reachable via other path",
                stacklevel=2
            )

    # ── T-SSRC-06 ─────────────────────────────────────────────────────────────
    def test_06_eicc_has_no_frozen_github_fallback(self):
        """T-SSRC-06 (inverted after #513): EICC must NOT fall back to
        raw.githubusercontent.com. That mirror is frozen (js/feed-state.js);
        serving it made a stale 109-item feed look "API ● LIVE". When the
        Worker is down EICC shows an unavailable state instead."""
        self._assert_eicc_uses_snapshot()
        self.assertNotIn('raw.githubusercontent.com', self.snapshot_code,
                         "EICC snapshot must not fetch the frozen GitHub mirror")

    # ── T-SSRC-07 ─────────────────────────────────────────────────────────────
    def test_07_guard_has_check_2d(self):
        """T-SSRC-07: dashboard_frontend_guard.py must contain CHECK 2d single-source check."""
        with open(GUARD_PY, 'r', encoding='utf-8', errors='replace') as f:
            guard_content = f.read()

        self.assertIn(
            'CHECK 2d',
            guard_content,
            "dashboard_frontend_guard.py is missing CHECK 2d (single-source mandate). "
            "Add CHECK 2d to enforce EICC_DATA_URLS uses api/feed.json as PRIMARY."
        )
        self.assertIn(
            'EICC_DATA_URLS',
            guard_content,
            "dashboard_frontend_guard.py does not inspect EICC_DATA_URLS. "
            "The guard must verify EICC uses the correct single source."
        )
        self.assertIn(
            'latest.json',
            guard_content,
            "Guard does not check for latest.json in EICC_DATA_URLS — regression undetectable."
        )

    # ── T-SSRC-08 ─────────────────────────────────────────────────────────────
    def test_08_check_2d_logic_detects_dual_source_regression(self):
        """T-SSRC-08: CHECK 2d inline logic must detect latest.json as EICC PRIMARY.

        Inlines the CHECK 2d detection logic (mirroring dashboard_frontend_guard.py CHECK 2d)
        against a synthetically regressed index.html to verify the logic correctly catches
        the dual-source bug when someone reverts the fix.

        NOTE: Uses inline logic (not subprocess) to avoid FUSE truncation side-effects
        on the guard .py file in the CI sandbox. T-SSRC-07 verifies the guard file itself
        contains the CHECK 2d code.
        """
        if 'var EICC_DATA_URLS' not in self.content:
            self.skipTest("EICC_DATA_URLS not found in index.html — skipping regression simulation")

        # Build a regressed index (bug re-introduced: latest.json as PRIMARY)
        broken_eicc_replacement = (
            "var EICC_DATA_URLS = [\n"
            "    'api/v1/intel/latest.json',\n"
            "    'api/feed.json',\n"
            "    'https://raw.githubusercontent.com/cyberdudebivash/"
            "CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/main/api/feed.json'\n"
            "];"
        )
        broken_content = re.sub(
            r'var EICC_DATA_URLS\s*=\s*\[.*?\];',
            broken_eicc_replacement,
            self.content,
            count=1,
            flags=re.DOTALL
        )

        # Verify: broken content TRIGGERS failures
        broken_failures = _check_2d_failures(broken_content)
        self.assertTrue(
            len(broken_failures) > 0,
            "CHECK 2d inline logic did NOT detect the dual-source regression.\n"
            "Broken EICC_DATA_URLS had latest.json as PRIMARY but zero failures returned.\n"
            "Fix: ensure CHECK 2d logic detects when EICC_DATA_URLS[0] contains latest.json."
        )
        fail_messages = [msg for _, msg in broken_failures]
        self.assertTrue(
            any('DUAL-SOURCE' in m or 'latest.json' in m or 'REGRESSION' in m
                for m in fail_messages),
            f"Failures detected but none mention the actual bug. Failures: {fail_messages}"
        )

        # Verify: fixed content produces ZERO failures
        fixed_failures = _check_2d_failures(self.content)
        self.assertEqual(
            len(fixed_failures), 0,
            f"CHECK 2d inline logic reports failures on the FIXED index.html: {fixed_failures}\n"
            "The fix in index.html may have been partially reverted."
        )

    # ── T-SSRC-09 ─────────────────────────────────────────────────────────────
    def test_09_check_2d_logic_passes_on_fixed_index(self):
        """T-SSRC-09: CHECK 2d inline logic must produce zero failures on the fixed index.html.

        This is the positive-path test for the single-source mandate. Verifies the current
        index.html passes all CHECK 2d conditions clean.

        NOTE: Uses inline logic (not subprocess) to avoid FUSE truncation side-effects.
        T-SSRC-07 verifies the guard file itself contains the CHECK 2d code.
        """
        failures = _check_2d_failures(self.content)
        self.assertEqual(
            len(failures), 0,
            "CHECK 2d inline logic reports failures on the current (should-be-fixed) index.html:\n"
            + "\n".join(f"  FAIL: {msg}" for _, msg in failures)
            + "\nThe EICC single-source fix may have been reverted. "
            "Ensure EICC_DATA_URLS[0] = 'api/feed.json' and latest.json is absent from EICC_DATA_URLS."
        )

    # ── T-SSRC-10 ─────────────────────────────────────────────────────────────
    def test_10_eicc_has_exactly_two_url_entries(self):
        """T-SSRC-10: the EICC snapshot makes exactly 2 reads:
          /api/health    (freshness contract, never counted as intel)
          /api/feed.json (the only feed source)
        More entries increase the risk of re-introducing a divergent source."""
        self.assertEqual(
            self.snapshot_urls, [('HEALTH_URL', '/api/health'), ('FEED_URL', '/api/feed.json')],
            f"EICC snapshot sources changed: {self.snapshot_urls!r}. Extra entries increase dual-source risk."
        )

    # ── T-SSRC-11 ─────────────────────────────────────────────────────────────
    def test_11_v175_comment_present_in_eicc_block(self):
        """T-SSRC-11: the single-source rationale stays documented where EICC
        chooses its sources (audit trail for future engineers)."""
        header = self.snapshot_src[:self.snapshot_src.index('(function')]
        self.assertIn('/api/feed.json  -- the authoritative R2 feed', header)
        self.assertIn('There is no raw.githubusercontent.com fallback', header)

if __name__ == '__main__':
    unittest.main(verbosity=2)
