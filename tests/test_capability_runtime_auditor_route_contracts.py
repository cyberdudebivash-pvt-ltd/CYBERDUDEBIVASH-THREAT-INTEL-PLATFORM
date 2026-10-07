import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "capability_runtime_auditor",
    ROOT / "scripts" / "capability_runtime_auditor.py",
)
auditor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(auditor)


def test_verified_billing_base_is_valid_only_when_concrete_child_routes_exist(monkeypatch):
    monkeypatch.setattr(auditor, "_static_json_exists", lambda _dep: False)
    assert auditor._api_exists(
        "/api/v2/billing",
        ["/api/v2/billing/account", "/api/v2/billing/subscriptions/create"],
    )
    assert not auditor._api_exists("/api/v2/billing", ["/api/health"])


def test_arbitrary_missing_route_prefix_is_not_accepted(monkeypatch):
    monkeypatch.setattr(auditor, "_static_json_exists", lambda _dep: False)
    routes = ["/api/v2/billing/account", "/api/v1/news/feed"]
    assert not auditor._api_exists("/api/v2", routes)
    assert not auditor._api_exists("/api/v1", routes)
    assert not auditor._api_exists("/api/missing", routes)


def test_real_child_endpoint_matching_behavior_is_preserved(monkeypatch):
    monkeypatch.setattr(auditor, "_static_json_exists", lambda _dep: False)
    assert auditor._api_exists(
        "/api/v2/billing/account",
        ["/api/v2/billing/account"],
    )
    assert auditor._api_exists(
        "/api/mssp/tenants/tenant-123/feed",
        ["/api/mssp/tenants/{id}/feed"],
    )
