"""F26 (2026-10-02): premium feed metadata states its real contents.

feed.standard.json, one of the Enterprise/MSSP premium feeds, described
itself as "all 176 quality-gated items" whatever the baseline held (985
items on 2026-10-02). The count is _meta.item_count; no description may state
a different one.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import generate_tiered_feeds as gtf  # noqa: E402
import scripts.r2_upload as r2_upload  # noqa: E402  (the module the generator imports)


def _baseline():
    tiers = [("GOLD", 6.0)] * 5 + [("SILVER", 3.5)] * 7 + [("STANDARD", 1.0)] * 30
    return [
        {
            "id": f"ITEM-{i}",
            "title": f"Advisory {i} affecting example software",
            "risk_score": 7.5,
            "severity": "HIGH",
            "premium_tier": tier,
            "_intelligence_richness": richness,
            "published_at": "2026-10-02T00:00:00Z",
        }
        for i, (tier, richness) in enumerate(tiers)
    ]


def test_no_feed_description_states_a_count_other_than_its_items(tmp_path, monkeypatch):
    baseline = tmp_path / "feed.baseline.json"
    baseline.write_text(json.dumps(_baseline()), encoding="utf-8")
    (tmp_path / "api").mkdir()
    monkeypatch.setattr(gtf, "BASELINE_PATH", baseline)
    monkeypatch.setattr(gtf, "API_DIR", tmp_path / "api")
    monkeypatch.setattr(gtf, "PREMIUM_STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(gtf, "REPO", tmp_path)
    monkeypatch.setattr(gtf, "DRY_RUN", False)
    uploads = []
    monkeypatch.setattr(r2_upload, "get_credentials", lambda: ("account", "key", "secret"))
    monkeypatch.setattr(r2_upload, "s3_cp", lambda src, bucket, key, endpoint, **kw: uploads.append(key) or True)

    assert gtf.main() == 0
    assert sorted(uploads) == [f"premium/feeds/feed.{t}.json" for t in ("executive", "gold", "silver", "standard")]

    feeds = sorted((tmp_path / "staging").glob("feed.*.json")) + [tmp_path / "api" / "feed.trial.json"]
    assert len(feeds) == 5
    for path in feeds:
        meta = json.loads(path.read_text(encoding="utf-8"))["_meta"]
        stated = [int(n) for n in re.findall(r"\b\d+\b", meta["description"])]
        assert all(n == meta["item_count"] for n in stated), (path.name, meta["description"], meta["item_count"])
