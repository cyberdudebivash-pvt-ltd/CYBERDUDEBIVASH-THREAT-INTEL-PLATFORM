"""R22 regression: historical newness must not erase canonical CTI inventory."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import safe_io
import intel_dedup_engine


def records():
    return [
        {"id": "intel--first", "stix_id": "intel--first", "title": "Independent CVE-A Advisory",
         "source": "public-cisa", "published_at": "2026-10-09T10:00:00Z", "tlp": "TLP:CLEAR"},
        {"id": "intel--second", "stix_id": "intel--second", "title": "Independent CVE-B Advisory",
         "source": "partner-internal", "published_at": "2026-10-08T11:00:00Z", "tlp": "TLP:AMBER"},
    ]


def test_canonical_snapshot_retains_already_seen_records(monkeypatch):
    class CrossRunHistory:
        def dedup_batch(self, candidates):
            pytest.fail("Canonical snapshot must not invoke persistent cross-run engine")
    monkeypatch.setattr(intel_dedup_engine, "get_dedup_engine", lambda: CrossRunHistory())
    rows = records()
    original = copy.deepcopy(rows)
    kept, removed = safe_io.dedup_items(rows, use_persistent_history=False)
    assert len(kept) == 2
    assert removed == 0
    assert kept == original
    assert kept[1]["tlp"] == "TLP:AMBER", "No implicit declassification"


def test_default_incremental_mode_still_drops_seen_entries(monkeypatch):
    class SeenIndex:
        def dedup_batch(self, rows):
            return [], len(rows)
    monkeypatch.setattr(intel_dedup_engine, "get_dedup_engine", lambda: SeenIndex())
    kept, removed = safe_io.dedup_items(records())
    assert kept == []
    assert removed == 2


def test_canonical_still_deduplicates_within_same_manifest(monkeypatch):
    class SeenIndex:
        def dedup_batch(self, rows):
            pytest.fail("No persistent state reads allowed")
    monkeypatch.setattr(intel_dedup_engine, "get_dedup_engine", lambda: SeenIndex())
    items = records()
    kept, removed = safe_io.dedup_items(items + [copy.deepcopy(items[0])],
                                         use_persistent_history=False)
    assert len(kept) == 2
    assert removed >= 1
    assert len({i["id"] for i in kept}) == 2


def test_stage_32_uses_snapshot_mode_while_default_contract_preserved():
    source = (ROOT / "scripts" / "run_pipeline.py").read_text(encoding="utf-8")
    assert "items, removed = dedup_items(items, use_persistent_history=False)" in source
    safe_source = (ROOT / "scripts" / "safe_io.py").read_text(encoding="utf-8")
    assert "use_persistent_history: bool = True" in safe_source
