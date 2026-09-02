#!/usr/bin/env python3
"""
scripts/r2_state_sync.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Cross-Run Intel State R2 Sync (P0 FIX)
================================================================================
Root cause fixed: main's branch ruleset now requires "Changes must be made
through a pull request", so multi-source-intel.yml's and sentinel-blogger.yml's
direct `git push origin main` for these three files has been rejected on
every scheduled run since ~2026-08-26 -- silently, until the companion fix in
this same effort made both push-exhaustion paths loud (see
tests/test_git_publish_no_silent_push_failure.py). true_intel_ingestor.py was
genuinely fetching fresh intelligence every run (confirmed live: 227 new RSS
items in one run alone) but every byte of the resulting state was discarded
before reaching main, so every run started from the same frozen 2026-08-26
state -- this is the direct mechanism behind api/feed.json's generated_at
staying frozen despite dozens of "green" pipeline runs in between.

Extends the pattern already reviewed and approved for issue #274 / PR #293
(api/ai/{tracker,health,executive-brief,monetization}.json moved off git onto
R2) to the four files true_intel_ingestor.py's and sentinel-blogger.yml's
own pipeline's cross-run state actually depends on:

  data/cache/feed_state.json    -- per-source last_seen timestamps + reason
                                    codes. Read+written every run by
                                    true_intel_ingestor.py; also read by
                                    scripts/source_fabric_health.py (invoked
                                    from sentinel-blogger.yml) and
                                    scripts/intel_dedup_engine.py.
  data/processed_intel.json     -- SHA256 dedup fingerprint store. Read+
                                    written every run by
                                    true_intel_ingestor.py; prevents
                                    reprocessing already-seen items.
  data/stix/feed_manifest.json  -- the raw accumulated intel items. Written
                                    (additive merge) by true_intel_ingestor.py;
                                    read AND further enriched (MITRE tags, IOC
                                    hardening, quality scoring, dedup) by
                                    dozens of call sites throughout
                                    scripts/run_pipeline.py, which is the
                                    Single Source of Truth this file's own
                                    docstring at line 2168 describes it as.
  data/feed_manifest.json       -- the EII-enriched manifest (distinct file,
                                    NOT the same as data/stix/feed_manifest.json
                                    above). Read-then-patched in place by
                                    run_pipeline.py, apex_quality_field_backfill.py,
                                    cve_id_backfill.py, actor_attribution_enricher.py,
                                    generate_advisory_pdfs.py and
                                    threat_graph_engine.py, all within
                                    sentinel-blogger.yml -- and, like the
                                    three files above, one of
                                    safe_git_commit.py's CRITICAL files whose
                                    git push was being silently rejected by
                                    the same root cause.

Unlike issue #274's AI-tracker files (pure output, regenerated fresh every
run, no need to read prior state back in), these four are genuinely
bidirectional cross-run state that multi-source-intel.yml and/or
sentinel-blogger.yml read at the START of their run and write back at the
END -- so this is a download-before/upload-after wrapper around each
workflow's existing processing, not a one-way "stop committing, start
uploading" change. Every consumer above keeps reading/writing the exact same
local file paths it always has; this script's only job is making sure the
freshest cross-workflow copy is sitting at that path before those consumers
run, and that whatever they leave there gets published back to R2 after.

Concurrency note: R2 objects are plain last-write-wins storage, not
transactional. multi-source-intel.yml (cron '45 1,5,9,13,17,21') and
sentinel-blogger.yml (cron '0,4,8,12,16,20') are deliberately staggered by
the workflows' own existing schedule comments specifically to avoid
overlapping writes to this same state -- this script does not add its own
locking on top of that existing mitigation, and does not claim to. If a run
overruns into the next window, last-write-wins is the accepted risk; there
is no stronger coordination primitive available from plain R2 object storage
without introducing a new dependency this fix's scope doesn't justify.

Usage:
  python3 scripts/r2_state_sync.py --download   # run BEFORE ingestion/pipeline
  python3 scripts/r2_state_sync.py --upload     # run AFTER ingestion/pipeline

Environment variables (same names already used by scripts/r2_upload.py):
  CF_ACCOUNT_ID            -- Cloudflare account ID
  AWS_ACCESS_KEY_ID        -- R2 access key   (mapped from CF_R2_ACCESS_KEY_ID)
  AWS_SECRET_ACCESS_KEY    -- R2 secret key   (mapped from CF_R2_SECRET_ACCESS_KEY)

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import time

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from r2_upload import (  # noqa: E402
    BUCKET_DATA,
    get_credentials,
    install_awscli,
    s3_cp,
    s3_get,
    s3_sync,
    s3_sync_download,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [r2-state-sync] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("r2-state-sync")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Single source of truth for which local paths are R2-authoritative state,
# and what key each lives under.
#
# data/stix/feed_manifest.json MUST use the key "intel/feed_manifest.json" --
# NOT a path-mirrored key -- because scripts/r2_upload.py's STAGE 3.5 upload
# (sentinel-blogger.yml) already publishes this exact file under that exact
# key, every run, and workers/intel-gateway/src/index.js's handleFeedJson
# already reads it from there. Using a different key here would silently
# fork this platform's manifest state into two R2 objects that never see
# each other's writes -- confirmed by reading both the existing upload call
# site and the Worker's read call site, not assumed.
#
# feed_state.json / processed_intel.json have no pre-existing R2 presence
# (confirmed: no reference to either anywhere in r2_upload.py or the Worker),
# so their keys mirror their local relative path, matching this codebase's
# existing convention for genuinely-new R2 objects (e.g. r2_upload.py's
# "api/feed.json" -> R2 key "api/feed.json").
#
# data/feed_manifest.json (top-level -- the EII-enriched manifest, distinct
# from data/stix/feed_manifest.json's raw ingestion bundle) belongs in this
# list for the same reason as the three above: it is bidirectional cross-run
# state, not a fresh-every-run output. Confirmed by reading every writer:
# run_pipeline.py, apex_quality_field_backfill.py, cve_id_backfill.py,
# actor_attribution_enricher.py, generate_advisory_pdfs.py and
# threat_graph_engine.py all read-then-patch this same file in place, and
# every one of those steps in sentinel-blogger.yml runs between this
# workflow's "Download Intel State from R2" step and its "Upload Intel State
# to R2 (final, post-enrichment)" step -- so no wiring change is needed
# there, only this entry. It has no pre-existing R2 key of its own (r2_upload.py
# and r2-data-sync.yml only ever touch data/stix/feed_manifest.json), so its
# key mirrors its local path, same convention as feed_state.json /
# processed_intel.json above. This file is also independently subject to the
# exact same P0 push-rejection root cause this script fixes for the other
# three (it is in safe_git_commit.py's CRITICAL file list) -- its
# generated_at was frozen at the same 2026-08-26 incident date before this
# fix, for the same reason.
STATE_FILES: list[tuple[str, str]] = [
    ("data/cache/feed_state.json", "data/cache/feed_state.json"),
    ("data/processed_intel.json", "data/processed_intel.json"),
    ("data/stix/feed_manifest.json", "intel/feed_manifest.json"),
    ("data/feed_manifest.json", "data/feed_manifest.json"),
    # CodeRabbit review finding on this migration (verified, not taken on
    # faith): multi-source-intel.yml's "Commit Intel State & Manifest" step
    # still `git add -f`'d these 5 append-only registry files after the
    # STATE_FILES above were pulled off that same push -- but main's branch
    # ruleset rejects ANY direct push, not just pushes of specific files, so
    # that push was always going to keep failing regardless of which files
    # remained on it. Since PR #330 made push exhaustion hard-fail the job
    # (deliberately, to stop it silently discarding real state), leaving
    # these 5 on the git path meant this job would now hard-fail on every
    # run that touched any of them -- confirmed by reading
    # intel_persistence_engine.py's own docstring, which describes all 5 as
    # written every run. Same root cause, same fix, same file family as the
    # entries above: no pre-existing R2 key for any of them (confirmed: no
    # reference anywhere in r2_upload.py or the Worker), so keys mirror
    # local paths per this module's established convention.
    ("data/intelligence_repository/intelligence_index.json", "data/intelligence_repository/intelligence_index.json"),
    ("data/intelligence_repository/advisory_registry.json", "data/intelligence_repository/advisory_registry.json"),
    ("data/intelligence_repository/intel_retention_registry.json", "data/intelligence_repository/intel_retention_registry.json"),
    ("data/intelligence_repository/intel_lifecycle_registry.json", "data/intelligence_repository/intel_lifecycle_registry.json"),
    ("data/intelligence_repository/historical_feed_registry.json", "data/intelligence_repository/historical_feed_registry.json"),
]

# data/intelligence_repository/advisories/ is a directory of monthly chunk
# files (registry_<YYYYMM>.json, "never overwritten" per
# intel_persistence_engine.py's own docstring) -- not a single JSON object,
# so it needs sync (prefix-level) rather than cp (key-level) semantics.
# Same root cause and fix as STATE_FILES above; kept as a separate list
# because s3_sync()/s3_sync_download()'s directory contract genuinely
# differs from s3_cp()/s3_get()'s single-object OK/NOT_FOUND/ERROR one (see
# s3_sync_download()'s docstring: without --delete, sync is inherently
# additive/bootstrap-safe, so it doesn't need the same three-way branching).
STATE_DIRS: list[tuple[str, str]] = [
    ("data/intelligence_repository/advisories", "data/intelligence_repository/advisories"),
]

UPLOAD_RETRY_ATTEMPTS = 4


def _is_recognized_state_shape(data) -> bool:
    """True unless `data` is a bare JSON scalar (string/number/bool/null).

    Every file in STATE_FILES is documented as a list or an object (a dict
    keyed by source/fingerprint/registry entries) -- never a lone scalar.
    This is deliberately a coarse, file-shape-agnostic check rather than a
    per-file schema validator: the 9 files in STATE_FILES have 9 different
    internal shapes, and hand-encoding each one's exact schema here would be
    both a maintenance burden and a second, competing source of truth for
    a contract each file's own real consumer (true_intel_ingestor.py,
    run_pipeline.py, intel_persistence_engine.py, ...) already enforces by
    construction. What every one of them agrees on, unconditionally, is that
    a bare scalar is never a valid top-level value -- so that's the one
    invariant checked here, closing the "valid JSON, wrong shape" gap
    without inventing a second schema authority.
    """
    return isinstance(data, (list, dict))


def download(root: pathlib.Path, endpoint: str) -> int:
    """
    Populate each local state path from its R2-authoritative copy.

    Three-way outcome per file, per s3_get()'s contract:
      OK        -> local path now holds the R2 copy.
      NOT_FOUND -> one-time bootstrap: leave whatever's already on disk (the
                   current git-checkout copy, on the first run after this
                   migration lands) in place if present; if nothing is on
                   disk either (a genuinely brand-new environment), that's
                   fine too -- the downstream consumer (true_intel_ingestor.py
                   / run_pipeline.py) already handles a missing/absent file
                   as "start empty", which is what a real first-ever run is.
      ERROR     -> hard fail immediately. Silently proceeding as if this were
                   NOT_FOUND would risk the downstream consumer treating a
                   transient R2 outage as "nothing has ever been seen before",
                   discarding real dedup history and reintroducing duplicates
                   into the customer-facing feed.

    PRODUCTION-VERIFICATION HARDENING (2026-09-02): s3_get() writes directly
    to its destination path, so validating local_path in place (as this
    function used to) meant a malformed or wrong-shape download had already
    overwritten a good local copy by the time validation ran -- the ERROR
    log line and had_error=True were accurate, but the damage to the file
    on disk was already done, and nothing here restored it. Downloads now
    go to a `.tmp` sibling first, validated, and only promoted onto
    local_path via an atomic replace on success -- mirroring the write-tmp/
    verify/replace pattern true_intel_ingestor.py's own _save_manifest()
    already uses for several of these same files on the write side. A
    failed validation now leaves whatever was already at local_path
    (git-checkout copy or a prior successful download) untouched, and is
    reported the same way a NOT_FOUND-with-no-local-copy case already was.
    """
    had_error = False
    for local_rel, r2_key in STATE_FILES:
        local_path = root / local_rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = local_path.with_name(local_path.name + ".r2sync.tmp")
        outcome = s3_get(str(tmp_path), BUCKET_DATA, r2_key, endpoint)

        if outcome == "OK":
            try:
                with open(tmp_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if not _is_recognized_state_shape(data):
                    raise ValueError(f"top-level JSON value is a bare {type(data).__name__}, not a list/object")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                # A malformed or wrong-shape download is at least as dangerous
                # as an outright read error: a downstream consumer that trusts
                # this file (true_intel_ingestor.py's dedup state,
                # run_pipeline.py's Single Source of Truth manifest) could
                # crash mid-run or, worse, silently misbehave on partially-
                # parseable content. Fail loudly rather than handing corrupt
                # state downstream -- and, unlike before this hardening,
                # leave the existing local_path (if any) untouched rather
                # than having already overwritten it.
                log.error(
                    "FATAL: downloaded %s but it is not valid, recognized-shape JSON (%s) -- "
                    "refusing to hand corrupt state to downstream consumers. Existing local "
                    "copy of %s (if any) is untouched.",
                    r2_key, exc, local_rel,
                )
                had_error = True
                tmp_path.unlink(missing_ok=True)
                continue
            tmp_path.replace(local_path)
            continue
        tmp_path.unlink(missing_ok=True)
        if outcome == "NOT_FOUND":
            if local_path.exists():
                log.info(
                    "BOOTSTRAP: %s not yet in R2 -- keeping existing local copy "
                    "(%d bytes) as the one-time bootstrap source.",
                    r2_key, local_path.stat().st_size,
                )
            else:
                log.info(
                    "BOOTSTRAP: %s not yet in R2 and no local copy exists -- "
                    "this consumer's own first-run-empty handling applies.",
                    r2_key,
                )
            continue
        # outcome == "ERROR"
        log.error(
            "FATAL: could not determine R2 state for %s -- refusing to guess "
            "whether this is a fresh environment or a transient outage. "
            "See the ERROR log line above for the underlying cause.",
            r2_key,
        )
        had_error = True

    for local_rel, r2_prefix in STATE_DIRS:
        local_dir = root / local_rel
        local_dir.mkdir(parents=True, exist_ok=True)
        if not s3_sync_download(str(local_dir), BUCKET_DATA, r2_prefix, endpoint):
            log.error(
                "FATAL: could not sync %s from R2 -- see the WARN log line "
                "above for the underlying cause. Existing local copy (if "
                "any) is left untouched.",
                r2_prefix,
            )
            had_error = True

    return 1 if had_error else 0


def upload(root: pathlib.Path, endpoint: str) -> int:
    """Publish each local state path back to its R2-authoritative key, with
    the same 4-attempt retry budget already established for git-push
    exhaustion elsewhere in this pipeline (see safe_git_commit.py /
    multi-source-intel.yml's "Commit Intel State & Manifest" step) for
    consistency. A file that was never present locally (nothing to publish,
    e.g. an ingestion run that legitimately produced no output) is skipped,
    not an error.

    R2 has no cross-object transactions (see this module's docstring's
    Concurrency note), so a run where some of STATE_FILES' 4 uploads succeed
    and others exhaust their retries leaves R2 in a genuinely MIXED state --
    e.g. a freshly-uploaded data/stix/feed_manifest.json paired with a
    stale, previous-run data/feed_manifest.json that failed to publish.
    Building real cross-file atomicity (stage-then-promote) is out of scope
    for a last-write-wins object store this fix doesn't otherwise depend on;
    instead this function tracks succeeded vs. failed files explicitly so a
    genuinely partial run is loudly distinguishable from a total failure --
    the previous per-file-only message wrongly implied 'NOT persisted' even
    when other files in the same run *had* persisted."""
    had_error = False
    succeeded: list[str] = []
    failed: list[str] = []
    for local_rel, r2_key in STATE_FILES:
        local_path = root / local_rel
        if not local_path.exists():
            log.info("SKIP: %s has no local copy to publish (nothing changed?).", local_rel)
            continue

        for attempt in range(1, UPLOAD_RETRY_ATTEMPTS + 1):
            if s3_cp(str(local_path), BUCKET_DATA, r2_key, endpoint):
                succeeded.append(r2_key)
                break
            if attempt < UPLOAD_RETRY_ATTEMPTS:
                sleep_secs = attempt * 15
                log.warning("Retrying %s upload in %ds...", r2_key, sleep_secs)
                time.sleep(sleep_secs)
        else:
            failed.append(r2_key)
            log.error(
                "FATAL: %s failed to upload to R2 after %d attempts -- this "
                "file's state was NOT persisted; the next scheduled run will "
                "read it stale again.",
                r2_key, UPLOAD_RETRY_ATTEMPTS,
            )
            had_error = True

    for local_rel, r2_prefix in STATE_DIRS:
        local_dir = root / local_rel
        if not local_dir.exists() or not any(local_dir.iterdir()):
            log.info("SKIP: %s has no local content to publish.", local_rel)
            continue

        for attempt in range(1, UPLOAD_RETRY_ATTEMPTS + 1):
            if s3_sync(str(local_dir), BUCKET_DATA, r2_prefix, endpoint, content_type="application/json"):
                succeeded.append(r2_prefix)
                break
            if attempt < UPLOAD_RETRY_ATTEMPTS:
                sleep_secs = attempt * 15
                log.warning("Retrying %s sync in %ds...", r2_prefix, sleep_secs)
                time.sleep(sleep_secs)
        else:
            failed.append(r2_prefix)
            log.error(
                "FATAL: %s failed to sync to R2 after %d attempts -- this "
                "run's additions were NOT persisted; the next scheduled run "
                "will read it stale again.",
                r2_prefix, UPLOAD_RETRY_ATTEMPTS,
            )
            had_error = True

    if failed and succeeded:
        log.error(
            "MIXED STATE WARNING: this run partially published its R2 state -- "
            "%d file(s) now fresh (%s), %d file(s) still stale from a previous "
            "run (%s). These files are no longer guaranteed mutually "
            "consistent; if downstream behavior looks wrong, check whether it "
            "correlates with this run.",
            len(succeeded), ", ".join(succeeded), len(failed), ", ".join(failed),
        )

    return 1 if had_error else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--download", action="store_true", help="Populate local state from R2 before processing.")
    mode.add_argument("--upload", action="store_true", help="Publish local state to R2 after processing.")
    parser.add_argument("--root", type=pathlib.Path, default=REPO_ROOT, help="Repository root (default: auto-detected).")
    args = parser.parse_args()

    cf_account, _, _ = get_credentials()
    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"
    install_awscli()

    if args.download:
        return download(args.root, endpoint)
    return upload(args.root, endpoint)


if __name__ == "__main__":
    sys.exit(main())
