# CYBERDUDEBIVASH® SENTINEL APEX
## Business Continuity Plan (BCP) & Disaster Recovery (DR) Runbook
**SOC 2 Control: CC9.2 — Business Continuity and Disaster Recovery**
**Version:** 163.0.0 | **Owner:** CTO / SRE Commander | **Review Cadence:** Quarterly
**Last Updated:** 2026-09-10

---

## 0. Accuracy Notice (2026-09-10 rewrite)

The prior version of this document (v162.0.0, 2026-05-26) described a multi-region AWS deployment
(CloudFront, Route 53, us-east-1/eu-west-1/ap-south-1), a ClickHouse HA cluster, a Redis cluster,
Kubernetes autoscaling, PagerDuty on-call, and specific "✅ verified" RTO/RPO figures, and closed
with a line asserting this control was SOC 2 "CERTIFIED." **None of that infrastructure exists in
this platform.** This was already flagged as a known gap in `CHANGELOG.md`'s v200 risk register
("`docs/BCP_DISASTER_RECOVERY.md` describes infrastructure ... not evidenced in the actual
single-Worker deployment") and left unfixed for several months. This rewrite replaces every claim
in that document with what is actually true today, verified against the live codebase rather than
assumed from the prior draft. Where a real gap exists, it is stated as an open item, not
papered over with an invented number.

---

## 1. Actual Production Architecture

The platform runs entirely on **Cloudflare's edge platform** — there is no AWS, ClickHouse, Redis,
or Kubernetes anywhere in the production path:

| Component | Real implementation |
|---|---|
| Compute | 3 Cloudflare Workers: `workers/intel-gateway`, `workers/revenue-engine`, `workers/intel-retention-engine` (see each `wrangler.toml`) |
| Key-value state | Cloudflare KV namespaces (`API_KEYS_KV`, `RATE_LIMIT_KV`, `ANALYTICS_KV`, `SECURITY_HUB_KV`, `REVENUE_CRM_KV`) |
| Object storage | Cloudflare R2 buckets (`sentinel-apex-data`, `sentinel-apex-reports`) |
| Relational state | Cloudflare D1 where used by revenue-engine |
| CI/CD & pipeline compute | GitHub Actions (scheduled workflows, not a Kubernetes cluster) |

**A genuine, structural resilience property of this architecture**: Cloudflare Workers execute at
Cloudflare's own global edge network (hundreds of PoPs) by default — there is no single-datacenter
dependency for compute the way a traditional single-region deployment would have. This is real and
requires no configuration on our part. It does **not** protect against a Cloudflare-wide platform
incident (rare, but has happened industry-wide to Cloudflare customers generally) — everything here
runs on one provider, and that is a genuine, disclosed concentration risk, not a solved problem.

The `infrastructure/{clickhouse,redis,kubernetes,terraform}/` directories and `platform/` monorepo
scaffold in this repository describe a different, more traditional architecture that was planned at
some point but is not what is deployed to production. They are not deleted here (Deprecation
Instead of Deletion) but must not be read as describing the live system.

## 2. Backup — real, automated, and running today

`.github/workflows/automated-backup.yml` runs daily (`0 1 * * *` UTC):
- `agent/backup/backup_engine.py --full`: encrypted, versioned backup of platform data to the
  configured destination (`CDB_BACKUP_DESTINATION`).
- `scripts/backup_kv_to_r2.py`: snapshots Cloudflare KV namespaces to R2 (`kv-snapshots/` prefix,
  explicitly excluded from the 7-day ephemeral-retention lifecycle policy — see
  `config/r2_lifecycle_policy.json` — because backup/DR data must outlive the disposable-artifact
  policy that governs everything else in R2).
- `scripts/backup_r2.py`: manifest + integrity check (SHA-256) of R2 bucket contents, sampled on a
  rotating window rather than 100%/day (see `docs/P0_R2_COST_CONTAINMENT.md` for why — a daily
  full-bucket scan was the second amplifier in the 2026-09-04 R2 billing incident).

**Open item, not yet closed**: the `verify-backup` job (`workflow_dispatch`, `backup_type=verify`)
calls `agent/backup/backup_engine.py --verify`, which re-downloads the encrypted archive and
re-checks its SHA-256 against the manifest — it does **not** decrypt or extract the archive, so it
confirms the backup file wasn't corrupted in transit/storage, not that a real restore would succeed.
The actual restore implementations (`scripts/restore_kv_from_r2.py`, `agent/backup/restore_engine.py`)
are fully coded but, as of this writing, are not invoked by any CI workflow and have no evidenced
restore-drill run. **A backup that has never been restored from is an unverified backup.** This is
tracked as an open action item (§5), not claimed as resolved.

## 3. R2 cost/lifecycle safety net

See `docs/P0_R2_COST_CONTAINMENT.md` for the full incident history and fix (PRs #369/#370/#374/#377).
Summary: the root cause of a real $27.31 R2 billing-overage incident (unbounded whole-corpus sync)
is fixed and CI-gated (`r2-finops-regression-gate.yml`, green on every push). A permanent, native
7-day object-lifecycle backstop is built and unit-tested (`scripts/r2_lifecycle_manager.py`); whether
it is actually armed on the production buckets is now checked automatically once a day
(`automated-backup.yml`'s `cf-data-backup` job, added 2026-09-10) rather than being an unverified
assumption, since applying it requires real Cloudflare credentials no sandboxed engineering session
has ever had.

## 4. Alerting and incident communication — real, but single-channel

Real, secret-backed Telegram alerting exists and is independently verified (not just claimed) in:
`scripts/pipeline_alert.py`, `scripts/check_pipeline_staleness.py`, `scripts/enterprise_alert_manager.py`,
wired into `enterprise-governance.yml`, `enterprise-rollback-governance.yml`, `self-healing.yml`, and
(as of 2026-09-10) `storage-governance.yml`'s anomaly-detection step, which previously received real
secrets but never actually sent a message — fixed to use the same `send_telegram()` function the
other call sites already prove works, rather than left as silent false confidence.

**Open items, not yet closed:**
- One Telegram channel + one email inbox (`ops/INCIDENT-RESPONSE.md`) — no on-call rotation, no
  escalation tiers, no PagerDuty (the prior version of this document claimed PagerDuty; it is not
  configured anywhere in this repository).
- The production deploy path itself (`deploy-worker.yml`, `master-deployment-orchestrator.yml`,
  `post-deploy-validation.yml`) and the R2 FinOps regression gate have no failure notification at
  all — a failure here is visible only as a red status in the GitHub Actions UI.
- No uptime/synthetic monitoring exists from outside Cloudflare's own infrastructure — a
  Cloudflare-wide incident would not be independently detected by anything in this repository.
- No evidence either core static secret (`ADMIN_SECRET`, the JWT signing secret) has ever been
  rotated since initial provisioning. `data/governance/jwt_governance.json` (the one committed run
  of the rotation-age checker) states plainly: `"secret_metadata.json not present (key rotation
  tracking not yet active)"`.

## 5. Actual Recovery Scenarios

### 5.1 Worker deploy failure / bad release
**Detection:** `deploy-worker.yml` / `post-deploy-validation.yml` CI status (currently: manual
observation of the Actions tab only — see §4's open item).
**Recovery:** `wrangler rollback` to the prior Worker version, or revert-and-redeploy via a new PR
per this repository's standard git workflow. No automated traffic failover exists or is needed —
Cloudflare serves the previously-deployed Worker version until a new deploy completes; there is no
partial-rollout state to reconcile.

### 5.2 KV/R2 data loss or corruption
**Detection:** Application-level validation gates (`scripts/regression_tests.py`,
`p33_production_certification.py`) would surface schema/content anomalies on the next pipeline run;
no real-time corruption alarm exists today.
**Recovery, as designed (not yet drilled):** restore the affected namespace/bucket from the most
recent `backup_kv_to_r2.py`/`backup_r2.py` snapshot using `scripts/restore_kv_from_r2.py` /
`agent/backup/restore_engine.py`. **This path has never been exercised end-to-end** (§2). Until a
real restore drill is run and its result recorded here, treat actual recovery time as unknown, not
as the specific minute figures the prior version of this document asserted.

### 5.3 Pipeline staleness (data silently stops updating)
**Real, evidenced precedent**: the 2026-09 dashboard-freshness incident stalled report generation
for approximately 10 days before detection (see `docs/P0_R2_COST_CONTAINMENT.md` §8b). Detection is
now real: `scripts/check_pipeline_staleness.py` (`pipeline-staleness-monitor.yml`) polls the GitHub
Actions API directly and alerts via Telegram on genuine multi-cycle staleness, with thresholds
calibrated to each monitored workflow's actual cadence (fixed 2026-09-10 after a prior version's
thresholds were tighter than the workflows they monitored could ever satisfy, guaranteeing false
alarms — see that script's own header comment).

## 6. Open Action Items (tracked here, not silently dropped)

1. Run a real restore drill (`scripts/restore_kv_from_r2.py`) against a non-production namespace,
   record the result and actual time-to-restore here, and wire it into a periodic CI check —
   carefully, since this script's target is a live Cloudflare KV namespace and a careless
   implementation could overwrite production data. Requires design review before automating.
2. Add real failure notification (reusing `scripts/pipeline_alert.py`'s proven `send_telegram()`) to
   `deploy-worker.yml`, `master-deployment-orchestrator.yml`, `post-deploy-validation.yml`, and
   `r2-finops-regression-gate.yml`.
3. Establish rotation for `ADMIN_SECRET` and the JWT signing secret, and populate
   `data/sovereign/secret_metadata.json` so `scripts/jwt_governance.py`'s existing age-check has
   real data to evaluate. Requires an operator with production secret-management access.
4. Decide, as a business/infra decision (not a documentation fix), whether multi-provider or
   independent-of-Cloudflare uptime monitoring is warranted given the platform's current stage, and
   whether an on-call rotation beyond the current single Telegram channel is needed.

## 7. BCP Document Sign-off

- **Rewritten:** 2026-09-10, against verified live code and configuration, replacing a version that
  described non-existent infrastructure.
- **Review Date:** 2026-09-10
- **Next Review:** 2026-12-10 (quarterly)
- **SOC 2 status:** self-assessed readiness only — see `data/compliance/soc2_readiness_report.json`,
  which explicitly disclaims that it "does not constitute SOC 2 certification of any kind." This
  document is not itself an audit or certification artifact.
