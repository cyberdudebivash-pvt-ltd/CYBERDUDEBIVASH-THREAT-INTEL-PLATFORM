"""Buyer pages state the platform's real compliance and renewal status.

config/commercial-contract.json records "_attestation_status":
"not_currently_independently_attested"; compliance.html and trust-center.html
describe SOC 2 / ISO 27001 *readiness*. Pre-release sweep (2026-09-28) found
other pages contradicting that and each other: "SOC 2 Type II audit
commenced Q1 2026 ... report expected Q3 2026" with 70-80% progress bars,
"audit initiated ... report expected Q4 2026", "audit in progress (Q3 2026)",
offers of a SOC 2 "bridge letter" (which only extends an existing SOC 2
report) and "interim controls attestation", ATT&CK and STIX/TAXII labelled
"CERTIFIED" (neither has a certification programme), and "No auto-renewal"
next to Razorpay subscriptions that renew until cancelled. These checks keep
that from coming back. Checked per visible text node (HTML comments, scripts
and styles removed), like scripts/verify_public_claims.py. Local files only.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PAGES = sorted([p.relative_to(REPO).as_posix() for p in REPO.glob("*.html")] +
               [p.relative_to(REPO).as_posix() for p in (REPO / "sales").glob("*.html")])

FALSE_STATUS = [
    (r"bridge\s+letter", "a SOC 2 bridge letter requires an existing SOC 2 report"),
    (r"\baudit\s+(?:commenced|initiated|underway|in\s+progress)\b", "no audit engagement has started"),
    (r"undergoing\s+(?:a\s+)?soc\s?2", "no audit engagement has started"),
    (r"report\s+expected\s+q[1-4]", "no audit report is scheduled against an engagement"),
    (r"interim\s+controls\s+attestation", "the platform is not independently attested"),
    (r"soc\s?2\s+audit\s+trail\s+enabled", "an audit log is not a SOC 2 attribute"),
]
CERTIFIED_STANDARD = re.compile(r"(?:ATT&CK|STIX|TAXII)[^<]{0,40}</div>\s*<div[^>]*>\s*●?\s*CERTIFIED", re.I)
HELD_CERT = re.compile(r"\b(?:SOC\s?2|ISO\s?27001|ISO\s?42001|FedRAMP|PCI[\s-]DSS)\b[^.?]{0,25}\b(?:certified|compliant|attested)\b", re.I)
NEGATION = re.compile(r"\b(?:not|no|never|nor|without)\b|n't", re.I)


def _nodes(page):
    raw = (REPO / page).read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>", " ", raw, flags=re.S | re.I)
    metas = re.findall(r'<meta[^>]+content="([^"]*)"', raw, re.I)
    nodes = [" ".join(html.unescape(n).split()) for n in re.split(r"<[^>]+>", raw)] + [html.unescape(m) for m in metas]
    return raw, [n for n in nodes if n]


@pytest.mark.parametrize("page", PAGES)
def test_no_false_audit_status(page):
    _, nodes = _nodes(page)
    hits = [(why, n[:120]) for n in nodes for pat, why in FALSE_STATUS if re.search(pat, n, re.I)]
    assert not hits, f"{page}: {hits}"


@pytest.mark.parametrize("page", PAGES)
def test_no_held_certification_claim(page):
    # A question ("Are you SOC 2 or ISO 27001 certified?") or a negated
    # statement in the same text node is honest; a bare claim is not.
    _, nodes = _nodes(page)
    hits = [n[:120] for n in nodes if HELD_CERT.search(n) and not NEGATION.search(n) and not n.rstrip().endswith("?")]
    assert not hits, f"{page}: {hits}"


@pytest.mark.parametrize("page", PAGES)
def test_open_standards_are_not_labelled_certified(page):
    raw, _ = _nodes(page)
    m = CERTIFIED_STANDARD.search(raw)
    assert not m, f"{page}: {m.group(0)[:120]!r}"


@pytest.mark.parametrize("page", PAGES)
def test_no_auto_renew_only_for_the_gumroad_grant(page):
    # Razorpay subscriptions renew until cancelled; only the Gumroad access
    # grant does not auto-renew, so the claim must name the grant.
    _, nodes = _nodes(page)
    hits = [n[:120] for n in nodes if re.search(r"no\s+auto-?renew", n, re.I) and not re.search(r"grant|gumroad", n, re.I)]
    assert not hits, f"{page}: {hits}"


@pytest.mark.parametrize("page", ["security-compliance.html", "enterprise-procurement-pack.html", "executive-briefing.html"])
def test_procurement_pages_state_not_attested(page):
    _, nodes = _nodes(page)
    assert any(re.search(r"not (?:independently )?attested", n, re.I) for n in nodes), page


def test_no_invented_audit_progress_bars():
    raw, _ = _nodes("security-compliance.html")
    assert 'class="soc2-bar"' not in raw
    assert not re.search(r"—\s*\d{2}%</div>", raw)
