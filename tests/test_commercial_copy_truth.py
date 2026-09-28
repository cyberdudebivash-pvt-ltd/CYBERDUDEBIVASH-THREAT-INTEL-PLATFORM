"""Commercial copy truth (P0 go-live, 2026-09-25).

Public manual payment proof is retired (docs/COMMERCIAL_POLICY_V1.md): no
customer page may ask for a payment screenshot, a UPI/NEFT/crypto proof or a
transaction hash, publish crypto addresses, promise "instant" or manual
activation, or claim a SOC 2 / ISO 27001 certification the platform does not
hold (config/commercial-contract.json: _attestation_status).
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PUBLIC_PAGES = sorted(p for p in REPO.glob("*.html"))

FORBIDDEN = [
    (r"payment\s+screenshot", "asks for a payment screenshot"),
    (r"send\s+(us\s+)?(the\s+|your\s+)?(payment|transaction)\s+(screenshot|proof)", "asks for payment proof"),
    (r"(upi|neft|imps|bank)\s+(payment\s+)?proof(?!s are not accepted)", "asks for UPI/NEFT/bank proof"),
    (r"transaction\s+hash\s+to\s+verify", "crypto transaction verification"),
    (r"/api/payment/verify-bsc", "calls the non-existent crypto verifier"),
    (r"\bbc1q[0-9a-z]{6,}|\bT[1-9A-HJ-NP-Za-km-z]{33}\b", "publishes a crypto address"),
    (r"manual\s+activation", "promises manual activation"),
    (r"instant\s+activation(?!, valid for 1 year)", "promises instant activation of a paid plan"),
    (r"(soc\s*2|iso\s*27001)[^.<]{0,20}\bcertified\b", "claims a certification"),
]


def _visible(src: str) -> str:
    src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)
    return src


def test_public_pages_exist():
    assert len(PUBLIC_PAGES) > 50


def test_checkout_does_not_invent_customer_counts_or_ratings():
    text = _visible((REPO / "upgrade.html").read_text(encoding="utf-8"))
    assert not re.search(r"\d[\d,.]*\+?\s+active teams|avg rating", text, re.I)


def test_no_retired_manual_payment_or_overclaim_copy_on_public_pages():
    hits = []
    for page in PUBLIC_PAGES:
        text = _visible(page.read_text(encoding="utf-8", errors="replace"))
        for pattern, why in FORBIDDEN:
            for m in re.finditer(pattern, text, flags=re.I):
                ctx = text[max(0, m.start() - 40):m.end() + 2].lower()
                # "aligned, not certified" and "Are you ... certified?" are the
                # honest disclaimer and an FAQ question, not a claim.
                if why == "claims a certification" and ("not certified" in ctx or text[m.end():m.end() + 1] == "?"):
                    continue
                hits.append(f"{page.name}: {why}: ...{text[max(0, m.start()-40):m.end()+40]!r}...")
    assert not hits, "\n".join(hits)


def test_checkout_support_wording_is_sales_and_checkout_support():
    upgrade = (REPO / "upgrade.html").read_text(encoding="utf-8")
    assert "Sales &amp; checkout support" in upgrade
    assert "API access activates automatically after payment confirmation" in upgrade


def test_recurring_checkout_never_calls_one_time_orders():
    # Stage 24: PRO / Enterprise / MSSP are subscription-only.
    upgrade = (REPO / "upgrade.html").read_text(encoding="utf-8")
    assert "/api/payment/razorpay/create-order" not in upgrade
    assert "/api/payment/razorpay/verify" not in upgrade
    assert "/api/v2/billing/subscriptions/create" in upgrade


def test_api_docs_rate_limits_match_canonical_commercial_contract():
    """Buyer-facing API quotas must equal the enforced gateway contract."""
    import json

    contract = json.loads((REPO / "config/commercial-contract.json").read_text(encoding="utf-8"))
    docs = _visible((REPO / "api-docs.html").read_text(encoding="utf-8"))

    expected = {
        "Free": ("free", "Public endpoints only"),
        "Professional": ("pro", "All endpoints"),
        "Enterprise": ("enterprise", "All endpoints + SIEM"),
        "MSSP": ("mssp", "All + Multi-tenant"),
    }
    for label, (tier_id, endpoint_copy) in expected.items():
        tier = contract["tiers"][tier_id]
        daily = f'{tier["requests_per_day"]:,}'
        per_min = f'{tier["requests_per_minute"]:,}'
        pattern = (
            rf"<td>{re.escape(label)}\b.*?</td>"
            rf"<td>{re.escape(daily)}</td>"
            rf"<td>{re.escape(per_min)}</td>"
            rf"<td>{re.escape(endpoint_copy)}</td>"
            rf"<td>HTTP 429</td>"
        )
        assert re.search(pattern, docs, re.I | re.S), (
            f"{label} API docs quota drift: expected "
            f"{daily}/day and {per_min}/minute from commercial-contract.json"
        )

    assert not re.search(r"<td>Unlimited</td>", docs, re.I)


def test_pricing_structured_data_does_not_publish_unlimited_api_access():
    pricing = _visible((REPO / "pricing.html").read_text(encoding="utf-8"))
    assert "unlimited access, 15-min SLA" not in pricing
    assert "50,000 API calls/day, 1,200 requests/minute" in pricing


def test_homepage_does_not_restore_withdrawn_social_proof_or_market_superlatives():
    """Evidence-register withdrawals must stay withdrawn on the main sales surface."""
    text = _visible((REPO / "index.html").read_text(encoding="utf-8"))

    forbidden = [
        (r"join\s+1[,.]?200\+\s+soc\s+analysts", "unverified subscriber/analyst count"),
        (r"(deployed|used)\s+by\s+500\+\s+security\s+teams", "unverified customer/team count"),
        (r"what\s+analysts\s+say", "unaudited testimonial section"),
        (r"mid-market\s+fintech,\s*india", "unaudited customer attribution"),
        (r"enterprise\s+mssp,\s*global", "unaudited customer attribution"),
        (r"security\s+consultancy,\s*apac", "unaudited customer attribution"),
        (r"the\s+only\s+ai-native\s+threat\s+intelligence\s+platform", "unsupported market superlative"),
        (r"updated\s+every\s+15\s+minutes\s+from\s+50\+\s+sources", "unverified fixed source/cadence claim"),
    ]
    hits = [why for pattern, why in forbidden if re.search(pattern, text, re.I)]
    assert not hits, "homepage restored withdrawn/unverified claims: " + ", ".join(hits)


def test_evidence_register_still_marks_customer_social_proof_unverified():
    register = (REPO / "config/evidence-register.json").read_text(encoding="utf-8")
    assert '"claim": "Verified / professional / analyst / team head-counts"' in register
    assert '"classification": "UNVERIFIED"' in register
    assert "No replacement quotes were written" in register
