# Workflow Operational Recommendations

**Program:** Enterprise Release Readiness Program — Phase 7/9 (evidence-justified hardening options; no
change proposed here has been applied unless explicitly marked APPLIED)
**Principle followed:** per this program's explicit constraint, nothing below optimizes for the number of
files touched. Every recommendation states the evidence behind it and is separable from the others — none
require accepting the whole list to act on one.

---

## 1. Applied this session

| Change | File | Evidence | Risk |
|---|---|---|---|
| Added 3 missing bare-paren-close EOF tokens (`");"`, `"),"`, `")"`) | `scripts/encoding_guard.py` | Reproducing `generate-and-sync.yml` CI failure, quoted log, git-stash A/B verified | None — strictly widens acceptance, cannot regress a currently-passing file (see `WORKFLOW_ROOT_CAUSE_ANALYSIS.md` §2.3) |

## 2. Recommended, not applied — requires explicit authorization

### 2.1 Stagger the 00:00 UTC `sentinel-data-writer` cluster

**Evidence:** `WORKFLOW_SCHEDULE_REVIEW.md` §1-2 — six workflows (`convergence`, `precognition-engine`,
`sentinel-blogger`, `bughunter-resilient`, `omnishield`, `detection-engine`) trigger within 30 minutes of
each other at 00:00 UTC daily, against a concurrency group that can only run one and queue one at a time.
This is the single largest scheduling collision in the platform and recurs every day without exception.

**Proposed minimal change:** offset `convergence.yml` (currently `0 */12`) to `20 */12` and
`omnishield.yml` (currently `15 */12`) to `40 */12` — both already run independently of the others'
content, a 20-40 minute shift changes nothing about what they produce, and this alone breaks the 6-workflow
cluster into two smaller, non-overlapping groups of 2-3. `sentinel-blogger.yml`'s own schedule — the
highest-criticality member — is deliberately left untouched.

**Why not applied automatically:** this is a behavior change to production schedules, explicitly named in
this program's constraints as requiring evidence-backed authorization before modification, not something to
apply opportunistically inside an audit pass. The evidence above is offered so this decision can be made
deliberately, not to pre-empt it.

**Alternative not recommended:** widening the concurrency group's effective capacity (e.g., splitting
`sentinel-data-writer` into two parallel groups) was considered and rejected as a first move — it changes
the group's fundamental serialization guarantee (which exists to protect concurrent writes to shared state)
for 14 workflows at once, a far larger blast radius than a two-workflow schedule offset for the same
practical benefit.

### 2.2 Escalate the GitHub Pages deployment mechanism if the stall recurs again

**Evidence:** `WORKFLOW_ROOT_CAUSE_ANALYSIS.md` §3 — 4 confirmed occurrences of the same Pages
`deployment_queued` stall today (11:14, 12:08, 12:52, and 17:41 UTC), despite this morning's PR #125
already adding cross-workflow concurrency coordination and an observability gate. The durable fix
(migrating `sentinel-blogger.yml`'s and `weekly-threat-brief.yml`'s Pages deploy step from
`JamesIves/github-pages-deploy-action` to `actions/upload-pages-artifact` + `actions/deploy-pages`) is
already fully scoped in `TITAN_PAGES_DEPLOYMENT_INCIDENT_2026-08-06.md` §3, blocked only on a one-time,
non-code repository setting change (Settings → Pages → Build and deployment → Source → "GitHub Actions").

**Recommendation:** if this stall is observed a 5th time, treat that as sufficient evidence to make the
one-time settings change and ship the already-scoped migration, rather than continuing to accumulate
occurrences. This program does not make that settings change itself (no tool access to repository settings,
and it is exactly the kind of infrastructure-affecting action this program's own guidance reserves for
explicit authorization).

### 2.3 Investigate GitHub Actions runner-capacity contention with GitHub Support if it recurs beyond today

**Evidence:** `WORKFLOW_FAILURE_ANALYSIS.md` §3 — 5 jobs across 6 different concurrency groups queued for
15-16 minutes with `runner_id:0` and no log archive, spanning at least 16:16Z-18:13Z today, on top of an
earlier (~15:34-17:25Z) window this program had already identified before the formal audit began. This
platform has no self-hosted runners (100% `ubuntu-latest`/`ubuntu-24.04`), so this is GitHub-hosted-runner
contention, not a capacity problem this repository controls directly.

**Recommendation:** no repository-side fix exists for this. If the pattern persists into tomorrow (i.e., is
not resolved by the time this document is read), it is worth checking GitHub's public status page and, if
warranted, opening a support inquiry — but a single day's contention window, even a multi-hour one, does not
yet clear the bar for that escalation on its own.

## 3. Explicitly considered and rejected

- **Increasing `sbom-gate`'s or other starved jobs' `timeout-minutes`.** The failures in
  `WORKFLOW_FAILURE_ANALYSIS.md` §3 are queue-time cancellations before a runner was ever assigned — a
  longer `timeout-minutes` value has no effect on a job that never starts running. This would be a change
  with zero benefit to the actual problem, exactly the "increase timeouts without evidence" anti-pattern
  this program's own constraints warn against.
- **Removing or loosening the `sentinel-data-writer` concurrency group's `cancel-in-progress: false`
  setting.** This setting is correct and protects against mid-write cancellation corrupting a commit; the
  collision this program found is about the group's *pending-slot* behavior, which `cancel-in-progress`
  does not govern either way (see `WORKFLOW_CONCURRENCY_REVIEW.md` §2). Changing it would not fix the
  identified problem and would introduce the exact risk it exists to prevent.
- **Broadening `encoding_guard.py`'s `__tests__/`-style scope-exclusion to cover the scaffolding
  directories** (`evidence-registry/`, `intelligence-platform/`, `enterprise-gateway/`,
  `relationship-framework/`) as an alternative to the token-enumeration fix actually applied. Considered and
  documented in `WORKFLOW_ROOT_CAUSE_ANALYSIS.md` §2.3 as the guard's own stated "general fix" direction, but
  rejected for *this* fix because it is a larger behavioral change (reduced truncation-detection coverage
  across 4 directories) than the narrow, evidenced problem required. Left as a documented option for a
  future maintainer if token enumeration keeps recurring.

## 4. Next 3 highest-leverage improvements (forward-looking, not evidence of a current defect)

Per this repository's own "Continuous Self-Improvement Engine" convention:

1. **A dedicated `historical success-rate` pass per workflow** — this audit established a complete static
   configuration inventory (`WORKFLOW_INVENTORY.md`) and deep evidence for every failure actually observed
   in one ~2-hour window, but a full 30-day rolling success-rate per workflow (mentioned as a possible Phase
   1 field) was explicitly scoped out as too large for this pass (`WORKFLOW_SCHEDULE_REVIEW.md` §5). Worth a
   dedicated future pass if ongoing reliability tracking becomes a stated priority.
2. **Consolidate `actions/checkout` and `actions/setup-python` versions** — `WORKFLOW_INVENTORY.md` §6 found
   3 different `setup-python` version pins and 2 files still on `checkout@v4` while the rest use `v6.0.2`.
   Not a defect, but a small, low-risk normalization opportunity.
3. **A named owner/on-call convention per workflow criticality tier.** This audit had to *infer* criticality
   from workflow names and job structure (stated explicitly as a rubric in `WORKFLOW_INVENTORY.md`'s header)
   because no workflow declares an owner or escalation contact anywhere in its YAML or a companion file. For
   the 6 workflows this audit classified CRITICAL (`deploy-worker.yml`, `enterprise-rollback-governance.yml`,
   `deploy-revenue-engine.yml`, `sentinel-blogger.yml`, `automated-backup.yml`, `revenue-orchestrator.yml`),
   an explicit, documented owner would shorten response time on a genuine incident.
