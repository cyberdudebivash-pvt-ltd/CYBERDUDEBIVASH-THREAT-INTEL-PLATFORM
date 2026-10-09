"""P0 R19 regression: empty or non-public/malformed input must never be enriched."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import enrich_feed_apex as enhancer


@pytest.mark.parametrize("payload", ["", "[]", '{"items":[]}', "null", "{}", '{"items":{}}', '[null]', "bad json"])
def test_empty_or_malformed_feed_is_blocked_without_mutation(tmp_path, monkeypatch, payload):
    target = tmp_path / "feed.json"
    target.write_text(payload, encoding="utf-8")
    original_bytes = target.read_bytes()
    monkeypatch.setattr(enhancer, "FEED_PATH", target)
    with pytest.raises(SystemExit) as raised:
        enhancer.main()
    assert raised.value.code == 2, "P0 blocker must not silently pass"
    assert target.read_bytes() == original_bytes, "must preserve input bytes, including empty feeds"


def test_missing_feed_is_blocked_without_creation(tmp_path, monkeypatch):
    target = tmp_path / "missing" / "feed.json"
    monkeypatch.setattr(enhancer, "FEED_PATH", target)
    with pytest.raises(SystemExit) as raised:
        enhancer.main()
    assert raised.value.code != 0
    assert not target.exists()
