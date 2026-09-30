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
