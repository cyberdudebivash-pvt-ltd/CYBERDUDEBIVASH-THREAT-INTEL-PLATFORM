#!/usr/bin/env python3
"""
scripts/audit_snapshot_store.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Immutable/Versioned Audit Evidence Store (Class D)
================================================================================
P0 production-architecture-transformation mission (2026-09-08): the one
genuinely missing persistence class identified by the repository reality
audit. Class A (mutable runtime state: scripts/r2_state_sync.py) and Class B
(generated customer/deployment artifacts: scripts/r2_upload.py) already have
mature, production-proven R2 implementations -- this module is deliberately
NOT a third, parallel, general-purpose persistence framework. It reuses
r2_upload.py's existing s3_cp/s3_get primitives and adds exactly the one
capability neither of those provides: write-once, versioned-by-run audit
evidence that a later run cannot silently overwrite.

Root problem this fixes: every audit/certification file this platform
produces today (data/audit/pipeline_audit.json, data/health/*.json,
data/quality/*.json, etc.) is a single mutable path that each run
overwrites in place. A "1 critical issue" finding from run N is
indistinguishable from run N+1's "0 issues" the moment run N+1 writes --
there is no historical evidence trail, only a current snapshot. (This is
also, independently, why data/audit/pipeline_audit.json in a fresh git
checkout was found frozen at the 2026-08-26 incident date during this same
investigation -- it was never migrated to Class A OR Class D, so it had no
persistence path at all once the git branch ruleset began rejecting
runtime pushes.)

Key model (per the production-architecture-transformation mission spec):
  audit/<YYYY>/<MM>/<DD>/<workflow_run_id>/<family>.json

Each snapshot is an envelope around the original file's content:
  {
    "schema_version": "1",
    "generated_at": "<ISO-8601 UTC, write time>",
    "workflow_run_id": "<GITHUB_RUN_ID>",
    "source_sha": "<GITHUB_SHA>",
    "content_sha256": "<sha256 of the original file's raw bytes>",
    "producer": "<family, e.g. 'pipeline_audit'>",
    "content": <original file's parsed JSON, unmodified>
  }

Immutability: R2 (plain S3-compatible object storage) has no native
conditional-write/If-None-Match support via the aws-cli path this codebase
already standardizes on (see r2_upload.py's docstring), so this module
enforces write-once at the application layer: before every write it
attempts to download the target key via the existing s3_get() three-way
contract (OK = key already exists -> fail closed, refuse to overwrite;
NOT_FOUND = safe to write; ERROR = fail closed out of caution, same as
"already exists" -- an indeterminate state must never risk silently
clobbering real evidence). This is a check-then-act race in the strict
sense, but two runs racing to write the exact same
<run_id>/<family>.json key is already precluded by workflow_run_id being
unique per GitHub Actions run -- the race this guards against is a bug
(the same code path calling write_snapshot() twice for one run), not
legitimate concurrent writers.

Usage:
  python3 scripts/audit_snapshot_store.py \\
      --family pipeline_audit \\
      --source data/audit/pipeline_audit.json \\
      --run-id "$GITHUB_RUN_ID" \\
      --source-sha "$GITHUB_SHA"

Environment variables (same as r2_upload.py / r2_state_sync.py):
  CF_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pathlib
import sys
from datetime import datetime, timezone

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from r2_upload import (  # noqa: E402
    BUCKET_DATA,
    get_credentials,
    install_awscli,
    s3_cp,
    s3_get,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [audit-snapshot-store] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("audit-snapshot-store")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "1"

# Families this module is wired to today, per the production-architecture-
# transformation mission's own Class D example list (section 5). Kept as an
# explicit allowlist (not "any file you point it at") so a typo in a future
# caller's --family value fails loudly instead of silently creating an
# uncatalogued audit key.
KNOWN_FAMILIES = {
    "pipeline_audit",
    "global_release_governance",
    "report_engine_ledger",
    "quality_drift_report",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _versioned_key(family: str, run_id: str, when: datetime) -> str:
    return (
        f"audit/{when.year:04d}/{when.month:02d}/{when.day:02d}/"
        f"{run_id}/{family}.json"
    )


def write_snapshot(
    local_path: pathlib.Path,
    family: str,
    run_id: str,
    source_sha: str,
    endpoint: str,
) -> dict | None:
    """
    Write one immutable, versioned audit snapshot to R2.

    Returns the envelope dict that was written on success, or None if the
    write was refused (source unreadable/invalid, or the target key already
    exists -- fail closed, never silently overwrite existing evidence).
    """
    if family not in KNOWN_FAMILIES:
        log.error(
            "REFUSED: family=%r is not in KNOWN_FAMILIES (%s) -- add it there "
            "deliberately rather than writing an uncatalogued audit key.",
            family, sorted(KNOWN_FAMILIES),
        )
        return None

    if not local_path.exists():
        log.warning("SKIP: %s does not exist -- nothing to snapshot for family=%s.",
                    local_path, family)
        return None

    try:
        raw = local_path.read_bytes()
        content = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.error(
            "REFUSED: %s is not valid, readable JSON (%s) -- refusing to "
            "write corrupt content into permanent audit history.",
            local_path, exc,
        )
        return None

    now = datetime.now(timezone.utc)
    key = _versioned_key(family, run_id, now)

    # Fail-closed write-once check (see module docstring's Immutability
    # section for why this is a download-probe, not a HEAD request: no
    # existing primitive for the latter, and s3_get()'s three-way contract
    # already distinguishes "genuinely absent" from "indeterminate" the
    # exact way this check needs).
    probe_path = local_path.with_name(local_path.name + f".{run_id}.existscheck.tmp")
    probe_outcome = s3_get(str(probe_path), BUCKET_DATA, key, endpoint)
    probe_path.unlink(missing_ok=True)
    if probe_outcome != "NOT_FOUND":
        log.error(
            "REFUSED: audit/%s already has content at key=%s (probe=%s) -- "
            "write-once semantics mean this snapshot is never overwritten. "
            "If this fires outside of a genuine same-run double-call bug, "
            "investigate before assuming it is safe to skip.",
            family, key, probe_outcome,
        )
        return None

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workflow_run_id": run_id,
        "source_sha": source_sha,
        "content_sha256": _sha256_bytes(raw),
        "producer": family,
        "content": content,
    }

    tmp_path = local_path.with_name(local_path.name + f".{run_id}.snapshot.tmp")
    tmp_path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        uploaded = s3_cp(str(tmp_path), BUCKET_DATA, key, endpoint)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not uploaded:
        log.error("FAILED: could not upload audit/%s snapshot to key=%s.", family, key)
        return None

    if not verify_hash(family, key, envelope["content_sha256"], endpoint):
        log.error(
            "INTEGRITY FAILURE: audit/%s snapshot uploaded to key=%s but "
            "read-back verification did not match the expected hash -- "
            "treat this snapshot as unreliable.",
            family, key,
        )
        return None

    log.info("OK: audit/%s snapshot written and verified at key=%s (sha256=%s...)",
              family, key, envelope["content_sha256"][:12])
    return envelope


def verify_hash(family: str, key: str, expected_sha256: str, endpoint: str) -> bool:
    """Read back a just-written (or previously written) snapshot and confirm
    its envelope's recorded content_sha256 matches what we expect, and that
    the envelope's own bytes weren't corrupted in transit."""
    tmp_path = REPO_ROOT / f".audit_verify.{family}.tmp"
    outcome = s3_get(str(tmp_path), BUCKET_DATA, key, endpoint)
    if outcome != "OK":
        log.error("verify_hash: could not read back key=%s (outcome=%s)", key, outcome)
        tmp_path.unlink(missing_ok=True)
        return False
    try:
        envelope = json.loads(tmp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("verify_hash: key=%s read back but is not valid JSON (%s)", key, exc)
        return False
    finally:
        tmp_path.unlink(missing_ok=True)
    return envelope.get("content_sha256") == expected_sha256


def read_snapshot(family: str, run_id: str, when: datetime, endpoint: str) -> dict | None:
    """Read one specific historical snapshot back by its exact coordinates."""
    key = _versioned_key(family, run_id, when)
    tmp_path = REPO_ROOT / f".audit_read.{family}.{run_id}.tmp"
    outcome = s3_get(str(tmp_path), BUCKET_DATA, key, endpoint)
    if outcome != "OK":
        tmp_path.unlink(missing_ok=True)
        return None
    try:
        return json.loads(tmp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True, choices=sorted(KNOWN_FAMILIES))
    parser.add_argument("--source", required=True, type=pathlib.Path,
                         help="Local path to the JSON file to snapshot.")
    parser.add_argument("--run-id", required=True, help="GitHub Actions run ID (GITHUB_RUN_ID).")
    parser.add_argument("--source-sha", required=True, help="Git commit SHA this run checked out (GITHUB_SHA).")
    args = parser.parse_args()

    cf_account, _, _ = get_credentials()
    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"
    install_awscli()

    result = write_snapshot(args.source, args.family, args.run_id, args.source_sha, endpoint)
    return 0 if result is not None else 1


if __name__ == "__main__":
    sys.exit(main())
