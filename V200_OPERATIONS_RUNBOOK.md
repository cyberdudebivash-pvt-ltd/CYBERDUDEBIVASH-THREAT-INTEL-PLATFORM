# Operations Runbook — v200

**Project TITAN Stage 22 Phase 8**
**Describes the actual deployed operational model** — a single Cloudflare Worker, not the
multi-region/ClickHouse/Kubernetes architecture described in `docs/BCP_DISASTER_RECOVERY.md`, which
`OPERATIONAL_READINESS.md` §1 found does not match reality. This runbook is deliberately written to
match what operators can actually do against the real system.

## Deployment

**Trigger**: push to `main` touching `workers/intel-gateway/src/**` or `wrangler.toml`, or manual
`workflow_dispatch` on `deploy-worker.yml`.

**What happens**: version injection from `config/version.json` → 4 data-integrity hard-fail gates
(encoding, output schema, dashboard-contract, regression-immunity) → pricing-consistency gate →
ASCII/null-byte + `node --check` syntax validation → esbuild bundle pre-flight → version-governance
drift check → JWT-secret presence check → `wrangler deploy --env production`.

**Approval**: script-based only — there is no GitHub-native `environment:` protection block
requiring a human click before deploy (`TITAN_V200_RELEASE_AUDIT.md` §9). If your organization
requires a human-in-the-loop gate before every production deploy, that gate does not exist today and
would need to be added to `deploy-worker.yml`.

## Post-deploy validation

`post-deploy-validation.yml` fires automatically (`workflow_run` trigger) after `deploy-worker.yml`
completes: API availability, version match, advisory count, JWT check, frontend integrity, full
validator, report-URL integrity — 7 gates, all script-based.

## Health check

`GET /api/health` — public, no auth. Checked by every deploy/rollback/orchestrator workflow. Also
probed on a schedule by `scripts/sla_engine.py`, writing `data/health/sla_status.json` and
`runtime_health.json`.

## Rollback procedure

1. Identify the target commit/tag to roll back to.
2. Trigger `enterprise-rollback-governance.yml` manually (`workflow_dispatch`), typing `CONFIRM` as
   required input.
3. The workflow tags current state, git-reverts to the target, and runs a post-rollback canary
   check.
4. A Telegram notification fires on completion (success or failure).
5. Alternative/lower-level path: `scripts/rollback_authority.py` (snapshot / register / rollback /
   validate / history / status subcommands) for operations outside the GitHub Actions UI.

There is no automatic rollback-on-failed-health-check — this is a human-triggered procedure.

## Incident response

**Alerting**: `enterprise-alerts.yml` runs every 30 minutes, classifies P0–P3 via
`scripts/enterprise_alert_manager.py`, notifies via **Telegram** (the only live channel — Slack is
referenced only as a commented-out example in `automated-backup.yml`; PagerDuty is not wired to
anything despite being named in `docs/BCP_DISASTER_RECOVERY.md`).

**On a P0/P1 alert**: 1) check `/api/health` and `data/health/sla_status.json` for current state;
2) check the most recent `deploy-worker.yml`/`post-deploy-validation.yml` runs for a correlated bad
deploy; 3) if a bad deploy is the cause, follow the rollback procedure above; 4) if the cause is
external (upstream feed source down, Cloudflare platform incident), there is no automated
multi-region failover — see `OPERATIONAL_READINESS.md` §1 for why the documented failover
capability does not currently exist in the actual deployment.

## Backup and restore

**Backup**: daily, 01:00 UTC (`automated-backup.yml`) — all 4 KV namespaces (`API_KEYS_KV`,
`RATE_LIMIT_KV`, `ANALYTICS_KV`, `SECURITY_HUB_KV`) exported to R2 as dated JSON snapshots
(`scripts/backup_kv_to_r2.py`), plus R2-to-R2 backup (`scripts/backup_r2.py`). Manual trigger
supports full/incremental/verify modes.

**Restore**: `scripts/restore_kv_from_r2.py`, pointed at a specific dated snapshot.

**Not backed up**: no D1 database exists in the live deployment, so there is nothing D1-specific to
restore.

## Scheduled automation load

~150–160 scheduled workflow runs/day across 55 workflow files (`TITAN_V200_RELEASE_AUDIT.md` §9).
Several workflows include explicit "CI bot guard" logic to prevent bot-authored commits from
re-triggering deploys — be aware of this when debugging an unexpected deploy trigger.

## Escalation

No PagerDuty integration exists today. Escalation is Telegram-based; ensure
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are current Cloudflare-bound secrets and that the
destination chat is actively monitored — there is no secondary paging path if it is not.
