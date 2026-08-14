#!/usr/bin/env python3
"""
scripts/r2_reports_verifier.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- RX-PUB-A0 Reports Artifact Identity Verifier

RX-PUB-A0 Phase 9 / Sections 19-25: closes the gap documented in
docs/RX_PUB_A0_INCIDENT_ROOT_CAUSE.md and docs/RX_PUB_A0_EXECUTION_PATH.md --
scripts/r2_upload_verifier.py (STAGE 3.6) already does exactly this kind of
authenticated, hash-based, HARD FAIL post-upload verification, but is scoped
exclusively to the single data-bucket manifest object
(sentinel-apex-data/intel/feed_manifest.json). It never checks a single
reports/*.html object. This script is the same verification pattern --
reused via direct import, not reimplemented -- applied to the actual
customer-facing report artifacts.

Per the mission's Section 3 correction: a clean `aws s3 sync` exit code is a
transfer-decision fact (missing / size differs / mtime newer), never a
content-identity proof. This script supplies the missing proof directly:
SHA-256 of the exact bytes on both sides.

SCOPE (bounded, not the full ~15k+ historical corpus -- see Section 36 cost
governance): verifies every report currently in the active generation
window (data/stix/feed_manifest.json) -- the same set
generate_intel_reports.py's "Zero-skip" policy unconditionally regenerates
every pipeline run, so this is exactly the "changed this run" set the
mission's Section 22 requires full (non-sampled) verification for. Historical
reports outside this window are out of scope per Section 26.

For each in-window report:
  Layer A (cheap, always): S3 API head-object -- existence, size, ETag.
  Layer B (SHA-256, always for in-window reports): S3 API get-object -> SHA-256
    of the exact remote bytes, compared against the local file's SHA-256.

Writes data/quality/rx_pub_a0_reports_artifact_manifest.json (Phase 9 schema)
and HARD FAILS (nonzero exit) if any in-window report's remote SHA-256 does
not match its local SHA-256, or does not exist in R2 at all.

Environment variables consumed (same names r2_upload.py already uses):
  CF_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
  CF_R2_REPORTS_KEY_ID, CF_R2_REPORTS_SECRET_KEY (optional, preferred if set --
    same dedicated-token swap pattern as r2_upload.py's reports-upload phase)

No secrets are logged.

RX-PUB-A0.4 Phase 2 extension (Sections 12-16): also fetches the
customer-facing public HTTP URL for each in-window report and computes its
SHA-256, closing the R2-vs-CUSTOMER half of the identity chain PR #183 left
open (it only closed LOCAL-vs-R2). Per Section 4's reuse mandate this is an
extension of this same script/manifest, not a new parallel verifier --
public fetches need no R2 credentials at all, so they run independently of
whether the R2 credential-gated checks above ran. Distinguishes "R2 object
correct but customer response stale" from "R2 object itself wrong" by
capturing both facts per report rather than conflating them into one
pass/fail bit.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# RX-PUB-A0: swap in the dedicated reports-bucket credentials (if configured)
# BEFORE importing r2_upload_verifier, whose R2 connection helpers
# (_s3api_head_object / _boto3_head_object) read CF_ACCOUNT_ID / ACCESS_KEY /
# SECRET_KEY as module-level constants captured at import time -- same
# swap-then-restore pattern r2_upload.py's main() already uses for its own
# reports-bucket upload phase.
_reports_key_id = os.environ.get("CF_R2_REPORTS_KEY_ID", "").strip()
_reports_secret = os.environ.get("CF_R2_REPORTS_SECRET_KEY", "").strip()
_orig_key_id    = os.environ.get("AWS_ACCESS_KEY_ID", "")
_orig_secret    = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
if _reports_key_id and _reports_secret:
    os.environ["AWS_ACCESS_KEY_ID"]     = _reports_key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = _reports_secret

import r2_upload_verifier as _verifier  # noqa: E402 -- reuse, not reimplement
import r2_upload as _r2_upload  # noqa: E402 -- BUCKET_REPORTS, get_credentials()

# Restore whatever the job-level credentials were, now that the reports-scoped
# constants have been captured inside _verifier's module globals.
os.environ["AWS_ACCESS_KEY_ID"]     = _orig_key_id
os.environ["AWS_SECRET_ACCESS_KEY"] = _orig_secret

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [rx-pub-a0-reports-verify] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.rx_pub_a0_reports_verifier")

MANIFEST_PATH   = REPO_ROOT / "data" / "stix" / "feed_manifest.json"
OUTPUT_PATH     = REPO_ROOT / "data" / "quality" / "rx_pub_a0_reports_artifact_manifest.json"
BUCKET_REPORTS  = _r2_upload.BUCKET_REPORTS
GENERATOR_NAME  = "generate_intel_reports.py"
PUBLIC_BASE_URL = os.environ.get("RX_PUB_A0_PUBLIC_BASE_URL", "https://intel.cyberdudebivash.com")
PUBLIC_TIMEOUT  = 15
PUBLIC_MAX_RETRIES = 3
PUBLIC_RETRY_DELAY = 3
# CodeRabbit finding: worst case (every report exhausts retries) is
# PUBLIC_MAX_RETRIES * (PUBLIC_TIMEOUT + PUBLIC_RETRY_DELAY) per report --
# at 150+ in-window reports that can exceed STAGE 3.6a's workflow timeout
# (deploy-worker.yml / sentinel-blogger.yml, 15 min) before this script ever
# reaches its own manifest write, losing ALL results for the run rather than
# just the unreachable ones. RUN_DEADLINE_SECONDS bounds total wall-clock
# time across the whole in-window loop (both R2 and public layers) well
# under that limit; any report not yet started when the deadline is hit is
# recorded explicitly (not silently dropped) and the manifest is still
# written with everything processed so far.
RUN_DEADLINE_SECONDS = 600
_SAFE_RESPONSE_HEADERS = (
    "cf-ray", "cache-control", "age", "etag", "last-modified",
    "cf-cache-status", "content-length", "content-type",
)

# RX-PUB-A0.6B: same Cloudflare zone-level cache-purge secrets
# .github/workflows/dashboard-feeds-sync.yml already uses for its own static
# URL list (Section 4 reuse mandate) -- not a new credential. Both optional:
# if unset, purge is skipped (never attempted, never a hard failure) exactly
# like that workflow's own "[SKIP] CF_ZONE_ID or CF_CACHE_PURGE_TOKEN not
# configured" behavior.
CF_ZONE_ID          = os.environ.get("CF_ZONE_ID", "").strip()
CF_CACHE_PURGE_TOKEN = os.environ.get("CF_CACHE_PURGE_TOKEN", "").strip()
CACHE_PURGE_TIMEOUT = 15


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_in_window_entries() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Cannot parse %s: %s", MANIFEST_PATH, e)
        return []
    if isinstance(data, list):
        return data
    for key in ("advisories", "items", "data", "entries"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def _local_report_path(entry: dict) -> Path | None:
    ru = (entry.get("internal_report_url") or entry.get("report_url") or "").strip()
    if ru.startswith("/"):
        p = REPO_ROOT / ru.lstrip("/")
        return p if p.exists() else None
    intel_id = entry.get("id") or entry.get("stix_id")
    if not intel_id:
        return None
    matches = sorted((REPO_ROOT / "reports").rglob(f"{intel_id}.html"))
    return matches[0] if matches else None


def _r2_key_for(local_path: Path) -> str:
    return str(local_path.relative_to(REPO_ROOT)).replace(os.sep, "/")


class PublicFetchConfigError(ValueError):
    """PUBLIC_BASE_URL (or RX_PUB_A0_PUBLIC_BASE_URL override) failed the
    scheme/host allowlist check. Raised at call time, not import time, so a
    bad override fails the specific fetch loudly rather than silently
    falling through to an unrestricted request."""


def _validate_public_url(url: str) -> None:
    """CodeRabbit SSRF finding (CWE-918): RX_PUB_A0_PUBLIC_BASE_URL is
    CI-environment-controlled, not end-user input, so the practical exposure
    is low -- but urlopen() with a request-influenced URL and no host/scheme
    restriction is exactly the ast-grep urlopen-unsanitized-data pattern, and
    costs nothing to close. HTTPS-only, plus an explicit allowlist covering
    the real production host and RX_PUB_A0_PUBLIC_ALLOWED_HOSTS-provided test
    hosts (comma-separated, e.g. for local/dev overrides) -- never a wildcard
    fallback that would defeat the allowlist's purpose."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise PublicFetchConfigError(f"public fetch URL must be https, got scheme={parsed.scheme!r}: {url}")
    extra_hosts = {
        h.strip().lower() for h in os.environ.get("RX_PUB_A0_PUBLIC_ALLOWED_HOSTS", "").split(",") if h.strip()
    }
    allowed_hosts = {"intel.cyberdudebivash.com"} | extra_hosts
    if (parsed.hostname or "").lower() not in allowed_hosts:
        raise PublicFetchConfigError(
            f"public fetch host {parsed.hostname!r} not in allowlist {sorted(allowed_hosts)} "
            f"(set RX_PUB_A0_PUBLIC_ALLOWED_HOSTS to add test hosts): {url}"
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Disables following redirects entirely for the public fetch opener --
    simpler and strictly safer than validating each redirect hop against the
    allowlist, and this endpoint family has no legitimate reason to redirect."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_PUBLIC_OPENER = urllib.request.build_opener(_NoRedirect)


def _fetch_public(url: str) -> dict:
    """GET the customer-facing public URL. Returns a dict with 'bytes' (or
    None on failure), 'status', and safe response headers only -- never logs
    or returns the raw response body beyond what the caller hashes in
    memory. Bounded retries, matching the R2 helpers' retry policy. Redirects
    are not followed (see _NoRedirect) and the target is validated against an
    HTTPS+host allowlist before every attempt (see _validate_public_url)."""
    _validate_public_url(url)
    last_status = None
    last_error = None
    last_headers: dict = {}
    for attempt in range(1, PUBLIC_MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers={"User-Agent": "SentinelApex-RX-PUB-A0-Verifier/1.0"})
        try:
            with _PUBLIC_OPENER.open(req, timeout=PUBLIC_TIMEOUT) as resp:
                body = resp.read()
                headers = {k.lower(): v for k, v in resp.getheaders() if k.lower() in _SAFE_RESPONSE_HEADERS}
                return {"bytes": body, "status": resp.status, "headers": headers, "error": None}
        except urllib.error.HTTPError as e:
            last_status = e.code
            last_headers = {k.lower(): v for k, v in (e.headers.items() if e.headers else []) if k.lower() in _SAFE_RESPONSE_HEADERS}
            if e.code == 404:
                return {"bytes": None, "status": 404, "headers": last_headers, "error": "HTTP 404"}
            last_error = f"HTTP {e.code}"
        except Exception as e:
            last_error = str(e)
        if attempt < PUBLIC_MAX_RETRIES:
            time.sleep(PUBLIC_RETRY_DELAY)
    return {"bytes": None, "status": last_status, "headers": last_headers, "error": last_error or "fetch failed"}


# RX-PUB-A0.6A: publication-gate awareness. Calls the platform's own,
# already-live /api/v1/reports/{id}/publication-status endpoint -- the same
# HTTP-boundary-reuse pattern _fetch_public already uses for report bodies --
# rather than re-deriving a P20/P21/P23/P25/P26 verdict in Python (mission
# Section 5's explicit prohibition on duplicating that logic).
PUBLICATION_STATUS_PATH_TEMPLATE = "api/v1/reports/{intel_id}/publication-status"


def _fetch_publication_status(intel_id: str) -> dict:
    """Returns {"customer_ready": bool|None, "state": str|None,
    "reason_codes": list, "fetch_error": str|None}. A None customer_ready
    always means "we could not determine this," never "false" -- callers
    must not treat a fetch failure as an implicit denial verdict."""
    url = f"{PUBLIC_BASE_URL}/{PUBLICATION_STATUS_PATH_TEMPLATE.format(intel_id=intel_id)}"
    try:
        resp = _fetch_public(url)
    except PublicFetchConfigError as e:
        return {"customer_ready": None, "state": None, "reason_codes": [], "fetch_error": str(e)}
    if resp["bytes"] is None:
        return {
            "customer_ready": None, "state": None, "reason_codes": [],
            "fetch_error": resp.get("error") or f"HTTP {resp.get('status')}",
        }
    try:
        data = json.loads(resp["bytes"])
    except Exception as e:
        return {"customer_ready": None, "state": None, "reason_codes": [], "fetch_error": f"invalid JSON: {e}"}
    return {
        "customer_ready": data.get("customer_ready"),
        "state":          data.get("state"),
        "reason_codes":   data.get("reason_codes") or [],
        "fetch_error":    None,
    }


def _expected_live_behavior(pub_status: dict) -> str:
    """Maps a publication-status result to what the public HTTP layer SHOULD
    do, per mission Section 6. PENDING_PUBLICATION / HISTORICAL_POLICY are
    reserved for future extension -- the live publication-status API does not
    yet return either, so they are never produced here; adding them later is
    additive (new elif branch), not a breaking change to this function."""
    if pub_status.get("fetch_error"):
        return "UNKNOWN_EXPECTATION"
    customer_ready = pub_status.get("customer_ready")
    if customer_ready is True:
        return "SERVE_CANONICAL_ARTIFACT"
    if customer_ready is False:
        if "ITEM_NOT_RESOLVABLE" in (pub_status.get("reason_codes") or []):
            return "UNKNOWN_EXPECTATION"
        return "DENY_PUBLICATION_GATE"
    return "UNKNOWN_EXPECTATION"


def _unresolvable_live_state(pub_status: dict) -> str:
    """Distinguishes, within UNKNOWN_EXPECTATION, a platform-side resolver
    gap (LIVE_RESOLUTION_FAILED -- RX-PUB-A0.6C's target) from this
    verifier's own inability to reach/parse publication-status
    (LIVE_UNKNOWN -- a verifier-side transient, not a platform defect)."""
    if pub_status.get("fetch_error"):
        return "LIVE_UNKNOWN"
    if "ITEM_NOT_RESOLVABLE" in (pub_status.get("reason_codes") or []):
        return "LIVE_RESOLUTION_FAILED"
    return "LIVE_UNKNOWN"


def _purge_public_url(url: str) -> bool:
    """RX-PUB-A0.6B: precise, single-URL Cloudflare cache purge -- never a
    zone-wide purge (mission Section 14). Reuses the exact CF_ZONE_ID /
    CF_CACHE_PURGE_TOKEN secrets and purge_cache API call
    .github/workflows/dashboard-feeds-sync.yml already uses for its own
    static URL list; this is the same mechanism applied to a dynamically
    detected stale report URL instead of a fixed list.

    Returns True only on a confirmed-successful Cloudflare API response.
    Never raises -- a purge failure must never crash STAGE 3.6a or be
    confused with an R2/identity failure. Never logs the token.

    Ordering contract (mission Section 15): callers MUST only invoke this
    after the R2 layer has confirmed remote_sha256 == artifact_sha256 for
    this exact report -- never purge toward a canonical object that has not
    been verified. verify_one() below enforces this by construction (this
    function is only reachable from the SERVE_CANONICAL_ARTIFACT branch,
    which runs after the R2-layer check)."""
    if not (CF_ZONE_ID and CF_CACHE_PURGE_TOKEN):
        return False
    try:
        _validate_public_url(url)
    except PublicFetchConfigError:
        # Same host/scheme allowlist as every other outbound call in this
        # script (mission Section 36) -- never purge an unvalidated target.
        return False
    try:
        body = json.dumps({"files": [url]}).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/purge_cache",
            data=body, method="POST",
            headers={
                "Authorization": f"Bearer {CF_CACHE_PURGE_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=CACHE_PURGE_TIMEOUT) as resp:
            result = json.loads(resp.read())
            return bool(result.get("success"))
    except Exception as e:
        log.warning("Cache purge request failed for %s: %s", url, e)
        return False


def _attempt_purge_and_reverify(result: dict, public_url: str, local_sha256: str) -> None:
    """RX-PUB-A0.6B: mutates `result` in place. Only ever called for a
    report the publication gate expects to serve, and only from call sites
    that have already confirmed `publication_state == "REMOTE_VERIFIED"`
    (mission Section 15 -- never purge toward an unverified canonical
    object). Purges the exact URL once, then re-fetches once (bounded, not
    a retry loop -- a purge either takes effect promptly or it did not
    succeed) to check whether the edge has converged with R2."""
    result["cache_purge_attempted"] = True
    purged = _purge_public_url(public_url)
    result["cache_purge_succeeded"] = purged
    if not purged:
        result["public_still_stale"] = True
        return
    try:
        recheck = _fetch_public(public_url)
    except PublicFetchConfigError:
        result["public_still_stale"] = True
        return
    if recheck["bytes"] is not None and _sha256_bytes(recheck["bytes"]) == local_sha256:
        result["live_state"] = "LIVE_VERIFIED"
        result["public_sha256"] = local_sha256
        result["public_verified_at"] = _verifier._utc_now()
        result["public_verified_after_invalidation"] = True
        result["public_response_headers"] = recheck["headers"]
        result.pop("public_error", None)
    else:
        result["public_still_stale"] = True


def verify_one(local_path: Path, r2_key: str, skip_public: bool = False) -> dict:
    local_bytes = local_path.read_bytes()
    local_sha256 = _sha256_bytes(local_bytes)
    result = {
        "r2_key":         r2_key,
        "size_bytes":     len(local_bytes),
        "generator":      GENERATOR_NAME,
        "artifact_sha256": local_sha256,
        "remote_sha256":  None,
        "remote_verified_at": None,
        "publication_state": "PENDING",
        "public_sha256":  None,
        "public_verified_at": None,
        "live_state":     "PENDING",
        "public_response_headers": {},
        # RX-PUB-A0.6A: publication-gate-aware fields (see _fetch_publication_status /
        # _expected_live_behavior below). None until the public-HTTP layer runs.
        "publication_gate_state": None,
        "customer_ready": None,
        "expected_live_behavior": None,
        "publication_gate_bypass": False,
        # RX-PUB-A0.6B
        "cache_purge_attempted": False,
        "cache_purge_succeeded": None,
        "public_verified_after_invalidation": False,
        "public_still_stale": False,
    }

    # -- R2 layer (LOCAL vs R2) -----------------------------------------
    head = _verifier._s3api_head_object(BUCKET_REPORTS, r2_key)
    if head is None:
        head = _verifier._boto3_head_object(BUCKET_REPORTS, r2_key)

    if head is None:
        result["publication_state"] = "UNKNOWN"
        result["error"] = "head-object failed via both awscli and boto3"
    elif head["status"] == 404:
        result["publication_state"] = "FAILED"
        result["error"] = "R2 object does not exist"
    else:
        remote_bytes = _get_object_bytes(BUCKET_REPORTS, r2_key)
        if remote_bytes is None:
            result["publication_state"] = "UNKNOWN"
            result["error"] = "get-object failed -- could not fetch remote bytes for SHA-256 comparison"
        else:
            remote_sha256 = _sha256_bytes(remote_bytes)
            result["remote_sha256"] = remote_sha256
            result["remote_verified_at"] = _verifier._utc_now()
            if remote_sha256 == local_sha256:
                result["publication_state"] = "REMOTE_VERIFIED"
            else:
                result["publication_state"] = "STALE_OR_DIVERGENT"
                result["error"] = (
                    f"artifact_sha256 ({local_sha256[:16]}...) != remote_sha256 "
                    f"({remote_sha256[:16]}...) -- local and R2 bytes diverge"
                )

    # -- Public HTTP layer (R2 vs CUSTOMER) -- runs independently of the --
    # R2 credential-gated checks above; needs no R2 credentials at all.
    if skip_public:
        return result

    # RX-PUB-A0.6A: before judging byte identity, determine what the
    # platform's own publication gate says SHOULD happen for this report.
    # Reuses the already-live, already-authoritative
    # /api/v1/reports/{id}/publication-status endpoint (wrapping
    # evaluatePublicationGate) -- per mission Section 5, never reimplements
    # P20/P21/P23/P25/P26 logic in Python. RX-PUB-A0.5 Run 1 (PR #192) and
    # RX-PUB-A0.6's Phase 0 (docs/RX_PUB_A0_6_PROOF_BEFORE_CHANGE.md) showed
    # that treating every non-matching byte comparison as "divergence" was
    # wrong: most of them were the gate correctly denying a below-threshold
    # report, or a resolver miss the gate never got to evaluate at all.
    intel_id = Path(r2_key).stem
    pub_status = _fetch_publication_status(intel_id)
    result["publication_gate_state"] = pub_status.get("state")
    result["customer_ready"] = pub_status.get("customer_ready")
    expected = _expected_live_behavior(pub_status)
    result["expected_live_behavior"] = expected

    public_url = f"{PUBLIC_BASE_URL}/{r2_key}"
    try:
        public = _fetch_public(public_url)
    except PublicFetchConfigError as e:
        result["live_state"] = "LIVE_FETCH_FAILED"
        result["public_error"] = f"public fetch target rejected by allowlist: {e}"
        return result
    result["public_response_headers"] = public["headers"]
    served_is_html = "text/html" in (public["headers"].get("content-type") or "")

    if public["status"] == 404:
        if expected == "DENY_PUBLICATION_GATE":
            result["live_state"] = "LIVE_EXPECTED_DENIAL"
        elif expected == "SERVE_CANONICAL_ARTIFACT":
            result["live_state"] = "LIVE_MISSING_UNEXPECTED"
            result["public_error"] = (
                "publication gate says customer_ready=true but public HTTP GET returned 404"
            )
            # RX-PUB-A0.6B: a 404 for a gate-approved report whose R2 copy
            # is independently confirmed correct could be a stale/negative
            # cache entry (mission Section 13) -- try a precise purge and
            # one re-fetch before accepting this as a genuine defect. Never
            # purges toward an object R2 itself hasn't verified.
            if result["publication_state"] == "REMOTE_VERIFIED":
                _attempt_purge_and_reverify(result, public_url, local_sha256)
        else:
            result["live_state"] = _unresolvable_live_state(pub_status)
            result["public_error"] = "public HTTP GET returned 404; publication gate could not evaluate this report"
    elif public["bytes"] is None:
        result["live_state"] = "LIVE_FETCH_FAILED"
        result["public_error"] = public.get("error") or "public HTTP GET failed"
    else:
        public_sha256 = _sha256_bytes(public["bytes"])
        result["public_sha256"] = public_sha256
        result["public_verified_at"] = _verifier._utc_now()
        served_matches_canonical = public_sha256 == local_sha256

        if expected == "DENY_PUBLICATION_GATE" and public["status"] == 200 and served_is_html:
            # HARD DEFECT (mission RX-PUB-A0.6 Section 9, verbatim): the
            # publication gate says this report must not be served, but the
            # public route returned a real HTML body anyway -- regardless of
            # whether that body happens to match the canonical artifact.
            # Never silently folded into LIVE_STALE_OR_DIVERGENT.
            result["live_state"] = "PUBLICATION_GATE_BYPASS"
            result["publication_gate_bypass"] = True
            result["public_error"] = (
                "HARD DEFECT: publication gate says customer_ready=false but the public "
                "route served an HTML body -- publication gate bypass"
            )
        elif expected == "DENY_PUBLICATION_GATE":
            # 200 but not an HTML body (e.g. the gate's own JSON denial
            # response) -- correct, expected behavior.
            result["live_state"] = "LIVE_EXPECTED_DENIAL"
        elif expected == "SERVE_CANONICAL_ARTIFACT":
            if served_matches_canonical:
                result["live_state"] = "LIVE_VERIFIED"
            else:
                result["live_state"] = "LIVE_STALE_OR_DIVERGENT"
                result["public_error"] = (
                    f"artifact_sha256 ({local_sha256[:16]}...) != public_sha256 "
                    f"({public_sha256[:16]}...) -- local and customer-served bytes diverge"
                )
                # RX-PUB-A0.6B: the confirmed root cause (docs/RX_PUB_A0_6_
                # PROOF_BEFORE_CHANGE.md Phase 0) -- a gate-approved,
                # R2-verified-correct report can still be served stale
                # bytes by a lagging Cloudflare edge POP. Purge the exact
                # URL and re-check once before accepting this as terminal.
                if result["publication_state"] == "REMOTE_VERIFIED":
                    _attempt_purge_and_reverify(result, public_url, local_sha256)
        else:
            # UNKNOWN_EXPECTATION: the gate never evaluated this report (a
            # resolver miss / ITEM_NOT_RESOLVABLE), or our own fetch of its
            # verdict failed -- byte equality is not a meaningful question
            # when we don't know what SHOULD be served (mission Section 30,
            # Question B unanswerable). Never counted as a hash match or a
            # divergence either way.
            result["live_state"] = _unresolvable_live_state(pub_status)
            result["public_error"] = (
                "publication gate could not evaluate this report -- serving status not "
                "verifiable against an expectation"
            )

    return result


def _get_object_bytes(bucket: str, key: str) -> bytes | None:
    """get-object via the same awscli s3api pattern _s3api_head_object uses.
    Not present in r2_upload_verifier.py (it only ever needed head-object) --
    this is the one genuinely new primitive this script adds, kept as small
    and consistent with the existing helper's style as possible."""
    import subprocess
    import tempfile

    if not (_verifier.CF_ACCOUNT_ID and _verifier.ACCESS_KEY and _verifier.SECRET_KEY):
        return None

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"]     = _verifier.ACCESS_KEY
    env["AWS_SECRET_ACCESS_KEY"] = _verifier.SECRET_KEY
    env["AWS_DEFAULT_REGION"]    = "auto"

    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "obj"
        cmd = [
            "aws", "s3api", "get-object",
            "--bucket", bucket, "--key", key,
            "--endpoint-url", _verifier.R2_ENDPOINT,
            str(out_path),
        ]
        for attempt in range(1, _verifier.MAX_RETRIES + 1):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=_verifier.REQUEST_TIMEOUT, env=env,
                )
                if result.returncode == 0 and out_path.exists():
                    return out_path.read_bytes()
                log.warning(
                    "get-object failed (attempt %d/%d) for s3://%s/%s: rc=%d stderr=%s",
                    attempt, _verifier.MAX_RETRIES, bucket, key,
                    result.returncode, result.stderr.strip()[:200],
                )
            except Exception as e:
                log.warning(
                    "get-object error (attempt %d/%d) for s3://%s/%s: %s",
                    attempt, _verifier.MAX_RETRIES, bucket, key, e,
                )
            if attempt < _verifier.MAX_RETRIES:
                time.sleep(_verifier.RETRY_DELAY)
    return None


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enforce", action="store_true",
        help="Hard-fail (nonzero exit) on any STALE_OR_DIVERGENT/FAILED R2 report or "
             "LIVE_STALE_OR_DIVERGENT public report. Not passed in CI yet -- "
             "observability-only bake-in period, matching the same rollout pattern "
             "scripts/report_engine_consistency_gate.py already established for a new "
             "gate on this exact keyspace. Once a run history exists showing zero "
             "false positives, add --enforce to the STAGE 3.6a workflow step to make "
             "this a real HARD FAIL gate (RX-PUB-A0 Section 25 requires this eventually)."
    )
    parser.add_argument(
        "--skip-public", action="store_true",
        help="Skip the public HTTP fetch/SHA-256 layer (R2-only, PR #183's original "
             "scope). Escape hatch for cost governance (Section 37) if public "
             "verification duration becomes a measured problem; not used by default."
    )
    args = parser.parse_args()

    r2_creds_present = bool(_verifier.CF_ACCOUNT_ID and _verifier.ACCESS_KEY and _verifier.SECRET_KEY)

    log.info("=" * 70)
    log.info("RX-PUB-A0 Reports Artifact Identity Verifier")
    log.info("Bucket: %s  |  in-window manifest: %s", BUCKET_REPORTS, MANIFEST_PATH)
    log.info("Public base URL: %s  |  public checks: %s", PUBLIC_BASE_URL, "OFF" if args.skip_public else "ON")
    log.info("R2 credentials: %s", "configured" if r2_creds_present else "missing")
    log.info("Mode: %s", "ENFORCE (hard fail on mismatch)" if args.enforce else "observability-only (bake-in)")
    log.info("=" * 70)
    t0 = time.time()

    if not r2_creds_present and args.skip_public:
        log.warning(
            "R2 credentials absent and --skip-public set -- nothing to verify. "
            "Trusting Stage 3.5 exit code as source of truth for this run (same "
            "soft-pass posture as r2_upload_verifier.py's own credential-absent path)."
        )
        return 0
    if not r2_creds_present:
        log.warning(
            "R2 credentials absent (CF_ACCOUNT_ID / AWS_ACCESS_KEY_ID / "
            "AWS_SECRET_ACCESS_KEY) -- R2 layer will classify every report UNKNOWN. "
            "Public HTTP layer needs no R2 credentials and still runs."
        )

    entries = _load_in_window_entries()
    log.info("In-window manifest entries: %d", len(entries))

    manifest_out: dict = {
        "schema_version": "2",
        "generated_at":   _verifier._utc_now(),
        "pipeline_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "release_sha":    os.environ.get("GITHUB_SHA", "unknown"),
        "bucket":         BUCKET_REPORTS,
        "public_base_url": PUBLIC_BASE_URL,
        "reports":        {},
    }

    verified = 0
    mismatched = 0
    missing_local = 0
    unknown = 0
    live_verified = 0
    live_mismatched = 0
    live_unknown = 0
    # RX-PUB-A0.6A: distinct counters per mission Section 32 -- an expected
    # denial must never be combined with a genuine failure, and a bypass
    # must never be silently absorbed into either.
    live_expected_denial = 0
    live_resolution_failed = 0
    live_fetch_failed = 0
    live_not_processed_deadline = 0
    publication_gate_bypass = 0
    # RX-PUB-A0.6B: mission Section 35 -- event-derived only, counted from
    # what _attempt_purge_and_reverify actually recorded per report.
    cache_invalidations_attempted = 0
    cache_invalidations_succeeded = 0
    cache_invalidations_failed = 0
    public_verified_after_invalidation = 0
    public_still_stale = 0

    deadline_hit = False
    for _loop_idx, entry in enumerate(entries):
        intel_id = entry.get("id") or entry.get("stix_id")
        if not intel_id:
            continue

        if not deadline_hit and (time.time() - t0) > RUN_DEADLINE_SECONDS:
            deadline_hit = True
            log.error(
                "Run deadline (%ds) exceeded after %d/%d reports -- stopping "
                "and recording the rest as UNVERIFIED_DEADLINE rather than "
                "silently dropping them or letting the workflow step timeout "
                "kill this process before it writes the manifest.",
                RUN_DEADLINE_SECONDS, _loop_idx, len(entries),
            )

        if deadline_hit:
            # RX-PUB-A0.6A: explicit deadline classification (mission Section
            # 26/27) -- distinct from a genuine fetch/resolution failure so a
            # future --enforce pass can treat "never reached" differently
            # from "reached and failed" if that distinction ever matters,
            # and so this never silently reads as an ordinary UNKNOWN.
            manifest_out["reports"][intel_id] = {
                "publication_state": "NOT_PROCESSED_DEADLINE",
                "live_state": "LIVE_NOT_PROCESSED_DEADLINE",
                "error": f"run deadline ({RUN_DEADLINE_SECONDS}s) exceeded before this "
                         f"report was reached -- not processed this run",
            }
            unknown += 1
            live_not_processed_deadline += 1
            continue

        local_path = _local_report_path(entry)
        if not local_path:
            missing_local += 1
            manifest_out["reports"][intel_id] = {
                "publication_state": "FAILED",
                "live_state": "UNKNOWN",
                "error": "no local HTML artifact found for an in-window manifest entry",
            }
            continue

        r2_key = _r2_key_for(local_path)
        result = verify_one(local_path, r2_key, skip_public=args.skip_public)
        result["source_record_id"] = intel_id
        result["source_updated_at"] = entry.get("processed_at") or entry.get("timestamp") or ""
        result["path"] = str(local_path.relative_to(REPO_ROOT))
        manifest_out["reports"][intel_id] = result

        if result.get("cache_purge_attempted"):
            cache_invalidations_attempted += 1
            if result.get("cache_purge_succeeded"):
                cache_invalidations_succeeded += 1
            else:
                cache_invalidations_failed += 1
            if result.get("public_verified_after_invalidation"):
                public_verified_after_invalidation += 1
            elif result.get("public_still_stale"):
                public_still_stale += 1

        state = result["publication_state"]
        if state == "REMOTE_VERIFIED":
            verified += 1
        elif state == "STALE_OR_DIVERGENT" or state == "FAILED":
            mismatched += 1
            log.error("[%s] %s: %s", state, intel_id, result.get("error", ""))
        else:
            unknown += 1
            log.warning("[%s] %s: %s", state, intel_id, result.get("error", ""))

        live_state = result["live_state"]
        if live_state == "LIVE_VERIFIED":
            live_verified += 1
        elif live_state == "PUBLICATION_GATE_BYPASS":
            # Never combined with any other counter (mission Section 32) --
            # this is the single most severe outcome this verifier can
            # observe: a report the platform's own gate says must not be
            # served was served anyway.
            publication_gate_bypass += 1
            log.error("[PUBLICATION_GATE_BYPASS] %s: %s", intel_id, result.get("public_error", ""))
        elif live_state == "LIVE_EXPECTED_DENIAL":
            # Correct, intended behavior -- the gate denied and the public
            # route correctly withheld the body. Not a failure; tracked
            # separately so it can never inflate a failure count.
            live_expected_denial += 1
        elif live_state in ("LIVE_STALE_OR_DIVERGENT", "LIVE_MISSING_UNEXPECTED"):
            live_mismatched += 1
            log.error("[%s] %s: %s", live_state, intel_id, result.get("public_error", ""))
        elif live_state == "LIVE_RESOLUTION_FAILED":
            # Gate never evaluated this report (resolver miss) -- a real,
            # separate defect class (RX-PUB-A0.6C), but not evidence of
            # divergent bytes, since there is no expectation to compare
            # against yet.
            live_resolution_failed += 1
            log.warning("[LIVE_RESOLUTION_FAILED] %s: %s", intel_id, result.get("public_error", ""))
        elif live_state == "LIVE_FETCH_FAILED":
            live_fetch_failed += 1
            log.warning("[LIVE_FETCH_FAILED] %s: %s", intel_id, result.get("public_error", ""))
        elif live_state != "PENDING":
            live_unknown += 1
            log.warning("[%s] %s: %s", live_state, intel_id, result.get("public_error", ""))

    elapsed = round(time.time() - t0, 2)
    manifest_out["summary"] = {
        "total_in_window":  len(entries),
        "remote_verified":  verified,
        "stale_or_divergent_or_failed": mismatched,
        "unknown":          unknown,
        "missing_local":    missing_local,
        # Unchanged names/semantics -- scripts/ci_stats_extract.py's existing
        # "rx_pub_a0" extractor and any other consumer keep working exactly
        # as before (Backward Compatibility principle). live_verified is
        # unaffected by this PR's changes; live_stale_or_divergent_or_missing
        # and live_unknown now mean something narrower and more correct than
        # before (gate-expected-denials and gate-unresolvable reports are no
        # longer folded into them -- see the new fields below), which can
        # only ever make these two numbers smaller, never larger, for the
        # same underlying data.
        "live_verified":    live_verified,
        "live_stale_or_divergent_or_missing": live_mismatched,
        "live_unknown":     live_unknown,
        # RX-PUB-A0.6A: new, distinct semantic classes (mission Section 32) --
        # never combined with the failure counters above.
        "live_expected_denial":   live_expected_denial,
        "live_resolution_failed": live_resolution_failed,
        "live_fetch_failed":      live_fetch_failed,
        "live_not_processed_deadline": live_not_processed_deadline,
        "publication_gate_bypass": publication_gate_bypass,
        # RX-PUB-A0.6B (mission Section 35)
        "cache_invalidations_attempted": cache_invalidations_attempted,
        "cache_invalidations_succeeded": cache_invalidations_succeeded,
        "cache_invalidations_failed":    cache_invalidations_failed,
        "public_verified_after_invalidation": public_verified_after_invalidation,
        "public_still_stale": public_still_stale,
        "elapsed_seconds":  elapsed,
        "run_deadline_exceeded": deadline_hit,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest_out, indent=2, default=str), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    log.info("Wrote %s", OUTPUT_PATH)

    # Sync the manifest to R2 (BUCKET_DATA, intel/ prefix) so it's observable
    # via GitHub issue #185's /api/v1/rx-pub-a0/reports-identity endpoint
    # (workers/intel-gateway/src/rx-pub-a0-handlers.js reads this exact key)
    # without waiting for the *next* pipeline run's STAGE 3.5 pass -- this
    # stage runs AFTER STAGE 3.5, so nothing else would upload it this run
    # otherwise. Same "generated late, needs its own sync" situation
    # scripts/r2_upload.py's upload_p40_artifacts() exists for. Uses the
    # current (DATA-bucket-scoped, already restored above) os.environ
    # credentials directly rather than r2_upload.get_credentials(), which
    # sys.exit(1)s on absence -- unacceptable here, this stage must never
    # crash over a missing/wrong credential; best-effort only, and local
    # file + git history remain the source of truth either way.
    _data_account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    _data_key_id  = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    _data_secret  = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    if _data_account and _data_key_id and _data_secret:
        try:
            _endpoint = f"https://{_data_account}.r2.cloudflarestorage.com"
            if _r2_upload.s3_cp(
                str(OUTPUT_PATH), _r2_upload.BUCKET_DATA,
                "intel/rx_pub_a0_reports_artifact_manifest.json", _endpoint,
            ):
                log.info("Synced manifest to R2 (intel/rx_pub_a0_reports_artifact_manifest.json)")
            else:
                log.warning("Manifest R2 sync failed -- local file/git history remain authoritative")
        except Exception as e:
            log.warning("Manifest R2 sync raised %r -- local file/git history remain authoritative", e)
    else:
        log.warning("DATA-bucket R2 credentials absent -- manifest not synced to R2 this run")

    log.info(
        "R2 summary: %d in-window, %d REMOTE_VERIFIED, %d STALE_OR_DIVERGENT/FAILED, "
        "%d UNKNOWN, %d missing-local, %.2fs",
        len(entries), verified, mismatched, unknown, missing_local, elapsed,
    )
    log.info(
        "Public HTTP summary: %d LIVE_VERIFIED, %d LIVE_EXPECTED_DENIAL (gate-correct, "
        "not a failure), %d LIVE_STALE_OR_DIVERGENT/MISSING_UNEXPECTED, "
        "%d LIVE_RESOLUTION_FAILED, %d LIVE_FETCH_FAILED, %d LIVE_NOT_PROCESSED_DEADLINE, "
        "%d UNKNOWN",
        live_verified, live_expected_denial, live_mismatched,
        live_resolution_failed, live_fetch_failed, live_not_processed_deadline, live_unknown,
    )
    if cache_invalidations_attempted:
        log.info(
            "Cache purge summary: %d attempted, %d succeeded, %d failed | "
            "%d converged after purge (now LIVE_VERIFIED), %d still stale after purge",
            cache_invalidations_attempted, cache_invalidations_succeeded, cache_invalidations_failed,
            public_verified_after_invalidation, public_still_stale,
        )

    # RX-PUB-A0.6A / mission Section 9: a publication-gate bypass is the
    # single most severe outcome this verifier can observe -- a report the
    # platform's own gate says must not be served was served anyway. Always
    # surfaced with its own block, distinct from and in addition to the
    # general failure summary below, and never silently folded into an
    # ordinary mismatch count (mission Section 52 lists this as an automatic
    # mission blocker).
    if publication_gate_bypass > 0:
        log.error("!" * 70)
        log.error(
            "PUBLICATION_GATE_BYPASS x%d -- a report the platform's publication gate "
            "denied (customer_ready=false) was served with a real HTML body at its "
            "public URL. This is a customer-facing access-control defect, not a byte "
            "divergence (RX-PUB-A0.6 mission Section 9).",
            publication_gate_bypass,
        )
        log.error("!" * 70)

    # CodeRabbit finding (RX-PUB-A0 Section 27 "do not fail-open"): an
    # unverifiable report (retries exhausted, auth/config error) is NOT the
    # same claim as a verified-matching report. "could not verify" must
    # never silently read as "verified" -- so every failure/unresolved/
    # unprocessed class below blocks a PASS claim, exactly as before this
    # PR. LIVE_EXPECTED_DENIAL is deliberately excluded: it is the gate
    # working correctly, not a failure (mission Section 32).
    total_failures = (
        mismatched + unknown
        + live_mismatched + live_unknown
        + live_resolution_failed + live_fetch_failed + live_not_processed_deadline
        + publication_gate_bypass
    )
    if total_failures > 0:
        log.error("=" * 70)
        log.error(
            "%s -- %d R2 mismatch/missing + %d R2 unverifiable + %d public HTTP "
            "mismatch/missing + %d public resolution-failed + %d public fetch-failed + "
            "%d not-processed-by-deadline + %d publication-gate bypass(es). A changed, "
            "certified commercial artifact must be remotely AND publicly "
            "verified before this run can be treated as production-certified "
            "(RX-PUB-A0 Sections 12, 25, 27; RX-PUB-A0.6 Sections 9, 26-27).",
            "HARD FAIL" if args.enforce else "WOULD HARD FAIL (--enforce not set)",
            mismatched, unknown, live_mismatched, live_resolution_failed,
            live_fetch_failed, live_not_processed_deadline, publication_gate_bypass,
        )
        log.error("=" * 70)
        return 1 if args.enforce else 0

    if args.skip_public:
        log.info("PASS (R2-only -- --skip-public was set) -- every in-window report's R2 SHA-256 matches its local artifact.")
    else:
        log.info(
            "PASS -- every in-window report's R2 SHA-256 matches its local artifact, and "
            "every public HTTP response matches either the canonical artifact "
            "(LIVE_VERIFIED) or the publication gate's expected denial (LIVE_EXPECTED_DENIAL)."
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log.critical("Unhandled exception: %s\n%s", e, traceback.format_exc())
        sys.exit(1)
