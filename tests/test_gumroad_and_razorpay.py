"""
Regression tests for the Razorpay + Gumroad dual-checkout system.

The live Razorpay/Gumroad checkout implementation lives in
workers/intel-gateway/src/index.js (handleWebhookGumroad, handleWebhookRazorpay,
provisionApiKey) and upgrade.html (the single checkout page for both
gateways) -- see workers/intel-gateway/src/gumroad-lifecycle.js's header
comment for why this is one system, not a second parallel one.

Two test styles, matching this repo's existing conventions:

  1. Real-execution style -- subprocess-runs the actual Node unit test file
     (gumroad-lifecycle.test.js) and the actual monetization CI gate
     (scripts/validate_monetization.py), asserting they pass. This reuses
     those checks rather than re-deriving them in Python (Principle 4).
  2. Static-analysis style (tests/test_enterprise_pricing.py,
     tests/test_developer_portal.py convention) -- regex/string assertions
     against the real source files for wiring this repo's Node ESM loader
     can't otherwise unit-test (KV writes, ctx.waitUntil, the Workers
     runtime), and against the frontend pages for the required markers.

Run with: pytest tests/test_gumroad_and_razorpay.py -v
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATEWAY_SRC = REPO_ROOT / "workers" / "intel-gateway" / "src" / "index.js"
GUMROAD_LIFECYCLE_SRC = REPO_ROOT / "workers" / "intel-gateway" / "src" / "gumroad-lifecycle.js"
GUMROAD_LIFECYCLE_TEST = REPO_ROOT / "workers" / "intel-gateway" / "src" / "__tests__" / "gumroad-lifecycle.test.js"
VALIDATE_MONETIZATION = REPO_ROOT / "scripts" / "validate_monetization.py"
INDEX_HTML = REPO_ROOT / "index.html"
UPGRADE_HTML = REPO_ROOT / "upgrade.html"
WELCOME_HTML = REPO_ROOT / "welcome.html"


def _node_available() -> bool:
    try:
        return subprocess.run(["node", "--version"], capture_output=True, timeout=5).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _html_references_host(html_text: str, host: str) -> bool:
    """True if any src=/href= URL in the page has `host` as its exact
    hostname (or a subdomain of it). Deliberately does not use a raw
    `host in html_text` substring check: that form is flagged by CodeQL
    (py/incomplete-url-substring-sanitization) because it doesn't verify
    the domain's position -- "evil.com/checkout.razorpay.com" would also
    match. Parsing each URL and comparing the hostname is the precise
    check the query recommends instead.
    """
    for url in re.findall(r'(?:src|href)=["\']([^"\']+)["\']', html_text):
        hostname = urlsplit(url).hostname or ""
        if hostname == host or hostname.endswith("." + host):
            return True
    return False


needs_node = pytest.mark.skipif(not _node_available(), reason="node not available in this environment")


def _extract_function(src: str, name: str) -> str:
    """Extract one top-level `async function <name>(...) { ... }` body,
    matching the pattern already used by scripts/validate_monetization.py's
    validate_worker_api_auth_enforcement() for the same purpose.
    """
    match = re.search(
        rf"async function {re.escape(name)}\s*\(.*?\)\s*\{{(.*?)(?=\n(?:async function|export default))",
        src, re.DOTALL,
    )
    assert match, f"could not locate async function {name}() in {GATEWAY_SRC.name}"
    return match.group(1)


@pytest.fixture(scope="module")
def gateway_src() -> str:
    assert GATEWAY_SRC.exists(), f"{GATEWAY_SRC} not found"
    return GATEWAY_SRC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gumroad_webhook_body(gateway_src: str) -> str:
    return _extract_function(gateway_src, "handleWebhookGumroad")


@pytest.fixture(scope="module")
def gumroad_lifecycle_src() -> str:
    assert GUMROAD_LIFECYCLE_SRC.exists(), f"{GUMROAD_LIFECYCLE_SRC} not found"
    return GUMROAD_LIFECYCLE_SRC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Real-execution: the actual Node unit tests and the actual CI gate
# ---------------------------------------------------------------------------

@needs_node
def test_gumroad_lifecycle_node_unit_tests_pass():
    assert GUMROAD_LIFECYCLE_TEST.exists(), f"{GUMROAD_LIFECYCLE_TEST} not found"
    result = subprocess.run(
        ["node", "--test", str(GUMROAD_LIFECYCLE_TEST)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"gumroad-lifecycle.test.js failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_monetization_integrity_gate_passes():
    """Reuses the real, already-live CI gate rather than re-deriving its
    Razorpay/Gumroad marker and manual-payment-absence checks here."""
    result = subprocess.run(
        [sys.executable, str(VALIDATE_MONETIZATION)],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"validate_monetization.py gate failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# 2. Static analysis: Gumroad webhook wiring (KV writes, cancellation, email)
# ---------------------------------------------------------------------------

def test_gumroad_webhook_requires_shared_secret_auth(gumroad_webhook_body: str):
    assert "GUMROAD_WEBHOOK_SECRET" in gumroad_webhook_body
    assert "timingSafeEqual" in gumroad_webhook_body


def test_gumroad_webhook_handles_cancellation_event(gumroad_webhook_body: str):
    assert "isGumroadCancellationEvent" in gumroad_webhook_body, (
        "handleWebhookGumroad must check isGumroadCancellationEvent() -- "
        "a Gumroad subscription cancellation/end ping must not be treated as a new sale"
    )
    assert "gumroad_sub_key_map:" in gumroad_webhook_body, (
        "cancellation handling needs a subscription_id -> apiKey lookup"
    )
    assert 'applySubscriptionStatusChange(env, ctx, mappedKey, "cancelled"' in gumroad_webhook_body, (
        "cancellation must reuse applySubscriptionStatusChange() (single source of truth "
        "for subscription_status transitions), not a second ad-hoc KV write"
    )


def test_gumroad_webhook_provisioning_writes_subscription_map(gumroad_webhook_body: str):
    assert "gumroad_sub_key_map:${subscription_id}" in gumroad_webhook_body.replace(" ", ""), (
        "a new recurring sale must record subscription_id -> apiKey so a later "
        "cancellation/end ping (which carries no apiKey) can find the key"
    )


def test_gumroad_webhook_sends_activation_email(gumroad_webhook_body: str):
    assert "sendActivationEmail(env, email, tier, apiKey)" in gumroad_webhook_body, (
        "Gumroad checkout happens entirely on Gumroad's hosted page -- there is no "
        "client-side callback into this app, so email is the only delivery channel "
        "for the API key; this must call the existing sendActivationEmail(), not "
        "reimplement email delivery"
    )


def test_gumroad_webhook_reuses_pure_tier_inference(gumroad_webhook_body: str):
    assert "inferGumroadTier(product_name, variants)" in gumroad_webhook_body


def test_index_js_reexports_gumroad_lifecycle_functions(gateway_src: str):
    assert "from './gumroad-lifecycle.js'" in gateway_src
    assert "inferGumroadTier" in gateway_src
    assert "isGumroadCancellationEvent" in gateway_src


# ---------------------------------------------------------------------------
# 3. Static analysis: tier-inference bug fix stays fixed
# ---------------------------------------------------------------------------

def test_gumroad_tier_inference_does_not_false_positive_on_sentinel(gumroad_lifecycle_src: str):
    """Regression guard: the original inline check was `pnl.includes("ent")`,
    which matches the substring "ent" inside "Sentinel" -- every product here
    is branded "...SENTINEL APEX...", so that check misclassified every PRO
    sale as ENTERPRISE. Must never come back."""
    assert 'includes("ent")' not in gumroad_lifecycle_src
    assert 'includes(\'ent\')' not in gumroad_lifecycle_src


# ---------------------------------------------------------------------------
# 4. Static analysis: frontend paywall + checkout pages
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def index_html_text() -> str:
    assert INDEX_HTML.exists()
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def upgrade_html_text() -> str:
    assert UPGRADE_HTML.exists()
    return UPGRADE_HTML.read_text(encoding="utf-8")


def test_index_html_ioc_paywall_applies_blur_styling(index_html_text: str):
    style_match = re.search(r"\.cdb-ioc-lock-blur\s*\{([^}]*)\}", index_html_text)
    assert style_match, "expected .cdb-ioc-lock-blur rule in index.html"
    assert "blur(" in style_match.group(1), "gated IOC fields must be visually blurred for free tier"


def test_index_html_ioc_paywall_has_dual_gateway_ctas(index_html_text: str):
    assert "cdb-ioc-unlock-group" in index_html_text
    assert "gateway=razorpay" in index_html_text, "paywall must offer a Razorpay CTA"
    assert "gateway=gumroad" in index_html_text, "paywall must offer a Gumroad CTA"
    # Both CTAs must route through the one real checkout page, not a new one
    assert "/upgrade.html?plan=pro&utm_source=ioc-blur&gateway=razorpay" in index_html_text
    assert "/upgrade.html?plan=pro&utm_source=ioc-blur&gateway=gumroad" in index_html_text


def test_upgrade_html_still_has_automated_checkout_markers(upgrade_html_text: str):
    """Anti-regression: same markers scripts/validate_monetization.py enforces --
    duplicated here so this test file stands on its own."""
    assert _html_references_host(upgrade_html_text, "checkout.razorpay.com")
    assert "initiateRazorpayCheckout" in upgrade_html_text
    assert _html_references_host(upgrade_html_text, "gumroad.com")


def test_upgrade_html_handles_gateway_hint(upgrade_html_text: str):
    assert "_gatewayHint" in upgrade_html_text
    assert "gumroad-panel" in upgrade_html_text
    assert "section-payment-methods" in upgrade_html_text


@needs_node
def test_upgrade_html_inline_js_syntax_valid():
    """Same node --check technique scripts/validate_monetization.py uses."""
    data = UPGRADE_HTML.read_text(encoding="utf-8")
    # </script\s*> (not bare </script>): CodeQL's py/bad-tag-filter flags an
    # end-tag regex that requires an exact match immediately before ">",
    # since it would miss a real closing tag with whitespace before the
    # bracket (e.g. "</script >").
    scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script\s*>", data, re.IGNORECASE)
    assert scripts, "expected inline <script> blocks in upgrade.html"
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False, encoding="utf-8") as f:
        f.write("\n".join(scripts))
        tmp_path = f.name
    result = subprocess.run(["node", "--check", tmp_path], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, f"upgrade.html inline JS syntax error: {result.stderr}"


# ---------------------------------------------------------------------------
# 5. welcome.html -- Gumroad post-checkout confirmation page
# ---------------------------------------------------------------------------

def test_welcome_html_exists_and_handles_gumroad_redirect():
    assert WELCOME_HTML.exists(), (
        "welcome.html is the landing page a merchant-configured Gumroad "
        "post-purchase redirect (?email=...&gateway=gumroad) points to"
    )
    data = WELCOME_HTML.read_text(encoding="utf-8")
    assert not data.startswith("﻿"), "welcome.html: BOM detected"
    assert "gateway" in data
    assert "gumroad-panel" in data
    assert "cdbCopyApiKey" in data, "expected a 1-click copy-API-key affordance"


@needs_node
def test_welcome_html_inline_js_syntax_valid():
    data = WELCOME_HTML.read_text(encoding="utf-8")
    # </script\s*> (not bare </script>): CodeQL's py/bad-tag-filter flags an
    # end-tag regex that requires an exact match immediately before ">",
    # since it would miss a real closing tag with whitespace before the
    # bracket (e.g. "</script >").
    scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script\s*>", data, re.IGNORECASE)
    assert scripts
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False, encoding="utf-8") as f:
        f.write("\n".join(scripts))
        tmp_path = f.name
    result = subprocess.run(["node", "--check", tmp_path], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, f"welcome.html inline JS syntax error: {result.stderr}"
