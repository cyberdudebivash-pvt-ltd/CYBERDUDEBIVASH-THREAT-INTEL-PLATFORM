"""R28: forensic output must not make failed provenance disappear."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p0_r28_provenance_diagnostic import diagnose

def _run(tmp_path, records):
    path = tmp_path / "feed.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    before = path.read_bytes()
    result = diagnose(path)
    assert path.read_bytes() == before
    return result

def test_empty_feed_blocked(tmp_path):
    result = _run(tmp_path, [])
    assert result["status"] == "BLOCKED"
    assert result["records"] == 0

def test_absent_fields_reported_without_backfill(tmp_path):
    result = _run(tmp_path, [{"id": "item-1", "source_url": "https://example.org/article", "published_at": "2026-10-09T00:00:00Z"}])
    assert result["status"] == "BLOCKED"
    assert result["violations"]["M3"] == 1
    assert result["missing_fields"]["retrieval_timestamp"] == 1
    assert result["missing_fields"]["content_hash"] == 1

def test_self_publisher_and_low_quality_blocked(tmp_path):
    result = _run(tmp_path, [{"id": "item-2", "source": "SENTINEL-APEX"}])
    assert result["status"] == "BLOCKED"
    assert result["violations"]["M4"] == 1
    assert result["violations"]["M8"] == 1

def test_malformed_feed_rejected(tmp_path):
    p = tmp_path / "feed.json"
    p.write_text('{"advisories": []}', encoding="utf-8")
    assert diagnose(p)["status"] == "INVALID_INPUT"
