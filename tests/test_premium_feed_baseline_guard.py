"""F26 (2026-10-02): the premium baseline's shrinkage guard.

Measured in production: every publisher run refused to update
api/feed.baseline.json ("SHRINKAGE GUARD: new baseline (42) is 4% of prior
(985)", run 36969320297). The four Enterprise/MSSP premium feeds built from
it therefore served items published 2026-08-19..26. _merge() drops prior
items older than MERGE_WINDOW_H by design, but the guard divided by the
whole prior baseline. Once the prior aged past the window (it could no
longer be persisted, F25), no update could ever pass.

These tests pin the corrected contract:
  * a prior that is entirely older than the merge window never blocks a
    rebuild from the live feed;
  * prior items older than the window do not count against the new baseline;
  * the guard still refuses a run that would lose in-window premium items,
    the pipeline-defect case it exists for.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import premium_feed_baseline as pfb  # noqa: E402


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _items(prefix: str, n: int, hours_ago: float, risk: float = 7.5) -> list:
    return [
        {
            "id": f"{prefix}-{i}",
            "title": f"Advisory {prefix} {i} affecting example software",
            "risk_score": risk,
            "severity": "HIGH",
            "published_at": _iso(hours_ago),
        }
        for i in range(n)
    ]


@pytest.fixture
def engine(tmp_path, monkeypatch):
    feed = tmp_path / "feed.json"
    baseline = tmp_path / "feed.baseline.json"
    report = tmp_path / "baseline_report.json"
    monkeypatch.setattr(pfb, "FEED_PATH", feed)
    monkeypatch.setattr(pfb, "BASELINE_PATH", baseline)
    monkeypatch.setattr(pfb, "REPORT_PATH", report)
    monkeypatch.setattr(pfb, "DRY_RUN", False)
    monkeypatch.setattr(pfb, "MIN_RISK_SCORE", 0.5)
    monkeypatch.setattr(pfb, "SHRINKAGE_FLOOR", 0.70)
    monkeypatch.setattr(pfb, "MERGE_WINDOW_H", 96)

    def run(live, prior):
        feed.write_text(json.dumps(live), encoding="utf-8")
        baseline.write_text(json.dumps(prior), encoding="utf-8")
        rc = pfb.main()
        written = json.loads(baseline.read_text(encoding="utf-8"))
        rep = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
        return rc, written, rep

    return run


def test_prior_entirely_older_than_the_merge_window_does_not_freeze_the_baseline(engine):
    # The production shape on 2026-10-02: 985 prior items from August, 42 live.
    live = _items("LIVE", 42, hours_ago=2)
    prior = _items("AUG", 985, hours_ago=24 * 37)
    rc, written, report = engine(live, prior)
    assert rc == 0, "a stale prior must not block the rebuild"
    assert {i["id"] for i in written} == {i["id"] for i in live}
    assert report["prior_baseline"] == 985
    assert report["prior_in_window"] == 0


def test_aged_out_prior_items_do_not_count_against_the_new_baseline(engine):
    # 900 aged-out and 50 in-window prior items; 45 new live items. The
    # merge keeps the 50 and adds the 45, so no in-window item is lost.
    live = _items("LIVE", 45, hours_ago=1)
    prior = _items("OLD", 900, hours_ago=24 * 10) + _items("RECENT", 50, hours_ago=12)
    rc, written, report = engine(live, prior)
    assert rc == 0
    ids = {i["id"] for i in written}
    assert len(ids) == 95
    assert not any(i.startswith("OLD-") for i in ids), "aged-out items leave the baseline"
    assert report["prior_in_window"] == 50


def test_guard_still_refuses_to_lose_in_window_premium_items(engine):
    # Negative control: 100 in-window prior items, and a defect upstream makes
    # 80 of them fail the quality gate (risk below the floor). Only 20 would
    # survive: the prior baseline must be kept, not replaced.
    prior = _items("RECENT", 100, hours_ago=6)
    live = _items("RECENT", 80, hours_ago=6, risk=0.1)  # same ids, now rejected
    rc, written, _ = engine(live, prior)
    assert rc == 1
    assert [i["id"] for i in written] == [i["id"] for i in prior], "prior baseline retained unchanged"


def test_guard_counts_only_what_the_merge_can_keep(engine):
    # Negative control for the denominator: in-window loss is still caught
    # when aged-out items dominate the prior. 1,000 aged-out + 100 in-window;
    # 80 of the in-window ones are rejected, so only 20 of 100 survive.
    prior = _items("OLD", 1000, hours_ago=24 * 30) + _items("RECENT", 100, hours_ago=6)
    live = _items("RECENT", 80, hours_ago=6, risk=0.1)
    rc, written, _ = engine(live, prior)
    assert rc == 1
    assert len(written) == 1100, "prior baseline retained unchanged"
