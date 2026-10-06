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
from scripts.intelligence_integrity_gate import ENTROPY_ACTOR_MIN, EntropyGate


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
