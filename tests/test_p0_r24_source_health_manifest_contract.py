"""P0 R24: registered source health recognizes canonical manifest envelope."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import source_fabric_health as sfh


@pytest.mark.parametrize("payload", [
    [{"id": "intel--one", "feed_source": "rss_vendor_example"}],
    {"advisories": [{"id": "intel--one", "feed_source": "rss_vendor_example"}]},
    {"reports": [{"id": "intel--one", "feed_source": "rss_vendor_example"}]},
    {"items": [{"id": "intel--one", "feed_source": "rss_vendor_example"}]},
    {"data": [{"id": "intel--one", "feed_source": "rss_vendor_example"}]},
    {"entries": [{"id": "intel--one", "feed_source": "rss_vendor_example"}]},
])
def test_manifest_envelopes_preserve_real_rows(payload):
    assert sfh._manifest_rows(payload) == [
        {"id": "intel--one", "feed_source": "rss_vendor_example"}
    ]


@pytest.mark.parametrize("payload", [None, {}, {"advisories": {}}, "not-json",
                                        [], {"advisories": []}, [None, 2]])
def test_missing_or_invalid_manifest_never_creates_fake_source_rows(payload):
    assert sfh._manifest_rows(payload) == []


def _source():
    return {
        "source_id": "test_verified_rss",
        "canonical_name": "Reviewed RSS source",
        "pipeline_feed_source_key": "rss:*",
        "implementation_status": "ACTIVE",
        "integration_mode": "EVENT_STREAM",
        "wave": 1,
        "freshness_expectation": "DAILY",
        "criticality": "HIGH",
        "connector_ref": "scripts/true_intel_ingestor.py",
    }


def _audit(monkeypatch, payload):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(sfh, "load_registry", lambda: {"registry_version": "test-only"})
    monkeypatch.setattr(sfh, "all_sources", lambda: [_source()])
    monkeypatch.setattr(sfh, "_load_json_safe", lambda path: (
        payload if path == sfh.MANIFEST_PATH else
        {"sources": {}} if path == sfh.FEED_STATE_PATH else None
    ))
    return sfh.compute_health()


def test_real_fresh_event_from_envelope_has_observed_healthy_source(monkeypatch):
    source_event = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    raw = {"advisories": [{
        "id": "intel--fresh", "feed_source": "rss_vendor_example",
        "published_at": source_event,
    }]}
    result = _audit(monkeypatch, raw)
    assert result["manifest_total_entries"] == 1
    assert result["health_breakdown"]["HEALTHY"] == 1
    assert result["sources"][0]["records_received_current_window"] == 1


def test_old_event_remains_stale_and_does_not_pass_g10(monkeypatch):
    source_event = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    raw = {"advisories": [{
        "id": "intel--stale", "feed_source": "rss_vendor_example",
        "published_at": source_event
    }]}
    result = _audit(monkeypatch, raw)
    assert result["health_breakdown"]["HEALTHY"] == 0
    assert result["health_breakdown"]["STALE"] == 1


def test_zero_records_or_unmatched_collector_never_makes_healthy_source(monkeypatch):
    for payload in [{"items": []}, {"items": [{
        "id": "intel--unknown", "feed_source": "not_an_authorized_registry_key",
        "published_at": datetime.now(timezone.utc).isoformat()
    }]}]:
        result = _audit(monkeypatch, payload)
        assert result["health_breakdown"]["HEALTHY"] == 0
        assert result["sources"][0]["records_received_current_window"] == 0
