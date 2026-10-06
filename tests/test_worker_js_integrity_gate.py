"""
tests/test_worker_js_integrity_gate.py

Regression coverage for scripts/worker_js_integrity_gate.py's check_file(),
added after a real production incident: an exact-equality check against
VALID_EOF's bare closing tokens ("};", "}", ...) flagged
workers/intel-gateway/src/intel-static-proxy.js's legitimate last line --
`export { handleIntelStaticProxy, INTEL_STATIC_PROXY };` -- as TRUNCATED_EOF
and blocked deploy-worker.yml (run 33669781683 and 33660901724 on main,
2026-09-02), even though the file is not truncated. The fix changed the
check from exact-equality to a suffix match. These tests pin that fix and
confirm it does not also let genuine truncation slip through.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import worker_js_integrity_gate as gate  # noqa: E402


class TestCheckFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def _write(self, content: str) -> Path:
        p = Path(self.tmpdir.name) / "sample.js"
        # Pad past MIN_BYTES so only the EOF check under test can fail.
        padding = "// padding line to clear the 1KB minimum-size gate\n" * 25
        p.write_text(padding + content, encoding="ascii")
        return p

    def test_bare_closing_brace_is_valid_eof(self):
        p = self._write("function f() {\n  return 1;\n}\n")
        self.assertEqual(gate.check_file(p), [])

    def test_real_named_export_statement_is_valid_eof(self):
        # The exact regression this test guards: a full statement whose
        # last line ends with, but is not equal to, a VALID_EOF token.
        p = self._write("function handleX() {}\n\nexport { handleX, SOME_CONST };\n")
        self.assertEqual(gate.check_file(p), [])

    def test_module_exports_object_literal_is_valid_eof(self):
        p = self._write("module.exports = { handleX, SOME_CONST };\n")
        self.assertEqual(gate.check_file(p), [])

    def test_genuinely_truncated_file_still_fails(self):
        # Cut off mid-expression -- the real failure mode this gate exists
        # to catch. Must still be flagged after the suffix-match fix.
        p = self._write("export function handleX(req) {\n  const x = compute(req")
        errors = gate.check_file(p)
        self.assertTrue(any("TRUNCATED_EOF" in e for e in errors))

    def test_null_bytes_still_fail(self):
        p = self._write("const x = 1;\n}\n")
        p.write_bytes(p.read_bytes() + b"\x00")
        errors = gate.check_file(p)
        self.assertTrue(any("NULL_BYTES" in e for e in errors))

    def test_non_ascii_still_fails(self):
        padding = "// padding line to clear the 1KB minimum-size gate\n" * 25
        p = Path(self.tmpdir.name) / "sample.js"
        p.write_bytes((padding + "const label = 'café';\n}\n").encode("utf-8"))
        errors = gate.check_file(p)
        self.assertTrue(any("NON_ASCII" in e for e in errors))

    def test_too_small_still_fails(self):
        p = Path(self.tmpdir.name) / "tiny.js"
        p.write_text("}\n", encoding="ascii")
        errors = gate.check_file(p)
        self.assertTrue(any("TOO_SMALL" in e for e in errors))


class TestRealWorkerSourcePasses(unittest.TestCase):
    """Sanity check against this checkout's actual Worker source -- pins
    the fix against the real file that triggered the incident, not just a
    synthetic fixture."""

    def test_intel_static_proxy_passes(self):
        f = REPO_ROOT / "workers" / "intel-gateway" / "src" / "intel-static-proxy.js"
        if not f.exists():
            self.skipTest("workers/intel-gateway/src/intel-static-proxy.js not present in this checkout")
        self.assertEqual(gate.check_file(f), [])

    def test_all_worker_src_files_pass(self):
        if not gate.WORKER_SRC.exists():
            self.skipTest("workers/intel-gateway/src not present in this checkout")
        failures = {}
        for f in sorted(gate.WORKER_SRC.glob("*.js")):
            errors = gate.check_file(f)
            if errors:
                failures[f.name] = errors
        self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
