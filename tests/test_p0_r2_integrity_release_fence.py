"""P0 #725: integrity verifier and release-surface gates must fail CLOSED.

Run #2520 reported a failed Stage 3.6 verifier followed by a successful
Stage 3.7 KV cache bust. The old verifier also had soft-pass paths for
missing S3 credentials and private-bucket HTTP 403 responses. No production
credentials, R2 I/O or network are used by these contract tests.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import r2_upload_verifier as verifier


def test_missing_verifier_credentials_are_a_hard_failure():
    with patch.object(verifier, "CF_ACCOUNT_ID", ""), \
         patch.object(verifier, "ACCESS_KEY", ""), \
         patch.object(verifier, "SECRET_KEY", ""):
        verified, message, details = verifier.verify_r2_object()
    assert verified is False
    assert details["reason_code"] == "MISSING_AUTHORITY"
    assert "UNVERIFIED" in message


def test_http_403_private_bucket_cannot_soft_pass_an_unverified_s3_head():
    with patch.object(verifier, "CF_ACCOUNT_ID", "account-fixture"), \
         patch.object(verifier, "ACCESS_KEY", "fake-key"), \
         patch.object(verifier, "SECRET_KEY", "fake-secret"), \
         patch.object(verifier, "R2_ENDPOINT", "https://r2.example.invalid"), \
         patch.object(verifier, "_s3api_head_object", return_value=None), \
         patch.object(verifier, "_boto3_head_object", return_value=None), \
         patch.object(verifier, "_http_head_diagnostic", return_value={"status": 403, "etag": ""}):
        verified, message, details = verifier.verify_r2_object()
    assert verified is False, "private R2 denial cannot certify object presence"
    assert details["reason_code"] == "AUTHENTICATED_READ_UNAVAILABLE"
    assert details["http_diagnostic"]["status"] == 403
    assert "Cannot verify R2 upload" in message


def test_authenticated_object_missing_is_hard_failure():
    with patch.object(verifier, "CF_ACCOUNT_ID", "account-fixture"), \
         patch.object(verifier, "ACCESS_KEY", "fake-key"), \
         patch.object(verifier, "SECRET_KEY", "fake-secret"), \
         patch.object(verifier, "_s3api_head_object",
                      return_value={"status": 404, "content_length": 0, "etag": "", "source": "fake-s3"}):
        verified, message, details = verifier.verify_r2_object()
    assert verified is False
    assert "NOT FOUND" in message


def test_authenticated_matching_s3_head_remains_eligible(tmp_path):
    source = tmp_path / "feed_manifest.json"
    body = b'{"items":[]}' + b" " * 2048
    source.write_bytes(body)
    md5 = hashlib.md5(body, usedforsecurity=False).hexdigest()
    with patch.object(verifier, "CF_ACCOUNT_ID", "account-fixture"), \
         patch.object(verifier, "ACCESS_KEY", "fake-key"), \
         patch.object(verifier, "SECRET_KEY", "fake-secret"), \
         patch.object(verifier, "MANIFEST_PATH", source), \
         patch.object(verifier, "_s3api_head_object",
                      return_value={"status": 200, "content_length": len(body),
                                    "etag": md5, "source": "fake-s3"}):
        verified, _, details = verifier.verify_r2_object()
    assert verified is True
    assert details["etag_check"] == "PASS"


def test_release_workflow_requires_verified_r2_for_every_distribution_boundary():
    workflow = yaml.safe_load((ROOT / ".github/workflows/sentinel-blogger.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["generate-and-sync"]["steps"]
    by_name = {s.get("name"): (i, s) for i, s in enumerate(steps)}
    integrity_name = "STAGE 3.6 - R2 Upload Integrity Verifier (HARD FAIL)"
    i_integrity, verifier_step = by_name[integrity_name]
    assert verifier_step["id"] == "r2-manifest-integrity"
    assert "scripts/r2_upload_verifier.py" in verifier_step["run"]
    assert verifier_step.get("continue-on-error") is not True
    protected = (
        "STAGE 3.7 - Bust Worker KV Cache",
        "STAGE 4.1 - Final R2 Full Sync (v184.0 -- post-git-push complete feed)",
        "Upload Intel State to R2 (final, post-enrichment)",
        "STAGE 4.9.9 - Capture pre-deploy timestamp",
        "STAGE 5 - Deploy to GitHub Pages",
        "STAGE 5.4.9.1 - GitHub Pages Deployment Freshness Gate (v184.1)",
    )
    for name in protected:
        index, step = by_name[name]
        assert index > i_integrity, name
        condition = str(step.get("if", ""))
        assert "steps.r2-manifest-integrity.outcome == 'success'" in condition, name
        assert "!cancelled()" in condition, name


def test_workflow_cannot_treat_r2_integrity_step_as_soft_warning():
    contents = (ROOT / ".github/workflows/sentinel-blogger.yml").read_text(encoding="utf-8")
    assert 'id: r2-manifest-integrity' in contents
    assert 'if: always()\n        run: python3 scripts/bust_kv_cache.py' not in contents
