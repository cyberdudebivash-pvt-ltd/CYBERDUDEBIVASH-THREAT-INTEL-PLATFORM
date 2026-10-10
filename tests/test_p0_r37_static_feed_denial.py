"""P0 R37 negative controls for legacy GitHub Pages intelligence paths."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p0_r37_static_feed_denial import neutralise_legacy_static_feeds

class StaticFeedDenialTests(unittest.TestCase):
    def test_stale_items_never_survive_pages_build(self):
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td)
            (dist / "feed.json").write_text(json.dumps([{"id": "expired", "title": "Old vulnerability"}]))
            (dist / "latest.json").write_text(json.dumps({"count": 99, "data": [{"id": "expired"}]}))
            neutralise_legacy_static_feeds(dist)
            for name in ("feed.json", "latest.json"):
                result = json.loads((dist / name).read_text())
                self.assertEqual(result["error"], "legacy_static_feed_disabled")
                self.assertEqual(result["items"], [])
                self.assertEqual(result["data"], [])
                self.assertEqual(result["count"], 0)
                self.assertIs(result["live_data_available"], False)
                self.assertNotIn("Old vulnerability", (dist / name).read_text())

    def test_missing_legacy_files_are_denied_too(self):
        with tempfile.TemporaryDirectory() as td:
            neutralise_legacy_static_feeds(Path(td))
            self.assertEqual(sorted(p.name for p in Path(td).iterdir()), ["feed.json", "latest.json"])
            self.assertEqual(json.loads((Path(td) / "feed.json").read_text())["items"], [])

    def test_source_intelligence_is_never_deleted(self):
        with tempfile.TemporaryDirectory() as td:
            dist = Path(td) / "dist"
            dist.mkdir()
            source = Path(td) / "archive.json"
            source.write_text('[{"id":"historical-archive"}]')
            neutralise_legacy_static_feeds(dist)
            self.assertEqual(source.read_text(), '[{"id":"historical-archive"}]')

    def test_pages_builder_always_neutralises_aliases_before_manifest(self):
        script = (ROOT / "scripts/build_dist_artifact.py").read_text()
        self.assertLess(script.index("neutralise_legacy_static_feeds(DIST_DIR)"), script.index("# ── 5. Validate report_url"))
        self.assertIn('"feed.json", "feed_manifest.json", "latest.json"', script)

    def test_fast_pages_publish_runs_tests_and_artifact_gate(self):
        workflow = (ROOT / ".github/workflows/pages-fast-publish.yml").read_text()
        self.assertIn("test_p0_r37_static_feed_denial.py", workflow)
        self.assertIn("legacy_static_feed_disabled", workflow)
        self.assertIn("'scripts/p0_r37_static_feed_denial.py'", workflow)

if __name__ == "__main__":
    unittest.main()
