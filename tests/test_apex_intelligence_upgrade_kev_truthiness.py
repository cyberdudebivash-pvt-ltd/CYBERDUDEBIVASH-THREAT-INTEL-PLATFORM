#!/usr/bin/env python3
"""
tests/test_apex_intelligence_upgrade_kev_truthiness.py — RX-PR1 regression suite

ORIGIN: REPORT-X dual-platform forensics (RX-STABILIZATION-1). PR-E1 (frontend
js/metric-normalize.js) and PR-E2 (scripts/context_aware_narrative_engine.py)
already fixed the same defect class: `bool(item.get("kev") or item.get("in_kev")
or item.get("kev_present"))` treats ANY non-empty string as truthy, so a
legacy value like `"NO"` or `"false"` reads as KEV-confirmed.

This session found four more untouched instances of the identical bug in
agent/apex_intelligence_upgrade.py (generate_technical_narrative's non-CANE
fallback, generate_campaign_intelligence, generate_ai_insight_premium,
generate_executive_summary — the last of which is confirmed live-called from
the real customer report path) plus two in scripts/ (persistent_campaign_graph_
engine.py's knowledge-graph node attribute, explainable_confidence_engine.py's
kev_confirmed confidence-score contributor). All were fixed by reusing the
already-approved canonical helper, context_aware_narrative_engine._kev_confirmed(),
instead of re-deriving the parsing logic.

MANDATE: These tests are the permanent regression guard for that reuse. If they
         fail, one of these call sites has reverted to the bare-truthiness
         pattern (or a new instance of it was introduced elsewhere and wired
         to a different local variable) and confirmed-exploitation language
         can once again be shown for an item that explicitly reports kev="NO".
"""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO, "scripts")
AGENT_DIR = os.path.join(REPO, "agent")
# agent/ has its own, unrelated explainable_confidence_engine.py (a dormant
# duplicate — see REPORT-X findings). Insert AGENT_DIR first so SCRIPTS_DIR
# ends up at sys.path[0] and wins the bare `import explainable_confidence_
# engine` below, matching how agent/apex_intelligence_upgrade.py's own guarded
# import resolves it in real production use.
for _p in (AGENT_DIR, SCRIPTS_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import explainable_confidence_engine as _ece   # noqa: E402
import persistent_campaign_graph_engine as _pcge  # noqa: E402
import apex_intelligence_upgrade as _aiu       # noqa: E402

# Legacy string values a real feed could still send that must NOT read as
# KEV-confirmed (the exact bug: bool("NO") / bool("false") / bool("0") are
# all True in Python).
FALSE_LIKE_STRINGS = ["NO", "no", "false", "False", "0", ""]
TRUE_LIKE_STRINGS = ["YES", "yes", "true", "True", "1"]


@pytest.mark.parametrize("value", FALSE_LIKE_STRINGS)
def test_explainable_confidence_engine_does_not_award_kev_points_for_false_like_string(value):
    item = {"kev": value, "title": "Example advisory", "severity": "MEDIUM"}
    assert _ece._kev_confirmed_check(item) is False, (
        f"explainable_confidence_engine treated kev={value!r} as confirmed — "
        f"this would award kev_confirmed confidence points for an item that "
        f"is not actually KEV-listed."
    )


@pytest.mark.parametrize("value", TRUE_LIKE_STRINGS)
def test_explainable_confidence_engine_recognises_true_like_string(value):
    item = {"kev": value}
    assert _ece._kev_confirmed_check(item) is True


@pytest.mark.parametrize("value", FALSE_LIKE_STRINGS)
def test_campaign_graph_kev_node_attribute_not_set_for_false_like_string(value):
    item = {"kev": value, "title": "Example advisory"}
    assert _pcge._kev_confirmed_check(item) is False


@pytest.mark.parametrize("value", FALSE_LIKE_STRINGS)
def test_apex_intelligence_upgrade_technical_narrative_no_confirmed_exploit_language(value):
    """generate_technical_narrative()'s non-CANE fallback (CLS_CVE_GENERIC /
    CLS_THREAT_INTEL, or CANE unavailable) must not show 'CISA KEV CONFIRMED'
    language for an item whose kev field is a false-like string."""
    item = {
        "title": "CVE-2026-11111 Example vulnerability in a Windows service",
        "description": "A vulnerability affecting an internal Windows service.",
        "cvss_score": 7.5,
        "kev": value,
    }
    html = _aiu.generate_technical_narrative(item)
    assert "CISA KEV CONFIRMED" not in html, (
        f"generate_technical_narrative() showed confirmed-KEV language for "
        f"kev={value!r} — the bare bool() truthy bug is back."
    )


def test_apex_intelligence_upgrade_technical_narrative_shows_confirmed_for_true_kev():
    item = {
        "title": "CVE-2026-22222 Example vulnerability in a Windows service",
        "description": "A vulnerability affecting an internal Windows service.",
        "cvss_score": 9.1,
        "kev": True,
    }
    html = _aiu.generate_technical_narrative(item)
    assert "CISA KEV CONFIRMED" in html


@pytest.mark.parametrize("value", FALSE_LIKE_STRINGS)
def test_apex_intelligence_upgrade_executive_summary_not_in_kev_for_false_like_string(value):
    """generate_executive_summary() is confirmed live-called from the real
    customer report path (scripts/generate_intel_reports.py). A false-like
    kev string must render as "Not in CISA KEV", not "CISA KEV CONFIRMED"."""
    item = {
        "title": "CVE-2026-33333 Example vulnerability",
        "description": "A vulnerability in an example product.",
        "risk_score": 6.0,
        "kev": value,
    }
    html = _aiu.generate_executive_summary(item)
    assert "Not in CISA KEV" in html
    assert "CISA KEV CONFIRMED" not in html


def test_apex_intelligence_upgrade_executive_summary_confirms_true_kev():
    item = {
        "title": "CVE-2026-44444 Example vulnerability",
        "description": "A vulnerability in an example product.",
        "risk_score": 9.5,
        "kev": True,
    }
    html = _aiu.generate_executive_summary(item)
    assert "CISA KEV CONFIRMED" in html


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
