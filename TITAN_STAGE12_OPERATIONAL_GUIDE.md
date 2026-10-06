# Project TITAN Stage 12 — Operational Guide

## What is, and isn't, running

Nothing is running. Every class documented here is plain, uninstantiated source under
`workers/intel-gateway/src/evidence-registry/` — zero imports from `index.js` or any
`pNN-handlers.js` file (enforced by `zero-blast-radius.test.js` and Phase 7's governance
checks), zero HTTP routes, zero customer visibility. "Operational" in this guide means: how a
future, separately-authorized integration would instantiate and wire this layer, and how to
verify it's still safe to leave dormant in the meantime.

## Instantiation (for a future integration point)

```js
import { EvidenceRegistry } from "./evidence-registry/registry-service.js";
import { EvidenceService } from "./evidence-registry/evidence-service.js";
import { EvidenceQueryEngine } from "./evidence-registry/query-engine.js";
import { EvidenceProvenanceEngine } from "./evidence-registry/provenance-engine.js";
import { RelationshipResolutionService } from "./evidence-registry/relationship-resolution.js";
import { ServicePlatformMetrics } from "./evidence-registry/service-metrics.js";

const registry = new EvidenceRegistry();          // Stage 11 — one repository, one indexes, one version manager
const metrics = new ServicePlatformMetrics();       // shared across every Stage 12 component below

const evidenceService = new EvidenceService({ registry, serviceMetrics: metrics });
const queryEngine = new EvidenceQueryEngine(registry, metrics);
const provenanceEngine = new EvidenceProvenanceEngine(registry, metrics);
const relationshipResolution = new RelationshipResolutionService({ metrics }); // unwired by default -- see below
```

All five components share the **same** `registry` and `metrics` instances — constructing
independent ones per component would defeat both "One Registry" (divergent state) and
"one place to see observability" (split counters).

## Wiring Relationship Resolution (blocked pending ADR-0010)

`RelationshipResolutionService` ships with `NullRelationshipProvider`, which throws on every
call. To wire a real provider once ADR-0010 (Relationship Graph Ownership) is Accepted:

```js
import { RelationshipProviderInterface } from "./evidence-registry/relationship-resolution.js";
// import { buildP31RelationshipBlock } from "./p31-handlers.js";  // only after ADR-0010 Acceptance

class P31RelationshipProvider extends RelationshipProviderInterface {
  async getRelationshipsFor(entityId) {
    // adapt buildP31RelationshipBlock()'s shape to {relatedEntityId, relationshipType, confidence}
  }
}
const relationshipResolution = new RelationshipResolutionService({ provider: new P31RelationshipProvider(), metrics });
```

This wiring step is explicitly **not** part of Stage 12 and should not be done without first
re-confirming ADR-0010's disposition in `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` — Stage 12's
Acceptance covered ADR-0008/0011/0012 only.

## Rollback

Every Stage 12 file is new; none modify a Stage 8/10/11 file's behavior (verified:
`backward-compatibility.test.js` and the full 153-test Stage 11 suite remain green — see
completion report §6). Rollback is deleting the six new source files, their `__tests__/`
counterparts, and the seven new governance-check functions — a clean file-level revert with
zero data migration (nothing persists beyond a single process's in-memory registry) and zero
consumer impact (there are no consumers yet).

## Observability

`EvidenceMetricsService.snapshot()` (or any component's own `ServicePlatformMetrics.snapshot()`
if not routed through the facade) returns:

```json
{
  "registry": { "evidence_count": 0, "lifecycle_transitions": 0, "...": "EvidenceRegistryMetrics, Stage 11, unmodified" },
  "service": {
    "call_counts": {}, "call_latency_stats": {},
    "query_counts": {}, "relationship_resolutions": 0, "relationship_resolution_failures": 0,
    "provenance_lookups": {}, "validation_failures": 0, "contract_version_mismatches": 0
  }
}
```

No external sink — same passive-accumulator design as Stage 11's `registry-metrics.js`. A future
integration would read this snapshot into a `data/quality/`-style report, matching this
platform's existing convention (not done this stage — no scheduled caller exists yet, same gap
Stage 11's own metrics collector still has).

## Performance baseline (Phase 8, measured this stage)

`__tests__/service-performance-smoke.test.js`, run against Node 22, single process, 1,000-record
registry:

| Operation | Volume | Measured | Budget | Margin |
|---|---|---|---|---|
| `EvidenceService.registerEvidence` | 1,000 records | 39.0ms | 1,500ms | 38x under |
| `EvidenceQueryEngine` (all 12 dimensions) | 100 samples/dimension (1,200 lookups) | 147.4ms | 500ms | 3.4x under |
| `EvidenceProvenanceEngine` (all 6 lineage kinds) | 100 samples/kind (600 reads) | 4.2ms | 500ms | 119x under |

Not a load-tested production benchmark (no concurrency, no Worker cold-start harness) — a smoke
test confirming this layer's own overhead over Stage 11's already-smoke-tested registry stays a
rounding error against the platform's cold-start budget (CLAUDE.md: <50ms for the *whole
request*), consistent with `registry-performance-smoke.test.js`'s own stated scope.

## Support readiness

N/A this stage — nothing customer-facing exists yet to support. Support readiness becomes
relevant starting whichever future stage adds the first real route on top of this platform,
contingent on `DEBT-015`'s monitoring/alerting gap being closed first (pre-existing, platform-
wide, not new to Stage 12).
