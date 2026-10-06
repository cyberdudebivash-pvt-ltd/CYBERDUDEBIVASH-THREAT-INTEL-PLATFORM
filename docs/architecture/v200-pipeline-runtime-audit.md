# Sentinel APEX — sentinel-blogger Pipeline Runtime Audit

**Reference run:** [33732260058](https://github.com/cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/33732260058) (run #2227), job 100574674167
**Reference commit:** `0431fe121` — PR #343
**Audit method:** Direct observation of the live production run via the GitHub Actions API (`get_workflow_run`, `list_workflow_jobs`), captured at successive checkpoints as the run progressed from step 1/172 through step 156/172, cross-referenced against `.github/workflows/sentinel-blogger.yml` and the invoked scripts. Not inferred from YAML alone.
**Status at time of writing:** Run still `in_progress` at step 156/172 (`STAGE 5.8.1c — Deployment Convergence Engine`), 25+ minutes into that single step. All 155 preceding steps: `success`, zero failures.

---

## 1. Headline numbers

| Metric | Value |
|---|---|
| Total steps | 172 (+ 2 post-job cleanup steps) |
| Job started | 2026-09-03T08:14:14Z |
| Deploy step (`STAGE 5 — Deploy to GitHub Pages`) started | 2026-09-03T09:26:17Z |
| Deploy step completed | 2026-09-03T09:26:30Z (13s) |
| Elapsed to reach deploy (pre-deploy duration) | **1h 12m 03s** (4,323s) |
| Elapsed from deploy to last observation (post-deploy, partial — run not yet finished) | **29m 15s and counting** (as of 09:55:45Z) |
| Deploy occurs at step | 139 of 172 (81% through the step count, but only ~52% through elapsed time so far, since the post-deploy tail is still running) |
| Steps still pending after last observation | 16 (157–172) plus 2 post-job cleanup steps |

**This confirms the mission brief's core structural complaint is real and measured, not anecdotal:** a large, expensive post-deploy tail runs after customer-facing publication, and one single post-deploy step has — by itself — already run longer than the entire pre-deploy pipeline's second-largest stage.

---

## 2. Top slowest stages (of steps observed complete as of this audit)

| Rank | Stage | Start | End | Duration | Pre/Post-deploy | Blocking? |
|---|---|---|---|---|---|---|
| 1 | `STAGE 5.8.1c` — Deployment Convergence Engine | 09:30:27 | *(in progress)* | **≥25m18s, capped at 28m internal deadline** | POST-deploy | Non-blocking on timeout (degrades to WARNING, see §4) |
| 2 | `STAGE 3.5` — Upload Intel to Cloudflare R2 | 08:47:07 | 09:09:00 | 21m53s | Pre-deploy | Yes (MANDATORY) |
| 3 | `STAGE 1-3` — Master Pipeline Orchestrator | 08:17:55 | 08:39:15 | 21m20s | Pre-deploy | Yes |
| 4 | `STAGE 3.6a` — Reports Artifact Identity Verifier | 09:11:22 | 09:21:25 | 10m03s | Pre-deploy | Observability (non-blocking) |
| 5 | `STAGE 3.1.8` — IOC Quality Hardener | 08:39:26 | 08:41:59 | 2m33s | Pre-deploy | Yes |
| 6 | `STAGE 5.8.1b` — Report URL Canary | 09:28:02 | 09:30:27 | 2m25s | POST-deploy | Yes (pre-convergence gate) |
| 7 | `STAGE 3.5.1` — R2 Reports Index Integrity Gate | 09:09:00 | 09:11:20 | 2m20s | Pre-deploy | Yes |
| 8 | `STAGE 4` — Git Sync (commit + push metadata) | 09:22:36 | 09:24:53 | 2m17s | Pre-deploy (blocks deploy) | Yes |
| 9 | Install pipeline dependencies | 08:15:17 | 08:17:08 | 1m51s | Pre-deploy | Yes |
| 10 | `STAGE 3.1.9` — Real OSINT IOC Enrichment | 08:41:59 | 08:43:07 | 1m08s | Pre-deploy | Yes |

**Concentration finding:** the top 4 stages alone (#1–#4) account for roughly **75–80% of total elapsed wall-clock time** across all 172 steps, despite being 4 out of 172 (2.3% of step count). Steps 87–122 (36 consecutive P20–P38 certification stages) collectively completed in **under 90 seconds total** — these are not the bottleneck; the four stages above are.

---

## 3. `STAGE 5.8.1c` — Deployment Convergence Engine (primary post-deploy bottleneck)

Read directly from `scripts/deployment_convergence_validator.py` (1,061 lines) and its workflow invocation (`sentinel-blogger.yml` lines 3881–3931):

- Four sequential phases: **Phase 1** (fixed 90s wait for Pages push detection) → **Phase 2** (CDN readiness probe, up to `MAX_RETRIES=8` attempts with exponential backoff 30s→180s +15s jitter) → **Phase 3** (a *second*, independent up-to-8-attempt backoff retry loop) → **Phase 4** (convergence confirmation, up to `CONFIRM_RUNS×3 = 9` more probe attempts).
- Hard-capped at an internal `timeout 1680` (28 minutes), specifically engineered (per its own code comment) to avoid GitHub Actions' 30-minute step timeout producing a hard failure — on internal deadline, exit code 124 is remapped to a non-blocking `DEPLOYMENT_DEGRADED` (exit 0).
- **This is the single largest concrete opportunity in the entire pipeline for closing the gap to the mission's ≤45-minute target.** Worst case, it alone can consume 28 of a 45-minute budget. Best case (fast convergence), it still pays the fixed 90s+45s phase-wait tax before any probing starts.
- It is *not* a redundant/legacy stage — it exists to solve a real problem (confirming CDN convergence post-deploy before declaring the release stable) — but its retry structure (three independent retry/backoff loops stacked sequentially: Phase 2, Phase 3, Phase 4) is a strong candidate for consolidation into a single bounded probe loop with one backoff policy, which is a scoped, testable, low-blast-radius change distinct from re-architecting the other 171 steps.

---

## 4. Section 13 re-verification: dashboard/homepage health (finding contradicts mission brief)

The mission brief's section 13 asserts the live dashboard is currently showing `SYNC: LOADING`, `NO DATA`, blank KPIs, `LIVE 0`, and "No Threat Intelligence Available."

**This was independently tested twice this session** — once before today's deploy (against the prior production state) and once immediately after `STAGE 5 — Deploy to GitHub Pages` completed for run #2227 — using a full-execution simulation (jsdom 30, real DOM, real production `fetch()` against `https://intel.cyberdudebivash.com/`, not a static read):

| Check | Result |
|---|---|
| `#sync-val` text | `SYNC: ⚡ LIVE` |
| `#threat-grid` children rendered | 500 cards |
| `window.__DATA_LOADED__` | `true` |
| `window.__INTEL_RENDERED__` | `true` |
| Data freshness | `2026-09-03T08:19:37Z` (same-day, from this run's own enrichment pass) |
| Script errors | 23, all a single unrelated jsdom limitation (no native `<canvas>` 2D context — a GPU-tier-detection engine artifact, not the intel-loading path; does not occur in real browsers) |

**Conclusion: the flagship dashboard is not currently broken.** Either the brief's claim reflects a stale/prior observation (possibly from before this run's deploy landed), a different environment (specific browser/cache/device) this test can't reach, or was scaffolding language rather than a live-verified finding. Section 13's specific remediation demand (trace R2→Worker→API→apex-data-plane.js→KPI→render) is not needed as a bug fix on today's evidence — the chain is demonstrably working end-to-end right now.

---

## 5. Version inventory (repository-wide, executable surfaces: `.github/workflows`, `scripts`, `workers`)

| Pattern | Occurrences |
|---|---|
| `v134` | 233 |
| `v149` | 133 |
| `v184.0` | 547 |
| `v184.1` | 16 |
| `v184` (any) | 659 |
| `v185.0` | 73 |
| `v185.1` | 8 |
| `v185.2` | 35 |
| `v185` (any) | 157 |
| `v200` | 25 |

**This confirms the mission's version-drift premise is accurate and measured:** `PIPELINE_VERSION` is declared `200.0`, but `v184`-labeled stage names/comments outnumber `v200`-labeled ones by roughly **26:1**. A full per-occurrence A–G classification (per mission section 3) across ~1,900 individual matches was out of scope for this pass — that is a multi-day mechanical-plus-judgment task in its own right (each occurrence needs code-level context, not just a grep hit) and is flagged as follow-up work, not attempted here to avoid a low-confidence mass-reclassification.

---

## 6. What this audit deliberately does not conclude

Per the mission's own Section 2 instruction ("do not modify architecture until this evidence exists") and this repository's CLAUDE.md Architecture Preservation Rule (architectural changes require substantially stronger evidence than feature additions, and a HIGH blast-radius change must be re-scoped before proceeding), this audit stops at evidence. It does not itself delete, reorder, or consolidate any of the 172 stages, touch R2 write topology, or change git-sync behavior — seeing one production run's timing is necessary but not sufficient evidence to safely re-architect a revenue-critical publication pipeline unattended. See the accompanying session report for a scoped proposal on what a safe first increment would look like.
