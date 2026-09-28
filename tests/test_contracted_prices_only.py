"""
tests/test_contracted_prices_only.py

Pre-release pricing sweep (2026-09-28). config/commercial-contract.json is the
one authoritative plan contract; scripts/verify_commercial_contract.py already
pins pricing.html and the config/runtime tables to it. This file covers the
buyer pages that sweep found quoting plans, prices and quotas the platform
does not sell:

- upgrade.html re-priced the displayed plan from ?kit=X&amount=Y ("$149
  one-time") while checkout created the recurring subscription for the mapped
  tier at its contracted price ($499/month). A URL must never set a price.
- cyber-kits.html sold one-time kits nothing could check out or deliver; it is
  now a redirect.
- index.html sold four feeds at $79-$149/month with checkout links to plans
  checkout does not know (resolveCheckoutPlan fails closed to FREE).
- store.html's plan cards and comparison table invented a "Team $149/mo" tier,
  "Unlimited" API cells, per-month quotas and a $149/month AI feed the
  contract includes at no extra price.
- enterprise.html showed an uncontracted "Business $899/mo" tier.
- enterprise-procurement-pack.html quoted $39 / $399 per month annual.
- admin.html computed MRR at $29 / $199.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((REPO / "config" / "commercial-contract.json").read_text(encoding="utf-8"))
TIERS = CONTRACT["tiers"]
AI_FEED = CONTRACT["features"]["ai_threat_feed"]["entitlements"]
PAID = ("pro", "enterprise", "mssp")

# The plans upgrade.html's resolveCheckoutPlan() accepts (plus its alias).
CHECKOUT_PLANS = {"free", "pro", "enterprise", "mssp", "community"}


def _text(page):
    # HTML comments are dropped: the sweep notes on each page quote the
    # retired values on purpose; the rendered page must not.
    html = (REPO / page).read_text(encoding="utf-8")
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def _usd(v):
    return "${:,}".format(v)


def _root_pages():
    return sorted(p.name for p in REPO.glob("*.html"))


# ── Checkout links ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("page", _root_pages())
def test_checkout_links_name_a_plan_checkout_sells(page):
    html = _text(page)
    bad = []
    for plan in re.findall(r"upgrade\.html\?[^\"'\s>]*?\bplan=([A-Za-z0-9_-]+)", html):
        p = plan.lower()
        if p.endswith("-annual"):
            p = p[: -len("-annual")]
        if p not in CHECKOUT_PLANS:
            bad.append(plan)
    assert bad == [], f"checkout links to plans checkout does not sell (they fall back to FREE): {bad}"


@pytest.mark.parametrize("page", _root_pages())
def test_no_page_prices_checkout_from_the_url(page):
    assert not re.search(r"upgrade\.html\?[^\"'\s>]*\bamount=", _text(page)), \
        "a link passes a price to checkout in the URL"


def test_upgrade_page_never_reads_a_price_from_the_url():
    html = _text("upgrade.html")
    assert "params.get('amount')" not in html and 'params.get("amount")' not in html
    assert "KIT_MAP" not in html
    # The plan still resolves through the fail-closed allowlist.
    assert "var resolvedPlan = resolveCheckoutPlan(params);" in html


def test_kits_page_is_a_redirect_to_the_store():
    html = _text("cyber-kits.html")
    assert "window.location.replace('/store.html'" in html
    assert 'content="0; url=/store.html"' in html
    assert "noindex" in html
    assert len(html) < 4000, "a redirect page carries no offer content"
    assert not re.search(r"upgrade\.html\?kit=", html)


# ── Homepage offer cards ────────────────────────────────────────────────────

def test_homepage_feed_cards_quote_the_pro_plan():
    html = _text("index.html")
    for price in ("$79", "$99", "$129", "$149"):
        assert not re.search(re.escape(price) + r"(?:<[^>]+>|\s)*(?:/mo\b|/month)", html), \
            f"homepage quotes an uncontracted {price} monthly price"
    assert html.count("INCLUDED WITH PRO") >= 4
    assert "plan=ai-prompt-feed" not in html and "plan=ai-supply-chain" not in html


# ── store.html ──────────────────────────────────────────────────────────────

def _compare_table():
    html = _text("store.html")
    return html[html.index('<table class="compare-table">'): html.index("</table>", html.index('<table class="compare-table">'))]


def _row(table, label):
    m = re.search(r'<td class="col-feature">' + re.escape(label) + r"</td>(.*?)</tr>", table)
    assert m, f"comparison row missing: {label}"
    return [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1))]


def test_store_comparison_table_is_the_contract():
    table = _compare_table()
    order = ("free", "pro", "enterprise", "mssp")
    assert _row(table, "Monthly") == ["$0"] + [_usd(TIERS[k]["usd_monthly"]) + "/mo" for k in PAID]
    assert _row(table, "Annual")[1:] == [_usd(TIERS[k]["usd_annual"]) + "/yr" for k in PAID]
    assert _row(table, "API requests / day") == ["{:,}".format(TIERS[k]["requests_per_day"]) for k in order]
    assert _row(table, "API requests / minute") == ["{:,}".format(TIERS[k]["requests_per_minute"]) for k in order]
    assert _row(table, "Seats") == ["{:,}".format(TIERS[k]["seats"]) for k in order]
    assert _row(table, "Items") == [str(AI_FEED[k]["items"]) for k in order]
    assert _row(table, "Support") == [TIERS[k]["support"] for k in order]
    assert _row(table, "Uptime commitment") == [TIERS[k]["uptime_commitment"] for k in order]
    assert _row(table, "P0 outage credit") == [TIERS[k]["p0_outage_credit"] for k in order]


def test_store_has_no_uncontracted_tier_or_unlimited_quota():
    html = _text("store.html")
    assert not re.search(r"Team\s*\$", html), "uncontracted Team tier"
    table = _compare_table()
    assert "Unlimited" not in table and "add-on" not in table and "/each" not in table


def test_store_plan_cards_quote_contracted_quotas():
    html = _text("store.html")
    row = html[html.index('<div class="api-tier-row">'): html.index('<div class="cta-banner banner-api"')]
    for k in PAID:
        t = TIERS[k]
        assert _usd(t["usd_annual"]) + "/yr" in row
        assert "{:,} API requests/day &middot; {:,}/min".format(t["requests_per_day"], t["requests_per_minute"]) in row
        assert "{} API keys &middot; {} seat".format(t["api_keys"], t["seats"]) in row
    assert "Unlimited" not in row and "requests/month" not in row
    assert "Custom</div>" not in row, "MSSP is a contracted price, not 'Custom'"


def test_store_ai_feed_is_included_not_sold_separately():
    # Contract: "Included with the existing plans; no separate price and no
    # second invoice."
    html = _text("store.html")
    card = html[html.index('<div class="product-name">AI/LLM Threat Intel Feed</div>'):]
    card = card[: card.index("</a>")]
    assert "Included" in card
    assert not re.search(r"\$</span>\s*\d", card), "AI feed carries a separate price"


def test_store_bundle_values_pro_at_the_annual_price():
    html = _text("store.html")
    assert "worth $588" not in html
    assert "1-year Pro API subscription (worth {})".format(_usd(TIERS["pro"]["usd_annual"])) in html


# ── enterprise.html ─────────────────────────────────────────────────────────

def test_enterprise_tier_grid_is_the_contract():
    html = _text("enterprise.html")
    grid = html[html.index('<div class="tier-grid">'): html.index('<div class="final-cta">')]
    assert "$899" not in html and "10,788" not in html, "uncontracted Business tier"
    for k in PAID:
        t = TIERS[k]
        assert '<div class="tier-price">{}<span>/mo</span></div>'.format(_usd(t["usd_monthly"])) in grid
        assert "or {}/yr billed annually".format(_usd(t["usd_annual"])) in grid
        assert "{:,} API requests/day · {:,}/min".format(t["requests_per_day"], t["requests_per_minute"]) in grid
        assert t["support"].rstrip(".") in grid
        assert "{} uptime commitment".format(t["uptime_commitment"]) in grid
    assert grid.count("White-label deployment</li>") == 3
    assert grid.count('<span class="check">✓</span> White-label deployment') == \
        sum(1 for k in PAID if TIERS[k]["white_label"])


# ── enterprise-procurement-pack.html ────────────────────────────────────────

def test_procurement_pack_annual_prices_are_the_contract():
    html = _text("enterprise-procurement-pack.html")
    assert "$39/mo annual" not in html and "$399/mo annual" not in html
    for k in PAID:
        t = TIERS[k]
        assert "{}/mo or {}/yr".format(_usd(t["usd_monthly"]), _usd(t["usd_annual"])) in html


# ── admin.html (operator revenue tracker) ───────────────────────────────────

def test_admin_mrr_uses_contracted_prices():
    html = _text("admin.html")
    assert "const mrr = proSeats * {} + entSeats * {};".format(
        TIERS["pro"]["usd_monthly"], TIERS["enterprise"]["usd_monthly"]) in html
    assert "$29/mo" not in html and "$199/mo" not in html


# ── No uncontracted discounts (owner decision 2026-09-28) ───────────────────

@pytest.mark.parametrize("page", _root_pages())
def test_no_student_or_researcher_discount(page):
    # The contract has no discount and checkout cannot apply one.
    html = _text(page)
    assert not re.search(r"student[^<]{0,80}(?:discount|% off)|(?:discount|% off)[^<]{0,80}student", html, re.I), \
        "page offers an uncontracted student/researcher discount"


# ── Keyless Free tier (owner decision 2026-09-28) ───────────────────────────
# commercial-contract.json grants FREE "api_keys": 0; both free-key routes
# answer 410 (pinned by verify_commercial_contract.py C64+ and the gateway's
# commercial-contract-runtime.test.js). No page may request or promise one.

FREE_KEY_ROUTES = ("/api/keys/free", "/api/apikeys/request-free")


def test_contract_free_tier_is_keyless():
    assert TIERS["free"]["api_keys"] == 0


@pytest.mark.parametrize("page", _root_pages())
def test_no_page_requests_a_free_key(page):
    html = _text(page)
    for route in FREE_KEY_ROUTES:
        assert not re.search(r"fetch\([^)]*" + re.escape(route), html), f"page calls the retired {route}"


@pytest.mark.parametrize("page", _root_pages())
def test_no_page_promises_a_free_key(page):
    visible = re.sub(r"<script\b.*?</script>", "", _text(page), flags=re.S | re.I)
    assert not re.search(r"free\s+(?:api\s+)?key|free\s+account", visible, re.I), \
        "page offers a free API key or account; the Free tier is keyless"


def test_signup_page_shows_keyless_free_start():
    html = _text("get-api-key.html")
    assert 'id="free-keyless-panel"' in html
    assert "30 requests/minute and 50/day" in html
    assert "showInstantKey" not in html and "instant-key-box" not in html
    # Community resolves to the keyless panel, never a key request.
    assert "document.getElementById('free-keyless-panel').style.display = keyless ? 'block' : 'none';" in html


def test_signup_page_quotes_contracted_paid_quotas():
    html = _text("get-api-key.html")
    assert "10,000 req/month" not in html and "calls/day/day" not in html
    assert "5,000 requests/day, 120/min, 10 API keys" in html
    assert "50,000 API requests/day, 600/min, 50 API keys" in html
