# Project TITAN Stage 15 — Operational Guide

## What runs today

Two governance-script entry points, both advisory-only (same non-blocking posture as every prior stage's checks — CI wraps this script in `continue-on-error`):

```bash
python3 scripts/titan_architecture_governance_check.py
```
Runs all 55 checks (including Stage 15's #55, Gateway-bypass detection) and prints the Gateway adoption metrics line first, before the findings list. Exit code 0 if clean, 1 if findings exist — neither blocks the build.

```bash
python3 scripts/test_titan_stage14_governance_checks.py
```
39 fixture tests (32 from Stage 14 + 7 from Stage 15) proving positive and negative detection for every Stage 14/15 check, run against temp directories, never the real repo.

The two snapshot scripts (`scripts/enterprise_gateway_snapshot.mjs`, `scripts/intelligence_platform_snapshot.mjs`) are unchanged in how they run — see `TITAN_STAGE14_OPERATIONAL_GUIDE.md` and `TITAN_STAGE15_MIGRATION_RUNBOOK.md` respectively.

## Reading the adoption metrics

```
Gateway adoption (Stage 15, informational -- not a pass/fail gate): 1/2 known consumers
Gateway-backed (50.0%); 1 direct-composition legacy
```

`total_known_consumers` counts only `.mjs`/`.js` files under `scripts/` that reference `intelligence-platform/` or `enterprise-gateway/` — it is **not** a count of every file in the repo that touches evidence/intelligence concepts (see `TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md` §2.3 for why the much larger P16-P38/Python universe is excluded by design, not by oversight). This number will only move when a new `scripts/` consumer is added or the deprecated script is fully removed (Stage 16+).

## Migration guidance for a future consumer

A new internal script that needs evidence/intelligence functionality should import `createEnterpriseGateway()` from `enterprise-gateway/platform.js` and call `gateway.dispatch({capability, method, args, grantedCapabilities})` — never `createIntelligencePlatform()` directly. `check_gateway_bypass_new_direct_composition_consumers()` will flag the latter pattern automatically (advisory, not blocking) if it's not the one named legacy exception. See `scripts/enterprise_gateway_snapshot.mjs` as the reference pattern.

## Rollback

See `TITAN_STAGE15_MIGRATION_RUNBOOK.md` §5 — a single source revert, no data/schema/flag implications.

## Observability

Gateway-level observability is unchanged from Stage 14 (`GatewayMetrics.snapshot()`, the shared `ServicePlatformMetrics` call-count/latency-percentile chain — see `TITAN_STAGE14_PHASE2_COMPLETION_REPORT.md` §2.3 for the full trace). Stage 15 adds one static, point-in-time signal on top: the adoption-metrics line above, computed fresh on every governance-script run, not persisted or trended over time.

## Gateway Adoption Dashboard — specification (not built this stage)

The brief calls for a dashboard *specification*, not an implementation — appropriate given the current 2-consumer sample size doesn't yet justify a live dashboard. If/when adoption grows past a handful of consumers, this is what should exist:

- **Data source:** `compute_gateway_adoption_metrics()`'s return shape (already JSON-serializable: `total_known_consumers`, `gateway_backed`, `direct_composition_legacy`, `adoption_percentage`, `consumers[]` with per-file classification) — no new data model needed, just a scheduled capture of this function's output.
- **Suggested cadence:** one snapshot per governance-script CI run (once that CI wiring exists — see "Known limitations" below), appended to a `data/quality/gateway_adoption_history.jsonl`-style file, mirroring this repo's existing `data/quality/*.json` / `data/observability/*_telemetry.jsonl` conventions rather than inventing a new storage pattern.
- **Suggested view:** adoption percentage over time (line), current consumer list with classification (table) — composable from the existing `data/observability/dashboard.html`/`dashboard_payload.json` generation pipeline (`scripts/` already has an "Enterprise Observability Layer" bot producing exactly this kind of artifact for other metrics) rather than a new bespoke dashboard.
- **Explicitly not specified here:** real-time updates, alerting thresholds, or a standalone new HTML page — none justified by a 2-consumer sample; would be premature scope for the actual current adoption scale.

## Support readiness

- **"The governance script reports a new Gateway bypass finding"** — a new `scripts/*.mjs`/`*.js` file imports `intelligence-platform/` directly. Either route it through `EnterpriseGateway.dispatch()` instead (preferred), or, if direct composition is genuinely required and reviewed, add its filename to `AUTHORIZED_LEGACY_GATEWAY_BYPASS_CONSUMER_NAMES` in `scripts/titan_architecture_governance_check.py` with a comment explaining why (mirroring how `intelligence_platform_snapshot.mjs` itself is documented there).
- **"The adoption percentage looks wrong / didn't move"** — confirm the file actually lives under `scripts/` and has a `.js`/`.mjs` extension; the scan does not currently recurse into other top-level directories (by design — see the adoption report §2.1 for why `scripts/` was the right and complete scope this stage).
- **"I want to un-deprecate `intelligence_platform_snapshot.mjs`"** — see `TITAN_STAGE15_MIGRATION_RUNBOOK.md` §5; it's a clean revert with no downstream effects.

## Known limitations

- Neither snapshot script is CI-wired (confirmed by exhaustive workflow grep) — both are manual/dev-invocation only, despite their own docstrings' "or by CI" language. Pre-existing, not fixed this stage.
- The `node --test` suites (359 tests across the three directories) still run only locally/manually — CI runs only the advisory governance script. Stage 14's own #1 highest-leverage recommendation, still outstanding.
- Adoption metrics are computed fresh on each run, not persisted/trended — see the Dashboard specification above for what a future, larger-scale version would need.
- The Gateway-bypass check scans `scripts/` only, by filename-extension (`.js`/`.mjs`) — a hypothetical future consumer written as `.mts`/`.cjs` or placed outside `scripts/` would not be caught. Not observed in the repository today (confirmed: `scripts/` contains 100% of the non-test JS/mjs surface outside the three canonical directories), so not treated as a current gap, but worth knowing if the repo's layout changes.

## Performance baseline summary

See `TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md` §7 for the full measured Gateway-vs-direct-composition comparison (~107-157µs overhead per call, 3 runs). No regression against Stage 14's own baseline categories, re-measured alongside.
