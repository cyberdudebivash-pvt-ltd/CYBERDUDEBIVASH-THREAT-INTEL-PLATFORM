"""
tests/test_intelligence_content_contract.py
CYBERDUDEBIVASH(R) SENTINEL APEX v185.0 -- Content Contract Gate (Phase 4)

Deterministic tests for scripts/intelligence_content_contract.py and
scripts/report_type_contracts.py against the golden fixtures in
tests/fixtures/golden_intelligence_reports.py. No live network calls, no
dependency on the live feed snapshot.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import pytest

from intelligence_content_contract import validate_intelligence_content
from report_type_contracts import classify_report_type, CVE_VULNERABILITY, RANSOMWARE, MALWARE, \
    INCIDENT_BREACH, SECURITY_ADVISORY, NEWS, INDICATOR_FEED

from tests.fixtures.golden_intelligence_reports import (
    CVE_VALID, CVE_WARN, CVE_HOLD,
    RANSOMWARE_VALID, RANSOMWARE_WARN, RANSOMWARE_HOLD,
    MALWARE_VALID, MALWARE_WARN, MALWARE_HOLD,
    INCIDENT_VALID, INCIDENT_WARN, INCIDENT_HOLD,
    ADVISORY_VALID, ADVISORY_WARN, ADVISORY_HOLD,
    NEWS_VALID, NEWS_WARN, NEWS_HOLD,
    INDICATOR_VALID, INDICATOR_WARN, INDICATOR_HOLD,
)


# ---------------------------------------------------------------------------
# Report-type classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture,expected_type", [
    (CVE_VALID, CVE_VULNERABILITY),
    (RANSOMWARE_VALID, RANSOMWARE),
    (MALWARE_VALID, MALWARE),
    (INCIDENT_VALID, INCIDENT_BREACH),
    (ADVISORY_VALID, SECURITY_ADVISORY),
    (NEWS_VALID, NEWS),
    (INDICATOR_VALID, INDICATOR_FEED),
])
def test_report_type_classification(fixture, expected_type):
    assert classify_report_type(fixture) == expected_type


# ---------------------------------------------------------------------------
# VALID fixtures: must not HOLD. PASS or WARN are both acceptable --
# "valid" does not mean "perfect", it means "safe and honest to publish".
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture,label", [
    (CVE_VALID, "CVE"), (RANSOMWARE_VALID, "RANSOMWARE"), (MALWARE_VALID, "MALWARE"),
    (INCIDENT_VALID, "INCIDENT"), (ADVISORY_VALID, "ADVISORY"), (NEWS_VALID, "NEWS"),
    (INDICATOR_VALID, "INDICATOR"),
])
def test_valid_fixtures_never_hold(fixture, label):
    r = validate_intelligence_content(fixture)
    assert r.severity != "HOLD", f"{label}_VALID unexpectedly HOLD: {[v.code for v in r.violations]}"
    assert r.hold_publication is False
    assert r.valid is True


def test_valid_fixture_indicator_minimal_still_passes():
    """INDICATOR_WARN fixture has no severity field (OPTIONAL for this
    report type) -- must not be penalized for an OPTIONAL field's absence."""
    r = validate_intelligence_content(INDICATOR_WARN)
    codes = [v.code for v in r.violations]
    assert "MISSING_CRITICAL_SECTION" not in codes or all(
        v.field != "severity" for v in r.violations if v.code == "MISSING_CRITICAL_SECTION"
    )


# ---------------------------------------------------------------------------
# WARN fixtures: real but non-blocking. Must not PASS silently (there IS a
# real defect to surface) and must not HOLD (not publication-unsafe).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture,label", [
    (CVE_WARN, "CVE"), (RANSOMWARE_WARN, "RANSOMWARE"), (MALWARE_WARN, "MALWARE"),
    (INCIDENT_WARN, "INCIDENT"), (ADVISORY_WARN, "ADVISORY"), (NEWS_WARN, "NEWS"),
])
def test_warn_fixtures_not_hold(fixture, label):
    r = validate_intelligence_content(fixture)
    assert r.severity != "HOLD", f"{label}_WARN unexpectedly HOLD: {[v.code for v in r.violations]}"


# ---------------------------------------------------------------------------
# HOLD fixtures: each carries a deliberately unsafe/misleading defect and
# MUST be blocked from publication.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture,label,expected_code", [
    (CVE_HOLD, "CVE", "PLACEHOLDER"),
    (RANSOMWARE_HOLD, "RANSOMWARE", "UNSAFE_HTML"),
    (MALWARE_HOLD, "MALWARE", "INTERNAL_INSTRUCTION"),
    (INCIDENT_HOLD, "INCIDENT", "INTERNAL_INSTRUCTION"),
    (ADVISORY_HOLD, "ADVISORY", "MALFORMED_REFERENCE"),
    (NEWS_HOLD, "NEWS", "INTERNAL_INSTRUCTION"),
    (INDICATOR_HOLD, "INDICATOR", "MISSING_CRITICAL_SECTION"),
])
def test_hold_fixtures_block_publication(fixture, label, expected_code):
    r = validate_intelligence_content(fixture)
    assert r.severity == "HOLD", f"{label}_HOLD did not HOLD (got {r.severity}): {[v.code for v in r.violations]}"
    assert r.hold_publication is True
    assert r.valid is False
    codes = [v.code for v in r.violations]
    assert expected_code in codes, f"{label}_HOLD: expected {expected_code} in {codes}"


# ---------------------------------------------------------------------------
# Report-type applicability: NOT_APPLICABLE fields must never generate a
# MISSING_CRITICAL_SECTION violation.
# ---------------------------------------------------------------------------

def test_news_missing_ioc_is_not_a_violation():
    """The mandate's core News Contract assertion: 0 IOC/0 ATT&CK/0 detection
    is a VALID state for news, not a defect. NEWS_VALID has no iocs field at
    all -- must not be flagged."""
    r = validate_intelligence_content(NEWS_VALID)
    codes = [v.code for v in r.violations]
    assert "MISSING_CRITICAL_SECTION" not in codes


def test_cve_missing_iocs_is_not_a_violation():
    """CVE advisories describe a vulnerability, not campaign infrastructure
    -- iocs is NOT_APPLICABLE for CVE_VULNERABILITY, never REQUIRED."""
    r = validate_intelligence_content(CVE_VALID)
    for v in r.violations:
        assert not (v.code == "MISSING_CRITICAL_SECTION" and v.field == "iocs")


# ---------------------------------------------------------------------------
# Idempotence / determinism: running the same item twice must produce the
# same severity and the same violation codes (order-independent).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture", [CVE_VALID, RANSOMWARE_HOLD, NEWS_WARN, INDICATOR_HOLD])
def test_deterministic(fixture):
    r1 = validate_intelligence_content(dict(fixture))
    r2 = validate_intelligence_content(dict(fixture))
    assert r1.severity == r2.severity
    assert sorted(v.code for v in r1.violations) == sorted(v.code for v in r2.violations)


# ---------------------------------------------------------------------------
# Report_url == source_url invariant (Phase 2's T09, re-surfaced here as a
# first-class HOLD-eligible violation).
# ---------------------------------------------------------------------------

def test_report_url_equals_source_url_holds():
    item = dict(CVE_VALID)
    item["id"] = "intel--fixture-t09-hold"
    item["report_url"] = item["source_url"]
    r = validate_intelligence_content(item)
    assert r.severity == "HOLD"
    codes = [v.code for v in r.violations]
    assert "REPORT_URL_IS_SOURCE_URL" in codes


def test_report_url_different_from_source_url_ok():
    item = dict(CVE_VALID)
    item["id"] = "intel--fixture-t09-ok"
    item["report_url"] = "https://intel.cyberdudebivash.com/reports/2026/08/intel--fixture-t09-ok.html"
    r = validate_intelligence_content(item)
    codes = [v.code for v in r.violations]
    assert "REPORT_URL_IS_SOURCE_URL" not in codes
