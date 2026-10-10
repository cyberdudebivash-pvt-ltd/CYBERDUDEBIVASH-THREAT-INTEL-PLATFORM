"""
tests/test_integrity_gate_actor_entropy.py

Intelligence Integrity Gate B, actor entropy (2026-09-26). The 18:30 and 22:11
sentinel-blogger runs on 2026-09-26 stopped at STAGE 3.93.15 and skipped the
deploy: 92% of the feed was CDB-UNATTR-CVE (the platform's own "no known actor"
placeholder), actor entropy fell to ~0.4 bits (< 0.5), and gate B HARD_FAILed
although the synthetic-CVE, authenticity and flood gates all passed.

The gate's own notes say unattributed CVE data "is the norm, not evidence of
synthetic generation". Low entropy now HARD_FAILs only when a named label (a
real actor or a synthetic CDB-*-GEN one) dominates; placeholder dominance is a
WARN finding.
"""
from scripts.intelligence_integrity_gate import (
    ENTROPY_ACTOR_MIN, FEED_MIN_UNIQUE_ACTORS, EntropyGate, FeedDiversityValidator,
)
import pytest


def _items(actors):
    return [
        {"title": f"Advisory {i}: distinct vulnerability in product {i * 7919 % 1000}", "actor": a}
        for i, a in enumerate(actors)
    ]


def _check(actors):
    hard_fail, findings = EntropyGate().check(_items(actors))
    actor_findings = [f for f in findings if "actor" in f.lower()]
    return hard_fail, actor_findings


def test_blocked_run_distribution_now_warns_instead_of_failing():
    # 22:11 run: 38 items, CDB-UNATTR-CVE = 92%.
    hard_fail, findings = _check(["CDB-UNATTR-CVE"] * 35 + ["CDB-UNATTR-APT"] * 3)
    assert hard_fail is False
    assert len(findings) == 1 and findings[0].startswith("[B] WARN")
    assert "CDB-UNATTR-CVE" in findings[0]


def test_all_unattributed_single_placeholder_warns():
    hard_fail, findings = _check(["CDB-UNATTR-CVE"] * 40)
    assert hard_fail is False
    assert findings[0].startswith("[B] WARN")


def test_named_actor_dominance_still_hard_fails():
    hard_fail, findings = _check(["APT28"] * 35 + ["CDB-UNATTR-CVE"] * 3)
    assert hard_fail is True
    assert findings[0].startswith("[B] LOW ACTOR DIVERSITY")


def test_synthetic_label_dominance_still_hard_fails():
    hard_fail, findings = _check(["CDB-APT-GEN-0042"] * 36 + ["CDB-UNATTR-CVE"] * 2)
    assert hard_fail is True
    assert findings[0].startswith("[B] LOW ACTOR DIVERSITY")


def test_diverse_feed_passes_without_warning():
    actors = ["CDB-UNATTR-CVE"] * 20 + ["APT28"] * 6 + ["Lazarus"] * 6 + ["FIN7"] * 6
    hard_fail, findings = _check(actors)
    assert hard_fail is False
    assert findings[0].startswith("[B] Actor diversity entropy")
    assert "WARN" not in findings[0]


def test_threshold_unchanged():
    assert ENTROPY_ACTOR_MIN == 0.5


def _diversity_check(actors, *, sources=2):
    items = _items(actors)
    for i, item in enumerate(items):
        item["source_url"] = f"https://source-{i % sources}.example/advisory/{i}"
    return FeedDiversityValidator().check(items)


@pytest.mark.parametrize("label", ["CDB-UNATTR-CVE", "CDB-UNATTR-APT", "unknown", "none", "n/a", ""])
def test_missing_named_attribution_warns_without_inventing_an_actor(label):
    hard_fail, findings = _diversity_check([label] * 25)
    assert hard_fail is False
    assert any(f.startswith("[C] WARN") and "No named actor" in f for f in findings)
    assert not any("ACTOR MONOCULTURE" in f for f in findings)


def test_production_distribution_of_17_missing_and_8_placeholders_passes():
    hard_fail, findings = _diversity_check([None] * 17 + ["CDB-UNATTR-CVE"] * 8, sources=4)
    assert hard_fail is False
    assert any("No named actor" in f for f in findings)


@pytest.mark.parametrize("label", ["APT28", "CDB-APT-GEN-0042"])
def test_named_or_synthetic_actor_monoculture_still_hard_fails(label):
    hard_fail, findings = _diversity_check([label] * 25)
    assert hard_fail is True
    assert any("ACTOR MONOCULTURE" in f for f in findings)


def test_placeholders_cannot_supply_a_second_named_actor():
    hard_fail, findings = _diversity_check(["APT28"] * 8 + ["CDB-UNATTR-CVE"] * 17)
    assert hard_fail is True
    assert any("Only 1 distinct actor" in f for f in findings)


def test_two_named_actors_still_pass():
    hard_fail, findings = _diversity_check(["APT28"] * 8 + ["Lazarus"] * 8 + ["CDB-UNATTR-CVE"] * 9)
    assert hard_fail is False
    assert not any("ACTOR MONOCULTURE" in f for f in findings)


def test_unattributed_window_still_requires_multiple_sources():
    hard_fail, findings = _diversity_check(["CDB-UNATTR-CVE"] * 25, sources=1)
    assert hard_fail is True
    assert any("SINGLE-SOURCE DOMINANCE" in f for f in findings)


def test_named_actor_minimum_is_unchanged():
    assert FEED_MIN_UNIQUE_ACTORS == 2
