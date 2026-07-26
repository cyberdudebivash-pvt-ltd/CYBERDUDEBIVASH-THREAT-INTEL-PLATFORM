"""
test_v44_subscription.py — RB-17 regression + backward-compatibility tests
Cryptographic key generation for CDBSubscriptionManager.provision_tenant()
"""
import json
import re
import pytest

from agent.subscription_manager import SUBSCRIPTION_CORE
from agent.license_validator import LICENSE_VALIDATOR

OLD_FORMAT_PATTERN = re.compile(r"^CDB-[A-Z]+-\d{10}$")


@pytest.fixture
def isolated_tenant_store(tmp_path, monkeypatch):
    """Redirect the tenant store to a throwaway file so tests never touch
    the real data/sovereign/tenants.json."""
    store = tmp_path / "tenants.json"
    store.write_text("{}")
    monkeypatch.setattr(LICENSE_VALIDATOR, "tenant_store", str(store))
    return store


def test_provisioned_key_is_not_old_deterministic_format(isolated_tenant_store):
    """RB-17: keys must not match the old CDB-{TIER}-{minute-timestamp} shape."""
    key = SUBSCRIPTION_CORE.provision_tenant("test-owner", tier="pro")
    assert not OLD_FORMAT_PATTERN.match(key), (
        f"key {key!r} still matches the deterministic pre-RB-17 format"
    )


def test_provisioned_key_has_sufficient_entropy(isolated_tenant_store):
    """The random component should be long enough to rule out brute-force
    guessing within any practical search space."""
    key = SUBSCRIPTION_CORE.provision_tenant("test-owner", tier="pro")
    random_component = key.split("-", 2)[-1]
    assert len(random_component) >= 32, (
        f"random component of {key!r} is shorter than expected for a 256-bit token"
    )


def test_two_same_minute_calls_produce_distinct_keys(isolated_tenant_store):
    """Regression for the pre-RB-17 bug: two provisions of the same tier in
    the same minute used to collide and silently overwrite each other."""
    key_a = SUBSCRIPTION_CORE.provision_tenant("owner-a", tier="pro")
    key_b = SUBSCRIPTION_CORE.provision_tenant("owner-b", tier="pro")
    assert key_a != key_b

    with open(isolated_tenant_store) as f:
        data = json.load(f)
    assert key_a in data and key_b in data, (
        "both entries must be present -- the old bug silently dropped one"
    )
    assert data[key_a]["owner"] == "owner-a"
    assert data[key_b]["owner"] == "owner-b"


def test_existing_pre_rb17_key_still_validates(isolated_tenant_store):
    """Backward compatibility: a key in the old deterministic format, already
    present in the store, must continue to validate exactly as before --
    is_valid() is format-agnostic and only checks dict membership + status/expiry."""
    old_style_key = "CDB-PRO-2607250815"
    with open(isolated_tenant_store, "w") as f:
        json.dump({
            old_style_key: {
                "tier": "pro",
                "status": "active",
                "expires": "2099-01-01T00:00:00",
                "owner": "legacy-tenant",
                "created_at": "2026-07-25T08:15:00",
            }
        }, f)

    assert LICENSE_VALIDATOR.is_valid(old_style_key) is True


def test_new_style_key_validates_normally(isolated_tenant_store):
    """A freshly provisioned (new-format) key must validate through the
    unmodified is_valid() path."""
    key = SUBSCRIPTION_CORE.provision_tenant("test-owner", tier="enterprise")
    assert LICENSE_VALIDATOR.is_valid(key) is True


def test_invalid_key_still_rejected(isolated_tenant_store):
    """Negative case, unaffected by this change."""
    assert LICENSE_VALIDATOR.is_valid("not-a-real-key") is False
