#!/usr/bin/env python3
"""
tests/test_generate_intel_reports_financial_impact.py — RX-PR1 Fix B regression suite

ORIGIN: REPORT-X dual-platform forensics (RX-STABILIZATION-1). Live-verified
against fixture A-1 (intel--f43ac4fcc6f30452, an OpenPhish phishing-URL
report — real catalog entry: severity=HIGH, cve=[], kev_present=false,
threat_type="") that scripts/generate_intel_reports.py::build_report_sections()
rendered "WHAT TO DO TODAY? PATCH WITHIN 14 DAYS" (a CVE remediation directive
on a record with no CVE and nothing to patch) and "FINANCIAL EXPOSURE $1M-$4M
exposure (Standard Enterprise rate)" (a specific-looking dollar figure with no
real customer telemetry behind it, framed as if customer-specific).

MANDATE: These tests are the permanent regression guard for both defects. If
         they fail, a non-vulnerability record can again be shown a patch
         directive it has no way to act on, or a false-precision financial
         figure can again be presented as if it were customer-specific.
"""

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import generate_intel_reports as gir  # noqa: E402


# Fixture A-1 — real catalog shape for intel--f43ac4fcc6f30452, captured via
# GET https://intel.cyberdudebivash.com/api/reports/index.json during RX-PR1
# forensics (2026-08-12). Only the fields build_report_sections() reads are
# reproduced; the full raw record is not publicly exposed.
FIXTURE_A1_PHISHING = {
    "id": "intel--f43ac4fcc6f30452",
    "title": "[OpenPhish] Phishing URL: https://a1d504.arcadejafet.cl/",
    "description": "A phishing URL was identified by OpenPhish.",
    "severity": "HIGH",
    "threat_type": "",
    "feed_source": "openphish",
    "risk_score": 7.0,
    "kev_present": False,
    "cve_id": None,
}


def test_fixture_a1_phishing_item_gets_no_patch_directive():
    html = gir.build_report_sections(dict(FIXTURE_A1_PHISHING))
    assert "PATCH WITHIN" not in html, (
        "A-1 (phishing URL, no CVE) was shown a CVE patch-remediation "
        "directive — there is nothing to patch on this record type."
    )
    assert "IMMEDIATE PATCH REQUIRED" not in html


def test_fixture_a1_phishing_item_gets_honest_financial_disclosure():
    html = gir.build_report_sections(dict(FIXTURE_A1_PHISHING))
    assert "CUSTOMER EXPOSURE: UNKNOWN" in html, (
        "A-1 must honestly disclose that no customer-specific financial "
        "telemetry is available, rather than presenting a severity-derived "
        "industry figure as if it were customer-specific."
    )
    assert "Standard Enterprise rate" not in html, (
        "The old unlabelled, unsourced 'Standard Enterprise rate' framing "
        "must not appear — any generic figure must be explicitly labelled "
        "an industry/scenario estimate with its source."
    )


def test_fixture_a1_phishing_item_industry_estimate_is_labelled_and_sourced():
    html = gir.build_report_sections(dict(FIXTURE_A1_PHISHING))
    assert "INDUSTRY/SCENARIO ESTIMATE" in html
    assert "IBM Cost of a Data Breach Report 2025" in html


@pytest.mark.parametrize("false_like_kev", ["NO", "no", "false", "False", "0", "", None, False])
def test_fixture_a1_variant_kev_false_like_never_shows_confirmed_language(false_like_kev):
    item = dict(FIXTURE_A1_PHISHING)
    item["kev"] = false_like_kev
    item.pop("kev_present", None)
    html = gir.build_report_sections(item)
    assert "IMMEDIATE PATCH REQUIRED" not in html


def test_genuine_cve_item_keeps_its_patch_directive():
    item = {
        "id": "intel--test-genuine-cve",
        "title": "CVE-2026-99999 Critical Remote Code Execution in Example Product",
        "description": "A critical remote code execution vulnerability affecting Example Product.",
        "severity": "HIGH",
        "threat_type": "Vulnerability",
        "feed_source": "nvd",
        "risk_score": 8.5,
        "cve_id": "CVE-2026-99999",
        "kev": "NO",
    }
    html = gir.build_report_sections(item)
    assert "PATCH WITHIN 14 DAYS" in html, (
        "A genuine CVE/vulnerability record must keep its patch-remediation "
        "directive — the A-1 fix must not over-suppress legitimate guidance."
    )


def test_genuine_kev_confirmed_cve_shows_immediate_patch_language():
    item = {
        "id": "intel--test-genuine-kev",
        "title": "CVE-2026-88888 Critical Remote Code Execution — Actively Exploited",
        "description": "A critical remote code execution vulnerability confirmed in CISA KEV.",
        "severity": "CRITICAL",
        "threat_type": "Vulnerability",
        "feed_source": "cisa_kev",
        "risk_score": 9.8,
        "cve_id": "CVE-2026-88888",
        "kev": True,
        "kev_present": True,
    }
    html = gir.build_report_sections(item)
    assert "IMMEDIATE PATCH REQUIRED" in html


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
