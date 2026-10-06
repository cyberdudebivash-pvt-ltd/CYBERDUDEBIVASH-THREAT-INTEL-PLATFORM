"""
tests/test_detection_bundle_injector_failure_isolation.py

Phase 4.1 mandate Section 20/39: deterministic tests proving
scripts/detection_bundle_injector.py's per-item exception isolation. Before
this fix, one item that crashed rule generation aborted run() entirely --
losing not just that item but every item successfully processed earlier in
the same run, since the feed/manifest write only happens once, after the
loop completes. No network calls.
"""
import json
import os

import scripts.detection_bundle_injector as dbi


GOOD_ITEM = {
    "stix_id": "intel--good0000000000000001",
    "id": "intel--good0000000000000001",
    "title": "CVE-2026-11111: Example Remote Code Execution",
    "cve_id": "CVE-2026-11111",
    "severity": "HIGH",
    "risk_score": 8.0,
    "tags": ["rce", "web"],
    "threat_type": "vulnerability",
}

# tags is a list containing a non-string element -- " ".join(tags) inside
# _classify_vuln() raises TypeError on this, simulating a real malformed-
# producer-output crash rather than an artificial one.
BAD_ITEM = {
    "stix_id": "intel--bad00000000000000002",
    "id": "intel--bad00000000000000002",
    "title": "CVE-2026-22222: Malformed tags field",
    "cve_id": "CVE-2026-22222",
    "severity": "HIGH",
    "risk_score": 9.0,
    "tags": ["ok", 12345, None],  # non-string element -> TypeError
    "threat_type": "vulnerability",
}


def _write_feed_and_manifest(tmp_path, items):
    feed_path = tmp_path / "feed.json"
    manifest_path = tmp_path / "manifest.json"
    feed_path.write_text(json.dumps(items), encoding="utf-8")
    manifest_path.write_text(json.dumps(items), encoding="utf-8")
    return feed_path, manifest_path


def test_bad_item_does_not_abort_the_whole_run(tmp_path, monkeypatch):
    monkeypatch.setattr(dbi, "DETECTIONS_DIR", tmp_path / "detections")
    monkeypatch.setattr(dbi, "TELEMETRY", tmp_path / "telemetry.json")
    monkeypatch.setattr(dbi, "MAX_ITEMS", 200)

    feed_path, manifest_path = _write_feed_and_manifest(tmp_path, [GOOD_ITEM, BAD_ITEM])

    # Must not raise -- this is the core regression this fix closes.
    result = dbi.run(feed_path, manifest_path)

    assert result["injected"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 0


def test_good_item_processed_before_bad_item_is_not_lost(tmp_path, monkeypatch):
    """Regression for the specific failure mode this fix closes: previously
    a crash on item N discarded every item 1..N-1 too, since the write
    happens once at the end of the loop. Puts the good item FIRST so a
    naive re-fix that only 'skips forward' past the crash without actually
    preserving prior work would still fail this test."""
    monkeypatch.setattr(dbi, "DETECTIONS_DIR", tmp_path / "detections")
    monkeypatch.setattr(dbi, "TELEMETRY", tmp_path / "telemetry.json")
    monkeypatch.setattr(dbi, "MAX_ITEMS", 200)

    feed_path, manifest_path = _write_feed_and_manifest(tmp_path, [GOOD_ITEM, BAD_ITEM])
    dbi.run(feed_path, manifest_path)

    written = json.loads(feed_path.read_text(encoding="utf-8"))
    good = next(i for i in written if i["stix_id"] == GOOD_ITEM["stix_id"])
    assert good.get("sigma_rule"), "good item's rules must survive a later item's crash"
    assert good.get("kql_query")
    assert good.get("suricata_rule")

    bad = next(i for i in written if i["stix_id"] == BAD_ITEM["stix_id"])
    assert not bad.get("sigma_rule"), "a failed item must not be left with partial/fabricated content"


def test_failure_is_logged_and_visible_in_telemetry_not_swallowed(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(dbi, "DETECTIONS_DIR", tmp_path / "detections")
    telemetry_path = tmp_path / "telemetry.json"
    monkeypatch.setattr(dbi, "TELEMETRY", telemetry_path)
    monkeypatch.setattr(dbi, "MAX_ITEMS", 200)

    feed_path, manifest_path = _write_feed_and_manifest(tmp_path, [GOOD_ITEM, BAD_ITEM])
    with caplog.at_level("ERROR"):
        dbi.run(feed_path, manifest_path)

    assert any("DETECT-FAIL" in r.message for r in caplog.records), \
        "a per-item failure must be logged, not silently swallowed"

    telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert telemetry["failed"] == 1
    assert BAD_ITEM["stix_id"][:40] in telemetry["failed_ids_sample"]


def test_all_items_failing_still_writes_telemetry(tmp_path, monkeypatch):
    """Section 21: failures must be observable even when nothing succeeds --
    previously the telemetry write was gated on injected > 0 alone, so an
    all-failure run left zero trace of what happened."""
    monkeypatch.setattr(dbi, "DETECTIONS_DIR", tmp_path / "detections")
    telemetry_path = tmp_path / "telemetry.json"
    monkeypatch.setattr(dbi, "TELEMETRY", telemetry_path)
    monkeypatch.setattr(dbi, "MAX_ITEMS", 200)

    feed_path, manifest_path = _write_feed_and_manifest(tmp_path, [BAD_ITEM])
    result = dbi.run(feed_path, manifest_path)

    assert result["injected"] == 0
    assert result["failed"] == 1
    assert telemetry_path.exists(), "telemetry must be written even when every item failed"
    telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert telemetry["failed"] == 1


def test_keyboard_interrupt_is_not_swallowed(tmp_path, monkeypatch):
    """Section 20: 'do not swallow system-wide fatal errors' -- the isolation
    catches Exception, never BaseException, so a genuine abort signal raised
    mid-item still propagates instead of being silently absorbed."""
    monkeypatch.setattr(dbi, "DETECTIONS_DIR", tmp_path / "detections")
    monkeypatch.setattr(dbi, "TELEMETRY", tmp_path / "telemetry.json")
    monkeypatch.setattr(dbi, "MAX_ITEMS", 200)

    def _boom(*_a, **_kw):
        raise KeyboardInterrupt()

    monkeypatch.setattr(dbi, "_classify_vuln", _boom)
    feed_path, manifest_path = _write_feed_and_manifest(tmp_path, [GOOD_ITEM])

    try:
        dbi.run(feed_path, manifest_path)
        assert False, "KeyboardInterrupt must propagate, not be caught as a per-item failure"
    except KeyboardInterrupt:
        pass
