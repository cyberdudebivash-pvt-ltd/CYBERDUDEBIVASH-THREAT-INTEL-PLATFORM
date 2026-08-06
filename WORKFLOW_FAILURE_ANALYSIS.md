# Workflow Failure Analysis

**Program:** Enterprise Release Readiness Program — Phase 2 (symptom catalog; see
`WORKFLOW_ROOT_CAUSE_ANALYSIS.md` for mechanism-level explanation and fixes)
**Scope:** Every workflow observed in a `failure` or unexpected `cancelled` state during the most recent
run-history window checked (2026-08-06, 16:16Z–17:57Z), plus the three workflows this program's own earlier
manual re-validation activity affected.
**Method:** Every run cited below was checked at the job level (`list_workflow_jobs`), not just the
run-level rollup — a run-level `"failure"` can mask a job-level `"cancelled"`, and conflating the two was
an explicit failure mode this program was warned against. Job logs were pulled directly
(`get_job_logs`/direct log fetch) wherever a log archive existed; where none existed, that is stated
explicitly rather than inferred.

---

## 1. Classification taxonomy applied

| Category | Definition used |
|---|---|
| Runner unavailable | Job never dispatched to a runner (`runner_id:0`, no `steps` array, no log archive exists) |
| Repository bug | Job executed, a step ran, and failed on this repository's own script/code |
| Dependency outage (external) | Job executed and failed because an external system (not this repo, not GitHub Actions infra) did not respond as expected |
| Concurrency cancellation | Job cancelled because a newer trigger replaced it in a shared concurrency group's pending slot |
| Manual cancellation | (not observed in this window) |

## 2. Incident catalog — 2026-08-06, 16:16Z–17:57Z window

| Workflow | Run(s) | Job conclusion | Category | Evidence basis |
|---|---|---|---|---|
| `access-governance-gate.yml` | `31123482028` (17:33:39Z) | cancelled, `runner_id:0`, no steps, queued 15:01 | **Runner unavailable** | `get_job_logs` → "No failed jobs found"; direct job-log fetch → HTTP 404 (no archive for a job that never ran) |
| `enterprise-observability.yml` | `31123700815` (17:38:16Z), `31119515846` (16:21:10Z) | both cancelled, `runner_id:0`, no steps, each queued exactly 15:01 | **Runner unavailable** | Same signature both times; workflow's own group (`sentinel-observability-writer`) is `cancel-in-progress:false` and structurally cannot self-cancel — cancellation is external |
| `sbom-generation.yml` | `31123481992` (17:33:39Z) | `sbom-python`: success; `sbom-docker`: success (Grype: 0 actionable criticals); `sbom-gate`: cancelled, `runner_id:0`, no steps; `attach-to-release`: correctly skipped (not a release event) | **Runner unavailable** (gate job only — the two substantive SBOM jobs completed and produced real artifacts) | 4-job breakdown confirms only the trivial downstream gate starved |
| `post-deploy-validation.yml` | `31123882200` (17:42:03Z) | cancelled, `runner_id:0`, no steps, queued 15:01 | **Runner unavailable** | Upstream `deploy-worker.yml` run `31123481980` independently confirmed `conclusion:success` — the deploy itself was healthy; only the post-deploy check job starved |
| `sentinel-blogger.yml` (2nd, later run) | `31124111016` (schedule, 17:57:08Z) | cancelled, `runner_id:0`, no steps, queued 16:19 | **Runner unavailable** | Checked specifically to rule out a second consecutive Pages-freshness-gate failure after the first one below — job-level data confirms this run never reached that gate, or any step, at all; it is the same starvation pattern as the other four, not a recurrence of §3's dependency outage |
| `generate-and-sync.yml` | `31123699233` (17:38:16Z) | failure — full execution through Stages 1-2, hard-failed at STAGE 3.2 GATE 3 (Encoding guard) | **Repository bug** | Quoted log: `FATAL: 1 Worker JS file(s) are TRUNCATED... relationship-types.js (lines=195, last=');')` |
| `sentinel-blogger.yml` | `31123481986` (17:33:39Z) | failure — full execution, ~100 stages passed, hard-failed at STAGE 5.4.9.1 (Pages freshness gate) | **Dependency outage (external)** | Quoted log: 36 retries over 12 minutes, live site `Last-Modified` never advanced; GitHub's `pages-build-deployment` run for this same commit independently confirmed still `status:queued` at time of check |
| `multi-source-intel.yml`, `detection-engine.yml`, `enterprise-intel-quality.yml` | (this program's own earlier manual dispatch, same window) | 2 of 3 cancelled | **Concurrency cancellation** | Already root-caused earlier in this program; explained structurally (not as an anomaly) by `WORKFLOW_CONCURRENCY_REVIEW.md` §2-3 |

## 3. What the five "Runner unavailable" cases have in common

`access-governance-gate.yml`, `enterprise-observability.yml` (both occurrences), `sbom-generation.yml`'s
`sbom-gate` job, `post-deploy-validation.yml`, and `sentinel-blogger.yml`'s own later scheduled run span
**six different concurrency groups** (`access-governance-${{ github.ref }}`, `sentinel-observability-writer`,
`sbom-generation-${{ github.ref }}`, `sentinel-post-deploy-validation`, and `sentinel-data-writer` itself) —
so this is not solely another instance of the `sentinel-data-writer` collision pattern documented in
`WORKFLOW_CONCURRENCY_REVIEW.md` (though it does affect that group too, on top of the collision mechanism
already explained there). Every one of these five jobs shares an identical fingerprint instead: `runner_id:0`,
empty `runner_name`, no `steps` array, and — critically — **no log archive exists for the job at all**
(`get_job_logs` reports zero failed jobs because the true conclusion is `cancelled`, not `failure`; direct
log-URL fetches for the job ID return HTTP 404). A job that never received a runner cannot have logs, by
definition.

Four of the five were queued for almost exactly **15 minutes and 1 second** before cancellation; the fifth
(`sentinel-blogger.yml`'s 17:57:08Z run) for **16 minutes 19 seconds** — close to the same duration, later
in the window. This uniform duration, combined with the fact that the same window also produced the
independently-explained `sentinel-data-writer` concurrency cancellations, is consistent with a period of
**repo-wide GitHub Actions runner-capacity contention** — the same class of transient platform-side
condition this program's earlier investigation (before this formal audit began) had already identified for
an *earlier* window today (~15:34–17:25 UTC). This window now confirmed to extend to at least **18:13:27Z**,
later than previously confirmed, rather than representing a new, distinct incident.

**Explicitly ruled out, not assumed:** `sentinel-blogger.yml`'s 17:57:08Z run was checked at the job level
specifically because its run-level conclusion (`failure`) invited the same misreading this program was
warned against — it would have been easy to record this as "the Pages freshness gate failed a second
consecutive time" without checking. It did not: the job never started (`runner_id:0`, no steps), so it never
reached the freshness gate, or any other stage. §2's row for `sentinel-blogger.yml`'s first, push-triggered
run (`31123481986`, 17:33:39Z) remains the only confirmed Pages-related failure today's data directly
examined.

**This is not asserted as certain** — GitHub does not expose a public status signal this program's tools
could independently query to confirm platform-side runner contention as opposed to some other explanation
for a 15-minute queued-then-cancelled job. It is the best-evidenced explanation available (uniform duration,
cross-cutting across unrelated concurrency groups, no log archive consistent with "never dispatched" rather
than "ran and failed"), stated as such rather than as a certainty.

## 4. Business-impact read of this catalog

Of the 7 workflows in this window's catalog:
- **1 required a real code fix** (`generate-and-sync.yml` — see `WORKFLOW_ROOT_CAUSE_ANALYSIS.md` §2 for the
  fix, now applied and pushed).
- **1 is working exactly as designed** (`sentinel-blogger.yml` — its brand-new freshness gate, added by
  PR #125 earlier today, correctly caught a genuine external Pages-deployment stall instead of silently
  publishing stale content; see `WORKFLOW_ROOT_CAUSE_ANALYSIS.md` §3).
- **5 needed no code change at all** — the deploy underlying `post-deploy-validation.yml` succeeded, the
  SBOMs underlying `sbom-generation.yml` were generated correctly, and the remaining "Runner unavailable"
  cases are a transient platform condition that resolves on retry, not a defect in this repository.

No customer-facing data was lost or corrupted in this window: every "Runner unavailable" case is a
*scheduled run that didn't happen*, not a run that happened incorrectly — the next scheduled or manually
re-dispatched run for each of those five workflows should proceed normally.
