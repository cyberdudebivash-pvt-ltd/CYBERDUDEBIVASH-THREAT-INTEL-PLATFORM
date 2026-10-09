"""P0 R18: absence of attack-chain evidence must not be reported as absence of activity."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from report_enhancer import build_kill_chain_section


def test_missing_attack_chain_reports_evidence_gap_not_absence():
    html = build_kill_chain_section({"title": "Advisory", "kill_chain": []})
    assert "ATTACK-CHAIN EVIDENCE: NOT PROVIDED" in html
    assert "not evidence that intrusion" in html
    assert "OBSERVED ACTIVITY: NONE REPORTED" not in html
    assert "60-second beacon" not in html


def test_missing_attack_chain_key_is_equally_fail_closed():
    html = build_kill_chain_section({"title": "Advisory"})
    assert "ATTACK-CHAIN EVIDENCE: NOT PROVIDED" in html
    assert "not asserted without corroborating evidence" in html


def test_non_list_attack_chain_cannot_inject_activity_claims():
    html = build_kill_chain_section({"kill_chain": {"phase": "unverified"}})
    assert "ATTACK-CHAIN EVIDENCE: NOT PROVIDED" in html
    assert "unverified" not in html


def test_explicit_recorded_phases_retained_with_uncertainty():
    html = build_kill_chain_section({
        "severity": "HIGH",
        "kill_chain": [{"phase": "reported phase", "description": "source-stated observation"}],
    })
    assert "reported phase" in html
    assert "source-stated observation" in html
    assert "not independently verified" in html
