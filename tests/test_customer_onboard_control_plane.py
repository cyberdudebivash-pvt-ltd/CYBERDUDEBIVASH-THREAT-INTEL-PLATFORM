import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "customer_onboard.py"
SPEC = importlib.util.spec_from_file_location("customer_onboard", MODULE_PATH)
customer_onboard = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(customer_onboard)


def test_paid_tier_requires_explicit_payment_reference():
    with pytest.raises(ValueError, match="verified payment reference"):
        customer_onboard.validate_provision_request("buyer@example.com", "PRO", 30, "")


def test_free_and_trial_do_not_require_payment_reference():
    customer_onboard.validate_provision_request("trial@example.com", "TRIAL", 14, "")
    customer_onboard.validate_provision_request("free@example.com", "FREE", 30, "")


@pytest.mark.parametrize("email", ["", "invalid", "@example.com", "buyer@"])
def test_invalid_email_fails_closed(email):
    with pytest.raises(ValueError, match="valid customer email"):
        customer_onboard.validate_provision_request(email, "PRO", 30, "PAY-1")


@pytest.mark.parametrize("days", [0, -1, 3661])
def test_invalid_subscription_duration_fails_closed(days):
    with pytest.raises(ValueError, match="subscription days"):
        customer_onboard.validate_provision_request("buyer@example.com", "PRO", days, "PAY-1")


def test_duplicate_customer_is_detected_by_email_or_reference(monkeypatch):
    monkeypatch.setattr(
        customer_onboard,
        "load_json",
        lambda *args, **kwargs: {
            "customers": [{
                "customer_id": "C-EXISTING",
                "email": "buyer@example.com",
                "reference_id": "SA-EXISTING",
            }]
        },
    )
    assert customer_onboard.find_existing_customer("BUYER@example.com", "new-ref")["customer_id"] == "C-EXISTING"
    assert customer_onboard.find_existing_customer("other@example.com", "SA-EXISTING")["customer_id"] == "C-EXISTING"


def test_welcome_package_does_not_claim_aws_residency():
    key = {
        "tier": "PRO",
        "api_calls_per_day": 5000,
        "key": "test-key",
        "expires_at": "2026-10-30T00:00:00+00:00",
        "key_hash": "a" * 64,
    }
    customer = {
        "customer_id": "C-1",
        "name": "Test",
        "email": "test@example.com",
        "company": "Example",
        "country": "IN",
        "jurisdiction": "South Asia",
        "dpa_version": "177.0.0",
    }
    sub = {
        "sub_id": "SUB-1",
        "started_at": "2026-09-30T00:00:00+00:00",
        "current_period_end": "2026-10-30T00:00:00+00:00",
        "payment_ref": "PAY-1",
    }
    package = customer_onboard.generate_welcome_package(key, customer, sub)
    assert "AWS Region" not in package
    assert "data-residency guarantee" in package


def _args(**overrides):
    values = {
        "name": "Buyer",
        "email": "buyer@example.com",
        "company": "Example",
        "country": "IN",
        "tier": "pro",
        "days": 30,
        "ref": "SA-TEST-1",
        "payment_ref": "PAY-1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_post_key_failure_compensates_by_revoking_live_credential(monkeypatch):
    key = {
        "key": "SA-PRO-SECRET",
        "key_hash": "b" * 64,
        "tier": "PRO",
        "api_calls_per_day": 5000,
        "expires_at": "2026-10-30T00:00:00+00:00",
    }
    revoked = []
    monkeypatch.setattr(customer_onboard, "find_existing_customer", lambda *a: None)
    monkeypatch.setattr(customer_onboard._gk, "generate_key", lambda **kw: key)
    monkeypatch.setattr(
        customer_onboard._gk, "revoke_key",
        lambda plaintext, reason="": revoked.append((plaintext, reason)) or True,
    )
    monkeypatch.setattr(
        customer_onboard, "register_customer",
        lambda **kw: (_ for _ in ()).throw(OSError("registry unavailable")),
    )

    with pytest.raises(OSError, match="registry unavailable"):
        customer_onboard.cmd_provision(_args())

    assert revoked
    assert revoked[0][0] == "SA-PRO-SECRET"
    assert "automatic_compensation" in revoked[0][1]


def test_compensation_failure_escalates_critical_state(monkeypatch):
    key = {
        "key": "SA-PRO-SECRET",
        "key_hash": "b" * 64,
        "tier": "PRO",
        "api_calls_per_day": 5000,
        "expires_at": "2026-10-30T00:00:00+00:00",
    }
    monkeypatch.setattr(customer_onboard, "find_existing_customer", lambda *a: None)
    monkeypatch.setattr(customer_onboard._gk, "generate_key", lambda **kw: key)
    monkeypatch.setattr(
        customer_onboard, "register_customer",
        lambda **kw: (_ for _ in ()).throw(OSError("registry unavailable")),
    )
    monkeypatch.setattr(
        customer_onboard._gk, "revoke_key",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("authority unavailable")),
    )

    with pytest.raises(RuntimeError, match="CRITICAL: onboarding failed"):
        customer_onboard.cmd_provision(_args())
