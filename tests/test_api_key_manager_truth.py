"""
tests/test_api_key_manager_truth.py

The customer API console (api-key-manager.html), 2026-09-26. Rendered against
production, most of it did not work or was invented:
  - Keys / Usage tabs called GET /api/account/usage, which did not exist, so
    every signed-in customer saw "Authentication required";
  - "Create key" and "Revoke" called /api/keys/create and DELETE /api/keys/:id,
    and the Webhooks tab /api/webhooks/siem -- none of which exist;
  - Usage charts plotted Math.random() "history" and "latency", a fixed
    endpoint mix and a hardcoded "~38ms" latency;
  - the Quota tab listed 60/500/2,000 requests per minute (the Worker enforces
    30/120/600), a per-tier "API keys" allowance and "feed items per request"
    caps that do not exist;
  - Billing showed $0 for a PRO customer (upper-case tier looked up in a
    lower-case price table).

Now the Worker serves GET /api/account/usage (account-usage.js), key issuance
is explained instead of faked, webhooks use the alert engine, and the numbers
come from the Worker's own limits. These tests keep it that way.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGE = (REPO / "api-key-manager.html").read_text(encoding="utf-8")
WORKER = (REPO / "workers" / "intel-gateway" / "src" / "index.js").read_text(encoding="utf-8")
QUOTA = (REPO / "workers" / "intel-gateway" / "src" / "daily-quota.js").read_text(encoding="utf-8")


def _page_api_paths():
    return sorted(set(re.findall(r"apiFetch\(\s*[`'\"]([^`'\"?$]+)", PAGE)))


def test_every_console_call_is_a_worker_route():
    paths = _page_api_paths()
    assert "/api/account/usage" in paths
    missing = [p for p in paths if f'"{p}"' not in WORKER]
    assert missing == [], f"console calls routes the Worker does not serve: {missing}"


def test_calls_to_routes_that_never_existed_are_gone():
    for dead in ("/api/keys/create", "/api/webhooks/siem", "/api/keys/${"):
        assert dead not in PAGE, dead


def test_no_fabricated_metrics():
    assert "Math.random" not in PAGE
    assert "~38ms" not in PAGE
    assert "_generate_synthetic_history" not in PAGE and "_generate_latency_history" not in PAGE


def _worker_rate_limits():
    m = re.search(r"const RATE_LIMITS = \{ FREE: (\d+), PRO: (\d+), ENTERPRISE: (\d+)", WORKER)
    assert m, "RATE_LIMITS not found"
    return [int(x) for x in m.groups()]


def _worker_daily_quotas():
    out = []
    for tier in ("FREE", "PRO", "ENTERPRISE"):
        m = re.search(tier + r":\s*Object\.freeze\(\{ limit: (\d+)", QUOTA)
        assert m, tier
        out.append(int(m.group(1)))
    return out


def _quota_row(label):
    row = re.search(r"<tr><td>" + re.escape(label) + r"</td>(.*?)</tr>", PAGE)
    assert row, label
    return [int(c.replace(",", "")) for c in re.findall(r">([\d,]+)</td>", row.group(1))]


def test_quota_tab_matches_the_limits_the_worker_enforces():
    assert _quota_row("Requests/minute") == _worker_rate_limits()
    assert _quota_row("Requests per UTC day") == _worker_daily_quotas()
    assert "Feed items/request" not in PAGE
    assert "<td>API keys</td>" not in PAGE


def test_get_a_key_copy_matches_daily_quotas():
    free, pro, ent = _worker_daily_quotas()
    assert f"{free} requests per UTC day" in PAGE
    assert f"Pro: {pro:,} requests per day" in PAGE
    assert f"Enterprise and MSSP: {ent:,}" in PAGE


def test_billing_lookup_is_case_safe():
    assert "TIER_COST[tier]" in PAGE and "const tier = String(data.tier || 'FREE').toLowerCase();" in PAGE
    assert "TIER_COST[data.tier]" not in PAGE


def test_webhooks_use_the_alert_engine_and_promise_no_unbuilt_formats():
    assert "channel: 'webhook'" in PAGE
    for claim in ("wh_format", "wh_secret", "HMAC signing secret", "LEEF"):
        assert claim not in PAGE, claim


def test_linked_pages_exist():
    for page in ("get-api-key.html", "upgrade.html"):
        assert (REPO / page).is_file()
        assert f'href="{page}"' in PAGE
