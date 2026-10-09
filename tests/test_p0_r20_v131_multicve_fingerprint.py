"""P0 R20 negative controls for heterogeneous CVE/actor deduplication."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from v131_fingerprint import advisory_fingerprint


def test_cve_array_no_longer_raises_and_has_stable_digest():
    value = {"id": "intel--one", "title": "Advisory", "cve": ["CVE-2026-1111", "CVE-2026-2222"], "actor_tag": "UNATTRIBUTED"}
    digest = advisory_fingerprint(value)
    assert len(digest) == 64
    assert digest == advisory_fingerprint({**value, "cve": list(reversed(value["cve"]))})


def test_scalar_legacy_cve_still_supported_without_field_mutation():
    record = {"title": "  Advisory ", "cve_id": "CVE-2026-1111", "actor_tag": "UNC"}
    original = dict(record)
    assert advisory_fingerprint(record) == advisory_fingerprint(
        {"title": "advisory", "cve": "cve-2026-1111", "actor_tag": "unc"})
    assert record == original


def test_multi_cve_distinguishes_different_advisories():
    base = {"title": "Same Headline", "actor_tag": "UNKNOWN"}
    assert advisory_fingerprint({**base, "cve": ["CVE-2026-1111"]}) != advisory_fingerprint(
        {**base, "cve": ["CVE-2026-1111", "CVE-2026-2222"]})


def test_canonical_json_avoids_pipe_field_delimiter_collisions():
    assert advisory_fingerprint({"title": "a|b", "cve": "c", "actor_tag": "d"}) != advisory_fingerprint(
        {"title": "a", "cve": "b|c", "actor_tag": "d"})


def test_heterogeneous_cve_lists_are_order_independent_and_not_declassified():
    sample = {"title": "Advisory", "cve": ["CVE-2026-1111", {"unexpected": 2}], "tlp": "TLP:AMBER"}
    original = {"title": "Advisory", "cve": ["CVE-2026-1111", {"unexpected": 2}], "tlp": "TLP:AMBER"}
    assert advisory_fingerprint(sample) == advisory_fingerprint(
        {**sample, "cve": list(reversed(sample["cve"]))})
    assert sample == original
    assert sample["tlp"] == "TLP:AMBER"


def test_malformed_record_refused():
    with pytest.raises(TypeError):
        advisory_fingerprint(["unvalidated"])


def test_fingerprint_is_explicitly_wired_to_stage_36():
    source = (ROOT / "scripts" / "apply_v131_upgrades.py").read_text(encoding="utf-8")
    assert "from v131_fingerprint import advisory_fingerprint" in source
    assert "fp = advisory_fingerprint(item)" in source
    assert 'fp_key = "|".join' not in source
