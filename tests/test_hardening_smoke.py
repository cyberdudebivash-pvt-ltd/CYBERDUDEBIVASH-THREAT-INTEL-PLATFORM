"""Regression coverage for false-green hardening and synthetic data pollution."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import hardening_smoke as smoke


class EvidenceTests(unittest.TestCase):
    def execute(self, runners, enabled=None):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence"
            with contextlib.redirect_stdout(io.StringIO()):
                code = smoke.run(out, enabled or {k: True for k in runners}, runners)
            return code, json.loads((out / "manifest.json").read_text())

    def test_engine_exception_fails_but_retains_manifest(self):
        def broken():
            raise RuntimeError("private exception content")
        code, manifest = self.execute({"quality": broken})
        self.assertEqual(code, 1)
        self.assertEqual(manifest["phases"]["quality"]["status"], "failed")
        self.assertNotIn("private exception content", json.dumps(manifest))

    def test_empty_or_nonfinite_evidence_fails(self):
        for evidence in ({}, [], None, {"score": float("nan")}):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.execute({"quality": lambda: evidence})[0], 1)

    def test_disabled_phase_is_not_called_or_reported_as_passed(self):
        code, manifest = self.execute({"quality": lambda: {"ok": True},
                                       "tenant": lambda: self.fail("disabled phase ran")},
                                      {"quality": True, "tenant": False})
        self.assertEqual(code, 0)
        self.assertEqual(manifest["phases"]["tenant"], {"status": "skipped"})
        self.assertFalse(manifest["production_certified"])

    def test_all_disabled_is_not_a_pass(self):
        self.assertEqual(self.execute({"quality": lambda: {}}, {"quality": False})[0], 1)

    def test_generated_data_is_isolated_and_cwd_restored(self):
        cwd = Path.cwd()
        seen = []
        def writer():
            seen.append(Path.cwd())
            self.assertNotEqual(Path.cwd(), cwd)
            Path("data/tenant").mkdir(parents=True)
            Path("data/tenant/synthetic.json").write_text("{}")
            return {"ok": True}
        self.assertEqual(self.execute({"tenant": writer})[0], 0)
        self.assertEqual(Path.cwd(), cwd)
        self.assertFalse(seen[0].exists())

    def test_tracked_reports_cannot_satisfy_missing_output(self):
        self.assertEqual(self.execute({"tenant": lambda: smoke.read_object(
            Path("data/tenant/tenant_isolation_report.json"))})[0], 1)

    def test_existing_evidence_and_repository_destinations_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                smoke.run(tmp, {}, {})
        with self.assertRaises(ValueError):
            smoke.run(ROOT / "data" / "ci-evidence", {}, {})

    def test_real_engines_execute(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(smoke.run(Path(tmp) / "evidence",
                                      {k: True for k in ("quality", "tenant", "monetization")}), 0)

    def test_workflow_cannot_swallow_errors_or_push_fixture_data(self):
        import yaml
        flow = yaml.safe_load((ROOT / ".github/workflows/production-hardening-final.yml").read_text())
        self.assertEqual(flow["permissions"], {"contents": "read"})
        steps = flow["jobs"]["production-hardening"]["steps"]
        self.assertFalse(any(s.get("continue-on-error") for s in steps))
        self.assertFalse(any("git push" in s.get("run", "") for s in steps))
        upload = next(s for s in steps if "actions/upload-artifact@" in s.get("uses", ""))
        self.assertEqual(upload["if"], "always()")
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        self.assertEqual(upload["with"]["retention-days"], 3)


if __name__ == "__main__":
    unittest.main()
