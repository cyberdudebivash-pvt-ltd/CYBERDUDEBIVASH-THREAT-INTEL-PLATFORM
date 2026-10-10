"""P0 R37 negative controls for legacy GitHub Pages intelligence paths."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p0_r37_static_feed_denial import neutralise_legacy_static_feeds
from p0_r37_live_legacy_canary import assert_unavailable, assert_matches_fresh_authority
import p0_r37_live_legacy_canary as live_canary

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

    def test_live_canary_rejects_stale_records_and_false_empty(self):
        with self.assertRaises(AssertionError):
            assert_unavailable(200, b'[{"id":"expired"}]', "/feed.json")
        with self.assertRaises(AssertionError):
            assert_unavailable(200, b'{"count":1,"items":[{"id":"expired"}]}', "/latest.json")
        with self.assertRaises(AssertionError):
            assert_unavailable(200, b'{"count":0,"items":[]}', "/latest.json")
        assert_unavailable(200, b'{"error":"legacy_static_feed_disabled","items":[],"data":[],"count":0,"live_data_available":false}', "/feed.json")
        assert_unavailable(503, b'{"error":"live_intelligence_unavailable","items":[],"data":[],"count":0,"live_data_available":false}', "/feed.json")
        assert_unavailable(404, b'Not Found', "/feed.json")

    def test_fresh_authoritative_worker_alias_is_allowed_not_stale_snapshot(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc).timestamp()
        stamp = "2026-10-10T10:00:00Z"
        api = json.dumps({"generated_at": stamp, "items": [{"id": "new-1"}]}).encode()
        same = json.dumps({"generated_at": stamp, "items": [{"id": "new-1"}]}).encode()
        assert_matches_fresh_authority(200, same, 200, api, "/feed.json", now)
        old = json.dumps({"generated_at": "2026-10-09T10:00:00Z", "items": [{"id": "old-1"}]}).encode()
        with self.assertRaises(AssertionError):
            assert_matches_fresh_authority(200, old, 200, api, "/feed.json", now)
        with self.assertRaises(AssertionError):
            assert_matches_fresh_authority(200, same, 503, b'{"items":[]}', "/feed.json", now)
        stale_api = json.dumps({"generated_at": "2026-10-09T10:00:00Z", "items": [{"id": "new-1"}]}).encode()
        with self.assertRaises(AssertionError):
            assert_matches_fresh_authority(200, stale_api, 200, stale_api, "/feed.json", now)

    def test_fast_pages_publish_runs_tests_and_artifact_gate(self):
        workflow = (ROOT / ".github/workflows/pages-fast-publish.yml").read_text()
        self.assertIn("test_p0_r37_static_feed_denial.py", workflow)
        self.assertIn("legacy_static_feed_disabled", workflow)
        canary = (ROOT / "scripts/p0_r37_live_legacy_canary.py").read_text()
        self.assertIn('for suffix in ("", "?" +', canary)
        self.assertIn("'scripts/p0_r37_static_feed_denial.py'", workflow)

    def test_response_diagnostics_capture_only_public_routing_metadata(self):
        url = "https://example.test/feed.json"
        raw = b'{"generated_at":"2026-10-09T05:38:01Z","items":[{"id":"private-body","title":"private-title"}]}'
        response = SimpleNamespace(status=200, read=lambda size: raw, headers={
            "CF-Cache-Status": "HIT", "Age": "104400", "X-Sentinel-Version": "v201",
            "Set-Cookie": "private-cookie", "Authorization": "private-token",
        })
        response_context = unittest.mock.MagicMock()
        response_context.__enter__.return_value = response
        with patch.object(live_canary.urllib.request, "urlopen", return_value=response_context) as request:
            self.assertEqual(live_canary._request(url), (200, raw))
        self.assertEqual(request.call_args.args[0].get_header("User-agent"), "SENTINEL-APEX-P0-LEGACY-CANARY/1.0")
        summary = live_canary._response_summary(url, 200, raw)
        self.assertEqual(summary["headers"]["CF-Cache-Status"], "HIT")
        self.assertEqual(summary["headers"]["Age"], "104400")
        self.assertEqual(summary["item_count"], 1)
        text = json.dumps(summary)
        for sensitive in ("private-body", "private-title", "private-cookie", "private-token"):
            self.assertNotIn(sensitive, text)
        live_canary._RESPONSE_METADATA.pop(url, None)

    def test_alias_mismatch_remains_fatal_with_routing_diagnostics(self):
        old = b'[{"id":"old-body-must-not-be-logged"}]'
        unavailable = b'{"error":"live_intelligence_unavailable","items":[],"live_data_available":false}'
        with patch.object(live_canary, "_request", side_effect=[(200, old), (503, unavailable)]) as request:
            with self.assertRaisesRegex(AssertionError, "live alias not backed by healthy API") as caught:
                live_canary.run("https://example.test")
        self.assertEqual(request.call_count, 2)
        diagnostics = json.loads(str(caught.exception).split("; responses=", 1)[1])
        self.assertEqual([row["status"] for row in diagnostics], [200, 503])
        self.assertEqual(diagnostics[0]["shape"], "list")
        self.assertEqual(diagnostics[1]["error"], "live_intelligence_unavailable")
        self.assertNotIn("old-body-must-not-be-logged", str(caught.exception))

if __name__ == "__main__":
    unittest.main()
