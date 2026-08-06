# Workflow Concurrency Architecture Review

**Program:** Enterprise Release Readiness Program — Phase 3
**Scope:** All 55 repository-committed GitHub Actions workflows (`.github/workflows/*.yml`)
**Method:** Direct extraction of every `concurrency:` block (`group:`, `cancel-in-progress:`) from the
committed YAML via `grep`, cross-referenced against real run history. No field in this document is
inferred or estimated — every group name and setting below is a verbatim quote from the file and line
cited.
**Status:** Evidence-based. Where evidence is incomplete, the gap is stated explicitly rather than filled
with an assumption.

---

## 1. Executive summary

All 55 of 55 workflows have concurrency protection: 54 via a workflow-level `concurrency:` block, and the
remaining one (`repository-integrity-check.yml`) via two job-level blocks instead (see §5). Across all 55
files there are **42 distinct literal concurrency-group-name strings**. 41 of those 42 are single-workflow
or self-scoped (per-`github.ref`, per-input, or per-`github.workflow`) groups with no cross-workflow
collision surface. **One group — the literal, unsuffixed string `sentinel-data-writer` — is shared by 15
separate workflow files (14 currently active, 1 manually disabled).** This is the dominant structural finding of this review: a single serialization point that
every content-generation and intelligence-enrichment workflow in the platform funnels through.

This is not a new discovery invented for this program — the pattern is a known, named, intentional
platform convention (`sentinel-blogger.yml` itself carries a "P0 RACE CONDITION FIX" comment documenting
its own addition to this group, and `TITAN_PAGES_DEPLOYMENT_INCIDENT_2026-08-06.md` / PR #125, merged
today at 14:36:58Z, added `weekly-threat-brief.yml` to the same group for the same reason: preventing
concurrent writers from racing on `gh-pages`). What this review adds is the **first complete enumeration**
of every member of that group in one place, and an explicit statement of the collision mode it does and
does not protect against.

---

## 2. What `cancel-in-progress: false` does and does not protect against

All 15 `sentinel-data-writer` members use `cancel-in-progress: false`. This is correct and intentional —
these are data-writing jobs (they commit back to the repository and/or push to `gh-pages`), and cancelling
one mid-write risks a corrupted or partial commit. However, **`cancel-in-progress: false` only protects the
one currently-*running* job in a concurrency group.** Per GitHub's own documented concurrency semantics: if
a second job targeting the same group arrives while the first is running, the second is queued (`pending`).
If a **third** job targeting the same group arrives before the first finishes, the third does not queue
behind the second — it **replaces** the second in the pending slot, and the second is cancelled. Only the
currently-running job and the single most-recently-queued job are ever kept; every other pending job for
that group is discarded.

This exact mechanism was directly observed and confirmed during this program's own re-validation activity
earlier today: three `sentinel-data-writer` members (`multi-source-intel.yml`, `detection-engine.yml`,
`enterprise-intel-quality.yml`) were dispatched within seconds of each other; one ran, and two of the three
were cancelled — not because `cancel-in-progress` was misconfigured (it was not), but because this
pending-slot-replacement behavior is inherent to any concurrency group with more than two near-simultaneous
triggers, regardless of the `cancel-in-progress` setting. The same signature (two same-timestamp
cancellations against a `sentinel-data-writer` member) is independently present in this repository's own
run history from August 4–5, confirming this is a standing structural characteristic of the group, not an
artifact of this program's own testing.

**Practical consequence:** with 14 active members on independent cron schedules (see
`WORKFLOW_SCHEDULE_REVIEW.md`), any hour in which three or more of those schedules land within the same
group's busy window can silently drop a scheduled run — the dropped run shows as `cancelled` in the Actions
tab, not as a retry-worthy `failure`, so it is easy to miss without deliberately looking (as this program
did).

---

## 3. The `sentinel-data-writer` group — full membership

| # | Workflow file | Display name | Trigger cadence | State |
|---|---|---|---|---|
| 1 | `sentinel-blogger.yml` | sentinel-blogger | push (`scripts/**.py`, `agent/**.py`) + schedule `0 0,8,16 * * *` + monthly `0 0 1 * *` + manual | Active — flagship pipeline |
| 2 | `multi-source-intel.yml` | CDB Multi-Source Intelligence Enrichment v142 | schedule `45 1,5,9,13,17,21 * * *` + manual | Active |
| 3 | `detection-engine.yml` | Detection Engine - Rule Generation | schedule `30 */12 * * *` + manual | Active |
| 4 | `enterprise-intel-quality.yml` | SENTINEL APEX Enterprise Intelligence Quality v1 | schedule `15 2,6,10,14,18,22 * * *` + manual | Active |
| 5 | `report-engine.yml` | Premium Report Engine - Weekly Briefing | schedule `0 6 * * 1` + manual | Active |
| 6 | `weekly-analyst-briefing.yml` | CDB Weekly Analyst Briefing | schedule `0 8 * * 1` + manual | Active |
| 7 | `bughunter-resilient.yml` | Bug Hunter Resilient Recon | schedule `15 */8 * * *` + manual | Active |
| 8 | `weekly-threat-brief.yml` | weekly-threat-brief | schedule `30 2 * * 1` + manual | Active — **joined this group via PR #125 today**, replacing its own previously-isolated `sentinel-weekly-brief` group |
| 9 | `precognition-engine.yml` | CDB Sentinel APEX -- Precognition Engine v184.0 | schedule `0 */8 * * *` + manual | Active |
| 10 | `arsenal.yml` | CDB Sentinel APEX - Arsenal v38.0 | schedule `0 6 * * *` | Active |
| 11 | `bughunter-recon.yml` | CDB Bug Hunter Recon Engine v49.0 | schedule **commented out** in file — manual-only at present | Active file, but not currently on a cron (see §6) |
| 12 | `convergence.yml` | CDB Sentinel APEX - Convergence v37.0 | schedule `0 */12 * * *` | Active |
| 13 | `omnishield.yml` | CDB Sentinel APEX - OmniShield v36.0 | schedule `15 */12 * * *` | Active |
| 14 | `syndicate.yml` | CyberDudeBivash Sentinel Syndication Engine | schedule **commented out** in file — manual-only at present | Active file, but not currently on a cron (see §6) |
| 15 | `r2-data-sync.yml` | " DISABLED - R2 Intel Data Sync v134 (merged into sentinel-blogger v134.0)" | workflow_dispatch only, `workflow_run` trigger also commented out | **`disabled_manually` at the GitHub platform level** — kept as a file per this repo's Deprecation Instead of Deletion policy, contributes zero runtime collision risk today |

**Active runtime membership: 14.** (15 files declare the group; 1 is platform-disabled.) Of the 14, 2
(`bughunter-recon.yml`, `syndicate.yml`) currently have no active cron trigger and only enter the group on
manual dispatch, so the effective *scheduled* collision surface is **12 workflows**, all on independent
cron expressions with no coordinating offset logic between them beyond what each file's own comments
mention pairwise (e.g. `multi-source-intel.yml`'s comment "FIXED: no overlap with sentinel-blogger" only
reasons about one other member, not the full group of 12).

---

## 4. All other concurrency groups — verified distinct, no collision

Every group below was checked against the full 55-file sweep and confirmed unique (single workflow file,
or a `${{ github.ref }}` / `${{ github.event.inputs.* }}` / `${{ github.workflow }}` suffix that makes each
run's group instance self-scoped and therefore non-colliding with any other workflow).

| Group pattern | Member(s) | Collision surface |
|---|---|---|
| `sentinel-data-writer-<suffix>` (nexus, genesis, zerodayhunter, hardening, factory, sovereign, ai-predictions) | 7 workflows, each its own suffixed group | None — deliberately namespaced out of the bare group despite the similar name |
| `sentinel-deployment` | `sync-dashboard.yml` (platform-disabled) | None (disabled) |
| `sbom-generation-${{ github.ref }}` | `sbom-generation.yml` | Self only |
| `platform-build-deploy-${{ github.ref }}` | `platform-build-deploy.yml` | Self only |
| `sentinel-storage-lifecycle` | `storage-lifecycle-governance.yml` | None |
| `access-governance-${{ github.ref }}` | `access-governance-gate.yml` | Self only |
| `sentinel-observability-writer` | `enterprise-observability.yml` | None (deliberately renamed off `sentinel-data-writer` per its own in-file comment, to avoid queuing behind 20–35min governance/hardening runs) |
| `worker-deploy` | `deploy-worker.yml` | None |
| `gumroad-refresh` | `gumroad-refresh.yml` | None |
| `sentinel-environment-promotion-${{ inputs.promote_to }}` | `environment-promotion.yml` | Self only, per-target-environment |
| `ui-file-guardian` | `ui-file-guardian.yml` | None |
| `sentinel-enterprise-alerts` | `enterprise-alerts.yml` | None |
| `production-rollback` | `enterprise-rollback-governance.yml` | None (intentionally exclusive — "Never cancel an in-flight rollback") |
| `sentinel-ai-writer` | `generate-and-sync.yml` | None |
| `v149-hardening-${{ github.ref }}` | `v149-hardening.yml` | Self only |
| `sast-${{ github.ref }}` | `sast-security-scan.yml` | Self only |
| `autonomous-guardian` | `autonomous-guardian.yml` | None |
| `sentinel-dashboard-feeds` | `dashboard-feeds-sync.yml` | None |
| `repository-integrity-validate-${{ github.ref }}` / `repository-integrity-drift-${{ github.ref }}` | `repository-integrity-check.yml` (2 jobs, 2 groups) | Self only |
| `revenue-engine-deploy` | `deploy-revenue-engine.yml` | None |
| `ai-threat-analyst-${{ github.ref }}` | `ai-threat-analyst.yml` | Self only |
| `apex-infra-pipeline` | `telemetry-fabric.yml` | None |
| `sentinel-post-deploy-validation` | `post-deploy-validation.yml` | None |
| `sentinel-governance-writer` | `enterprise-governance.yml` | None |
| `lead-autoresponder` | `lead_autoresponder.yml` | None |
| `sentinel-guardian` | `status-monitor.yml` | None |
| `sentinel-self-healing` | `self-healing.yml` | None |
| `report-generator-regression-${{ github.ref }}` | `report-generator-regression-gate.yml` | Self only (PR-validation gate; `cancel-in-progress: true` is correct here — a newer push should supersede an older gate run on the same ref) |
| `sentinel-storage-governance` | `storage-governance.yml` | None |
| `telegram-revenue` | `telegram-revenue.yml` | None |
| `sentinel-production` | `master-deployment-orchestrator.yml` | None |
| `sentinel-staleness-monitor` | `pipeline-staleness-monitor.yml` | None |
| `backup-${{ github.workflow }}` | `automated-backup.yml` | Self only (expands to this workflow's own name — functionally a no-op suffix since only this file uses it, but harmless) |
| `revenue-orchestrator` | `revenue-orchestrator.yml` | None |

**Total distinct groups: 41.** Zero unintended collisions found outside the `sentinel-data-writer` group
documented in §3.

---

## 5. Workflows with no concurrency protection at all

**None.** Verified directly (not inferred): `grep -lE "^\s*group:\s*\S+"` across all 55 files returns all
55 — every workflow in the repository has at least one `group:` declaration. 54 declare a workflow-level
`concurrency:` block (`^concurrency:` at column 0); the remaining file, `repository-integrity-check.yml`,
has no workflow-level block but declares two separate **job-level** `concurrency:` blocks instead
(`repository-integrity-validate-${{ github.ref }}` and `repository-integrity-drift-${{ github.ref }}`,
one per job) — a valid, deliberate pattern (its two jobs are independent and don't need to serialize with
each other), not a gap. This review's first draft incorrectly stated two workflows had no concurrency
block at all, based on an unchecked arithmetic assumption rather than direct verification; that claim has
been corrected here after re-running the check with an indentation-agnostic pattern.

---

## 6. Secondary finding: two `sentinel-data-writer` members have no active schedule

`bughunter-recon.yml` and `syndicate.yml` both carry a `schedule:` block whose `cron:` line is commented
out in the committed YAML (`#   - cron: '15 */8 * * *'` and `#   - cron: '0 */2 * * *'` respectively). Both
are `workflow_dispatch`-only at present. This is not a defect — it reduces the group's live collision
surface — but it means the group's *effective* current membership (12 scheduled + 2 manual-only) differs
from its *declared* membership (14 active), which matters for interpreting historical run-frequency data:
any future re-enablement of either cron would add a 13th or 14th scheduled contender to the busiest
concurrency group in the platform without further changes elsewhere.

---

## 7. Recommendation posture (holding for Phase 7)

This document is Phase 3 (evidence-gathering) only. Per this program's explicit constraint — do not remove
concurrency protections without analysis, do not restructure without evidence, do not optimize for the
number of files touched — no changes are proposed here. The `sentinel-data-writer` group's 14-way
membership is flagged for the Phase 4 (Schedule Review) cross-reference and the Phase 7 (Hardening)
decision, not acted on unilaterally in this document. See `WORKFLOW_SCHEDULE_REVIEW.md` for whether the 12
active cron schedules actually land close enough together in practice to make pending-slot cancellation a
frequent occurrence versus a rare edge case.
