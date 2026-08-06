# Enterprise Workflow Inventory

**Program:** Enterprise Release Readiness Program — Phase 1
**Scope:** All 55 workflows committed at `.github/workflows/*.yml` on `main`. (GitHub Actions additionally
lists 4 platform-native "dynamic" workflows with no committed YAML — Dependabot's dependency graph, CodeQL
default setup, code-scanning risk assessment, GitHub Pages build-deployment — these are covered in
`WORKFLOW_INVENTORY.md` §8, not in the per-workflow tables below, since there is no file to audit.)
**Method:** Every field below is extracted directly from the committed YAML (`grep`, cross-checked against
the GitHub API's live `name:`/`state:` fields) or is an explicitly-labeled inference from the workflow's
own display name and job names. No field is fabricated. Concurrency-group and schedule detail is
intentionally kept brief here — `WORKFLOW_CONCURRENCY_REVIEW.md` and `WORKFLOW_SCHEDULE_REVIEW.md` are the
canonical sources for that analysis; this document cross-references rather than duplicates it.

**Criticality rubric** (stated explicitly so the label is reproducible, not arbitrary):
- **CRITICAL** — directly serves the production customer-facing site/API, or directly fulfills paid revenue
- **HIGH** — gates a deployment, or produces data CRITICAL workflows directly consume
- **MEDIUM** — intelligence generation/enrichment feeding the platform but not directly customer-facing
- **LOW** — internal monitoring, observability, or periodic reporting only

---

## Category A — Deployment & Release (7 workflows)

| File | Display name | Purpose (grounded in job names) | Trigger | Primary timeout | Permissions | Criticality |
|---|---|---|---|---|---|---|
| `deploy-worker.yml` | deploy-worker | Deploys the Cloudflare Worker (job: `deploy`) | push to main, manual | 15m | `contents: read` | **CRITICAL** |
| `post-deploy-validation.yml` | SENTINEL APEX -- Post-Deploy Validation | Post-deploy smoke/health validation gated on `deploy-worker` success (job: `post-deploy-gate`) | `workflow_run` (deploy-worker), manual | 15m (+ ~10 sub-steps 2-5m each) | `contents: read`, `actions: read` | HIGH |
| `master-deployment-orchestrator.yml` | SENTINEL APEX -- Master Deployment Orchestrator | Post-deploy integrity/SLA/readiness evaluation (jobs: `orchestration-guard`, `deployment-integrity`, `manifest-freshness`, `sla-evaluation`, `deployment-readiness`) | `workflow_run` (deploy-worker), manual | 5 jobs, 5-10m each | `contents: read`, `actions: read` | HIGH |
| `environment-promotion.yml` | SENTINEL APEX -- Environment Promotion Pipeline | Controlled promotion between environments (jobs: `sequence-validation`, `change-management`, `release-certification`, `target-validation`, `promotion-summary`) | manual only | 5 jobs, 3-10m each | `contents: read`, `actions: read` | HIGH |
| `enterprise-rollback-governance.yml` | Enterprise Rollback Governance | Authorized rollback execution with audit trail (jobs: `authorize`, `snapshot`, `validate-target`, `rollback`, `post-rollback-canary`, `audit-log`) | manual only | 6 jobs, 2-15m each | `contents: write`, `actions: read`, `deployments: write` | **CRITICAL** (only path to reverting a bad production deploy) |
| `platform-build-deploy.yml` | platform-build-deploy | Builds/lints/security-scans services, frontend, Helm charts, Terraform (jobs: `lint`, `security-scan`, `build-services`, `build-frontend`, `validate-helm`, `terraform-validate`, `post-deploy-verify`) | push, pull_request | 7 jobs, 5-30m each | `contents: read`, `packages: write`, `security-events: write` | HIGH |
| `deploy-revenue-engine.yml` | deploy-revenue-engine | Deploys the revenue engine service (job: `deploy`) | push, manual | 15m | `contents: read` | **CRITICAL** (revenue-path deploy) |

## Category B — Content Generation & Publishing (`sentinel-data-writer` group; 17 workflows, 2 disabled)

Full concurrency-collision analysis for this category is in `WORKFLOW_CONCURRENCY_REVIEW.md` §3 and
`WORKFLOW_SCHEDULE_REVIEW.md` — not repeated here.

| File | Display name | Purpose | Schedule (UTC) | Timeout | Criticality |
|---|---|---|---|---|---|
| `sentinel-blogger.yml` | sentinel-blogger | Flagship content-generation + `gh-pages` publish pipeline (job: `generate-and-sync`) | `0,8,16` daily + monthly + push | 90m job cap | **CRITICAL** |
| `multi-source-intel.yml` | CDB Multi-Source Intelligence Enrichment v142 | Multi-source IOC/intel enrichment | 6x daily (`45 1,5,9,13,17,21`) | 25m | MEDIUM |
| `detection-engine.yml` | Detection Engine - Rule Generation | Generates detection rules (job: `generate-rules`) | `30 */12` | 10m | MEDIUM |
| `enterprise-intel-quality.yml` | SENTINEL APEX Enterprise Intelligence Quality v1 | Intelligence quality scoring | 6x daily (`15 2,6,10,14,18,22`) | 35m | MEDIUM |
| `report-engine.yml` | Premium Report Engine - Weekly Briefing | Weekly premium report generation | weekly Mon 06:00 | 15m | MEDIUM (direct revenue-product output) |
| `weekly-analyst-briefing.yml` | CDB Weekly Analyst Briefing | Weekly analyst briefing generation/send | weekly Mon 08:00 | 30m | MEDIUM |
| `bughunter-resilient.yml` | Bug Hunter Resilient Recon | Resilient recon scan (job: `resilient-recon`) | 3x daily (`15 */8`) | 15m | MEDIUM |
| `weekly-threat-brief.yml` | weekly-threat-brief | Weekly threat brief, also publishes to `gh-pages` directly | weekly Mon 02:30 | 20m (+10m sub) | MEDIUM |
| `precognition-engine.yml` | CDB Sentinel APEX -- Precognition Engine v184.0 | Predictive intelligence generation | 3x daily (`0 */8`) | 25m | MEDIUM |
| `arsenal.yml` | CDB Sentinel APEX - Arsenal v38.0 | Arsenal/tooling intelligence cycle | daily 06:00 | 15m | MEDIUM |
| `bughunter-recon.yml` | CDB Bug Hunter Recon Engine v49.0 | Recon scan (job: `bughunter-scan`) | **cron disabled in file — manual only** | 10m | LOW (currently manual-only) |
| `convergence.yml` | CDB Sentinel APEX - Convergence v37.0 | Convergence intelligence cycle | 2x daily (`0 */12`) | 20m | MEDIUM |
| `omnishield.yml` | CDB Sentinel APEX - OmniShield v36.0 | OmniShield intelligence cycle | 2x daily (`15 */12`) | 15m | MEDIUM |
| `syndicate.yml` | CyberDudeBivash Sentinel Syndication Engine | Cross-platform social syndication (LinkedIn/Twitter/Mastodon/Bluesky/Facebook/Tumblr/Reddit/Threads — ~20 distinct secrets) | **cron disabled in file — manual only** | 10m | LOW (currently manual-only; high secret-count makes it worth naming here) |
| `dashboard-feeds-sync.yml` | SENTINEL APEX — Dashboard Feeds Sync v184.0 | Syncs dashboard feed data to R2 + purges CF cache | 4x daily (`30 3,9,15,21`) | 15m | HIGH (customer dashboard freshness) |
| `r2-data-sync.yml` | " DISABLED - R2 Intel Data Sync v134 (merged into sentinel-blogger v134.0)" | **`disabled_manually`** — retained for Deprecation Instead of Deletion, manual-emergency-use only | none (workflow_run trigger also commented out) | 10m | N/A — disabled |
| `sync-dashboard.yml` | DISABLED - Dashboard Sync v134.0 (merged into sentinel-blogger v134.0) | **`disabled_manually`** — retained for Deprecation Instead of Deletion | none (schedule + workflow_run both commented out) | 15m | N/A — disabled |

## Category C — Intelligence Engines (isolated `sentinel-data-writer-<suffix>` groups; 9 workflows)

These share the *name* pattern with Category B's group but each has its own suffixed, non-colliding
concurrency group (see `WORKFLOW_CONCURRENCY_REVIEW.md` §4) — no cross-workflow collision risk in this
category.

| File | Display name | Purpose | Schedule (UTC) | Timeout | Criticality |
|---|---|---|---|---|---|
| `genesis-powerhouse.yml` | CDB GENESIS Intelligence Powerhouse v184.0 | Core intelligence generation cycle (job: `genesis-cycle`); upstream of `sentinel-factory.yml` | 4x daily (`45 */6`) | 30m | HIGH (feeds Category A's factory chain) |
| `sentinel-factory.yml` | CYBERDUDEBIVASH PRODUCT FACTORY v45.0 | Product assembly (job: `run-factory-assembly`), triggered by genesis-powerhouse completion | `workflow_run` (genesis-powerhouse), manual | 20m | HIGH |
| `nexus-intelligence.yml` | CDB NEXUS Intelligence Engine v39.0 | Nexus intelligence cycle | manual only (no active cron found) | 25m | MEDIUM |
| `zerodayhunter.yml` | CDB Sentinel APEX -- Zero-Day Hunter v184.0 | Zero-day hunting cycle | 4x daily (`45 */6`) | 25m | MEDIUM |
| `sovereign-platform.yml` | CDB Sovereign Intelligence Platform v184.0 | Sovereign platform intelligence cycle | 4x daily (`15 */6`) | 30m | MEDIUM |
| `ai-predictions.yml` | CDB AI Predictive Intelligence | AI-based predictive intelligence | 4x daily (`30 */6`) | 15m | MEDIUM |
| `ai-threat-analyst.yml` | CDB Sentinel APEX - AI Threat Analyst v37.0 | AI threat analysis cycle (job: `ai-analyst`) | 3x daily (`30 */8`) | 20m | MEDIUM |
| `generate-and-sync.yml` | SENTINEL APEX — Generate & Sync AI Tracker v160 | AI tracker generation/sync (job: `generate-ai-tracker`) — distinct file from `sentinel-blogger.yml` despite the similarly-named internal job there | 4x daily (`0 3,9,15,21`) | 20m | MEDIUM |
| `production-hardening-final.yml` | SENTINEL APEX — Final Production Hardening | Production hardening validation cycle | 4x daily (`0 1,7,13,19`) | 20m | MEDIUM |

## Category D — Security & Compliance (5 workflows)

| File | Display name | Purpose | Trigger | Timeout | Permissions | Criticality |
|---|---|---|---|---|---|---|
| `sast-security-scan.yml` | SAST Security Scan -- Bandit + Safety + Semgrep | Static analysis (jobs: `bandit`, `safety`, `semgrep`, `trufflehog`, `sast-gate`) | push, PR, daily `0 2`, manual | 5 jobs, 5-30m each | `contents: read`, `security-events: write`, `actions: read` | HIGH |
| `sbom-generation.yml` | SBOM Generation -- CycloneDX + SPDX | SBOM generation for Python + Docker (jobs: `sbom-python`, `sbom-docker`, `attach-to-release`, `sbom-gate`) | push, release, weekly `0 3 * * 1`, manual | 4 jobs, 5-30m each | `contents: write`, `security-events: write` | HIGH |
| `access-governance-gate.yml` | Access Governance Gate v184.0 | Access/permissions governance gate | push, PR, manual | 15m | `contents: read` | HIGH |
| `repository-integrity-check.yml` | repository-integrity-check | Canonical-docs validation + drift detection (jobs: `validate-canonical-docs`, `detect-repository-drift`) | push, weekly `17 6 * * 1` | 2 jobs, 5m each | `contents: read` | MEDIUM |
| `report-generator-regression-gate.yml` | Report Generator Regression Gate | Regression gate for report-generator manifest format | push, PR | 10m | `contents: read` | MEDIUM (PR gate, not production-runtime) |

## Category E — Governance & Observability (8 workflows)

| File | Display name | Purpose | Trigger | Timeout | Criticality |
|---|---|---|---|---|---|
| `enterprise-governance.yml` | SENTINEL APEX Enterprise Governance v2 | Governance gate + canary contract check (jobs: `governance_gate`, `canary_contract_check`) | 12x daily (`45 1,3,5,7,9,11,13,15,17,19,21,23`), push, manual | 20m / 10m | HIGH |
| `enterprise-observability.yml` | Enterprise Observability & Trust Validation | Observability/trust validation | 6x daily (`30 2,6,10,14,18,22`), manual | 25m | HIGH |
| `enterprise-alerts.yml` | SENTINEL APEX -- Enterprise Alert Monitor | Platform health alerting to Telegram (job: `platform-health-alert`) | every 30 minutes | 10m | HIGH (fastest-cadence monitor in the platform) |
| `autonomous-guardian.yml` | Autonomous Guardian Agent v184.0 | Post-run health checks after `sentinel-blogger` completes | `workflow_run` (sentinel-blogger), 2x daily, manual | 15m | HIGH |
| `status-monitor.yml` | CDB Platform Status Monitor v134 | Platform status check | 3x daily (`0 0,8,16`) | 10m | LOW |
| `self-healing.yml` | SENTINEL APEX -- Self-Healing Engine | Automated self-healing pass | every 2 hours (`15 */2`) | 20m | HIGH |
| `pipeline-staleness-monitor.yml` | Pipeline Staleness Monitor | Detects stale pipeline data | 4x daily (`0 0,6,12,18`) | 5m | LOW |
| `ui-file-guardian.yml` | UI File Guardian — SENTINEL APEX Card System v147 | UI file integrity baseline check | every 4 hours, push, manual | 10m | MEDIUM |

## Category F — Storage & Backup (3 workflows)

| File | Display name | Purpose | Trigger | Timeout | Permissions | Criticality |
|---|---|---|---|---|---|---|
| `automated-backup.yml` | Automated Backup — Encrypted / Versioned | Encrypted/versioned backup (jobs: `setup`, `full-backup`, `cf-data-backup`, `verify-backup`) | daily `0 1`, manual | 4 jobs, 5-30m each | `contents: read`, `actions: write` | **CRITICAL** (disaster-recovery path) |
| `storage-governance.yml` | SENTINEL APEX -- Storage Governance | Storage telemetry/scan/prune (jobs: `telemetry-collection`, `storage-scan`, `storage-prune`) | weekly `0 3 * * 1`, manual | 3 jobs, 5-15m each | `contents: write` | MEDIUM |
| `storage-lifecycle-governance.yml` | SENTINEL APEX Storage Lifecycle Governance v1 | Storage lifecycle governance | weekly `0 2 * * 0`, manual | 30m | `contents: write` | MEDIUM |

## Category G — Revenue & Monetization (4 workflows)

| File | Display name | Purpose | Trigger | Timeout | Criticality |
|---|---|---|---|---|---|
| `revenue-orchestrator.yml` | CYBERDUDEBIVASH REVENUE ORCHESTRATOR v44.0 | Purchase fulfillment/provisioning + CEO financial briefing (jobs: `fulfillment-and-provisioning`, `ceo-financial-briefing`) | `repository_dispatch` (gumroad_purchase, stripe_subscription_update), daily `0 0`, manual | 15m / 15m | **CRITICAL** (only automated path from a customer purchase to fulfillment) |
| `gumroad-refresh.yml` | gumroad-refresh | Refreshes Gumroad product data (job: `refresh-products`) | manual only | 10m | MEDIUM |
| `telegram-revenue.yml` | telegram-revenue | Revenue notifications to Telegram | 3x daily, manual | 10m | LOW |
| `lead_autoresponder.yml` | CDB Lead-to-Cash Auto-Responder | Lead-to-cash email auto-response | daily `0 8` | 10m | HIGH (direct lead conversion path) |

## Category H — Telemetry & Infrastructure (1 workflow)

| File | Display name | Purpose | Trigger | Timeout | Criticality |
|---|---|---|---|---|---|
| `telemetry-fabric.yml` | APEX Phase 5-10 — Telemetry & Intelligence Infrastructure Pipeline | Multi-stage telemetry/adversary-graph/AI-runtime-defense/malware-intelligence pipeline (6 jobs) | manual only (cron commented out) | 6 jobs, 15-25m each | MEDIUM |

## Category I — Hardening Suites (1 workflow)

| File | Display name | Purpose | Trigger | Timeout | Criticality |
|---|---|---|---|---|---|
| `v149-hardening.yml` | SENTINEL APEX v149 - Production Hardening Suite | Point-in-time hardening suite (cron commented out — manual only) | manual only | 15m | LOW (point-in-time, not continuously scheduled) |

---

## 6. Runner and action-version posture (all 55 workflows)

- **Runner:** 100% `ubuntu-latest`, except `platform-build-deploy.yml`, which pins all 7 of its jobs to
  `ubuntu-24.04` explicitly — the only workflow in the repository doing so. No self-hosted runners are used
  anywhere.
- **`actions/checkout` version:** overwhelmingly `v6.0.2`; two files (`dashboard-feeds-sync.yml`,
  `repository-integrity-check.yml`) still pin `v4`. Not a defect on its own, but a version-drift fact worth
  recording since a future bulk-bump would need to account for these two outliers.
- **`actions/setup-python` version:** split across `v5`, `v5.5.0`, `v5.6.0`, `v6.2.0` depending on file —
  no single canonical pin exists platform-wide.
- **Third-party (non-`actions/*`) actions in use:** `docker/setup-buildx-action`, `docker/build-push-action`,
  `docker/login-action`, `azure/setup-helm`, `hashicorp/setup-terraform`, `github/codeql-action/upload-sarif`,
  `softprops/action-gh-release`, `trufflesecurity/trufflehog` (pinned to `@main`, not a release tag — the
  only floating-ref third-party action found in the sweep), `JamesIves/github-pages-deploy-action` (used by
  both `sentinel-blogger.yml` and `weekly-threat-brief.yml` — see `TITAN_PAGES_DEPLOYMENT_INCIDENT_2026-08-06.md`
  for the incident this dual-writer pattern already caused and partially mitigated).
- **Artifact upload/download:** only 5 of 55 workflows use `actions/upload-artifact` or
  `actions/download-artifact` — `syndicate.yml`, `sast-security-scan.yml`, `sbom-generation.yml`,
  `automated-backup.yml`, `access-governance-gate.yml`. The rest either commit results directly
  (`contents: write` + `git push`) or push to external stores (R2/Cloudflare) rather than using Actions
  artifact storage.

## 7. `workflow_call` (reusable workflows)

Zero. No file in this repository defines or consumes a reusable workflow — confirmed by an explicit
`workflow_call:` grep across all 55 files returning no matches. All composition happens at the action
(`uses:`) level within single workflow files, or via the four `workflow_run` chains documented in
`WORKFLOW_DEPENDENCY_GRAPH.md`.

## 8. The 4 platform-native "dynamic" workflows (no committed YAML — informational only)

| Display name | Path | What it is |
|---|---|---|
| Dependency Graph | `dynamic/dependabot/update-graph` | GitHub-native Dependabot dependency-graph updater |
| Security Risk Assessment | `dynamic/github-code-scanning/code-security-risk-assessment` | GitHub-native code-scanning default-setup risk assessment |
| CodeQL | `dynamic/github-code-scanning/codeql` | GitHub-native default-setup CodeQL (not the repo's own `sast-security-scan.yml`, which is a separate, committed, advanced-setup scan) |
| pages-build-deployment | `dynamic/pages/pages-build-deployment` | GitHub Pages branch-based build/deploy processor — see `TITAN_PAGES_DEPLOYMENT_INCIDENT_2026-08-06.md` for a real, previously-documented incident involving this specific dynamic workflow |

These cannot be audited the way the other 55 are (no YAML to read, no permissions/secrets/timeout fields to
extract) — they are included here only so the inventory's workflow count (55 + 4 = 59) matches the GitHub
API's total exactly, closing out the Phase 0 count-reconciliation finding.
