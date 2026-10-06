"""
test_v44_subscription.py — RB-17 + RB-16 tests
Cryptographic key generation, revocation, and rotation for
CDBSubscriptionManager.
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


def _seed_tenant(store_path, key, **overrides):
    entry = {
        "tier": "pro",
        "status": "active",
        "expires": "2099-01-01T00:00:00",
        "owner": "seed-owner",
        "created_at": "2026-07-25T00:00:00",
    }
    entry.update(overrides)
    with open(store_path, "w") as f:
        json.dump({key: entry}, f)


# ─── RB-17: key generation ──────────────────────────────────────────────────

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


# ─── RB-16: revoke_tenant() ──────────────────────────────────────────────────

def test_revoke_marks_credential_revoked_and_preserves_metadata(isolated_tenant_store):
    key = "CDB-PRO-existing-key-for-revoke-test"
    _seed_tenant(isolated_tenant_store, key, owner="alice")

    result = SUBSCRIPTION_CORE.revoke_tenant(key, reason="test revocation")
    assert result == {"ok": True, "status": "revoked", "detail": "credential revoked"}

    with open(isolated_tenant_store) as f:
        data = json.load(f)
    assert data[key]["status"] == "revoked"
    assert data[key]["owner"] == "alice"  # historical metadata preserved
    assert data[key]["revoked_reason"] == "test revocation"
    assert "revoked_at" in data[key]


def test_revoke_is_idempotent(isolated_tenant_store):
    key = "CDB-PRO-idempotent-revoke-test"
    _seed_tenant(isolated_tenant_store, key)

    first = SUBSCRIPTION_CORE.revoke_tenant(key)
    second = SUBSCRIPTION_CORE.revoke_tenant(key)

    assert first["ok"] is True and first["status"] == "revoked"
    assert second["ok"] is True and second["status"] == "already_revoked"


def test_revoke_unknown_tenant_fails_gracefully(isolated_tenant_store):
    result = SUBSCRIPTION_CORE.revoke_tenant("CDB-PRO-never-existed")
    assert result == {"ok": False, "status": "not_found", "detail": "no tenant with that credential"}


def test_revoked_credential_fails_validation(isolated_tenant_store):
    key = "CDB-PRO-revoke-then-validate-test"
    _seed_tenant(isolated_tenant_store, key)

    SUBSCRIPTION_CORE.revoke_tenant(key)
    assert LICENSE_VALIDATOR.is_valid(key) is False


# ─── RB-16: rotate_tenant() ──────────────────────────────────────────────────

def test_rotate_issues_new_key_and_revokes_old(isolated_tenant_store):
    old_key = "CDB-PRO-rotate-source-test"
    _seed_tenant(isolated_tenant_store, old_key, owner="bob", tier="enterprise")

    result = SUBSCRIPTION_CORE.rotate_tenant(old_key)
    assert result["ok"] is True
    assert result["status"] == "rotated"
    new_key = result["new_key"]
    assert new_key != old_key

    with open(isolated_tenant_store) as f:
        data = json.load(f)

    assert data[old_key]["status"] == "revoked"
    assert data[old_key]["revoked_reason"] == "rotated"
    assert data[new_key]["status"] == "active"
    assert data[new_key]["owner"] == "bob"  # metadata carried forward
    assert data[new_key]["tier"] == "enterprise"
    assert data[new_key]["rotated_from"] == old_key


def test_old_credential_rejected_after_rotation(isolated_tenant_store):
    old_key = "CDB-PRO-rotate-old-rejected-test"
    _seed_tenant(isolated_tenant_store, old_key)

    SUBSCRIPTION_CORE.rotate_tenant(old_key)
    assert LICENSE_VALIDATOR.is_valid(old_key) is False


def test_new_credential_accepted_after_rotation(isolated_tenant_store):
    old_key = "CDB-PRO-rotate-new-accepted-test"
    _seed_tenant(isolated_tenant_store, old_key)

    result = SUBSCRIPTION_CORE.rotate_tenant(old_key)
    assert LICENSE_VALIDATOR.is_valid(result["new_key"]) is True


def test_no_duplicate_active_credentials_after_rotation(isolated_tenant_store):
    """Exactly one active credential must exist for the tenant post-rotation
    -- never both old and new simultaneously active."""
    old_key = "CDB-PRO-no-duplicate-active-test"
    _seed_tenant(isolated_tenant_store, old_key)

    result = SUBSCRIPTION_CORE.rotate_tenant(old_key)

    with open(isolated_tenant_store) as f:
        data = json.load(f)
    keys = [old_key, result["new_key"]]
    active_count = sum(1 for k in keys if data[k]["status"] == "active")
    assert active_count == 1


def test_repeated_rotate_on_already_rotated_key_fails_cleanly(isolated_tenant_store):
    old_key = "CDB-PRO-repeated-rotate-test"
    _seed_tenant(isolated_tenant_store, old_key)

    first = SUBSCRIPTION_CORE.rotate_tenant(old_key)
    second = SUBSCRIPTION_CORE.rotate_tenant(old_key)

    assert first["ok"] is True
    assert second == {"ok": False, "status": "already_revoked", "detail": "cannot rotate a revoked credential"}


def test_rotate_unknown_tenant_fails_gracefully(isolated_tenant_store):
    result = SUBSCRIPTION_CORE.rotate_tenant("CDB-PRO-never-existed-rotate")
    assert result == {"ok": False, "status": "not_found", "detail": "no tenant with that credential"}


def test_rotate_and_revoke_work_on_old_deterministic_format_keys(isolated_tenant_store):
    """Backward compatibility: RB-16 operations are format-agnostic, same
    as is_valid() -- a pre-RB-17-style key can still be revoked/rotated."""
    old_style_key = "CDB-PRO-2607250815"
    _seed_tenant(isolated_tenant_store, old_style_key, owner="legacy-tenant")

    rotate_result = SUBSCRIPTION_CORE.rotate_tenant(old_style_key)
    assert rotate_result["ok"] is True
    assert LICENSE_VALIDATOR.is_valid(old_style_key) is False
    assert LICENSE_VALIDATOR.is_valid(rotate_result["new_key"]) is True
