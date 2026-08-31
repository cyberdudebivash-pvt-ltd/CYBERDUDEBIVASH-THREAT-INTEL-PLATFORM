"""
tests/test_enterprise_suite.py

Verification for the enterprise B2B monetization work: TAXII 2.1 extensions
(workers/intel-gateway/src/taxii.js), SIEM/SOAR/MISP/OpenCTI connectors
(integrations/), and the B2B org/team seats engine
(workers/intel-gateway/src/teams.js).

Same constraint as tests/test_billing_ratelimit.py's header explains in
full: there is no local wrangler/miniflare harness in this environment, so
this cannot make 51 live HTTP calls against intel.cyberdudebivash.com (and
shouldn't -- that would burn real customer-facing quota). Every pure-logic
piece (taxii.js, teams.js) was extracted specifically to be unit-testable
under plain `node --test`; those real JS suites are run here via
subprocess (not re-implemented in Python), and this file adds Python-side
structural verification (index.js wiring, integrations/ file sanity) plus
one genuinely-functional test that mocks HTTP at the urllib layer to
exercise the real Splunk connector script end-to-end without a live call.
"""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
GATEWAY_SRC = REPO_ROOT / "workers" / "intel-gateway" / "src"
INDEX_JS = GATEWAY_SRC / "index.js"
INTEGRATIONS = REPO_ROOT / "integrations"


def _node_available() -> bool:
    return shutil.which("node") is not None


def _run_node_test(*test_files: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--test", *test_files],
        cwd=GATEWAY_SRC,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assert_suite_passes(case: unittest.TestCase, result: subprocess.CompletedProcess, min_pass: int):
    case.assertEqual(
        result.returncode, 0,
        f"suite failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
    )
    pass_count = re.search(r"^# pass (\d+)$", result.stdout, re.M)
    case.assertIsNotNone(pass_count, result.stdout)
    case.assertGreaterEqual(int(pass_count.group(1)), min_pass)
    case.assertIn("# fail 0", result.stdout, result.stdout)


# =============================================================================
# TASK 1 -- TAXII 2.1
# =============================================================================

@unittest.skipUnless(_node_available(), "node is not on PATH in this environment")
class TestTaxiiJsSuite(unittest.TestCase):
    """Runs the real taxii.js unit suite: collection registry, tier gating,
    item filtering (including the KEV/main backward-compat cases), cursor
    pagination, and the upgrade-payload builder."""

    def test_taxii_suite_passes(self):
        _assert_suite_passes(self, _run_node_test("__tests__/taxii.test.js"), min_pass=24)


class TestTaxiiDiscoveryStructure(unittest.TestCase):
    """
    "Authenticates against the TAXII 2.1 discovery endpoint using a mock
    PRO API key and asserts valid STIX 2.1 JSON structure" -- there is no
    live server to call, so this verifies the real handleTAXII() discovery
    response literal in index.js (not a re-implementation) has every field
    the TAXII 2.1 spec requires for a discovery document, and separately
    proves -- via the real taxii.js module, imported directly -- that a
    mock PRO-tier auth object clears every PRO-gated collection.
    """

    def setUp(self):
        self.source = INDEX_JS.read_text(encoding="utf-8")

    def test_discovery_response_has_required_taxii21_fields(self):
        # The literal object handleTAXII() returns for GET /taxii/ -- pull
        # the block between the two known anchors and check required keys
        # are present, rather than asserting on exact formatting.
        start = self.source.index('if (path === "/taxii/" || path === "/taxii")')
        end = self.source.index("// All other TAXII endpoints require PRO or ENTERPRISE", start)
        block = self.source[start:end]
        for required_field in ("title", "description", "default", "api_roots"):
            self.assertIn(f'{required_field}:', block, f"TAXII discovery response missing required field '{required_field}'")
        self.assertIn("application/taxii+json", self.source, "TAXII_CT content-type constant must be application/taxii+json;version=2.1")

    def test_content_type_is_stix21(self):
        self.assertIn('"application/stix+json;version=2.1"', self.source)

    @unittest.skipUnless(_node_available(), "node is not on PATH in this environment")
    def test_mock_pro_key_clears_pro_gated_collections(self):
        script = """
import { TAXII_COLLECTIONS, tierMeetsCollection } from './taxii.js';
const mockProAuth = { tier: 'PRO', key: 'cdb_pro_mock00000000000000000000' };
const results = TAXII_COLLECTIONS.map(c => ({ id: c.id, allowed: tierMeetsCollection(mockProAuth.tier, c) }));
console.log(JSON.stringify(results));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=GATEWAY_SRC, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        results = json.loads(result.stdout.strip())
        by_id = {r["id"]: r["allowed"] for r in results}
        self.assertTrue(by_id["sentinel-apex-main"])
        self.assertTrue(by_id["c2-indicators"])
        self.assertTrue(by_id["active-ransomware"])
        # A PRO key must NOT clear the two ENTERPRISE-only collections.
        self.assertFalse(by_id["sentinel-apex-kev"])
        self.assertFalse(by_id["apt-attribution"])


class TestTaxiiFreeKeyBlocked(unittest.TestCase):
    """
    "Validates that non-enterprise keys are blocked from raw TAXII streams
    with a clear upgrade payload."
    """

    def setUp(self):
        self.source = INDEX_JS.read_text(encoding="utf-8")

    def test_free_tier_denial_uses_upgrade_body_and_status_split(self):
        self.assertIn("buildTaxiiUpgradeBody", self.source)
        # An authenticated-but-FREE key (auth.key truthy) must get 403, not
        # the bare-no-credentials 401 -- this is the "clear upgrade
        # payload" distinction the task asks for.
        self.assertIn("const status = auth?.key ? 403 : 401;", self.source)

    @unittest.skipUnless(_node_available(), "node is not on PATH in this environment")
    def test_free_key_cleared_by_no_collection(self):
        script = """
import { TAXII_COLLECTIONS, tierMeetsCollection, buildTaxiiUpgradeBody } from './taxii.js';
const results = TAXII_COLLECTIONS.map(c => tierMeetsCollection('FREE', c));
console.log(JSON.stringify({ anyAllowed: results.some(Boolean), body: buildTaxiiUpgradeBody(null, 'https://x/upgrade') }));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=GATEWAY_SRC, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout.strip())
        self.assertFalse(out["anyAllowed"], "a FREE-tier key must not clear any TAXII collection")
        self.assertIn("upgrade_url", out["body"])
        self.assertEqual(out["body"]["required_tier"], "PRO")


# =============================================================================
# TASK 2 -- SIEM / SOAR / MISP / OpenCTI connectors
# =============================================================================

class TestIntegrationsFilesExist(unittest.TestCase):
    def test_splunk_connector_exists_and_is_valid_python(self):
        path = INTEGRATIONS / "splunk" / "sentinel_apex_splunk.py"
        self.assertTrue(path.exists())
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_elastic_pipeline_conf_exists_and_references_real_endpoint(self):
        path = INTEGRATIONS / "elastic" / "sentinel_pipeline.conf"
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("intel.cyberdudebivash.com/api/siem/splunk", content)
        self.assertIn("sentinel-threat-intel-", content)
        self.assertIn("json_lines", content, "NDJSON output from /api/siem/splunk requires the json_lines codec, not plain json")

    def test_misp_feed_descriptor_is_valid_json_and_points_at_real_endpoint(self):
        path = INTEGRATIONS / "misp" / "sentinel-apex-feed.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("intel.cyberdudebivash.com/api/misp/export", data["Feed"]["url"])
        self.assertEqual(data["Feed"]["source_format"], "misp")

    def test_opencti_connector_config_exists_and_points_at_real_taxii_server(self):
        compose = INTEGRATIONS / "opencti" / "docker-compose.yml"
        env_sample = INTEGRATIONS / "opencti" / ".env.sample"
        self.assertTrue(compose.exists())
        self.assertTrue(env_sample.exists())
        content = compose.read_text(encoding="utf-8")
        self.assertIn("intel.cyberdudebivash.com/taxii/", content)
        # Must not hardcode a real key -- placeholder comes from .env.
        self.assertNotIn("cdb_ent_", content.replace("cdb_ent_your_real_key_here", ""))

    def test_readme_distinguishes_new_connectors_from_legacy_dead_scripts(self):
        readme = (INTEGRATIONS / "README.md").read_text(encoding="utf-8")
        self.assertIn("splunk_hec_connector.py", readme)
        self.assertIn("not wired into any CI workflow", readme)


class TestSplunkConnectorFunctional(unittest.TestCase):
    """
    "Simulates the Splunk modular ingestion script and asserts error-free
    indicator parsing" -- a genuine functional test: mocks urllib at the
    HTTP layer (never touches the network) to feed the real script real-
    shaped NDJSON, then asserts the CSV it produces is correct.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(INTEGRATIONS / "splunk"))

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(INTEGRATIONS / "splunk"))
        sys.modules.pop("sentinel_apex_splunk", None)

    def _fake_ndjson_response(self, events):
        body = "\n".join(json.dumps(e) for e in events).encode("utf-8")
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = body
        cm.__exit__.return_value = False
        return cm

    def test_fetch_ndjson_events_parses_real_shaped_events(self):
        import sentinel_apex_splunk as sas

        events = [
            {"time": 1700000000, "event": {"id": "e1", "title": "Ransomware Alert", "severity": "HIGH", "risk_score": 88, "cve_ids": ["CVE-2026-1111"], "iocs": ["1.2.3.4"], "actor": "CDB-RAN-01", "apex_enterprise_score": 92}},
        ]
        with mock.patch("urllib.request.urlopen", return_value=self._fake_ndjson_response(events)):
            parsed = sas.fetch_ndjson_events("cdb_ent_mockkey", limit=10)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["event"]["id"], "e1")

    def test_malformed_lines_are_skipped_not_fatal(self):
        import sentinel_apex_splunk as sas

        body = b'{"time":1,"event":{"id":"ok"}}\nNOT JSON\n{"time":2,"event":{"id":"ok2"}}\n'
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = body
        cm.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=cm):
            parsed = sas.fetch_ndjson_events("cdb_ent_mockkey")
        self.assertEqual(len(parsed), 2)

    def test_403_raises_clear_enterprise_upgrade_message(self):
        import urllib.error

        import sentinel_apex_splunk as sas

        err = urllib.error.HTTPError(url="x", code=403, msg="Forbidden", hdrs=None, fp=io.BytesIO(b'{"error":"forbidden"}'))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                sas.fetch_ndjson_events("cdb_pro_notenterprise")
        self.assertIn("ENTERPRISE", str(ctx.exception))

    def test_events_to_kv_rows_expands_one_row_per_indicator(self):
        import sentinel_apex_splunk as sas

        events = [
            {"time": 1, "event": {"id": "e1", "title": "T1", "severity": "HIGH", "risk_score": 80, "cve_ids": ["CVE-1"], "iocs": ["1.1.1.1", "evil.example.com"], "apex_enterprise_score": 90}},
            {"time": 2, "event": {"id": "e2", "title": "CVE only", "severity": "LOW", "risk_score": 10, "cve_ids": ["CVE-2"], "iocs": []}},
        ]
        rows = sas.events_to_kv_rows(events)
        # 2 indicator rows for e1 + 1 CVE-fallback row for e2 (no indicators)
        self.assertEqual(len(rows), 3)
        keys = {r["threat_key"] for r in rows}
        self.assertEqual(keys, {"1.1.1.1", "evil.example.com", "CVE-2"})
        for row in rows:
            self.assertIn(set(row.keys()), [set(sas.CSV_FIELDS)])

    def test_write_kv_csv_round_trips_through_csv_dictreader(self):
        import sentinel_apex_splunk as sas

        rows = [{"threat_key": "1.2.3.4", "type": "high", "weight": 90, "description": "x", "source": "sentinel-apex", "first_seen": "2026-01-01T00:00:00Z", "sentinel_id": "e1", "sentinel_actor": "CDB-RAN-01", "sentinel_cve_ids": "CVE-1"}]
        out_path = REPO_ROOT / "tests" / "_tmp_threat_intel_test.csv"
        try:
            sas.write_kv_csv(rows, str(out_path))
            with open(out_path, newline="", encoding="utf-8") as f:
                read_back = list(csv.DictReader(f))
            self.assertEqual(len(read_back), 1)
            self.assertEqual(read_back[0]["threat_key"], "1.2.3.4")
            self.assertEqual(read_back[0]["weight"], "90")
        finally:
            out_path.unlink(missing_ok=True)


# =============================================================================
# TASK 3 -- B2B org/team seats
# =============================================================================

@unittest.skipUnless(_node_available(), "node is not on PATH in this environment")
class TestTeamsJsSuite(unittest.TestCase):
    def test_teams_suite_passes(self):
        _assert_suite_passes(self, _run_node_test("__tests__/teams.test.js"), min_pass=25)


class TestOrgRoutesWiring(unittest.TestCase):
    """Structural check that index.js actually imports teams.js and wires
    every route the task asked for, catching the "module written but never
    routed" class of bug."""

    def setUp(self):
        self.source = INDEX_JS.read_text(encoding="utf-8")

    def test_teams_module_is_imported(self):
        self.assertIn("from './teams.js'", self.source)

    def test_all_required_org_routes_are_wired(self):
        for route_marker in (
            '"/api/org/create"',
            '"/api/org/invite"',
            '"/api/org/usage"',
            '"/api/org/keys/rotate"',
            '"/api/org/invite/accept"',
        ):
            self.assertIn(route_marker, self.source, f"missing route wiring for {route_marker}")

    def test_org_routes_require_authentication(self):
        # POST /api/org/create and every route under the auth-required
        # block must check auth.key before touching org data.
        start = self.source.index('path.startsWith("/api/org/")')
        end = self.source.index('path === "/api/org/invite/accept"')
        block = self.source[start:end]
        self.assertIn("auth.key", block)
        self.assertIn("Authentication required", block)

    def test_admin_only_routes_check_role(self):
        start = self.source.index('path.startsWith("/api/org/")')
        end = self.source.index('path === "/api/org/invite/accept"')
        block = self.source[start:end]
        self.assertGreaterEqual(block.count('callerMember.role !== "ADMIN"'), 3, "invite, rotate, and invoice/generate must all be ADMIN-gated")

    def test_no_stripe_introduced_for_seat_billing(self):
        # This platform's only real payment gateways are Razorpay + Gumroad
        # (confirmed in billing-checkout.js); seat add-ons must route
        # through the same honest mailto-contact precedent already used
        # for MSSP, not a fabricated Stripe integration.
        teams_source = (GATEWAY_SRC / "teams.js").read_text(encoding="utf-8")
        self.assertNotIn("stripe", teams_source.lower())
        self.assertIn("mailto:enterprise@cyberdudebivash.com", teams_source)


class TestGstInvoiceHonesty(unittest.TestCase):
    """No fake PDF-binary generation is claimed anywhere -- confirms the
    invoice engine produces real structured data + printable HTML, matching
    premium-reports.js's own documented "JSON metadata until a PDF render
    service is wired" precedent instead of fabricating one."""

    def test_teams_js_does_not_claim_pdf_binary_generation(self):
        source = (GATEWAY_SRC / "teams.js").read_text(encoding="utf-8")
        self.assertNotIn("pdfkit", source.lower())
        self.assertNotIn("jspdf", source.lower())
        self.assertIn("renderInvoiceHtml", source)
        self.assertIn("print-to-PDF", source, "must document the real capability (browser print-to-PDF) instead of silently claiming server-side PDF generation")

    def test_seller_gstin_matches_the_one_already_used_sitewide(self):
        source = (GATEWAY_SRC / "teams.js").read_text(encoding="utf-8")
        self.assertIn("21ARKPN8270G1ZP", source)
        # Cross-check against a real page that already publishes this GSTIN.
        compliance_page = (REPO_ROOT / "security-compliance.html")
        if compliance_page.exists():
            self.assertIn("21ARKPN8270G1ZP", compliance_page.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
