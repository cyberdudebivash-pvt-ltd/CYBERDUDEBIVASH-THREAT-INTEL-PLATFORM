import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "workers" / "intel-gateway" / "src" / "index.js"


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "capability_live_probe",
        ROOT / "scripts" / "capability_live_probe.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_customer_read_aliases_canonicalize_before_auth_and_tier_classification():
    text = GATEWAY.read_text(encoding="utf-8")
    expected = {
        "/api/ai/tracker": "/api/ai/tracker.json",
        "/api/ai/health": "/api/ai/health.json",
        "/api/v1/intel/ai_summary": "/api/v1/intel/ai_summary.json",
        "/api/v1/intel/apex": "/api/v1/intel/apex.json",
    }
    for legacy, canonical in expected.items():
        assert f'["{legacy}", "{canonical}"]' in text

    canonicalize = text.index("path = READ_ROUTE_ALIASES.get(path) || path;")
    auth = text.index("let auth = await resolveAuth(request, env);", canonicalize)
    assert canonicalize < auth

    # The sensitive legacy aliases must resolve to the same canonical premium
    # paths already enforced by the existing entitlement plane.
    assert '"/api/v1/intel/apex.json"' in text
    assert '"/api/v1/intel/ai_summary.json"' in text
    assert "PREMIUM_INTEL_PATHS.has(pathname)" in text


def test_mutation_only_customer_routes_have_explicit_safe_wrong_method_contracts():
    text = GATEWAY.read_text(encoding="utf-8")
    for route, verb in {
        "/api/alerts/subscribe": "POST",
        "/api/alerts/test": "POST",
        "/api/alerts/unsubscribe": "DELETE",
        "/api/dark-web/scan": "POST",
    }.items():
        assert f'path === "{route}" && method !== "{verb}"' in text
        assert f'allowed: ["{verb}"]' in text

    # Production truth invariant: dark-web scan remains unavailable rather
    # than exposing the deterministic simulated implementation.
    assert 'path === "/api/dark-web/scan" && method === "POST"' in text
    assert "_darkWebUnavailable" in text


def test_live_probe_uses_revenue_authority_only_for_verified_revenue_families():
    probe = _load_probe()
    revenue = probe.REVENUE_BASE
    intel = probe.PRODUCTION_BASE

    for dep in (
        "/api/apikeys/rotate",
        "/api/crm/leads",
        "/api/customers/provision",
        "/api/deals",
        "/api/payments",
        "/api/revenue/commercial",
        "/api/subscriptions/expire-check",
        "/api/success/scores",
    ):
        assert probe._dependency_base(dep) == revenue

    for dep in (
        "/api/feed.json",
        "/api/v1/news/feed",
        "/api/alerts/subscribe",
        "/api/watchdog/health",
        "/api/v2/billing/account",
    ):
        assert probe._dependency_base(dep) == intel


def test_unknown_api_family_never_falls_through_to_revenue():
    probe = _load_probe()
    assert probe._dependency_base("/api/unknown/customer") == probe.PRODUCTION_BASE
