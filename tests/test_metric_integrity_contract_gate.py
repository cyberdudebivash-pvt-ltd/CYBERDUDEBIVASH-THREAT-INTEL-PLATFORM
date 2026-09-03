"""
tests/test_metric_integrity_contract_gate.py

Covers scripts/metric_integrity_contract_gate.py -- the new bake-in gate
that validates two contracts a concurrent session landed on main
(p0-revenue-os/config/metric_integrity_contract.json's forbidden_hardcodes
list, p0-revenue-os/config/public_nav.json's hide_until_auth list) against
the live CUSTOMER_UI page set. Exercises the two scan functions directly
against constructed fixtures (temp files), not this repo's real 137 pages,
so these tests stay fast and independent of this checkout's current content.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import metric_integrity_contract_gate as gate  # noqa: E402


class TestForbiddenHardcodeScan(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._orig_root = gate.REPO_ROOT
        gate.REPO_ROOT = Path(self.tmpdir.name)
        self.addCleanup(setattr, gate, "REPO_ROOT", self._orig_root)

    def _write(self, name: str, content: str) -> None:
        (Path(self.tmpdir.name) / name).write_text(content, encoding="utf-8")

    def test_exact_forbidden_string_is_found(self):
        self._write("a.html", '<div class="stat-val">77+</div>')
        findings = gate._scan_forbidden_hardcodes(["a.html"], ["77+", "115+"])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["page"], "a.html")
        self.assertIn("77+", findings[0]["hardcoded_strings"])

    def test_digit_embedded_in_longer_number_is_not_a_false_positive(self):
        # The real false positive this gate's boundary check exists to
        # rule out: a CSS hex color (#050810) or any longer number
        # containing "508" as a bare substring must not trip a "508" check.
        self._write("a.html", 'color:#050810; id="45089"')
        findings = gate._scan_forbidden_hardcodes(["a.html"], ["508"])
        self.assertEqual(findings, [])

    def test_standalone_digit_literal_is_still_found(self):
        self._write("a.html", "<p>508 advisories published this quarter</p>")
        findings = gate._scan_forbidden_hardcodes(["a.html"], ["508"])
        self.assertEqual(len(findings), 1)

    def test_allowlisted_page_string_pair_is_suppressed(self):
        self._write("a.html", '<div class="stat-val">77+</div>')
        gate.ALLOWLISTED_FINDINGS["a.html"] = {"77+"}
        self.addCleanup(gate.ALLOWLISTED_FINDINGS.pop, "a.html", None)
        findings = gate._scan_forbidden_hardcodes(["a.html"], ["77+"])
        self.assertEqual(findings, [])

    def test_clean_page_produces_no_finding(self):
        self._write("a.html", '<div class="stat-val" data-apex-metric="advisory_count_live">—</div>')
        findings = gate._scan_forbidden_hardcodes(["a.html"], ["77+", "115+", "508"])
        self.assertEqual(findings, [])


class TestNavLeakageScan(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._orig_root = gate.REPO_ROOT
        gate.REPO_ROOT = Path(self.tmpdir.name)
        self.addCleanup(setattr, gate, "REPO_ROOT", self._orig_root)

    def _write(self, name: str, content: str) -> None:
        (Path(self.tmpdir.name) / name).write_text(content, encoding="utf-8")

    def test_unguarded_restricted_label_is_found(self):
        self._write("a.html", '<nav><a href="/mssp-console.html">MSSP Console</a></nav>')
        findings = gate._scan_nav_leakage(["a.html"], ["MSSP Console"])
        self.assertEqual(len(findings), 1)
        self.assertIn("MSSP Console", findings[0]["unguarded_nav_labels"])

    def test_page_loading_hiding_runtime_is_exempt(self):
        self._write("a.html", '<a href="/x">MSSP Console</a><script src="/js/metric-normalize.js"></script>')
        findings = gate._scan_nav_leakage(["a.html"], ["MSSP Console"])
        self.assertEqual(findings, [])

    def test_filename_outside_script_src_does_not_exempt(self):
        # CodeRabbit review finding (verified, not taken on faith): the
        # runtime-detection check used to be a bare substring test over the
        # whole page, so a filename mentioned in a comment -- with no actual
        # <script src> loading it -- wrongly exempted a page that ships a
        # genuinely unguarded restricted nav link.
        self._write("a.html", '<a href="/x">MSSP Console</a><!-- metric-normalize.js -->')
        findings = gate._scan_nav_leakage(["a.html"], ["MSSP Console"])
        self.assertEqual(len(findings), 1)
        self.assertIn("MSSP Console", findings[0]["unguarded_nav_labels"])

    def test_label_not_present_produces_no_finding(self):
        self._write("a.html", '<nav><a href="/pricing.html">Pricing</a></nav>')
        findings = gate._scan_nav_leakage(["a.html"], ["MSSP Console"])
        self.assertEqual(findings, [])


class TestRealContractsLoadable(unittest.TestCase):
    """Sanity-checks the two real p0-revenue-os contract files this gate
    depends on still parse and still have the exact shape the gate's main()
    expects, so a schema change in either contract surfaces here instead of
    the gate silently scanning nothing."""

    def test_metric_integrity_contract_has_forbidden_hardcodes_list(self):
        if not gate.METRIC_CONTRACT_PATH.exists():
            self.skipTest("p0-revenue-os/config/metric_integrity_contract.json not present in this checkout")
        contract = gate._load_json(gate.METRIC_CONTRACT_PATH)
        forbidden = contract.get("fields", {}).get("forbidden_hardcodes")
        self.assertIsInstance(forbidden, list)
        self.assertGreater(len(forbidden), 0)

    def test_public_nav_contract_has_hide_until_auth_list(self):
        if not gate.NAV_CONTRACT_PATH.exists():
            self.skipTest("p0-revenue-os/config/public_nav.json not present in this checkout")
        contract = gate._load_json(gate.NAV_CONTRACT_PATH)
        hide_labels = contract.get("hide_until_auth")
        self.assertIsInstance(hide_labels, list)
        self.assertGreater(len(hide_labels), 0)


if __name__ == "__main__":
    unittest.main()
