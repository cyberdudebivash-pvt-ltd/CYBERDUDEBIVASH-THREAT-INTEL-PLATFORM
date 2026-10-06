"""
tests/test_report_generator_not_authoritative.py

RX-PUB-A0 Section 16 regression test: scripts/report_generator.py must no
longer be an authoritative report writer. Its generate_reports_from_manifest()
previously fell through to generate_report() -- a separate, independent HTML
render engine (_build_html(), its own "report_generator.py vN.x" engine
marker) -- whenever an existing report was missing, malformed, or below the
God Mode size/age threshold. That made it a second writer for the exact same
reports/*.html keyspace scripts/generate_intel_reports.py owns, which is the
Single-Source-of-Truth violation documented in
docs/REPORT_WRITER_OWNERSHIP_MATRIX.md ("Writer B").

This proves the fallthrough no longer writes anything: a below-threshold
report is left exactly as found (or absent, if it never existed) and is
counted as "not_authoritative" instead of being regenerated with the second
engine.
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import report_generator  # noqa: E402


class TestReportGeneratorNeverWrites(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="rg_test_"))
        self.reports_base = self.tmp / "reports"
        self.manifest_path = self.tmp / "feed_manifest.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_manifest(self, entries):
        self.manifest_path.write_text(json.dumps(entries), encoding="utf-8")

    def test_missing_report_is_not_generated_by_the_secondary_engine(self):
        """No existing file at all -- previously this unconditionally fell
        through to generate_report() and wrote one with the secondary
        engine. It must now be left absent and counted, not written.

        Deliberately omits internal_report_url/report_url: when either is
        set, generate_reports_from_manifest() resolves `expected` as a
        CWD-relative path (report_url.lstrip("/")), NOT relative to the
        reports_base argument -- so this test uses the processed_at-driven
        `reports_base / yyyy / mm / id.html` path instead, to actually
        exercise the isolated tmp directory rather than colliding with (or
        silently missing) real paths under the repo's own reports/ tree.
        """
        entry = {
            "id": "intel--doesnotexistyet00",
            "title": "Test Advisory",
            "processed_at": "2026-08-01T00:00:00Z",
        }
        self._write_manifest([entry])

        results = report_generator.generate_reports_from_manifest(
            manifest_path=str(self.manifest_path),
            reports_base=str(self.reports_base),
        )

        expected_path = self.reports_base / "2026" / "08" / "intel--doesnotexistyet00.html"
        self.assertFalse(
            expected_path.exists(),
            "report_generator.py must never write reports/*.html -- only "
            "scripts/generate_intel_reports.py may. Found a file written by "
            "the (should-be-disabled) secondary engine."
        )
        self.assertEqual(results["success"], 0, "success count must stay 0 -- this function no longer writes")
        self.assertGreaterEqual(results["not_authoritative"], 1)

    def test_small_existing_report_is_left_untouched_not_upgraded(self):
        """A report that exists but is under the God Mode size threshold
        previously got silently REPLACED by the secondary engine's own
        (different) rendering. It must now be left byte-for-byte as the
        canonical generator wrote it."""
        entry = {
            "id": "intel--smallreport000000",
            "title": "Test Advisory",
            "processed_at": "2026-08-01T00:00:00Z",
        }
        self._write_manifest([entry])

        report_path = self.reports_base / "2026" / "08" / "intel--smallreport000000.html"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        original_content = "<!DOCTYPE html><html><body>canonical-generator output, short</body></html>"
        report_path.write_text(original_content, encoding="utf-8")

        results = report_generator.generate_reports_from_manifest(
            manifest_path=str(self.manifest_path),
            reports_base=str(self.reports_base),
        )

        self.assertEqual(
            report_path.read_text(encoding="utf-8"), original_content,
            "the canonical generator's output must survive byte-for-byte -- "
            "report_generator.py must not silently replace it with its own "
            "separate engine's rendering just because it is under 60KB."
        )
        self.assertEqual(results["success"], 0)
        self.assertGreaterEqual(results["not_authoritative"], 1)

    def test_god_mode_protected_id_is_still_skipped_not_regressed(self):
        """Pre-existing behavior (unrelated to this fix) must survive: an
        operator-curated, protected report is still left alone."""
        protected_id = next(iter(report_generator.GODMODE_PROTECTED_IDS))
        entry = {
            "id": protected_id,
            "title": "Operator Curated",
            "processed_at": "2026-08-01T00:00:00Z",
        }
        self._write_manifest([entry])

        report_path = self.reports_base / "2026" / "08" / f"{protected_id}.html"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        original_content = "<!DOCTYPE html><html><body>operator curated, tiny on purpose</body></html>"
        report_path.write_text(original_content, encoding="utf-8")

        results = report_generator.generate_reports_from_manifest(
            manifest_path=str(self.manifest_path),
            reports_base=str(self.reports_base),
        )

        self.assertEqual(report_path.read_text(encoding="utf-8"), original_content)
        self.assertGreaterEqual(results["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
