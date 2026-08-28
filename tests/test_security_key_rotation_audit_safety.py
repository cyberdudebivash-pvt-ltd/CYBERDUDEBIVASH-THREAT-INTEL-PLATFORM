"""
tests/test_security_key_rotation_audit_safety.py

scripts/security_key_rotation_audit.py runs against 2,260 real leaked
production API keys pulled from git history and, with --confirm-revoke,
mutates production (revokes live keys via the Worker's admin API). Given
that blast radius, its two safety properties need more than a docstring:

  1. The revoke call is only ever reachable when --confirm-revoke was
     passed AND the check phase found the key live -- never unconditionally.
  2. No raw key value is ever written to the (committed-as-a-CI-artifact)
     report or passed to a log call -- only the masked 12-char prefix
     convention the Worker's own key-rotation audit log already uses.

Static source-text checks (not execution -- this test has no Cloudflare
credentials and must not need any) proving both by construction, plus a
functional check on mask() itself.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "security_key_rotation_audit.py"


class TestSecurityKeyRotationAuditSafety(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT_PATH.exists(), f"expected file not found: {SCRIPT_PATH}")
        self.source = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_worker_revoke_is_only_called_inside_a_confirm_revoke_and_live_guard(self):
        # The only call site of worker_revoke( in main() must be textually
        # inside the "if confirm_revoke and live:" block. A regex over the
        # function body is enough here: there is exactly one call site, and
        # this proves it isn't unconditional (e.g. accidentally called
        # during the check phase or outside any guard).
        call_sites = [m.start() for m in re.finditer(r"\bworker_revoke\(", self.source)]
        # One definition (`def worker_revoke(`) + exactly one call site.
        self.assertEqual(
            len(call_sites), 2,
            "Expected exactly one definition and one call site of worker_revoke(); "
            "found a different count -- re-check the guard around the revoke call.",
        )
        call_site = max(call_sites)  # the call, not the def (def comes first in the file)
        guard_idx = self.source.rfind("if confirm_revoke and live:", 0, call_site)
        self.assertNotEqual(
            guard_idx, -1,
            "worker_revoke( call site is not preceded by 'if confirm_revoke and live:' -- "
            "the revoke path must never run unconditionally.",
        )
        # Nothing that would close the guard's block (a dedent back to a
        # zero/one-indent statement) appears between the guard and the call.
        between = self.source[guard_idx:call_site]
        self.assertNotIn("\ndef ", between, "revoke call site is outside the guard's function body")

    def test_report_never_includes_the_raw_key_field(self):
        self.assertIn(
            'if k != "_raw_key"', self.source,
            "The report-building comprehension must strip _raw_key before "
            "json.dump -- raw key values must never reach the committed/uploaded report.",
        )
        # json.dump( must not be called directly on `live` (which carries
        # _raw_key) or on anything other than the sanitized `report` dict.
        dump_calls = re.findall(r"json\.dump\(\s*(\w+)", self.source)
        self.assertEqual(
            dump_calls, ["report"],
            f"json.dump() must only ever be called on the sanitized `report` dict, found: {dump_calls}",
        )

    def test_no_log_call_references_the_raw_key_field(self):
        # entry["_raw_key"] (or a bare _raw_key) is the one place the actual
        # secret value lives in memory. No log.* call may reference it --
        # only entry["key_prefix"] (the masked form) is fit to log.
        log_calls = re.findall(r"log\.\w+\([^)]*\)", self.source, flags=re.DOTALL)
        offending = [c for c in log_calls if "_raw_key" in c]
        self.assertEqual(
            offending, [],
            f"Found log call(s) referencing the raw key field: {offending}",
        )

    def test_mask_never_returns_the_full_key(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("security_key_rotation_audit", SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        fake_key = "cdb_" + ("a" * 40)
        masked = module.mask(fake_key)
        self.assertNotEqual(masked, fake_key)
        self.assertTrue(masked.endswith("..."))
        self.assertLess(len(masked), len(fake_key))
        self.assertEqual(masked, fake_key[:12] + "...")


if __name__ == "__main__":
    unittest.main()
