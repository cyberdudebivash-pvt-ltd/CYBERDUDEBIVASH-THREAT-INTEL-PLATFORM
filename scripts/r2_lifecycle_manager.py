#!/usr/bin/env python3
"""
scripts/r2_lifecycle_manager.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- R2 Native Lifecycle Policy Manager (P0 FinOps)
================================================================================
Manages Cloudflare R2's native object-lifecycle configuration (Expiration,
AbortIncompleteMultipartUpload) as code, per config/r2_lifecycle_policy.json.
This is the PREFERRED enforcement mechanism for the platform's pre-revenue
7-day ephemeral-retention mandate -- see that mandate's own instruction to
prefer Cloudflare-native lifecycle expiration over a recurring custom
LIST+DELETE sweep. This script never lists or deletes individual objects; it
only reads/writes ONE bucket-level lifecycle configuration document per
bucket (a single, tiny, non-recurring API call per invocation).

SCOPE, evidence-based (see docs/P0_R2_COST_CONTAINMENT.md Section 8 for the
full inventory this policy is derived from): only sentinel-apex-reports'
reports/ prefix gets an age-based Expiration rule. Every prefix in
sentinel-apex-data holds a single, overwrite-in-place "current state" key
(manifests, feeds, tiered products) rather than a date-partitioned
historical generation -- an age-based rule there would delete the ONLY copy
of currently-served data if the pipeline ever stalls past the expiration
window (this is not hypothetical: the 2026-09 dashboard-freshness incident
stalled report generation for ~10 days). AbortIncompleteMultipartUpload is
the one rule type safe to apply bucket-wide unconditionally -- it only ever
cleans up uploads that never completed, never a live object.

Modes (mirrors scripts/r2_reports_purge.py's established safety pattern):
  --show      Print the intended policy from config/r2_lifecycle_policy.json.
              No network call, no credentials required. DEFAULT when no
              mode flag is given.
  --verify    Read-only: GET the ACTUAL live lifecycle configuration from
              each bucket named in the policy and diff it against the
              intended policy. Requires real R2 credentials. Never mutates
              anything.
  --apply     Write the intended policy's lifecycle configuration to R2.
              Requires BOTH --execute AND --confirm-bucket <bucket> (per
              bucket being applied, exact match) -- an explicit,
              unambiguous statement of intent, identical in spirit to
              r2_reports_purge.py's own confirmation gate. Without
              --execute, --apply always dry-runs (prints the exact PUT
              payload, mutates nothing).

Usage:
  python3 scripts/r2_lifecycle_manager.py --show
  python3 scripts/r2_lifecycle_manager.py --verify
  python3 scripts/r2_lifecycle_manager.py --apply                                            # DRY RUN
  python3 scripts/r2_lifecycle_manager.py --apply --execute --confirm-bucket sentinel-apex-reports

Environment variables (same as scripts/r2_upload.py):
  CF_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from r2_upload import BUCKET_DATA, BUCKET_REPORTS, get_credentials, install_awscli  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [r2-lifecycle] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.r2_lifecycle_manager")

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / "config" / "r2_lifecycle_policy.json"
# Mirrors scripts/r2_reports_purge.py's PURGE_REPORT_PATH convention: a
# persisted, observable record of the last --verify/--apply outcome under
# this platform's standard data/quality/*.json location -- not a new
# P-layer certification (this is a manual admin tool, not a scheduled
# pipeline capability; see docs/P0_R2_COST_CONTAINMENT.md Section 8e for
# why a full P-layer observability surface was judged disproportionate
# here), but still a real, checkable artifact rather than log-only output.
LIFECYCLE_REPORT_PATH = REPO_ROOT / "data" / "quality" / "r2_lifecycle_report.json"

KNOWN_BUCKETS = {BUCKET_DATA, BUCKET_REPORTS}


def _write_report(mode: str, results: dict) -> None:
    report = {"mode": mode, **results}
    LIFECYCLE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIFECYCLE_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def load_policy() -> dict:
    if not POLICY_PATH.exists():
        raise SystemExit(f"FATAL: policy file not found: {POLICY_PATH}")
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def validate_policy(policy: dict) -> list[str]:
    """Returns a list of validation errors (empty = valid). Pure, no I/O --
    used both by the CLI (fail closed before any network call) and by the
    CI drift-gate tests (schema-only, never touches live R2)."""
    errors: list[str] = []
    max_days = policy.get("max_expiration_days_allowed")
    if not isinstance(max_days, int) or max_days <= 0:
        errors.append("max_expiration_days_allowed must be a positive integer")
        max_days = None

    rules = policy.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("policy must declare at least one rule in 'rules'")
        rules = []

    seen_ids: set[str] = set()
    for i, rule in enumerate(rules):
        label = f"rules[{i}]"
        if not isinstance(rule, dict):
            errors.append(f"{label} must be an object")
            continue
        rule_id = rule.get("rule_id")
        if not rule_id or not isinstance(rule_id, str):
            errors.append(f"{label}.rule_id missing")
        elif rule_id in seen_ids:
            errors.append(f"{label}.rule_id {rule_id!r} is a duplicate")
        else:
            seen_ids.add(rule_id)

        bucket = rule.get("bucket")
        if bucket not in KNOWN_BUCKETS:
            errors.append(f"{label}.bucket {bucket!r} is not one of {sorted(KNOWN_BUCKETS)}")
        if bucket == BUCKET_DATA:
            # Evidence-based exclusion (see module docstring) -- never
            # relaxed silently. A future edit that adds a sentinel-apex-data
            # rule must justify it explicitly by editing this check, not by
            # merely adding a config entry.
            errors.append(
                f"{label}: sentinel-apex-data may not carry an age-based Expiration rule "
                f"(see module docstring -- every prefix there is a single overwrite-in-place "
                f"current-state key, not a date-partitioned historical generation)"
            )

        prefix = rule.get("prefix")
        if not prefix or not isinstance(prefix, str):
            errors.append(f"{label}.prefix missing")
        elif bucket == BUCKET_REPORTS and prefix != "reports/":
            # CodeRabbit review finding (PR #377): the bucket-level check
            # above only rejects sentinel-apex-data -- without this, a
            # future config edit could add an Expiration rule for some
            # OTHER, unaudited prefix in sentinel-apex-reports (this bucket
            # currently has none, but nothing enforced that) and
            # build_lifecycle_configuration() would apply it unreviewed.
            # Only reports/ has been evidence-audited (see module
            # docstring) as safe for age-based expiration.
            errors.append(
                f"{label}: sentinel-apex-reports may only carry an Expiration rule for "
                f"the audited 'reports/' prefix, got {prefix!r}"
            )

        days = rule.get("expiration_days")
        if not isinstance(days, int) or days <= 0:
            errors.append(f"{label}.expiration_days must be a positive integer")
        elif max_days is not None and days > max_days:
            errors.append(
                f"{label}.expiration_days={days} exceeds max_expiration_days_allowed={max_days}"
            )

        if not rule.get("purpose"):
            errors.append(f"{label}.purpose missing (every rule must document why it exists)")

    multipart = policy.get("incomplete_multipart_abort_days", {})
    if isinstance(multipart, dict):
        for bucket, days in multipart.items():
            if bucket in ("_comment",):
                continue
            if bucket not in KNOWN_BUCKETS:
                errors.append(f"incomplete_multipart_abort_days has unknown bucket {bucket!r}")
            if not isinstance(days, int) or days <= 0:
                errors.append(f"incomplete_multipart_abort_days[{bucket!r}] must be a positive integer")
            elif max_days is not None and days > max_days:
                errors.append(
                    f"incomplete_multipart_abort_days[{bucket!r}]={days} exceeds "
                    f"max_expiration_days_allowed={max_days}"
                )

    return errors


def build_lifecycle_configuration(policy: dict, bucket: str) -> dict:
    """Builds the S3-compatible LifecycleConfiguration document for one
    bucket from the policy -- the exact shape `aws s3api
    put-bucket-lifecycle-configuration --lifecycle-configuration` expects.
    Returns {"Rules": []} (a valid, explicit "no rules for this bucket")
    when the policy declares none for it -- never omits the call entirely,
    so an existing stale rule on the live bucket is actively cleared, not
    silently left in place."""
    rules = []
    for rule in policy.get("rules", []):
        if rule.get("bucket") != bucket:
            continue
        rules.append({
            "ID": rule["rule_id"],
            "Filter": {"Prefix": rule["prefix"]},
            "Status": "Enabled",
            "Expiration": {"Days": rule["expiration_days"]},
        })

    multipart_days = policy.get("incomplete_multipart_abort_days", {}).get(bucket)
    if isinstance(multipart_days, int) and multipart_days > 0:
        rules.append({
            "ID": f"{bucket}-abort-incomplete-multipart",
            "Filter": {"Prefix": ""},
            "Status": "Enabled",
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": multipart_days},
        })

    return {"Rules": rules}


def cmd_show(policy: dict) -> int:
    errors = validate_policy(policy)
    print("=" * 70)
    print("R2 LIFECYCLE POLICY (from config/r2_lifecycle_policy.json)")
    print("=" * 70)
    print(json.dumps(policy, indent=2))
    print("-" * 70)
    if errors:
        print("SCHEMA VALIDATION: FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("SCHEMA VALIDATION: PASS")
    for bucket in sorted(KNOWN_BUCKETS):
        print(f"\nResolved LifecycleConfiguration for {bucket}:")
        print(json.dumps(build_lifecycle_configuration(policy, bucket), indent=2))
    return 0


def _run_aws(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def cmd_verify(policy: dict, endpoint: str) -> int:
    """Read-only. GETs the ACTUAL live lifecycle configuration for each
    bucket and diffs against the intended policy. Requires real credentials
    -- fails loudly (non-zero, clear message) rather than guessing when they
    are absent, per this platform's 'never claim production verification
    without querying production' rule."""
    overall_ok = True
    per_bucket: dict[str, dict] = {}
    for bucket in sorted(KNOWN_BUCKETS):
        expected = build_lifecycle_configuration(policy, bucket)
        actual, error = _get_live_configuration(bucket, endpoint)
        if actual is None:
            log.error("Could not read live lifecycle configuration for %s: %s", bucket, error)
            overall_ok = False
            per_bucket[bucket] = {"status": "READ_ERROR", "error": error}
            continue

        matches = actual == expected
        log.info("%s: live configuration %s intended policy", bucket, "MATCHES" if matches else "DOES NOT MATCH")
        per_bucket[bucket] = {"status": "MATCHES" if matches else "DRIFT", "expected": expected, "actual": actual}
        if not matches:
            overall_ok = False
            log.info("  expected: %s", json.dumps(expected))
            log.info("  actual:   %s", json.dumps(actual))

    _write_report("verify", {"overall_status": "PASS" if overall_ok else "DRIFT", "buckets": per_bucket})
    return 0 if overall_ok else 1


def _managed_rule_ids(policy: dict, bucket: str) -> set[str]:
    return {r["ID"] for r in build_lifecycle_configuration(policy, bucket)["Rules"]}


def _get_live_configuration(bucket: str, endpoint: str) -> tuple[dict | None, str | None]:
    """Returns (live_config, error). live_config is {"Rules": []} for a
    bucket with no lifecycle configuration at all (a real, valid state, not
    an error) -- distinguished from a genuine read failure via `error`."""
    cmd = [
        "aws", "s3api", "get-bucket-lifecycle-configuration",
        "--bucket", bucket,
        "--endpoint-url", endpoint,
        "--output", "json",
    ]
    result = _run_aws(cmd)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "NoSuchLifecycleConfiguration" in stderr:
            return {"Rules": []}, None
        return None, stderr[:500]
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return None, str(exc)
    return {"Rules": parsed.get("Rules", [])}, None


def cmd_apply(policy: dict, endpoint: str | None, *, execute: bool, confirm_bucket: str) -> int:
    buckets_in_policy = sorted({r["bucket"] for r in policy.get("rules", [])} | {
        b for b, d in policy.get("incomplete_multipart_abort_days", {}).items()
        if b in KNOWN_BUCKETS and isinstance(d, int) and d > 0
    })

    if execute:
        # CodeRabbit review finding (PR #377): this used to loop over EVERY
        # bucket in the policy regardless of --confirm-bucket, so
        # `--execute --confirm-bucket sentinel-apex-reports` still visited
        # sentinel-apex-data, found it didn't match, and returned exit 1 --
        # a successful single-bucket apply was indistinguishable from a
        # failure. --execute now targets exactly the confirmed bucket.
        if confirm_bucket not in buckets_in_policy:
            log.critical(
                "FATAL: --confirm-bucket %r does not name a bucket this policy declares "
                "rules for (%s). Refusing to apply.", confirm_bucket, sorted(buckets_in_policy),
            )
            return 1
        target_buckets = [confirm_bucket]
    else:
        target_buckets = buckets_in_policy

    exit_code = 0
    per_bucket: dict[str, dict] = {}
    for bucket in target_buckets:
        config_doc = build_lifecycle_configuration(policy, bucket)
        log.info("-" * 70)
        log.info("Bucket: %s", bucket)
        log.info("Intended LifecycleConfiguration (this policy's managed rules): %s", json.dumps(config_doc))

        if not execute:
            log.warning("[DRY-RUN] Would PUT this configuration. Re-run with --execute "
                        "--confirm-bucket %s to apply.", bucket)
            per_bucket[bucket] = {"status": "DRY_RUN", "intended": config_doc}
            continue

        # CodeRabbit review finding (PR #377, backed by AWS/R2 documentation):
        # PutBucketLifecycleConfiguration REPLACES the bucket's entire
        # lifecycle configuration -- it does not merge/append. Blindly PUTting
        # only this policy's rules would silently delete any pre-existing
        # rule this tool doesn't know about (e.g. configured manually via the
        # Cloudflare dashboard). Read-modify-write: GET first, and if the
        # live configuration contains any rule ID this policy doesn't
        # recognize as its own, abort rather than guess how to merge it --
        # merging a foreign rule's semantics safely cannot be automated, and
        # fail-closed-on-uncertainty is this codebase's established pattern
        # (see scripts/r2_cost_guard.py's enforce_budget()).
        live_config, get_error = _get_live_configuration(bucket, endpoint)
        if live_config is None:
            log.error("Could not read current live lifecycle configuration for %s before "
                      "applying (refusing to blindly overwrite): %s", bucket, get_error)
            exit_code = 1
            per_bucket[bucket] = {"status": "GET_ERROR", "error": get_error}
            continue
        managed_ids = _managed_rule_ids(policy, bucket)
        foreign_rules = [r for r in live_config["Rules"] if r.get("ID") not in managed_ids]
        if foreign_rules:
            log.critical(
                "FATAL: %s has %d existing lifecycle rule(s) this policy does not manage "
                "(IDs: %s). PutBucketLifecycleConfiguration would REPLACE the entire "
                "configuration and silently delete them. Refusing to apply -- review those "
                "rules manually, then either fold them into config/r2_lifecycle_policy.json "
                "or remove them via the Cloudflare dashboard before re-running.",
                bucket, len(foreign_rules), [r.get("ID") for r in foreign_rules],
            )
            exit_code = 1
            per_bucket[bucket] = {"status": "REFUSED_FOREIGN_RULES", "foreign_rule_ids": [r.get("ID") for r in foreign_rules]}
            continue

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(config_doc, fh)
            tmp_path = fh.name
        cmd = [
            "aws", "s3api", "put-bucket-lifecycle-configuration",
            "--bucket", bucket,
            "--endpoint-url", endpoint,
            "--lifecycle-configuration", f"file://{tmp_path}",
        ]
        result = _run_aws(cmd)
        if result.returncode != 0:
            log.error("PUT lifecycle configuration failed for %s: %s", bucket, result.stderr.strip()[:500])
            exit_code = 1
            per_bucket[bucket] = {"status": "PUT_FAILED", "error": result.stderr.strip()[:500]}
        else:
            log.info("Applied lifecycle configuration to %s.", bucket)
            per_bucket[bucket] = {"status": "APPLIED", "config": config_doc}

    if execute:
        _write_report("apply", {
            "overall_status": "PASS" if exit_code == 0 else "FAIL",
            "confirm_bucket": confirm_bucket,
            "buckets": per_bucket,
        })
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--show", action="store_true", help="Print the intended policy (default). No network call.")
    mode.add_argument("--verify", action="store_true", help="Read-only: diff live R2 config against intended policy.")
    mode.add_argument("--apply", action="store_true", help="Write the intended policy to R2 (dry-run unless --execute).")
    parser.add_argument("--execute", action="store_true", help="Actually mutate R2 (only meaningful with --apply).")
    parser.add_argument("--confirm-bucket", default="",
                        help="Must exactly match the bucket being applied, in addition to --execute.")
    args = parser.parse_args()

    policy = load_policy()

    if args.verify or args.apply:
        errors = validate_policy(policy)
        if errors:
            log.critical("FATAL: policy failed schema validation -- refusing to touch R2. Errors:")
            for e in errors:
                log.critical("  - %s", e)
            return 1

        # --apply without --execute is a pure, local dry-run -- it only
        # prints what WOULD be PUT (fully derivable from the policy file
        # already validated above), so it needs no credentials and makes no
        # network call at all. Real credentials are fetched only when a
        # live R2 call is actually about to happen: --verify (always a live
        # GET) or --apply --execute (a live PUT).
        if args.apply and not args.execute:
            return cmd_apply(policy, None, execute=False, confirm_bucket=args.confirm_bucket)

        cf_account, _access_key, _secret_key = get_credentials()
        endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"
        install_awscli()
        if args.verify:
            return cmd_verify(policy, endpoint)
        return cmd_apply(policy, endpoint, execute=args.execute, confirm_bucket=args.confirm_bucket)

    return cmd_show(policy)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log.critical("Unhandled exception in r2_lifecycle_manager.py:\n%s\n%s", e, traceback.format_exc())
        sys.exit(1)
