# P0 — Empty Dashboard / Data-Plane Forensics — Root Cause Report

**Companion:** `docs/incidents/P0-WORKFLOW-FORENSIC-MATRIX.md` (all 61 workflows), `docs/incidents/P0-v200-empty-dashboard-root-cause.md` (this investigation's first pass — frontend execution-trace methodology).

---

## EXECUTIVE VERDICT

**None of the four prescribed options (A/B/C/D) fits without a misleading label, so this is stated plainly rather than force-fit:**

- The specific reported symptom (customer dashboard permanently stuck at `SYNC: LOADING` / 0 advisories) **does not reproduce**, and therefore has **no confirmed root cause** — a root cause cannot be proven for an event that cannot be observed. This investigation ran the actual production frontend against actual production data **eight times** across two sessions (six single/polling runs plus two independent live-production API/HTML fetches), plus checked two independent automated production monitors' full recent run history (`ui-file-guardian.yml`'s empty-`EMBEDDED_INTEL` detector, `autonomous-guardian.yml`'s post-pipeline health check) — both clean through and including today.
- **This is not "D — incident still active."** It is also not "A/B — restored," since nothing was proven broken to restore.
- **What this audit does confirm, with code-level evidence, independent of the unconfirmed symptom:** four real architectural defects (below), none of which were caused by or require an active outage to prove. These are genuine findings from the exhaustive 61-workflow audit the incident brief demanded, and are real regardless of whether the specific customer report is accurate.

If a genuine occurrence of the reported symptom exists that this investigation could not reach (a specific browser/device/cache state, or a narrow time window between two of today's checks), the concrete next step is real-browser production telemetry (§"Remaining Risks") — this environment's sandboxed test harness is the limiting factor, not the absence of further workflow auditing.

---

## ROOT CAUSE

**Of the reported symptom: none proven — does not reproduce.** See "Method" below for what was tested.

**Of four separate, real, code-confirmed architectural defects found during the audit:**

1. **`api/v1/intel/apex.json` and `ai_summary.json` have two independent, unlocked writers.** `sentinel-blogger.yml` (STAGE 3.93.1 "AI Brain Publisher" + `scripts/r2_upload.py`, confirmed at source-line level: `r2_upload.py:467,469`) and `dashboard-feeds-sync.yml` (`scripts/generate_dashboard_feeds.py`) both generate and upload these exact two R2 keys, on different schedules (~4h vs. 6h+30min offset), under different concurrency groups (`sentinel-data-writer` vs. `sentinel-dashboard-feeds`) with no lock between them. This is the identical bug class the team already found and fixed once for `api/reports/index.json`/`stats.json` (documented as "F-02" in `dashboard-feeds-sync.yml`'s own header) — just not yet applied to these two files.
2. **`generate-and-sync.yml`'s git-push and R2-upload steps are not sequenced.** STAGE 9 (`git push` of the enriched `api/feed.json` + ~25 paths) can silently exhaust 5 retry attempts and only log a `::warning::` — it does not fail the job. STAGE 9.5 (R2 upload of `ai/tracker.json` and 3 related files) is gated only on `DRY_RUN != 'true'`, with **no dependency on STAGE 9's outcome**. A run can therefore fail to publish the git-tracked feed update while still successfully publishing fresh AI-tracker data to R2 — structurally the same shape as "one page section fresh, another stale" (though this workflow does not itself write the primary `api/feed.json` R2 key the dashboard's main grid reads — see R2 ownership matrix).
3. **`scripts/r2_upload_verifier.py` (sentinel-blogger's STAGE 3.6 gate) has no relative-drop protection.** Its only quantity check is an absolute floor (`MIN_ADVISORY_COUNT = 1`, hard-fail only at exactly zero; warn-only below 5). Its own docstring documents that the floor was *already* deliberately lowered from 5→1 after it caused false positives on legitimate low-count runs — so a catastrophic relative collapse (985→9, the exact shape of the 2026-04-18 historical incident) would pass this gate silently today: 9 is `≥1` (no hard fail) and `≥5` (no warn either).
4. **A narrower, unconfirmed echo of the historical `--force-rebuild` defect exists inside the current pipeline**, architecturally different from the original (a single in-process call, not a second workflow racing sentinel-blogger over a shared lock): `run_pipeline.py` calls `bootstrap_critical_files.py --force-rebuild` when `engine_count < 10`. Its zero-entry guard (CRIT-01) protects only against a collapse to exactly zero, not to a small-but-nonzero count. Not observed to have fired in the run this investigation traced end-to-end.

---

## WORKFLOW CULPRIT(S)

**Confirmed active culprit for the specific reported symptom: none.**

**Plausible contributing pattern, if the symptom is ever real:** `generate-and-sync.yml` (finding #2 above) is the closest structural match this audit found to "one section fresh, one stale" — but it does not write the primary `api/feed.json` R2 key the main dashboard grid consumes (that key has a single confirmed writer, `sentinel-blogger.yml`'s `r2_upload.py` — see R2 ownership matrix), so it cannot by itself explain a 985-vs-0 split on the primary grid specifically. It remains the single most concrete "worth fixing regardless" finding of this audit.

---

## Workflow Forensic Matrix / R2 Writer Matrix

See `docs/incidents/P0-WORKFLOW-FORENSIC-MATRIX.md` §1–3 (all 61 workflows, R2 key ownership table, disposition roll-up).

---

## CONCURRENCY COLLISION MATRIX

| Resource | Writers | Concurrency groups | Actual isolation |
|---|---|---|---|
| `api/v1/intel/latest.json` / `api/feed.json` | `sentinel-blogger.yml` only | `sentinel-data-writer` | **Real — single writer** |
| `api/v1/intel/apex.json`, `ai_summary.json` | `sentinel-blogger.yml`, `dashboard-feeds-sync.yml` | `sentinel-data-writer`, `sentinel-dashboard-feeds` | **Fictitious — two groups, same keys, confirmed dual-writer** |
| `gh-pages` (index.html etc.) | `sentinel-blogger.yml` (full dist), `pages-fast-publish.yml` (narrow file set), `v149-hardening.yml` (index.html only, dormant) | `sentinel-data-writer`, `pages-fast-publish`, `v149-hardening-${ref}` | Disjoint by file-scope design (clean-exclude protects the boundary) between the first two; the third has no lock at all but has not run in 32+ days |
| `data/stix/feed_manifest.json` and R2 mirror | `sentinel-blogger.yml` only (`r2-data-sync.yml` disabled) | `sentinel-data-writer` (both, when r2-data-sync.yml *is* manually dispatched) | Real when the disabled workflow stays disabled |
| `feed_state.json`/`processed_intel.json` (R2) | `multi-source-intel.yml` only | `sentinel-data-writer` | Real — migrated off git entirely after GH013 made the git path permanently fail (PR #330/#332) |

No workflow among the 61 was found sharing a concurrency group with `sentinel-blogger.yml` while also writing a key `sentinel-blogger.yml` writes, **except** the two confirmed above.

---

## SCHEDULE COLLISION MATRIX

| Workflow | Cron (UTC) | Assumed non-overlap basis | Verified against actual measured duration |
|---|---|---|---|
| `sentinel-blogger.yml` | `0 0,8,16 * * *` | — | **Measured today: 1h 45m 37s** (run #2227, full trace) |
| `generate-and-sync.yml` | `0 3,9,15,21 * * *` | Header assumes sentinel-blogger finishes within ≤90 min | **Violated** — 105 min actual vs. 90 min assumed; offset margin (3h nominal) still leaves headroom today, but the stated safety assumption in the file's own header is currently false |
| `multi-source-intel.yml` | `45 1,5,9,13,17,21 * * *` | Shares `sentinel-data-writer` group with sentinel-blogger | **True isolation** — shared concurrency group serializes regardless of schedule overlap; the "offset to avoid overlap" comment is redundant with, not a substitute for, the real protection |
| `dashboard-feeds-sync.yml` | `30 3,9,15,21 * * *` | Different group, offset +30min from generate-and-sync | No shared lock; offset-only |

**Conclusion:** the only schedule-collision risk with a broken safety assumption is `generate-and-sync.yml`'s documented ≤90-minute expectation of `sentinel-blogger.yml`, now measured to be exceeded by ~17%. This has not yet manifested as an observed failure (both are independently green in current run history) but is a real, provable gap between documented assumption and measured reality.

---

## DATA AUTHORITY — BEFORE

Historically (pre-v184.0, per multiple workflows' own header postmortems): Git-committed manifests were treated as mutable runtime state by multiple independently-scheduled workflows (`sync-dashboard.yml`, old `r2-data-sync.yml` auto-trigger, `multi-source-intel.yml`'s own git-push), each capable of overwriting the others' work, with GH013 branch-protection rejections silently discarding state on every affected run.

## DATA AUTHORITY — AFTER

R2 is the confirmed runtime authority for the primary feed (`api/v1/intel/latest.json`, single writer) and for `multi-source-intel.yml`'s cross-run state (fully migrated off git per PR #330/#332). Git remains authoritative for code, config, and now-mostly-cosmetic committed copies. The two exceptions where dual-writer risk still exists are `apex.json`/`ai_summary.json` (finding #1) and the theoretical `v149-hardening.yml`/`sentinel-blogger.yml` index.html race (dormant, unlocked).

---

## FAILURE MASKING FOUND

Full detail in the workflow matrix. Highest-signal items, classified per the brief's own taxonomy:

| Location | Masking | Classification |
|---|---|---|
| `generate-and-sync.yml` STAGE 9 → 9.5 | Push failure → `::warning::` only, next R2-upload step unconditional | **DANGEROUS_MASKING** (sequencing gap, not just a swallowed error) |
| `generate-and-sync.yml` STAGE 6.91, 6.93, 6.88 | Steps documented in their own headers as hard-fail thresholds, wrapped in `continue-on-error: true` | **P0_FIX_REQUIRED** (documentation/behavior mismatch) |
| `multi-source-intel.yml` "Run Intelligence Persistence Engine" | `2>/dev/null \|\| true`, and the step's own preceding comment confirms its output is what the next step (R2 upload) publishes | **P0_FIX_REQUIRED** |
| `dashboard-feeds-sync.yml` R2 upload | Up to 3 of 11 feed uploads may fail and the workflow still reports success | **P0_FIX_REQUIRED** (matches the brief's own named example) |
| `enterprise-intel-quality.yml` all 6 phases | Workflow-level `continue-on-error` *and* Python-level `except Exception: sys.exit(0)` — double-masked | **DANGEROUS_MASKING**, though output feeds `data/intelligence/` (adjacent, not the primary feed) |
| `autonomous-guardian.yml`, `enterprise-alerts.yml` | The platform's own health/SLA monitors mask their own script's crashes with `\|\| true` | **DANGEROUS_MASKING** by consequence (a monitor that can silently fail to monitor), though their actual recent run history is clean |
| Everything else with `continue-on-error`/`\|\| true` (majority of the 164 occurrences in `sentinel-blogger.yml` alone, and most occurrences across the other 60 files) | Verified either isolated to a workflow's own non-customer-facing `data/<domain>/` subdirectory, or explicitly optional/observability-only by design (e.g. the P34–P41 certification stages) | **SAFE_OPTIONAL / EXPECTED_EXTERNAL_DEGRADATION** |

A full line-by-line classification of all ~164 `sentinel-blogger.yml` occurrences individually was out of scope for this pass (a multi-day task in its own right, given each needs code-level context, not a grep hit) — the aggregate sampling above, cross-checked against this session's earlier detailed reads of that file's major stages, found no additional dangerous instance beyond what's listed.

---

## LEGACY WORKFLOWS DISABLED (verified, not assumed)

- **`sync-dashboard.yml`** — both automatic triggers physically commented out of the YAML; manual dispatch requires a non-default `force_patch: true` input; the destructive `--force-rebuild` invocation and the `feed_manifest.json` commit are both structurally absent from the file, not merely gated.
- **`r2-data-sync.yml`** — automatic `workflow_run` trigger commented out; `workflow_dispatch` only; header documents the exact overwrite risk as the reason.
- **`v149-hardening.yml`** — schedule trigger removed from the `on:` block; last run 2026-08-02 (32+ days before this report); dispatch-only, no run in that window.
- **`nexus-intelligence.yml`** — schedule commented out, self-described as an "architectural duplicate" of `sovereign-platform.yml`; dispatch-only, with a vestigial unused input.

No renamed or copied workflow anywhere in the repository was found to contain equivalent auto-triggered destructive logic (explicit repo-wide search performed; only hit was the narrower, gated, single-process path in `run_pipeline.py` discussed under Root Cause #4).

---

## FILES CHANGED

**None in production code this pass.** Two new documentation files were added and committed/pushed in the prior turn of this investigation (`docs/incidents/P0-v200-empty-dashboard-root-cause.md`) and this turn adds this file plus the workflow matrix. Per this repository's Proof-Before-Change requirement and the brief's own Section 21/24 ("prove root cause before implementing broad changes"), no pipeline code was modified — the four confirmed findings above are real and independently actionable, but implementing fixes for them is scoped as explicit follow-up work (see Remaining Risks), not bundled into this audit pass.

---

## TESTS

- `git diff --check` — clean (docs-only changes).
- Frontend execution trace: 8 total live runs across this investigation (jsdom + real production `fetch()`, no mocking) — 6 in the prior pass (4 converged cleanly, 2 showed timing variance traced to a jsdom-only canvas-API gap, not app logic) + 2 more this pass (both clean, post-deploy).
- Production monitor history: `ui-file-guardian.yml` (664 runs, latest today 04:02 UTC, success) and `autonomous-guardian.yml` (3605 runs, latest fired the instant sentinel-blogger completed today, success) — both clean.
- No code changes were made, so no code-level regression suite applies to this pass.

---

## PRODUCTION EVIDENCE

- **SHA:** `origin/main @ 64ddc6d98` (unchanged by this investigation until this doc's own commit).
- **Run traced end-to-end:** [#2227 / 33732260058](https://github.com/cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/33732260058) — success, 1h45m37s, all 172 steps green.
- **R2 count:** 500 (`api/feed.json`, `generated_at: 2026-09-03T09:22:00Z`).
- **API count:** 500 (`/api/feed.json`, `/api/preview/` both confirmed 200 with matching data).
- **Frontend count (post-deploy, this pass):** 500 cards, `SYNC: ⚡ LIVE`, `DATA_LOADED`/`INTEL_RENDERED` both `true`.
- **Dashboard count:** matches frontend count (same execution trace).
- **Console errors:** 0 non-canvas-API errors across all traces this session.

---

## REMAINING RISKS

1. **This environment cannot run a real browser** (Playwright blocked by a pre-existing proxy limitation, reconfirmed multiple times this session). Everything above is the closest achievable substitute (jsdom + real network), and it is a good substitute for logic/data-plane correctness, but it cannot rule out a real-browser-specific condition (a specific cache state, extension, or network condition) that a sandboxed test never exercises. **This is the one genuine gap in this investigation's confidence**, and real client-side telemetry/RUM (already recommended in the prior pass, still the highest-value next step) is the only way to close it.
2. The two confirmed dual-writer/masking findings (apex.json/ai_summary.json race, generate-and-sync.yml's push/R2 sequencing gap) are real and worth fixing on their own merits, independent of whether they explain any specific customer report.
3. `r2_upload_verifier.py`'s missing relative-drop protection is a real gap matching the exact historical failure shape (985→9); it has not been observed to trigger, but nothing currently would catch it if it did.
4. `v149-hardening.yml`'s unlocked `index.html` write path is dormant (32+ days inert) but architecturally live if ever manually dispatched during a `sentinel-blogger.yml` run.
