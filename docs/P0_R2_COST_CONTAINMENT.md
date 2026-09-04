# P0 — Sentinel APEX R2 Cost Containment

**Status:** Fixed (this document ships with the fix)
**Severity:** P0 — production business blocker (pre-revenue, ~$6/month total Cloudflare budget across all platforms)
**Date:** 2026-09-04

---

## 1. Incident evidence

| Metric | Value |
|---|---|
| Previous billing cycle: R2 Class A operations | 3,004,147 |
| Previous billing cycle: R2 Class A charge | $18.00 (pre-tax) |
| Previous billing cycle: total Cloudflare invoice | $27.31 |
| `sentinel-apex-data` objects (at incident time) | ~85.64K |
| `sentinel-apex-reports` objects (at incident time) | ~193.15K |
| Current cycle, early | ~574.63K Class A operations already accrued |

## 2. Root cause chain

This was not a single bad line — it was a **compounding pipeline defect** across four layers, each amplifying the one below it. All four had to be fixed for the incident to actually close.

1. **`scripts/run_pipeline.py` STAGE 3.6** called `scripts/generate_intel_reports.py` in its *default* mode — no `--only-missing`, no time filter — against the **entire historical manifest** (`data/stix/feed_manifest.json`, and again against `api/feed.json`), on **every** scheduled pipeline run. This re-rendered a report for every intel item ever ingested, not just new/changed ones.
2. Every rendered report embeds **live, minute-granularity `datetime.now(timezone.utc)` timestamps** into its SIGMA/YARA/KQL/SPL detection-content blocks (`generate_intel_reports.py` — the SIGMA rule builder, YARA rule builder, and KQL/SPL hunt-query builder each stamp `date:`/`Generated:` fields at render time). This guarantees every regenerated file's **byte content differs from the previous run's copy**, even when the underlying intel item is completely unchanged.
3. `_write_report_atomic()` unconditionally overwrote the on-disk HTML for every item, every run — refreshing **mtime** for the entire local `reports/` tree (then ~22K+ git-tracked files, ~193K in R2 historically) on every invocation.
4. `scripts/r2_upload.py`'s `main()` ran `aws s3 sync reports/ -> s3://sentinel-apex-reports/reports/` with `size_only=False` (real content/mtime comparison, reverted from `--size-only` in an earlier fix specifically to stop a staleness bug — see that code's own v184.2 history) and **no deterministic-key targeting, no bound**. Because of (2)/(3), essentially the *entire* local `reports/` tree looked "changed" to `aws s3 sync` on every run, so it re-uploaded (and, to build its comparison map, first **LISTed**) close to the entire ~193K-object historical corpus, every run.

This chain ran on `sentinel-blogger.yml`'s schedule — **`cron: '0 0,8,16 * * *'` (3×/day) + a monthly cron + every qualifying `push`** (to `scripts/**.py`, `agent/**.py`, workflow files, `index.html`, `feed_manifest.json` — frequent, given this repo's commit cadence). `aws s3 sync` also unconditionally paginates a `ListObjectsV2` call across the *entire* destination prefix to build its comparison map — independent of how much actually changed — adding ~194 Class A LIST calls per invocation on top of the PUT volume, purely as bucket-discovery overhead this architecture no longer needs.

**Order of magnitude:** ~193K objects × (LIST-share + PUT) × several runs/day/week is fully sufficient to produce a multi-million-operation billing cycle. This is a mechanism-level explanation, not a claim to a precise reconstructed number for the actual historical invoice — the previous cycle's exact run count/timing was not independently re-derived.

### Second, independent full-bucket amplifier: `scripts/backup_r2.py`

Confirmed via full forensic sweep (not assumed): `scripts/backup_r2.py`, invoked **daily** by `.github/workflows/automated-backup.yml` (`cron: "0 1 * * *"`, its own concurrency group — **not** serialized against `sentinel-blogger.yml`), did a full `ListObjectsV2` over **both** `sentinel-apex-data` and `sentinel-apex-reports`, then **unconditionally** `GetObject` + SHA-256'd **every single object**, no sampling, no bound (~278,790 GETs/day at incident-time object counts). This is mostly Class B (cheaper per-op than Class A) but is exactly the "historical verification scan / whole-bucket inventory" pattern the fix below prohibits, and its LIST volume (~280 Class A calls/day) is real. Also fixed in this PR — see §5.

## 3. Full R2 operation ownership matrix

Produced via direct code reads (all scripts named in the incident brief, plus every `.github/workflows/*.yml` with an `aws s3`/`s3api`/`boto3` reference) and a dedicated forensic sweep agent. Full detail lives in this PR's description; summary:

| Component | Bucket | Normal-op behavior (before fix) | Class | Disposition |
|---|---|---|---|---|
| `r2_upload.py` main() "Upload 4a" | `sentinel-apex-reports` | Whole-corpus `aws s3 sync`, every run | A (LIST+PUT) | **Removed.** Replaced by `r2_report_publisher.py`. |
| `r2_upload.py` main() "Upload 4a-PDF" | `sentinel-apex-data` (`reports/pdf/`) | Whole-prefix `aws s3 sync`, `size_only=True` | A (LIST+PUT) | **Removed.** Folded into `r2_report_publisher.py`. |
| `r2_upload.py` main() — manifests/AI/endpoint files | `sentinel-apex-data` | ~30-60 discrete, bounded `s3 cp` calls | A | **Kept**, unchanged — never the cost driver. |
| `backup_r2.py` | `sentinel-apex-data` + `sentinel-apex-reports` | Daily full LIST + 100% GET+SHA256, no bound | A (list) / B (get) | **Fixed** — `sentinel-apex-reports` removed from scope; `sentinel-apex-data` verification bounded to a rotating sample. |
| `r2_reports_integrity.py` | `sentinel-apex-reports` | Bounded (`MAX_CHECK=200` + current-run keys) | B | Unchanged — already bounded, not a contributor. |
| `r2_reports_verifier.py` | `sentinel-apex-reports` | **CORRECTED (P0 R2 COST AUDIT):** this row previously claimed "bounded (~500-item in-window scope, per its own docstring)" — that was FALSE. `_load_in_window_entries()` loaded and verified **every** entry in `feed_manifest.json` unconditionally (no time filter, no count cap); since that manifest is the append-only, ever-growing core intelligence record, this script's real R2 HEAD+GET cost scaled directly with total historical corpus size (150-1040 calls/run observed). Fixed: now filtered to the same `REPORT_WINDOW_HOURS` canonical-timestamp window `r2_report_publisher.py` uses, plus an independent hard `MAX_VERIFY_ITEMS=200` ceiling (matching its sibling's `MAX_CHECK` convention). | B | **Fixed this audit** — genuinely bounded now, matching its sibling. |
| `r2_upload_verifier.py` | `sentinel-apex-data` | Single-object HEAD check | B | Unchanged. |
| `r2_state_sync.py` | `sentinel-apex-data` | 10 small state files (was 9 — see P0 R2 COST AUDIT note below) + 1 bounded dir sync; invocations occur across `sentinel-blogger.yml` (3), `multi-source-intel.yml` (2), and `dashboard-feeds-sync.yml` (1) | A/B | Unchanged mechanism — small, already bounded, pre-justified duplicate call sites (documented pipeline-ordering reasons). **P0 R2 COST AUDIT FIX:** `data/cache/r2_report_publish_state.json` (`r2_report_publisher.py`'s own incremental-publish state) added to `STATE_FILES` — it was never staged anywhere in `safe_git_commit.py`, so it silently reverted to empty on every fresh CI checkout, defeating the "write-only-on-change" cost reduction `r2_report_publisher.py` depends on (see §7a). |
| `r2_resync_manifests.py` | `sentinel-apex-data` | **CORRECTED:** 12 hardcoded files (not "~51 items" as this row previously stated — verified directly against `RESYNC_FILES`), called 2×/run | A | Unchanged — same rationale as above. |
| `generate_intel_reports.py`'s own `r2_upload()` (`--upload-r2`) | `sentinel-apex-reports` | Per-item `s3 cp`, gated by `--only-missing` | A | Unchanged mechanism; now additionally gated by `--since-hours` (see §4). |
| `workers/intel-retention-engine` (Cloudflare Cron, not GH Actions) | `sentinel-apex-data` | `.get()` only, 6×/day | B | Confirmed read-only — no `.list()`/`.put()`/`.delete()` anywhere in its `src/` tree. Not a contributor. |
| `dashboard-feeds-sync.yml`, `generate-and-sync.yml` | `sentinel-apex-data` | Small, bounded `aws s3 cp` sets | A | Confirmed no reports-bucket contact. Not a contributor. |
| `r2-data-sync.yml` | `sentinel-apex-data` | `workflow_dispatch` only — auto-trigger explicitly disabled with a comment naming this exact failure class | A | Dormant. Not a contributor. |

No script anywhere in the repository **deleted** objects from `sentinel-apex-reports` — the bucket could previously only grow. `s3_delete()` is new (see §4).

## 4. New architecture

### 4.1 Deterministic, incremental, bounded report publishing

**`scripts/r2_report_publisher.py`** (new) replaces the whole-corpus sync entirely — not a flag around the old code path, the dangerous path no longer exists in the codebase (`scripts/r2_upload.py` no longer references `sentinel-apex-reports` at all).

- **Deterministic keys only.** Every key is derived from the current manifest via `generate_intel_reports.rel_report_path()` (`reports/{yyyy}/{mm}/{id}.html`) and the established flat PDF convention (`reports/pdf/{id}.pdf`) — never discovered via a bucket LIST. `list_calls` is `0` by construction on this path.
- **24-hour rolling window.** Only items whose **canonical intelligence timestamp** — `timestamp` → `processed_at` → `published_at` precedence, matching the platform's own pre-existing `intelligence_quality_scorer.py::_compute_age_days` convention, parsed via `scripts/canonical_timestamp.py` (never filesystem mtime) — falls within `REPORT_WINDOW_HOURS` (default 24) are eligible.
- **Write-only-on-change.** "Already published this exact content?" is answered from the publisher's own local state file (`data/cache/r2_report_publish_state.json`, SHA-256 per key) — never by asking R2. `unchanged` → zero PUT.
- **Bounded retirement.** An id previously published whose *stored* canonical timestamp (recorded at publish time, so this doesn't depend on the id remaining in `api/feed.json`'s own rolling window) ages past the window gets `DELETE`d. Bounded by construction — the state file only ever holds what this script itself published within roughly the last window, never the historical corpus.
- **Dangling-URL-free.** Every retired id's `report_url` / `internal_report_url` / `pdf_url` is cleared to `""` in every manifest that carries it — reusing, not duplicating, the already-established "`\"\"` is a valid, truthful state" contract from `scripts/report_url_integrity_gate.py` and `scripts/report_existence_validator.py`. Both existing CI gates pass unmodified.
- **Fail-closed budget.** The complete PUT/DELETE plan is computed *before* a single R2 call — `scripts/r2_cost_guard.py::enforce_budget()` aborts the entire run before any mutation if a ceiling is exceeded. No partial execution.

`scripts/r2_cost_guard.py` (new) is the single source of truth for R2 operation accounting across every script that mutates R2 in the normal pipeline. It defines `R2Budgets` (env-configurable ceilings), `enforce_budget()` (raises `R2BudgetExceeded`, fail-closed), and `emit_summary()` (prints the `R2_COST_GUARD` telemetry block, writes `data/quality/r2_cost_guard_report.json`, appends to `$GITHUB_STEP_SUMMARY`).

### 4.2 Report generation itself gated to the window

`scripts/generate_intel_reports.py` gained an additive, optional `--since-hours N` flag (default `None` = unbounded, 100% backward compatible for any caller that doesn't pass it). When set, an item whose canonical timestamp is outside the window is `continue`d past **before any field is touched** — not rendered, not written, `report_url`/`validation_status` left byte-identical. The manifest save path is unaffected: out-of-window items are never dropped, only skipped by the render loop (core intelligence records are not subject to this retention decision).

Wired into **all four** scheduled call sites (missing even one would let that path re-trigger regeneration for retired items — an already-cleared `report_url` reads as a fresh `--only-missing` repair candidate otherwise, discovered and fixed during this implementation):
- `run_pipeline.py` `stage_html_reports()` — both the `feed_manifest.json` and `api/feed.json` passes.
- `run_pipeline.py`'s "3.9-RPT" gap-fill pass.
- `run_pipeline.py`'s materialization-barrier (`--only-missing`) pass.
- `sentinel-blogger.yml` STAGE 5.4.0b's direct invocation.

`--fail-on-zero`'s semantics were adjusted alongside this (not weakened): it now fails only when there was at least one window-eligible, non-brand-skipped item and zero were written — a genuinely quiet 24h window (zero new intel) is a valid, expected state and exits 0.

### 4.3 Dashboard index bounded to the same window

`scripts/build_reports_index.py` no longer sorts/includes by filesystem mtime (forensic finding, matching `report_archive_manager.py`'s own documented conclusion: this repo's `reports/` tree has been bulk-seeded by single historical commits and reset on fresh checkouts, so mtime never reflected true report age). It now resolves each candidate file's canonical timestamp via its `api/feed.json` entry and excludes anything outside `REPORT_WINDOW_HOURS` — and excludes any file with **no** feed match at all (its age can't be proven, so it's not shown as current — fail-safe, matching the retention decision's own logic). `index.json` / `latest.json` / `stats.json` are **always** written, even when the window is genuinely empty, carrying an explicit `empty_state_message`: *"No intelligence reports generated during the last 24 hours."* The dashboard's REPORTS tab renders that exact string (not the generic filter-mismatch message) when the API response says the window is genuinely empty.

### 4.4 `backup_r2.py` bounded

- `sentinel-apex-reports` removed from `SOURCE_BUCKETS` entirely (regenerable, non-essential per the business decision, now itself bounded to 24h — daily-verifying it is exactly the prohibited "historical verification scan").
- `sentinel-apex-data`'s per-object GET+SHA256 verification is capped at `MAX_BACKUP_VERIFY_OBJECTS_PER_RUN` (default 2000) via a deterministic rotating window (`verify_sample_indices()`) — full coverage every `ceil(total/sample)` days (~43 days at incident-time object counts), not 100%/day. Un-sampled objects are still catalogued (key/size/etag, already paid for by the LIST) with `sha256` left unset, not silently dropped from the manifest.

### 4.5 One-time historical migration, kept separate from the recurring pipeline

`scripts/r2_reports_purge.py` (new) — manual/human-invoked only, **never** wired into any scheduled workflow.

- Dry-run by default. Destructive execution requires **both** `--execute` and `--confirm-bucket sentinel-apex-reports` (exact match).
- Hardcoded, asserted bucket allowlist — `sentinel-apex-data` and `cyberdudebivash-scan-results` are permanently, unconditionally rejected as targets (not configurable).
- Deletion candidates = every key under `reports/` **minus** the exact set `r2_report_publisher.py`'s own state file currently tracks as live — not object age/LastModified (unreliable here: the very bug this incident fixes means many historical objects' LastModified reflects *accidental re-uploads*, not when the underlying intel was actually current) and not path-derived month granularity (informational only, in the dry-run summary, never the deletion criterion).
- Refuses `--execute` outright if the keep-set is empty (i.e., the new publisher hasn't completed a real run yet in this environment) unless explicitly overridden — an empty keep-set is indistinguishable from "delete everything" otherwise.
- Batched `delete-objects` (≤1000 keys/call) — bounded call count even for the one-time purge itself.

### 4.6 Hard operation budgets (fail-closed, not warn-and-continue)

Set at `sentinel-blogger.yml` job level, evidence-based (see `scripts/r2_cost_guard.py`'s own docstring for the observed-volume reasoning):

```
PRE_REVENUE_COST_MODE        = true
REPORT_WINDOW_HOURS          = 24
R2_REPORT_PUBLISHING_ENABLED = true   # emergency kill switch
MAX_REPORT_UPLOADS_PER_RUN   = 500
MAX_REPORT_DELETIONS_PER_RUN = 500
MAX_R2_LIST_CALLS_PER_RUN    = 0
MAX_R2_DATA_WRITES_PER_RUN   = 200
```

`R2_REPORT_PUBLISHING_ENABLED` defaults `true` (not `false`, as an emergency-only first draft of this fix would have set it): the new architecture is safe-by-construction (bounded, zero LIST, budget-enforced) and the platform's own business requirement is that the dashboard keep showing current reports. The flag remains a genuine, instant, code-change-free kill switch for the report-publishing stage specifically, without needing to reintroduce the deleted whole-corpus code path to have "a switch that does something."

### 4.7 Cost telemetry

Every R2-mutating stage emits an `R2_COST_GUARD` block to its own log (grep-able), merges into `data/quality/r2_cost_guard_report.json` (this platform's standard `data/quality/*.json` convention, keyed per stage so multiple stages in one run don't clobber each other), and appends to `$GITHUB_STEP_SUMMARY`:

```
R2_COST_GUARD (CLOUDFLARE COST GUARD)
--------------------------------------
mode: PRE_REVENUE_COST_MODE
stage/workflow-run: r2_report_publisher / <run_id>
bucket: sentinel-apex-reports (+reports/pdf/ in sentinel-apex-data)
report candidates:
  new: <n>  changed: <n>  unchanged: <n>  expired (>window, retired): <n>
PUT: <n>  DELETE: <n>  LIST: 0  COPY: 0  multipart: 0
estimated Class A operations: <n>
budget (PUT/DELETE/LIST): 500/500/0
budget utilization: <pct>%
status: PASS | BLOCKED
```

**Billing accuracy note:** Cloudflare R2 does not bill `DeleteObject` as a Class A operation — `estimated_class_a` intentionally excludes `delete`. Delete count is still tracked and budget-capped for blast-radius safety, not cost.

`scripts/ci_stats_extract.py` gained a matching `r2_cost_guard` key (additive, appended after the last existing entry, own fallback tuple) so this report is visible through the same CI-summary mechanism as every other P-layer certification.

## 5. Permanent regression gate

`scripts/regression_tests.py` gained **T26** — a static source guard (same technique already established for the Worker side by `reports-canonical-write-guard.test.js`), asserting:
1. `scripts/r2_upload.py` contains no `s3_sync()` call site against `BUCKET_REPORTS`/`sentinel-apex-reports` (precise: matches call sites, not the still-legitimate generic helper's own definition).
2. `scripts/r2_report_publisher.py` contains no bucket-enumeration pattern (`list_objects`, `get_paginator`, etc.).
3. Every `generate_intel_reports.py` invocation in `run_pipeline.py` and `sentinel-blogger.yml` passes `--since-hours`.

Full new-behavior test coverage (65 new tests across 5 new files, plus updates to 2 existing test files whose fixtures encoded now-superseded assumptions — see §6):
- `tests/test_r2_cost_guard.py` — budget enforcement (fail-closed, before mutation), Class A billing-accuracy exclusion of DELETE, env-driven config, multi-stage report merging.
- `tests/test_r2_report_publisher.py` — window inclusion/exclusion/boundary/future-dated/malformed-timestamp handling, incremental hash-diff PUT decisions, retirement + a real bug this implementation caught and fixed (partial delete failure must not orphan the sibling object's tracked state or clear the wrong URL field — see git history), zero-LIST structural guarantee, a cost-simulation test proving plan cost scales with candidate count, not historical corpus size.
- `tests/test_generate_intel_reports_since_hours.py` — old items left byte-identical, never dropped from the manifest; fresh items still render; backward compatibility when the flag is omitted; malformed timestamps fail safe; `--fail-on-zero` doesn't false-fire on a genuinely quiet window.
- `tests/test_build_reports_index_window.py` — window filtering, no-feed-match exclusion, always-valid-JSON empty state with the exact required message.
- `tests/test_r2_reports_purge_safety.py` — bucket allowlist (both forbidden buckets + any other name), empty-keep-set refusal, CLI-level refusal behavior.

## 6. Existing tests updated (not weakened)

Two pre-existing test files encoded assumptions this fix intentionally supersedes; both were updated to preserve their original intent under the new architecture, per this incident's own governance requirement to update rather than silently break or delete:

- **`tests/test_build_reports_index_artifact_fallback.py`** — its isolated-fixture `setUp()` now also copies the new `canonical_timestamp.py` dependency. Its fixtures previously used `_write_feed([])` (empty feed) to simulate "id scrolled out of the feed window" — under the new architecture an id with *no* feed entry at all can never have its age proven, so it's correctly excluded from the hot index entirely now (not just under-enriched). Fixtures were updated to provide a minimal feed entry (`{"id": ..., "timestamp": <recent>}`) so the still-valid, still-important scenario they test — artifact-HTML-embedded-metadata fallback fills in title/severity/risk when the *feed entry itself* lacks those fields — remains exercised. Its mtime-ordering test was renamed and rebuilt around explicit canonical timestamps (mtime is no longer the sort key at all).
- **`tests/test_report_materialization_barrier.py`** — two fixtures used a fixed historical timestamp (`2026-06-01`); the materialization barrier's `generate_intel_reports.py` call now correctly excludes anything that old (see §4.2), so these fixtures were updated to a dynamically-computed recent timestamp (with the fixture's `report_url` path segment kept consistent with it, since `rel_report_path()` derives the actual render path from the timestamp, not from a pre-set URL string).

## 7. Residual, consciously out-of-scope items

- `r2_resync_manifests.py` is invoked twice per pipeline run. This duplication is pre-existing, individually documented, a deliberate fix for a real pipeline-ordering bug (the manifest changes between the two call sites). Small, already-bounded (12 hardcoded files — corrected count, see §3 table; was previously mis-documented as "~51 items"), not a contributor to this incident — left unchanged per Zero Unnecessary Modification.
- `r2_reports_integrity.py` / `r2_reports_verifier.py` are bounded-but-nonzero Class B consumers every run (`MAX_CHECK=200` and `MAX_VERIFY_ITEMS=200` respectively — see §3 table's P0 R2 COST AUDIT correction for `r2_reports_verifier.py`, which was NOT actually bounded before that audit despite this section previously claiming otherwise).
- This document, the code, and the tests demonstrate the **architecture** no longer permits the incident's mechanism. They do not and cannot guarantee Cloudflare's actual account invoice — traffic, other platforms sharing the account, tax, and Cloudflare's own pricing are external variables. Post-deployment Class A metric verification (before/after one full scheduled run) is a manual step for the human operator — see the PR description's Production Validation Plan.

## 7a. P0 R2 cost audit — post-merge forensic findings and fixes

A post-merge adversarial audit of this PR (before it merged) found and fixed two additional defects, neither caught by the original implementation or its test suite:

1. **`r2_reports_verifier.py` was never actually bounded.** Its own docstring claimed a "bounded (~500-item in-window scope)" and §3/§7 of this document (in its pre-audit form) repeated that claim — but `_load_in_window_entries()` loaded and verified **every** entry in `data/stix/feed_manifest.json` unconditionally: no time filter, no count cap. Because that manifest is the append-only, ever-growing core intelligence record (report retention removes entries from R2, never from the manifest — see §4.2), this script's real HEAD+GET call volume scaled directly with total historical corpus size, not with "changed this run." Historical evidence showed 150-1040 calls/run. **Fixed** by filtering to the same `REPORT_WINDOW_HOURS` canonical-timestamp window `r2_report_publisher.py` uses (reusing its `canonical_timestamp.py`-based logic, not reimplementing it), plus an independent hard `MAX_VERIFY_ITEMS` ceiling (default 200, matching `r2_reports_integrity.py`'s `MAX_CHECK` convention) so a defect in the window filter alone can never again let this script's cost scale with manifest size. Its HEAD/GET (Class B) operations are now also reported through `scripts/r2_cost_guard.py`'s shared cost ledger (new `head`/`get` fields, additive) — previously unaccounted for entirely.

2. **`r2_report_publisher.py`'s incremental-publish state never persisted across CI runs.** Its state file (`data/cache/r2_report_publish_state.json`) was not listed in `safe_git_commit.py`'s `JSON_GUARDED`, `files_to_stage`, or `_GENERATED_ARTIFACT_PATHS` — so it was never committed, and a fresh CI checkout always started from an empty state. This did not risk an unbounded operation (the retirement pass only ever deletes ids the state file itself already tracks, so an empty state causes zero uncontrolled deletes, and `build_plan()`'s output is still capped by the existing fail-closed budget in `r2_cost_guard.py`) — but it silently defeated the "write-only-on-change" design this whole cost fix depends on: every scheduled run would re-PUT every in-window candidate as "new," not just genuinely new/changed content. **Fixed** by adding this file to `scripts/r2_state_sync.py`'s existing `STATE_FILES` list (download-before/upload-after via R2) — reusing the exact mechanism this codebase already built and proved necessary for four other cross-run state files, rather than attempting git-commit persistence again. That mechanism exists specifically *because* `main`'s branch ruleset rejects direct pushes for this class of file (see `r2_state_sync.py`'s own module docstring) — a git-based fix for this file would have repeated a root cause this codebase already diagnosed and fixed elsewhere.
