"""P0 R19: live Intel release-truth preflight fail-closed, zero-network unit tests."""
from __future__ import annotations

import copy
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import p0_r19_live_release_truth as gate

SHA = "a" * 40
NOW = dt.datetime(2026, 10, 9, 10, 30, tzinfo=dt.timezone.utc)
BORN = (NOW - dt.timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
SLUG = "intel--valid-123"


def responses():
    return {
        "/api/health/live": {"status": "alive", "deploy_commit_sha": SHA},
        "/api/health": {
            "status": "ok", "checks": {"publication_integrity": "ok"},
            "intelligence": {
                "status": "fresh", "generated_at": BORN, "age_seconds": 900,
                "max_age_seconds": 21600,
            }
        },
        "/api/preview?limit=3": {
            "status": "ok", "preview": {
                "publication_state": "fresh", "freshness_status": "FRESH",
                "items": [{
                    "id": SLUG, "stix_id": SLUG, "internal_advisory_id": SLUG,
                    "stix_id_kind": "LEGACY_INTERNAL_IDENTIFIER",
                    "stix_object_id": None, "stix_object_id_validation": "UNAVAILABLE",
                    "tlp": "TLP:CLEAR", "report_customer_ready": False,
                    "report_publication_state": "BLOCKED",
                    "blog_url": "https://example.com/vendor-advisory",
                    "report_url": None,
                }]
            }
        },
        f"/api/v1/reports/{SLUG}/publication-status": {
            "report_id": SLUG, "customer_ready": False, "state": "BLOCKED",
        },
    }


def verify(payload):
    calls = []
    def fetch(path):
        calls.append(path)
        return copy.deepcopy(payload[path])
    result = gate.evaluate(SHA, fetch, now=NOW)
    assert len(calls) <= 4, "bounded GET budget for one sample"
    return result


def test_complete_but_blocked_sample_only_verifies_live_slice():
    r = verify(responses())
    assert r == {"status": "LIVE_SLICE_VERIFIED_NOT_ENTERPRISE_GO",
                 "reasons": [], "preview_checked": 1}


def test_deployed_sha_mismatch_must_block():
    payload = responses()
    payload["/api/health/live"]["deploy_commit_sha"] = "b" * 40
    assert "DEPLOYED_WORKER_SHA_MISMATCH" in verify(payload)["reasons"]


def test_stale_or_fabricated_health_age_blocks():
    payload = responses()
    payload["/api/health"]["intelligence"]["age_seconds"] = 0
    payload["/api/health"]["intelligence"]["generated_at"] = "2026-01-01T00:00:00Z"
    assert "INTELLIGENCE_SOURCE_CLOCK_INVALID" in verify(payload)["reasons"]


def test_blocked_link_exposure_blocks():
    payload = responses()
    payload["/api/preview?limit=3"]["preview"]["items"][0]["blog_url"] = (
        "https://intel.cyberdudebivash.com/reports/intel--valid-123/"
    )
    assert "BLOCKED_REPORT_LINK_EXPOSED" in verify(payload)["reasons"]


def test_unqualified_stix_id_claim_blocks():
    payload = responses()
    payload["/api/preview?limit=3"]["preview"]["items"][0]["stix_id_kind"] = "STIX_2_1_VERIFIED"
    assert "LEGACY_STIX_KIND_INCORRECT" in verify(payload)["reasons"]


def test_restricted_tlp_item_blocks():
    payload = responses()
    payload["/api/preview?limit=3"]["preview"]["items"][0]["tlp"] = "TLP:RED"
    assert "PREVIEW_TLP_NOT_CLEAR" in verify(payload)["reasons"]


def test_report_verdict_disagreement_blocks():
    payload = responses()
    payload[f"/api/v1/reports/{SLUG}/publication-status"]["customer_ready"] = True
    assert "REPORT_VERDICT_DIVERGENCE" in verify(payload)["reasons"]


def test_ready_report_with_real_link_and_same_status_can_pass_slice():
    payload = responses()
    item = payload["/api/preview?limit=3"]["preview"]["items"][0]
    item["report_customer_ready"] = True
    item["report_publication_state"] = "CUSTOMER_READY"
    item["blog_url"] = f"https://intel.cyberdudebivash.com/reports/{SLUG}/"
    payload[f"/api/v1/reports/{SLUG}/publication-status"]["customer_ready"] = True
    payload[f"/api/v1/reports/{SLUG}/publication-status"]["state"] = "CUSTOMER_READY"
    assert verify(payload)["status"] == "LIVE_SLICE_VERIFIED_NOT_ENTERPRISE_GO"


def test_ready_without_customer_link_fails_closed():
    payload = responses()
    item = payload["/api/preview?limit=3"]["preview"]["items"][0]
    item["report_customer_ready"] = True
    item["report_publication_state"] = "CUSTOMER_READY"
    payload[f"/api/v1/reports/{SLUG}/publication-status"]["customer_ready"] = True
    assert "READY_REPORT_LINK_MISSING" in verify(payload)["reasons"]


def test_worker_endpoint_failure_fails_closed():
    payload = responses()
    def fetch(path):
        if path == "/api/health/live":
            raise OSError("network down")
        return payload[path]
    assert "LIVE_HEALTH_UNAVAILABLE" in gate.evaluate(SHA, fetch, now=NOW)["reasons"]


def test_empty_expected_sha_and_bad_bounds_refused_without_requests():
    def never_called(_):
        raise AssertionError("Expected zero network")
    assert gate.evaluate("", never_called, now=NOW)["status"] == "BLOCKED"
    assert gate.evaluate(SHA, never_called, now=NOW, limit=20)["status"] == "BLOCKED"


def test_malformed_health_checks_fail_closed_instead_of_crashing():
    payload = responses()
    payload["/api/health"]["checks"] = None
    assert "PUBLICATION_HEALTH_NOT_OK" in verify(payload)["reasons"]


def test_report_status_claims_customer_ready_while_boolean_false_blocks():
    payload = responses()
    payload[f"/api/v1/reports/{SLUG}/publication-status"]["state"] = "CUSTOMER_READY"
    assert "REPORT_STATUS_CONTRADICTORY" in verify(payload)["reasons"]
