"""R35: invalid records must be rejected before the public feed write."""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from p0_r35_feed_prewrite_guard import assert_publishable

def test_empty_feed_is_not_releasable():
    with pytest.raises(ValueError, match="P0_FEED_PREWRITE_BLOCKED"):
        assert_publishable([])

def test_missing_provenance_denied():
    with pytest.raises(ValueError, match="M3"):
        assert_publishable([{"id": "a", "title": "Real incident", "source_url": "https://example.org/incident"}])

def test_internal_self_publisher_denied():
    with pytest.raises(ValueError, match="M4"):
        assert_publishable([{"id": "a", "title": "Incident", "source": "SENTINEL-APEX"}])

def test_prewrite_guard_before_any_feed_file_writes():
    source = (ROOT / "scripts/run_pipeline.py").read_text(encoding="utf-8")
    start = source.index("def stage_sync_root_feed_json")
    end = source.index("    # ---- Step 7: Write back canonical manifest", start)
    body = source[start:end]
    assert body.index("assert_publishable(payload)") < body.index("for target in targets:")
    assert "backfill_provenance(payload)" not in body

def test_valid_explicit_evidence_passes_only_prewrite_check():
    item = {
        "id": "verified-1", "title": "Reported vulnerability",
        "source": "Publisher", "source_name": "Publisher",
        "source_url": "https://publisher.example/incident/1",
        "publication_timestamp": "2026-10-09T13:00:00Z",
        "retrieval_timestamp": "2026-10-09T14:00:00Z",
        "content_hash": "abc123", "trust_score": 7, "evidence_count": 2
    }
    assert_publishable([item])  # Does not prove source authenticity or release GO.
