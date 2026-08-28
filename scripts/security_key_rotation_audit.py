#!/usr/bin/env python3
"""
scripts/security_key_rotation_audit.py
CYBERDUDEBIVASH SENTINEL APEX -- Leaked Tenant Key Rotation Audit
==================================================================
SEC-2026-08-28: commit bd25a21dc (2026-08-23) stripped 2,260 tenant
records' plaintext api_key values from data/sovereign/tenants.json (904
enterprise-tier), replacing them with cdb_REDACTED_ROTATE_REQUIRED_
placeholders after revenue-orchestrator.yml's SEC-2026-07-25 comment
documented the file used to be force-committed to this PUBLIC repo with
real keys on every purchase. That commit explicitly left two things
outstanding: the real keys were never rotated, and were never purged from
git history. This script closes the rotation gap: it checks whether any
of those pre-redaction key values are still live entries in the
production API_KEYS_KV namespace and, when asked, revokes the ones that
are via the Worker's own admin API (the same path DELETE
/api/admin/keys/{key} already uses -- so revocations get the existing
api_key_revoked audit-log entry for free, instead of a second,
parallel deletion mechanism).

Two-phase design, deliberately using two different credentials for two
different jobs:
  - CHECK  (read-only): Cloudflare KV REST GET against API_KEYS_KV,
    using CF_API_TOKEN/CF_ACCOUNT_ID (already used the same way by
    revenue-orchestrator.yml against a different namespace). Zero
    mutation -- safe to run any time.
  - REVOKE (mutating, opt-in only): DELETE against the Worker's own
    /api/admin/keys/{key}, using ADMIN_SECRET (already an Actions
    secret -- see commercial-customer-ops-certification.yml). Reuses
    the existing, audited revoke path rather than deleting the KV
    entry directly.

Never logs or writes a raw key value anywhere -- every reference uses the
same 12-char prefix convention the Worker's own key-rotation audit log
already uses (index.js api_key_rotated: old_key_prefix: oldKey.slice(0, 12)).

Usage:
  python3 scripts/security_key_rotation_audit.py                 # check only (default)
  python3 scripts/security_key_rotation_audit.py --confirm-revoke  # check + revoke live matches

Required environment:
  CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID   -- for the check phase
  ADMIN_SECRET                                  -- for the revoke phase (--confirm-revoke only)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [key_rotation_audit] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.security_key_rotation_audit")

LEAK_COMMIT_PARENT = "84e46c4f9be4a4e7e52c35cc2dc7d5e98fba5fcc"  # last commit with real plaintext keys
LEAKED_FILE_PATH = "data/sovereign/tenants.json"
API_KEYS_KV_NAMESPACE_ID = "ca786702c6df47b7a95d9777536c7cfb"  # workers/intel-gateway/wrangler.toml
ADMIN_BASE_URL = "https://intel.cyberdudebivash.com"
REPORT_PATH = "data/quality/security_key_rotation_audit_report.json"
REQUEST_TIMEOUT = 15
PACE_SECONDS = 0.08  # gentle rate-limiting, same spirit as bust_kv_cache.py


def mask(key: str) -> str:
    return key[:12] + "..." if isinstance(key, str) and len(key) > 12 else "***"


def load_pre_redaction_tenants() -> dict:
    result = subprocess.run(
        ["git", "show", f"{LEAK_COMMIT_PARENT}:{LEAKED_FILE_PATH}"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def kv_check_live(session: requests.Session, account_id: str, token: str, key: str) -> int:
    """Read-only Cloudflare KV GET. Returns HTTP status (200 = live, 404 = not found)."""
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        f"/storage/kv/namespaces/{API_KEYS_KV_NAMESPACE_ID}/values/{key}"
    )
    resp = session.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=REQUEST_TIMEOUT)
    return resp.status_code


def worker_revoke(session: requests.Session, admin_secret: str, key: str) -> int:
    """DELETE /api/admin/keys/{key} -- the Worker's own audited revoke path."""
    url = f"{ADMIN_BASE_URL}/api/admin/keys/{key}"
    resp = session.delete(url, headers={"X-Admin-Key": admin_secret}, timeout=REQUEST_TIMEOUT)
    return resp.status_code


def main() -> int:
    confirm_revoke = "--confirm-revoke" in sys.argv

    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    cf_account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    admin_secret = os.environ.get("ADMIN_SECRET", "").strip()

    if not cf_token or not cf_account:
        log.error("CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID not set -- cannot run the check phase.")
        return 1
    if confirm_revoke and not admin_secret:
        log.error("--confirm-revoke requires ADMIN_SECRET to be set.")
        return 1

    log.info("=" * 70)
    log.info("SENTINEL APEX -- Leaked Tenant Key Rotation Audit (SEC-2026-08-28)")
    log.info("Mode: %s", "CHECK + REVOKE" if confirm_revoke else "CHECK ONLY (dry run)")
    log.info("=" * 70)

    tenants = load_pre_redaction_tenants()
    log.info("Loaded %d pre-redaction tenant records from commit %s", len(tenants), LEAK_COMMIT_PARENT[:12])

    session = requests.Session()
    live, dead, errors, revoked = [], [], [], []

    for tenant_id, t in tenants.items():
        key = t.get("api_key")
        if not isinstance(key, str) or not key:
            continue

        status = kv_check_live(session, cf_account, cf_token, key)
        if status == 200:
            live.append({
                "tenant_id": tenant_id,
                "org_name": t.get("org_name"),
                "tier": t.get("tier"),
                "key_prefix": mask(key),
                "_raw_key": key,  # stripped before the report is written
            })
        elif status == 404:
            dead.append(tenant_id)
        else:
            errors.append({"tenant_id": tenant_id, "http_status": status})
        time.sleep(PACE_SECONDS)

    log.info("Live in API_KEYS_KV: %d", len(live))
    log.info("Not found (already dead / never provisioned): %d", len(dead))
    log.info("Lookup errors: %d", len(errors))

    if live:
        for entry in live:
            log.warning("  LIVE  tenant=%s tier=%s org=%r key=%s",
                         entry["tenant_id"], entry["tier"], entry["org_name"], entry["key_prefix"])

    if confirm_revoke and live:
        log.info("--confirm-revoke set: revoking %d live key(s) via the Worker's admin API...", len(live))
        for entry in live:
            rstatus = worker_revoke(session, admin_secret, entry["_raw_key"])
            ok = rstatus in (200, 404)  # 404 here means another process already revoked it -- fine
            revoked.append({
                "tenant_id": entry["tenant_id"],
                "key_prefix": entry["key_prefix"],
                "revoke_http_status": rstatus,
                "ok": ok,
            })
            log.info("  %s revoked %s (tenant %s): HTTP %d",
                     "OK" if ok else "FAIL", entry["key_prefix"], entry["tenant_id"], rstatus)
            time.sleep(PACE_SECONDS)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": LEAK_COMMIT_PARENT,
        "total_pre_redaction_tenants": len(tenants),
        "live_count": len(live),
        "dead_count": len(dead),
        "error_count": len(errors),
        "mode": "revoke" if confirm_revoke else "check_only",
        "live_keys_found": [{k: v for k, v in e.items() if k != "_raw_key"} for e in live],
        "revoked": revoked,
        "lookup_errors": errors,
    }
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    log.info("Report written to %s (no raw key values included)", REPORT_PATH)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        lines = [
            "## Leaked Tenant Key Rotation Audit",
            "",
            f"- Mode: **{report['mode']}**",
            f"- Pre-redaction tenants checked: {report['total_pre_redaction_tenants']}",
            f"- Live in API_KEYS_KV: **{report['live_count']}**",
            f"- Dead (already gone / never provisioned): {report['dead_count']}",
            f"- Lookup errors: {report['error_count']}",
        ]
        if revoked:
            ok_count = sum(1 for r in revoked if r["ok"])
            lines.append(f"- Revoked: {ok_count}/{len(revoked)}")
        with open(summary_path, "a") as f:
            f.write("\n".join(lines) + "\n")

    if live and not confirm_revoke:
        log.warning("")
        log.warning("CHECK ONLY -- no keys were revoked. Re-run with --confirm-revoke to revoke the live ones above.")
    elif not live:
        log.info("")
        log.info("None of the %d pre-redaction keys are live in API_KEYS_KV -- nothing to rotate.", len(tenants))

    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
