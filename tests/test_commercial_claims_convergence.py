"""Buyer-facing plan terms converge on the contract (R09, 2026-09-30).

config/commercial-contract.json is the single source for per-minute and
per-day limits, API keys, seats, uptime and incident response; sla.html's
tier table is the authority for latency and freshness (the contract's
_sla_authority). Until 2026-09-30 README.md and about twenty deployed pages
quoted other terms: "Unlimited" Enterprise/MSSP calls, FREE 100/day, hourly
limits, 99.95%/99.99% uptime, 5 seats, a 15-minute MSSP response, bcrypt-
hashed and HMAC-signed keys, and a UPI/PayPal manual-payment flow.

scripts/verify_commercial_contract.py sweeps those claim classes across
every buyer page. These tests pin the tables that publish the terms, so a
page cannot drift back with a figure the sweep does not treat as a class
(a per-minute limit of 500, a 4h MSSP response). Local files only.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((REPO / "config/commercial-contract.json").read_text(encoding="utf-8"))["tiers"]
EVIDENCE = json.loads((REPO / "config/platform-evidence.json").read_text(encoding="utf-8"))
ORDER = ("free", "pro", "enterprise", "mssp")
# build_dist_artifact.py ships root pages plus these directories.
DEPLOYED_PAGES = sorted(REPO.glob("*.html")) + sorted((REPO / "dashboard").glob("*.html")) \
    + sorted((REPO / "customer").glob("*.html"))


def _read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def _n(v):
    return f"{v:,}"


def _text(fragment):
    t = re.sub(r"<[^>]+>", " ", fragment)
    for entity, char in (("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "), ("&middot;", "·"), ("&amp;", "&")):
        t = t.replace(entity, char)
    return re.sub(r"\s+", " ", t).strip()


def _visible(html):
    """Page text with table rows kept apart, so one row's last cell never
    reads as the next row's first ("... 100" + "Seats" is not "100 Seats")."""
    t = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    t = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"</tr\s*>", " ¶ ", t, flags=re.I)
    return _text(t)


def _row(html, label):
    """Cells after the label cell of the one <tr> whose first cell is label."""
    rows = [[_text(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", r, flags=re.S)]
            for r in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, flags=re.S)]
    found = [r[1:] for r in rows if r and r[0] == label]
    assert len(found) == 1, f"expected one row labelled {label!r}, found {len(found)}"
    return found[0]


def _markdown_rows(md):
    rows = {}
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows[cells[0]] = cells[1:]
    return rows


def test_readme_tier_table_is_the_contract():
    md = _read("README.md")
    rows = _markdown_rows(md)
    assert rows["API requests / minute"] == [_n(CONTRACT[t]["requests_per_minute"]) for t in ORDER]
    assert rows["API requests / day"] == [_n(CONTRACT[t]["requests_per_day"]) for t in ORDER]
    assert rows["API keys"][0].startswith("—") and CONTRACT["free"]["api_keys"] == 0
    assert rows["API keys"][1:] == [str(CONTRACT[t]["api_keys"]) for t in ORDER[1:]]
    assert rows["Seats"] == [str(CONTRACT[t]["seats"]) for t in ORDER]
    assert [c.lower() for c in rows["Uptime commitment"]] == [CONTRACT[t]["uptime_commitment"] for t in ORDER]
    assert [c.lower() for c in rows["Incident response"]] == [CONTRACT[t]["incident_response"] for t in ORDER]
    assert rows["**Price (USD/mo)**"] == ["Free"] + [f"${_n(CONTRACT[t]['usd_monthly'])}" for t in ORDER[1:]]
    for t, name in (("pro", "PRO"), ("enterprise", "Enterprise"), ("mssp", "MSSP")):
        assert f"{name} ${_n(CONTRACT[t]['usd_annual'])}" in md


def test_sla_table_is_the_contract():
    sla = _read("sla.html")
    assert [c.lower() for c in _row(sla, "Platform Uptime")] == [CONTRACT[t]["uptime_commitment"] for t in ORDER]
    assert [c.lower() for c in _row(sla, "Incident Response")] == [CONTRACT[t]["incident_response"] for t in ORDER]


def test_trust_center_sla_rows_match_the_sla_table():
    sla, tc = _read("sla.html"), _read("trust-center.html")
    assert _row(tc, "API Uptime") == _row(sla, "Platform Uptime")
    assert _row(tc, "Feed Freshness") == _row(sla, "Data Freshness")
    assert _row(tc, "Support SLA") == _row(sla, "Incident Response")
    # Latency is a target, and PRO's is <800ms, not the Enterprise figure.
    assert _row(tc, "API Response P95") == [c if c == "Best effort" else f"{c} target"
                                            for c in _row(sla, "API p95 Latency")]
    assert _row(tc, "Rate Limit") == [f"{_n(CONTRACT[t]['requests_per_minute'])} req/min" for t in ORDER]


def _section(html, heading_id):
    """The <section> labelled by heading_id, so two tables that both have an
    "Enterprise" row are read separately."""
    m = re.search(r'<section\b[^>]*aria-labelledby="%s"[^>]*>(.*?)</section>' % re.escape(heading_id), html, flags=re.S)
    assert m, heading_id
    return m.group(1)


def test_enterprise_compliance_tables_are_the_contract():
    html = _read("enterprise-compliance.html")
    uptime = _section(html, "availability-heading")
    for label, tier in (("PRO", "pro"), ("Enterprise", "enterprise"), ("MSSP / White-Label", "mssp")):
        assert _row(uptime, label) == [CONTRACT[tier]["uptime_commitment"]]
    rates = _section(html, "api-security-heading")
    for label, tier in (("Free", "free"), ("Pro", "pro"), ("Enterprise", "enterprise"), ("MSSP", "mssp")):
        assert _row(rates, label) == [_n(CONTRACT[tier]["requests_per_minute"])]
    assert "sliding window" not in _visible(rates)


def test_api_reference_card_rate_cards_are_the_contract():
    html = _read("api-reference-card.html")
    cards = [(_text(v), _text(u)) for v, u in re.findall(
        r'class="rate-value"[^>]*>(.*?)</div>\s*<div class="rate-unit">(.*?)</div>', html, flags=re.S)]
    assert cards == [(_n(CONTRACT[t]["requests_per_minute"]),
                      f"requests / minute · {_n(CONTRACT[t]['requests_per_day'])} / day") for t in ORDER]
    extras = [_text(e) for e in re.findall(r'class="rate-extra">(.*?)</div>', html, flags=re.S)]
    assert "No SLA" in extras[0]
    for extra, tier in zip(extras[1:], ORDER[1:]):
        assert f"{CONTRACT[tier]['uptime_commitment']} SLA" in extra
    assert "Dedicated" not in extras[2], "dedicated support is the MSSP plan, not Enterprise"


def test_developer_portal_rate_table_is_the_contract():
    html = _read("developer-portal.html")
    for label, tier in (("Free", "free"), ("Professional", "pro"), ("Enterprise", "enterprise"), ("MSSP", "mssp")):
        assert _row(html, label) == [_n(CONTRACT[tier]["requests_per_day"]),
                                     _n(CONTRACT[tier]["requests_per_minute"]), "api-docs.html"]


def test_trial_center_daily_row_and_seat_answer_are_the_contract():
    html = _read("trial-center.html")
    assert _row(html, "API requests/day") == [_n(CONTRACT[t]["requests_per_day"]) for t in ORDER]
    text = _visible(html)
    assert (f"1 on FREE and PRO, {CONTRACT['enterprise']['seats']} on Enterprise and "
            f"{CONTRACT['mssp']['seats']} on MSSP") in text


def test_deployed_pages_quote_only_contract_rate_figures():
    per_minute = {CONTRACT[t]["requests_per_minute"] for t in ORDER}
    per_day = {CONTRACT[t]["requests_per_day"] for t in ORDER}
    lead = r"(?<![\d,.])([\d,]+)\s*(?:API\s+)?"
    patterns = (
        (re.compile(lead + r"(?:req(?:uest)?s?|calls)?\s*(?:/\s*|\s+per\s+)min(?:ute)?\b", re.I), per_minute),
        (re.compile(lead + r"(?:req(?:uest)?s?|calls|queries)?\s*(?:/\s*|\s+per\s+)day\b", re.I), per_day),
        (re.compile(lead + r"req(?:uest)?s?\s*(?:/\s*|\s+per\s+)(?:hr|hour)\b", re.I), set()),
    )
    hits = []
    for page in DEPLOYED_PAGES:
        text = _visible(page.read_text(encoding="utf-8", errors="replace"))
        for pattern, allowed in patterns:
            for m in pattern.finditer(text):
                if int(m.group(1).replace(",", "")) not in allowed:
                    hits.append(f"{page.relative_to(REPO)}: ...{text[max(0, m.start() - 50):m.end() + 10]}...")
    assert not hits, "\n".join(hits)


def test_security_page_describes_the_key_handling_the_gateway_implements():
    index_js = _read("workers/intel-gateway/src/index.js")
    text = _visible(_read("security-compliance.html"))
    # Keys: 20 random bytes (160 bits), stored as the raw record, rotation
    # revokes the old key at once.
    assert "new Uint8Array(20)" in index_js and "160-bit random" in text
    assert "old_key_revoked: true" in index_js and "revokes the old one immediately" in text
    assert "IP allowlisting: not currently offered" in text
    # Audit entries live AUDIT_TTL seconds (30 days) for every plan.
    assert re.search(r"const AUDIT_TTL\s*=\s*86400 \* 30;", index_js)
    assert "90-day" not in text and _row(_read("security-compliance.html"), "Audit logs (privileged actions)")[1:3] == ["30 days", "30 days"]
    for claim in ("bcrypt", "HMAC-SHA256 signed API key", "IP allowlisting for Enterprise", "IP CIDR",
                  "24h grace", "Per-key scope restrictions", "zero-downtime key rotation",
                  "MFA enforced", "MFA is enforced", "TLS 1.3 minimum", "Content Security Policy Level 3",
                  "Subresource Integrity on all", "sliding window", "PayPal"):
        assert claim.lower() not in text.lower(), claim


def test_api_docs_rate_limit_headers_match_the_gateway():
    index_js = _read("workers/intel-gateway/src/index.js")
    text = _visible(_read("api-docs.html"))
    # The gateway sets X-RateLimit-* in exactly one place: its 429 answer.
    sites = [m.start() for m in re.finditer(r'"X-RateLimit-Limit":', index_js)]
    assert len(sites) == 1 and "429" in index_js[max(0, sites[0] - 1500):sites[0]]
    assert "Successful responses do not carry rate-limit headers" in text
    assert "included in every response" not in text


def test_no_deployed_page_routes_payment_outside_razorpay_and_gumroad():
    # paypal.me links and raw UPI handles are the retired manual-payment
    # channel (render-test/verify_admin_commercial_readiness.js).
    retired = re.compile(r"paypal\.me/|\b[\w.-]+@(?:upi|ybl|okaxis|oksbi|okhdfcbank|okicici|paytm|ibl|axl)\b"
                         r"|choose\s+upi\s+or\s+paypal|submit\s+confirmation\s+form", re.I)
    hits = []
    for page in DEPLOYED_PAGES:
        src = re.sub(r"<!--.*?-->", " ", page.read_text(encoding="utf-8", errors="replace"), flags=re.S)
        hits += [f"{page.relative_to(REPO)}: {m.group(0)}" for m in retired.finditer(src)]
    assert not hits, "\n".join(hits)


def test_user_test_kit_quotes_contract_prices_and_checkout():
    text = _visible(_read("user-test-kit.html"))
    assert f"${CONTRACT['pro']['usd_monthly']}/month" in text.replace(" /month", "/month")
    assert f"${CONTRACT['enterprise']['usd_monthly']}/month" in text.replace(" /month", "/month")
    assert "Custom" not in re.findall(r"ENTERPRISE (\S+)", text)
    assert "Razorpay" in text and "Gumroad" in text


def test_published_evidence_floors_never_exceed_the_measured_values():
    floors = (
        (re.compile(r"(?<![\d,.])([\d,.]+)(K?)\+\s+(?:STIX\s+2\.1\s+)?bundles\b", re.I), "stix_bundles"),
        (re.compile(r"(?<![\d,.])([\d,.]+)(K?)\+\s+(?:published\s+|intelligence\s+)+reports\b", re.I),
         "published_intelligence_reports"),
    )
    quoted = {}
    for page in DEPLOYED_PAGES:
        text = _visible(page.read_text(encoding="utf-8", errors="replace"))
        for pattern, key in floors:
            for m in pattern.finditer(text):
                value = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
                assert value <= EVIDENCE[key], f"{page.name}: '{m.group(0)}' exceeds measured {key}={EVIDENCE[key]}"
                quoted.setdefault(page.name, set()).add(key)
    # The evidence blocks that replaced testimonials cite these floors.
    for name in ("demo.html", "enterprise.html", "mssp.html", "global-deployment.html"):
        assert "stix_bundles" in quoted.get(name, set()), name
