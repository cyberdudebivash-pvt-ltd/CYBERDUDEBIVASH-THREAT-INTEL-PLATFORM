"""Comparison pages and discount claims say only what is true.

The competitor pages (compare.html, alternative-to-mandiant.html,
alternative-to-recorded-future.html) stated things the platform's own data
or the vendors' public documentation contradict -- e.g. "Mandiant: no EPSS"
(Google Threat Intelligence documents EPSS), "YARA and Splunk SPL rules per
IOC" (the feed carries Sigma/KQL/Suricata), estimated competitor prices, a
3-year cost table, "undergoing SOC 2 Type II audit" (the Trust Center says
readiness), STIX import over TAXII (the server only publishes). Several
sales pages, the pricing page's Annual toggle and the checkout page's badge
said annual billing "saves 20%"; pricing-data.json gives 2 months free
(16.7%). These checks keep that from coming back. Local files only.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPARE_PAGES = ("compare.html", "alternative-to-mandiant.html", "alternative-to-recorded-future.html")
PRICING = json.loads((REPO / "workers/intel-gateway/src/pricing-data.json").read_text(encoding="utf-8"))["tiers"]


def _text(page: str) -> str:
    s = (REPO / page).read_text(encoding="utf-8")
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s)))


def _meta(page: str) -> str:
    head = (REPO / page).read_text(encoding="utf-8").split("</head>", 1)[0]
    return html.unescape(" ".join(re.findall(r'content="([^"]*)"', head)))


def test_annual_discount_matches_pricing_data():
    # Every paid tier: annual = 10 x monthly (2 months free, 16.7%).
    for tier, t in PRICING.items():
        assert t["usd_annual"] == 10 * t["usd_monthly"], tier
    bad = re.compile(r"(save|saves|saving|discount)[^.<>]{0,20}\b20\s?%|\b20\s?%[^.<>]{0,20}(annual|discount)", re.I)
    for page in sorted(REPO.glob("*.html")):
        body = page.read_text(encoding="utf-8", errors="replace")
        m = bad.search(body)
        assert not m, f"{page.name}: {m.group(0)!r}"


def test_comparison_pages_carry_no_unverifiable_or_false_claims():
    banned = [
        "$30k", "$50k", "$100k", "$200k", "90–97%", "10–50×", "5–10% of the cost", "<5% FPR",
        "YARA", "Splunk SPL", "SPL rules", "FAIR", "v15", "undergoing SOC 2", "bridge letter", "CNAME",
        "accepts inbound", "No EPSS", "CVSS only", "Not available", "Black box", "second-class",
        "5–10 business days", "2,600+", "74 Live", "Live Feeds", "every 6 hours", "6-Hour", "17-stage",
        "actor attribution", "$39/mo", "$399/mo", "90% of actively exploited", "Saves 4–6 hours",
        "3-Year Total", "Savings vs.",
    ]
    for page in COMPARE_PAGES:
        text = _text(page) + " " + _meta(page)
        for b in banned:
            assert b not in text, f"{page}: {b!r}"
        assert not re.search(r"\best\.", text), f"{page}: estimated price marker"


def test_comparison_pages_state_their_basis():
    for page in COMPARE_PAGES:
        text = _text(page)
        assert "as of September 2026" in text, page
        assert "confirm current terms with" in text, page
    for page in ("alternative-to-mandiant.html", "alternative-to-recorded-future.html"):
        assert "not affiliated with" in _text(page), page


def test_comparison_pages_quote_real_prices_and_quotas():
    for page in COMPARE_PAGES:
        text = _text(page)
        assert "$49" in text and "$499" in text and "$999" in text, page
    mandiant = _text("alternative-to-mandiant.html")
    assert "$415.83/mo billed annually ($4,990/yr)" in mandiant
    assert "$832.50/mo billed annually ($9,990/yr)" in mandiant
    assert "5,000 requests/day (PRO) · 50,000 (Enterprise, MSSP)" in mandiant
    quotas = (REPO / "workers/intel-gateway/src/daily-quota.js").read_text(encoding="utf-8")
    assert re.search(r"PRO:\s*Object\.freeze\(\{ limit: 5000\b", quotas)
    assert re.search(r"ENTERPRISE:\s*Object\.freeze\(\{ limit: 50000\b", quotas)


def test_detection_formats_claimed_are_the_ones_generated():
    reg = (REPO / "workers/intel-gateway/src/detection-registry.js").read_text(encoding="utf-8")
    assert "sigma: 'sigma_rule'" in reg and "kql: 'kql_query'" in reg and "suricata: 'suricata_rule'" in reg
    for page in COMPARE_PAGES:
        assert "Sigma, KQL" in _text(page) and "Suricata" in _text(page), page
