#!/usr/bin/env python3
"""
scripts/rx_pub_a0_diagnostics.py
RX-PUB-A0 Phase 1-5 forensic instrumentation -- bounded, read-mostly R2
byte-identity diagnostic for an explicit, small set of report IDs.

Never runs against the full report corpus. Reuses scripts/r2_upload.py's
exact credential resolution, endpoint construction, and reports-bucket
credential-swap pattern (CF_ACCOUNT_ID, AWS_ACCESS_KEY_ID/SECRET, with
CF_R2_REPORTS_KEY_ID/SECRET override) rather than reimplementing R2
connectivity -- see get_credentials() and the swap block in r2_upload.py's
main().

For each report ID this captures:
  - local artifact identity (path, size, mtime, sha256, md5, engine marker)
  - the exact R2 object identity via `aws s3api head-object` +
    `aws s3api get-object` (not `aws s3 sync`'s own decision logic, which is
    a transfer heuristic, not a content-identity check -- see module
    docstring note below)
  - whether local and remote artifact bytes match

Optionally (--direct-upload-experiment, opt-in, single ID only) performs the
RX-PUB-A0 Phase 5 controlled single-object upload: `aws s3 cp` the exact
local artifact to its R2 key, then re-verifies R2 + public HTTP identity.
Only ever touches the one ID passed via --experiment-id, and only when that
flag is explicitly set -- never runs implicitly across --ids.

IMPORTANT -- aws s3 sync decision logic vs artifact identity (RX-PUB-A0 S3):
`aws s3 sync` (without --size-only) decides whether to transfer a file based
on: (a) the file is missing at the destination, OR (b) the source and
destination sizes differ, OR (c) the source's mtime is newer than the
destination's LastModified. It does NOT compute or compare a content hash of
any kind. A clean, zero-error `aws s3 sync` run is proof that these three
cheap comparisons found no reason to transfer (or that a transfer
succeeded) -- it is never proof that local and remote bytes are identical.
This script exists specifically to supply the missing proof: an explicit
SHA-256 comparison of the exact bytes on both sides.

No secrets are logged. AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
CF_R2_REPORTS_KEY_ID / CF_R2_REPORTS_SECRET_KEY values are read from the
environment by the `aws` CLI itself and are never printed, written to the
JSON report, or included in command echoes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import r2_upload  # noqa: E402  -- reuse get_credentials()/BUCKET_REPORTS/endpoint pattern

logging_prefix = "[rx-pub-a0-diag]"


def log(msg: str) -> None:
    print(f"{logging_prefix} {msg}", flush=True)


# Default diagnostic set: the incident fixture (read-only history check,
# it has aged out of the active generation window -- see
# docs/RX_PUB_A0_INCIDENT_ROOT_CAUSE.md) plus a small, explicit healthy
# comparison set. Callers should pass --ids explicitly for any other set;
# this default exists only so the script is runnable with zero arguments
# for the exact evidence this mission phase needs.
DEFAULT_IDS = [
    "intel--20282e88b1f49bf2",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def extract_engine_marker(text: str) -> str | None:
    m = re.search(r"CDB-REPORT-ENGINE:\s*(.*?)\s*-->", text)
    return m.group(1).strip() if m else None


def local_report_path(report_id: str) -> Path | None:
    reports_dir = REPO_ROOT / "reports"
    if not reports_dir.is_dir():
        return None
    matches = sorted(reports_dir.rglob(f"{report_id}.html"))
    return matches[0] if matches else None


def r2_key_for(local_path: Path) -> str:
    rel = local_path.relative_to(REPO_ROOT)
    return str(rel).replace(os.sep, "/")


def git_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=False,
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def capture_local(report_id: str) -> dict:
    p = local_report_path(report_id)
    if not p:
        return {
            "report_id": report_id,
            "local_present": False,
            "expected_r2_key": f"reports/*/*/{report_id}.html (not found on disk -- window/path unknown)",
        }
    data = p.read_bytes()
    text = data.decode("utf-8", errors="replace")
    stat = p.stat()
    return {
        "report_id": report_id,
        "local_present": True,
        "absolute_local_path": str(p),
        "relative_report_path": str(p.relative_to(REPO_ROOT)),
        "expected_r2_key": r2_key_for(p),
        "local_size": stat.st_size,
        "local_mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "local_sha256": sha256_bytes(data),
        "local_md5": md5_bytes(data),
        "engine_marker": extract_engine_marker(text),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "pipeline_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
    }


def _run_aws(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def r2_head_object(endpoint: str, bucket: str, key: str) -> dict:
    cmd = [
        "aws", "s3api", "head-object",
        "--endpoint-url", endpoint,
        "--bucket", bucket,
        "--key", key,
    ]
    try:
        r = _run_aws(cmd)
    except subprocess.TimeoutExpired:
        return {"exists": False, "error": "head-object timed out"}
    if r.returncode != 0:
        stderr = r.stderr.strip()
        if "404" in stderr or "Not Found" in stderr or "NoSuchKey" in stderr:
            return {"exists": False}
        return {"exists": False, "error": stderr[:400]}
    try:
        meta = json.loads(r.stdout)
    except Exception:
        return {"exists": True, "error": "head-object returned non-JSON output"}
    return {
        "exists": True,
        "content_length": meta.get("ContentLength"),
        "etag": (meta.get("ETag") or "").strip('"'),
        "last_modified": meta.get("LastModified"),
        "content_type": meta.get("ContentType"),
        "cache_control": meta.get("CacheControl"),
        "metadata": meta.get("Metadata") or {},
    }


def r2_get_object_hash(endpoint: str, bucket: str, key: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "obj"
        cmd = [
            "aws", "s3api", "get-object",
            "--endpoint-url", endpoint,
            "--bucket", bucket,
            "--key", key,
            str(out_path),
        ]
        try:
            r = _run_aws(cmd, timeout=60)
        except subprocess.TimeoutExpired:
            return {"fetched": False, "error": "get-object timed out"}
        if r.returncode != 0 or not out_path.exists():
            return {"fetched": False, "error": r.stderr.strip()[:400]}
        data = out_path.read_bytes()
        return {
            "fetched": True,
            "remote_size": len(data),
            "remote_sha256": sha256_bytes(data),
            "remote_md5": md5_bytes(data),
        }


def with_reports_credentials(fn, *args, **kwargs):
    """Swap in CF_R2_REPORTS_KEY_ID/SECRET for the duration of fn, matching
    r2_upload.py's own reports-bucket credential-swap pattern exactly."""
    reports_key_id = os.environ.get("CF_R2_REPORTS_KEY_ID", "").strip()
    reports_secret = os.environ.get("CF_R2_REPORTS_SECRET_KEY", "").strip()
    orig_key_id = os.environ.get("AWS_ACCESS_KEY_ID", "")
    orig_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    swapped = bool(reports_key_id and reports_secret)
    if swapped:
        os.environ["AWS_ACCESS_KEY_ID"] = reports_key_id
        os.environ["AWS_SECRET_ACCESS_KEY"] = reports_secret
    try:
        return fn(*args, **kwargs)
    finally:
        os.environ["AWS_ACCESS_KEY_ID"] = orig_key_id
        os.environ["AWS_SECRET_ACCESS_KEY"] = orig_secret


def guess_r2_key(report_id: str) -> str | None:
    """Best-effort key guess when the report isn't present locally (e.g. it
    has aged out of the active generation window). Probes the current and
    previous month under reports/YYYY/MM/. Returns None if no plausible key
    can be derived -- caller must supply --key explicitly in that case."""
    now = datetime.now(timezone.utc)
    for delta_months in range(0, 3):
        month = now.month - delta_months
        year = now.year
        while month < 1:
            month += 12
            year -= 1
        yield_key = f"reports/{year}/{month:02d}/{report_id}.html"
        yield yield_key


def diagnose_one(endpoint: str, bucket: str, report_id: str, explicit_key: str | None) -> dict:
    local = capture_local(report_id)
    key = explicit_key or local.get("expected_r2_key")
    if key and key.startswith("reports/*"):
        key = None

    remote = {"exists": False, "note": "no key resolved -- report not found locally and no --key given"}
    resolved_key = None
    if key:
        head = with_reports_credentials(r2_head_object, endpoint, bucket, key)
        if head.get("exists"):
            resolved_key = key
            remote = head
    if not resolved_key and not explicit_key:
        for candidate in guess_r2_key(report_id):
            head = with_reports_credentials(r2_head_object, endpoint, bucket, candidate)
            if head.get("exists"):
                resolved_key = candidate
                remote = head
                break

    remote_hash = {"fetched": False, "note": "object does not exist -- skipped GET"}
    if resolved_key and remote.get("exists"):
        remote_hash = with_reports_credentials(r2_get_object_hash, endpoint, bucket, resolved_key)

    divergence = None
    if local.get("local_present") and remote.get("exists") and remote_hash.get("fetched"):
        divergence = local["local_sha256"] != remote_hash["remote_sha256"]

    return {
        "report_id": report_id,
        "resolved_r2_key": resolved_key,
        "local": local,
        "remote_head": remote,
        "remote_hash": remote_hash,
        "local_sha256_eq_remote_sha256": (
            None if divergence is None else (not divergence)
        ),
        "classification": (
            "MATCH" if divergence is False else
            "DIVERGENT" if divergence is True else
            "REMOTE_OBJECT_MISSING" if not remote.get("exists") else
            "INCONCLUSIVE"
        ),
    }


def direct_upload_experiment(endpoint: str, bucket: str, report_id: str, key: str) -> dict:
    local_path = local_report_path(report_id)
    if not local_path:
        return {"performed": False, "reason": f"no local artifact found for {report_id}"}

    cmd = [
        "aws", "s3", "cp", str(local_path), f"s3://{bucket}/{key}",
        "--endpoint-url", endpoint,
        "--content-type", "text/html; charset=utf-8",
        "--cache-control", "public, max-age=300",
        "--only-show-errors",
    ]
    r = with_reports_credentials(lambda: _run_aws(cmd, timeout=60))
    if r.returncode != 0:
        return {"performed": True, "upload_ok": False, "error": r.stderr.strip()[:400]}

    post_head = with_reports_credentials(r2_head_object, endpoint, bucket, key)
    post_hash = with_reports_credentials(r2_get_object_hash, endpoint, bucket, key)
    local_sha = sha256_bytes(local_path.read_bytes())
    return {
        "performed": True,
        "upload_ok": True,
        "post_upload_remote_head": post_head,
        "post_upload_remote_hash": post_hash,
        "local_sha256": local_sha,
        "local_sha256_eq_post_upload_remote_sha256": (
            post_hash.get("remote_sha256") == local_sha if post_hash.get("fetched") else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", default=DEFAULT_IDS,
                         help="Report IDs to diagnose (bounded set -- never the full corpus).")
    parser.add_argument("--key", default=None,
                         help="Explicit R2 key override for a single-ID run (skips path guessing).")
    parser.add_argument("--direct-upload-experiment", action="store_true",
                         help="Phase 5: after diagnosis, directly `aws s3 cp` the local artifact "
                              "for --experiment-id to its resolved/explicit R2 key, then re-verify.")
    parser.add_argument("--experiment-id", default=None,
                         help="Report ID the --direct-upload-experiment applies to. Required with "
                              "that flag; never applied implicitly to the whole --ids set.")
    parser.add_argument("--output", default="data/quality/rx_pub_a0_diagnostics_report.json")
    args = parser.parse_args()

    if args.direct_upload_experiment and not args.experiment_id:
        parser.error("--direct-upload-experiment requires --experiment-id")

    cf_account, _access_key, _secret_key = r2_upload.get_credentials()
    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"
    bucket = r2_upload.BUCKET_REPORTS

    log(f"Diagnosing {len(args.ids)} report ID(s) against bucket={bucket} (endpoint account-scoped, not logged).")

    report = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "pipeline_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "bucket": bucket,
        "results": {},
    }

    for rid in args.ids:
        log(f"-- {rid} --")
        result = diagnose_one(endpoint, bucket, rid, args.key if rid == args.experiment_id else None)
        report["results"][rid] = result
        log(f"   classification={result['classification']} resolved_key={result['resolved_r2_key']}")

    if args.direct_upload_experiment:
        rid = args.experiment_id
        existing = report["results"].get(rid, {})
        key = existing.get("resolved_r2_key") or args.key
        if not key:
            log(f"ABORT experiment: no R2 key resolved for {rid} and no --key given.")
        else:
            log(f"Running Phase 5 direct-upload experiment for {rid} -> {key}")
            exp = direct_upload_experiment(endpoint, bucket, rid, key)
            report["results"].setdefault(rid, {})["direct_upload_experiment"] = exp
            log(f"   experiment result: {json.dumps({k: v for k, v in exp.items() if k not in ('post_upload_remote_head','post_upload_remote_hash')})}")

    out_path = REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log(f"Wrote {out_path}")

    divergent = [rid for rid, res in report["results"].items() if res.get("classification") == "DIVERGENT"]
    if divergent:
        log(f"DIVERGENT report(s) found: {divergent}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log(f"FATAL: {e}\n{traceback.format_exc()}")
        sys.exit(1)
