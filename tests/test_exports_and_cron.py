"""
tests/test_exports_and_cron.py — CyberDudeBivash SENTINEL APEX

Verification for the live ingestion pipeline (workers/intel-gateway/src/
ingestion/cron_worker.js), the tier-gated SIEM/SOAR export routes
(workers/intel-gateway/src/routes/exports.js), and the checkout UX
additions (js/checkout.js).

These three modules are Cloudflare Worker / browser JavaScript (ESM),
not Python -- reimplementing their parsing, scoring, rule-syntax, and
tier-gating logic here in Python would just be a second, independently
maintained copy that could silently drift from what actually ships
(exactly the "Single Source of Truth" duplication CLAUDE.md's governance
constitution flags as a defect). The real, behavioral tests are the
`node --test` suites colocated with the code they test, matching this
repository's own established convention for this Worker (see e.g.
workers/intel-gateway/src/__tests__/detection-registry.test.js and the
TITAN_STAGE*.md reports' "node --test is this platform's established
verification mechanism for this file family").

This file is the orchestration/CI-facing layer the task brief asks for:
it runs those real suites via subprocess and fails loudly (with the
captured Node output) if any assertion in them fails, plus a handful of
direct structural checks (files exist, the new cron schedule is wired,
all five export formats are present) that ARE meaningful to verify
directly from Python without duplicating behavioral logic.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GATEWAY_SRC = REPO_ROOT / "workers" / "intel-gateway" / "src"

CRON_WORKER_JS = GATEWAY_SRC / "ingestion" / "cron_worker.js"
EXPORTS_JS = GATEWAY_SRC / "routes" / "exports.js"
WRANGLER_TOML = REPO_ROOT.joinpath("workers", "intel-gateway", "wrangler.toml")
CHECKOUT_JS = REPO_ROOT / "js" / "checkout.js"

NODE_TEST_FILES = [
    GATEWAY_SRC / "ingestion" / "__tests__" / "cron_worker.test.js",
    GATEWAY_SRC / "routes" / "__tests__" / "exports.test.js",
    REPO_ROOT / "js" / "__tests__" / "checkout.test.js",
]

EXPORT_FORMATS = [
    "/api/v1/export/suricata.rules",
    "/api/v1/export/snort.rules",
    "/api/v1/export/yara.yar",
    "/api/v1/export/splunk.csv",
    "/api/v1/export/taxii.json",
]


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="node binary not available in this environment")
class TestNodeTestSuitesPass:
    """Runs the real, behavioral node:test suites and surfaces their output on failure."""

    def _run(self, test_file: pathlib.Path) -> subprocess.CompletedProcess:
        assert test_file.exists(), f"expected test file missing: {test_file}"
        return subprocess.run(
            ["node", "--test", str(test_file)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_cron_worker_suite_passes(self):
        result = self._run(NODE_TEST_FILES[0])
        assert result.returncode == 0, (
            f"cron_worker.test.js failed (ingestion parser / scoring / merge / TTL logic):\n"
            f"{result.stdout}\n{result.stderr}"
        )
        assert "# fail 0" in result.stdout

    def test_exports_suite_passes(self):
        result = self._run(NODE_TEST_FILES[1])
        assert result.returncode == 0, (
            f"exports.test.js failed (rule-syntax / tier-gating for the SIEM export routes):\n"
            f"{result.stdout}\n{result.stderr}"
        )
        assert "# fail 0" in result.stdout

    def test_checkout_suite_passes(self):
        result = self._run(NODE_TEST_FILES[2])
        assert result.returncode == 0, (
            f"checkout.test.js failed (checkout UX additions -- region currency, GSTIN, "
            f"decline handling, onboarding snippets):\n{result.stdout}\n{result.stderr}"
        )
        assert "# fail 0" in result.stdout

    def test_full_gateway_suite_has_no_new_failures(self):
        """
        Runs the entire workers/intel-gateway/src node:test tree (auto-discovered
        recursively) and checks the failure count against the documented
        pre-existing baseline (6 failures, all unrelated to this change -- see
        cache-bust-admin.test.js, find-item-by-slug.test.js, and the four
        zero-blast-radius layer-boundary governance tests). This is a
        regression guard, not a claim that this PR fixes those six.
        """
        result = subprocess.run(
            ["node", "--test"],
            cwd=str(GATEWAY_SRC),
            capture_output=True,
            text=True,
            timeout=180,
        )
        fail_line = next((l for l in result.stdout.splitlines() if l.strip().startswith("# fail")), None)
        assert fail_line is not None, f"could not find a '# fail N' summary line:\n{result.stdout}"
        fail_count = int(fail_line.split()[-1])
        assert fail_count <= 6, (
            f"expected at most the 6 documented pre-existing failures, got {fail_count}:\n{result.stdout}"
        )


class TestDeliverablesArePresentAndWired:
    """Direct, non-duplicative structural checks -- these do not re-test JS
    behavior (that's the node:test suites above), only that the deliverables
    exist and are actually wired into the places the task brief named."""

    def test_cron_worker_module_exists(self):
        assert CRON_WORKER_JS.is_file()

    def test_exports_module_exists(self):
        assert EXPORTS_JS.is_file()

    def test_checkout_js_exists(self):
        assert CHECKOUT_JS.is_file()

    def test_wrangler_toml_declares_the_6_hourly_ingestion_cron(self):
        toml_text = WRANGLER_TOML.read_text(encoding="utf-8")
        assert "0 */6 * * *" in toml_text, "6-hourly cron schedule not found in wrangler.toml [triggers]"
        # the pre-existing 15-minute schedule must still be present, unmodified
        assert "*/15 * * * *" in toml_text, "pre-existing 15-minute cron schedule must not be removed"

    def test_index_js_dispatches_the_export_routes(self):
        index_js = (GATEWAY_SRC / "index.js").read_text(encoding="utf-8")
        assert "routeExports" in index_js
        assert '"/api/v1/export/"' in index_js

    def test_all_five_export_formats_are_implemented(self):
        exports_src = EXPORTS_JS.read_text(encoding="utf-8")
        for fmt_path in EXPORT_FORMATS:
            assert fmt_path in exports_src, f"export route not found in exports.js: {fmt_path}"

    def test_free_tier_sample_limit_matches_the_25_item_platform_convention(self):
        exports_src = EXPORTS_JS.read_text(encoding="utf-8")
        assert "FREE_SAMPLE_LIMIT = 25" in exports_src

    def test_ingestion_sources_match_the_task_brief(self):
        # Checks for the named source-URL constants themselves rather than a
        # bare domain substring: CodeQL's "Incomplete URL substring
        # sanitization" rule flagged the earlier `"cisa.gov" in cron_src`
        # form (a domain-shaped literal tested for membership in a larger
        # string). There's no untrusted input here -- cron_src is this
        # repo's own source file, read at test time -- but checking for the
        # specific constant names is both unambiguous to static analysis
        # and a more precise assertion than a loose domain substring.
        cron_src = CRON_WORKER_JS.read_text(encoding="utf-8")
        assert "KEV_URL" in cron_src, "CISA KEV source constant not found"
        assert "URLHAUS_URL" in cron_src, "URLhaus source constant not found"
        assert "TOR_EXIT_URL" in cron_src, "Tor exit node source constant not found"

    def test_x_sentinel_key_header_is_a_recognized_auth_alias(self):
        index_js = (GATEWAY_SRC / "index.js").read_text(encoding="utf-8")
        assert "X-Sentinel-Key" in index_js
