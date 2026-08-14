"""
tests/test_multi_source_collector.py

CI-workflow audit P0 fix: scripts/multi_source_collector.py was the only
api/feed.json writer that appended newly-collected items without
re-applying the platform's 500-item cap (output_validation_gate.py's
API_FEED_CAP and run_pipeline.py's stage_sync_root_feed_json() both
already enforce it). Confirmed live: api/feed.json grew from 244 items
(05:37 UTC) to 516 items (17:45 UTC) on 2026-08-14, hard-failing
STAGE 3.9 (Output Validation Gate) on every sentinel-blogger.yml and
deploy-worker.yml run since, and skipping ~40 downstream P20-P38
certification/deployment stages gated behind it (confirmed via run
31821295989's job step list -- STAGE 3.90 through STAGE 4.04 all
"skipped" because STAGE 3.9 hard-failed above them).

These tests exercise scripts/multi_source_collector.py's run() end-to-end
against a temp FEED_PATH, with all 8 network collectors monkeypatched so
no real HTTP calls are made, proving:
  1. new items pushing existing+deduped over the cap get trimmed to the
     newest 500 by published_at DESC.
  2. an already-oversized existing feed self-heals to 500 even on a run
     that finds zero new items (covers the current live state, where the
     fix must recover from an already-broken file, not just prevent new
     breakage).
  3. a feed already within the cap, with zero new items, is left
     untouched (no unnecessary rewrite).
"""
import json
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import multi_source_collector as msc  # noqa: E402

_COLLECTOR_NAMES = (
    "collect_github_advisories",
    "collect_cisa_alerts",
    "collect_urlhaus",
    "collect_malwarebazaar",
    "collect_bleepingcomputer",
    "collect_securityaffairs",
    "collect_cybersecuritynews",
    "collect_otx",
)


def _ts(day: int) -> str:
    # day 1 = oldest; higher day = newer. Zero-padded for lexicographic sort.
    return f"2026-01-{day:02d}T00:00:00Z"


def _item(n: int, ts: str) -> dict:
    return {
        "id": f"intel--test{n:020d}",
        "stix_id": f"intel--test{n:020d}",
        "title": f"Test Item {n}",
        "published_at": ts,
        "severity": "MEDIUM",
    }


class TestFeedCapEnforcement(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="msc_test_"))
        self.feed_path = self.tmp_dir / "feed.json"
        self.telemetry_path = self.tmp_dir / "telemetry.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run_with_collectors(self, new_items=None):
        """Run msc.run() against self.feed_path with all 8 network collectors
        mocked (collect_github_advisories optionally returns synthetic new
        items; the rest always return [])."""
        new_items = new_items or []
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(msc, "collect_github_advisories", return_value=new_items)
            )
            for name in _COLLECTOR_NAMES[1:]:
                stack.enter_context(patch.object(msc, name, return_value=[]))
            stack.enter_context(patch.object(msc, "FEED_PATH", self.feed_path))
            stack.enter_context(patch.object(msc, "TELEMETRY", self.telemetry_path))
            stack.enter_context(patch.object(msc, "DRY_RUN", False))
            msc.run()

    def test_new_items_pushing_over_cap_are_trimmed_to_newest_500(self):
        existing = [_item(i, _ts((i % 28) + 1)) for i in range(498)]
        self.feed_path.write_text(json.dumps(existing), encoding="utf-8")

        # 10 brand-new items, distinct titles so dedup keeps all of them,
        # timestamped newer than everything already in `existing`.
        new_items = [
            {
                "id": f"intel--brandnew{i:016d}",
                "stix_id": f"intel--brandnew{i:016d}",
                "title": f"Brand New Advisory {i}",
                "published_at": "2026-02-01T00:00:00Z",
                "severity": "HIGH",
            }
            for i in range(10)
        ]
        self._run_with_collectors(new_items=new_items)

        written = json.loads(self.feed_path.read_text(encoding="utf-8"))
        self.assertEqual(
            len(written), msc.API_FEED_CAP,
            "feed must be capped at API_FEED_CAP after adding new items pushes it over",
        )
        written_ids = {it["id"] for it in written}
        for it in new_items:
            self.assertIn(
                it["id"], written_ids,
                "newest items must survive the cap trim (sorted DESC before slicing)",
            )

    def test_already_oversized_feed_self_heals_with_zero_new_items(self):
        existing = [_item(i, _ts((i % 28) + 1)) for i in range(510)]
        self.feed_path.write_text(json.dumps(existing), encoding="utf-8")

        self._run_with_collectors(new_items=None)  # all 8 collectors return []

        written = json.loads(self.feed_path.read_text(encoding="utf-8"))
        self.assertEqual(
            len(written), msc.API_FEED_CAP,
            "an already-oversized feed must self-heal to the cap even when a run "
            "finds zero new items (covers recovering the currently-live broken state)",
        )

    def test_feed_within_cap_and_no_new_items_is_left_untouched(self):
        existing = [_item(i, _ts((i % 28) + 1)) for i in range(400)]
        self.feed_path.write_text(json.dumps(existing), encoding="utf-8")
        original_bytes = self.feed_path.read_bytes()

        self._run_with_collectors(new_items=None)

        self.assertEqual(
            self.feed_path.read_bytes(), original_bytes,
            "file must not be rewritten when already within the cap and no new items exist",
        )


if __name__ == "__main__":
    unittest.main()
