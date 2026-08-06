# Project TITAN Stage 13 — Operational Guide

## What is, and isn't, running

**Not running anywhere by default.** `workers/intel-gateway/src/intelligence-platform/` is not
imported by `index.js` or any `pNN-handlers.js` file — zero live Cloudflare Worker request ever
reaches this code. Verified independently by `intelligence-platform/__tests__/zero-blast-radius.test.js`
(Node) and ten new checks in `scripts/titan_architecture_governance_check.py` (Python).

**The one thing that does run:** `scripts/intelligence_platform_snapshot.mjs`, a standalone
Node CLI script (Phase 10's one authorized internal consumer), invoked manually or by CI — never
by a customer request. It is gated behind `EIPS_FLAGS.INTERNAL_ADOPTION_ENABLED`, which is
`true` in `development`/`testing` and `false` in `canary`/`production`:

```
node scripts/intelligence_platform_snapshot.mjs production   # no-op: flag is false, prints a message, exits 0
node scripts/intelligence_platform_snapshot.mjs development  # runs the platform, prints a JSON snapshot
```

## Instantiation (for a future integration point)

```js
import { createIntelligencePlatform } from "./intelligence-platform/platform.js";

const { enabled, platform, reason } = createIntelligencePlatform({ environment: "development" });
if (!enabled) {
  console.log(reason); // "EIPS_ENABLED is false for environment ..."
} else {
  const evidence = await platform.lookup.byCVE("CVE-2026-1234");
  const profile = await platform.threatIntelligence.getThreatProfile("cve", "CVE-2026-1234");
}
```

`createIntelligencePlatform()` accepts a `deps` override for every constructor argument
`IntelligenceService` itself accepts (`evidenceService`, `queryEngine`, `provenanceEngine`,
`relationshipResolution`, `serviceMetrics`) — the same dependency-injection pattern
`EvidenceService` established in Stage 12.

## Migration guidance — adopting this platform from a future consumer

There is no data to migrate (nothing before this stage produced `IntelligenceService`-shaped
output), so this section covers **adoption**, not schema migration:

1. **A future internal script** (batch job, report generator, CLI tool) — follow
   `scripts/intelligence_platform_snapshot.mjs`'s own pattern exactly: import from
   `intelligence-platform/platform.js`, check `resolveEipsFlags(environment).INTERNAL_ADOPTION_ENABLED`
   (or define a new, equally-narrow flag if the new consumer's risk profile differs), construct
   via `createIntelligencePlatform()`, never reach into `EvidenceRegistry`'s private fields
   (`_repository`/`_versionManager`/`_indexes`/`_metrics`/`_lifecycleStates`/`_lifecycleAuditTrail`
   — governed by `check_no_eips_registry_private_field_bypass()`).
2. **A future live `pNN-handlers.js` route or `index.js` wiring** — explicitly **not**
   authorized by this stage (see `TITAN_STAGE13_SERVICE_ARCHITECTURE.md` §10 and this stage's
   completion report). This is Stage 14's named scope ("Internal REST layer... Service
   gateway... API version negotiation"). Whoever picks that up should: (a) confirm
   `EIPS_ENABLED`/a new, purpose-specific flag for the target environment, (b) add the import
   AFTER the last existing import in `index.js` per this repository's Import Chain Protection
   rule, (c) update `zero-blast-radius.test.js` and the ten Stage 13 governance checks that
   currently assert this directory is unreachable from `index.js` — those assertions will need
   to change from "must not" to "must, and only via this one authorized route," mirroring how
   this stage itself updated `evidence-registry/__tests__/zero-blast-radius.test.js` with one
   narrow, named exception rather than a blanket relaxation.
3. **Relationship correlation, once ADR-0010 is Accepted** — implement a concrete
   `RelationshipProviderInterface` (see `evidence-registry/relationship-resolution.js`) backed
   by whatever ADR-0010's eventual Decision names as canonical, inject it via
   `createIntelligencePlatform({ deps: { relationshipResolution } })`. No change to
   `correlation-engine.js` itself is required — the pass-through contract was built for exactly
   this to be a DI swap, not a code change.

## Rollback

- **The one live consumer** (`intelligence_platform_snapshot.mjs`): stop invoking it, or rely
  on `INTERNAL_ADOPTION_ENABLED`'s existing `false` default in `canary`/`production` — no code
  change needed. `rollbackEipsFlags()` returns the all-disabled `production` state explicitly,
  for a caller that wants to force it regardless of environment.
- **The directory as a whole**: `git revert` the commits under this stage — nothing outside
  `intelligence-platform/` and the one snapshot script depends on it (verified by the
  zero-blast-radius tests/checks), so reverting is a clean, self-contained operation with zero
  downstream consumers to coordinate with.

## Observability

`ServicePlatformMetrics.snapshot()` (one shared instance across Stage 12 + 13 — see
`TITAN_STAGE13_SERVICE_ARCHITECTURE.md` §9) exposes: call counts and latency percentiles per
named operation, query counts per dimension (now including `correlation.*`-namespaced Stage 13
operations alongside Stage 12's own), relationship-resolution outcomes, provenance-lookup
counts, validation failures, and contract-version mismatches. Access via
`platform.metrics.snapshot()` or directly via `platform.evidenceService.metrics.snapshot()` —
both return the identical merged object, proven in `metrics-sharing.test.js`.

## Performance baseline (Phase 9, measured this stage)

See `TITAN_STAGE13_PERFORMANCE_BASELINE.md` for the full table and reproduction steps. Summary:
service composition ~0.5ms (100x+ under a 50ms budget), unified 10-dimension lookup over 1,000
records ~118ms (2.5x under a 300ms budget), 5-operation correlation over 1,000 records ~39ms
(12x+ under a 500ms budget), validation ~7ms (25x+ under a 200ms budget), shared-metrics
`.timed()` overhead ~4µs/call.

## Support readiness

- **Runbook for "the snapshot script is failing"**: it constructs an entirely fresh, in-memory
  `EvidenceRegistry` on every invocation and touches no external storage — a failure is a code
  or dependency issue, never a data/persistence issue. Re-run with
  `EIPS_ENVIRONMENT=development node scripts/intelligence_platform_snapshot.mjs` for full output.
- **Runbook for "governance flagged something in intelligence-platform/"**: run
  `python3 scripts/titan_architecture_governance_check.py` locally; every Stage 13 finding names
  the exact file and property violated (duplicate service, registry bypass, contract drift,
  etc.) — cross-reference against `TITAN_STAGE13_SERVICE_ARCHITECTURE.md` for what that property
  is supposed to mean.
- **Escalation path for ADR-0010**: unchanged from Stage 12 — see
  `docs/adr/0010-relationship-graph-ownership.md`'s own Approval section for required sign-offs.
