# Project TITAN Stage 13 — Enterprise Intelligence Platform Services, Contract Reference

Source: `workers/intel-gateway/src/intelligence-platform/service-contracts.js`. Every contract
below is `Object.freeze`d at every level (name, methods, history) — verified in
`service-contracts.test.js`. Versioning reuses Stage 12's `isContractForwardCompatible()`/
`checkContractCompatibility()` unchanged; see `TITAN_STAGE12_CONTRACT_DOCUMENTATION.md` for that
algorithm's own reference if needed — it is not re-documented here since it was not re-implemented
here.

## IntelligenceServiceContract — v1.0.0

**Source:** `intelligence-service.js`
**Owner:** Project TITAN Stage 13
**Deprecation guidance:** none yet (initial version). Any future breaking change to a listed
method requires a new `history` entry with `backwardCompatibleWithPrevious: false` and a
documented migration path, per this repository's Backward Compatibility principle.

| Method | Behavior |
|---|---|
| `IntelligenceLookupService.getEvidence(uuid)` | Direct delegate to `EvidenceService.lookup.getEvidence` |
| `IntelligenceLookupService.findEvidence(criteria)` | Direct delegate to `EvidenceService.lookup.findEvidence` |
| `IntelligenceLookupService.byCVE/byThreatActor/byCampaign/byIOC/byReport/byAttackTechnique/bySource/byConfidenceTier` | Delegate to `EnterpriseQueryService`'s corresponding `queryBy*` |
| `IntelligenceLookupService.byVendor/byProduct/byMalware` | Delegate to `EnterpriseQueryService`'s corresponding `queryBy*` — **throws**, documenting a confirmed platform gap (see `TITAN_STAGE13_QUERY_DOCUMENTATION.md` equivalent — Known Gaps in `TITAN_STAGE13_SERVICE_ARCHITECTURE.md` §5) |
| `ThreatIntelligenceService.getThreatProfile(dimension, value)` | Composes lookup + confidence aggregation + a provenance sample for one of 5 dimensions into one response |

## QueryContract — v1.0.0

**Source:** `query-service.js`

12 methods: `queryByEvidence`, `queryByReport`, `queryByCVE`, `queryByThreatActor`,
`queryByCampaign`, `queryByIOC`, `queryByConfidence`, `queryBySource`,
`queryByAttackTechnique` (9 delegate to `EvidenceQueryEngine` unchanged), plus `queryByVendor`,
`queryByProduct`, `queryByMalware` (3 throw a specific, named error — see
`TITAN_STAGE13_SERVICE_ARCHITECTURE.md` §5 for why each one does).

## CorrelationContract — v1.0.0

**Source:** `correlation-engine.js`

| Method | Behavior |
|---|---|
| `correlateEvidence(uuid)` | Every other evidence record sharing a `related_*` dimension |
| `aggregateConfidence(records)` | Tallies `canonical_confidence_object.tier` across a record set — projects P25's own score, does not recompute it |
| `correlateBySource/correlateByReport/correlateByIOC` | Direct delegates to `EvidenceQueryEngine` |
| `correlateByRelationship(entityId)` | Pass-through to `RelationshipResolutionService.resolveRelationships()` — **throws** if no provider injected (ADR-0010 not Accepted) |

## ProvenanceContract — v1.0.0

**Source:** `evidence-registry/provenance-engine.js` (Stage 12, reused directly — not
redefined). Same 6 methods as Stage 12's own `ProvenanceContract`:
`getEvidenceLineage`, `getVersionLineage`, `getRelationshipLineage`, `getConfidenceLineage`,
`getSourceLineage`, `getAuditLineage`. This is the identical object, importable from either
`evidence-registry/service-contracts.js` or `intelligence-platform/service-contracts.js` — see
`service-contracts.test.js`'s identity assertion.

## IntelligenceValidationContract — v1.0.0

**Source:** `intelligence-service.js`

| Method | Behavior |
|---|---|
| `validateEvidence(evidence, options)` | Direct delegate to `EvidenceValidationService.validateEvidence` |
| `validateBatch(entities)` | Direct delegate to `EvidenceValidationService.validateBatch` |
| `validateIntelligenceBundle({evidence, sourceId})` | New in Stage 13: cross-entity referential check (does `sourceId` resolve to registered evidence?) composed on top of the two delegates above — not a reimplementation of evidence validation itself |

**Naming note:** named `IntelligenceValidationContract`, not `ValidationContract`, specifically
to avoid colliding with Stage 12's own `ValidationContract` identifier — see
`TITAN_STAGE13_SERVICE_ARCHITECTURE.md` §8.

## IntelligenceMetricsContract — v1.0.0

**Source:** `intelligence-service.js` + `evidence-registry/service-metrics.js` (single shared
`ServicePlatformMetrics` instance — see `TITAN_STAGE13_SERVICE_ARCHITECTURE.md` §9)

| Method | Behavior |
|---|---|
| `IntelligenceMetricsService.snapshot()` | Passthrough to `EvidenceService.metrics.snapshot()` — already reflects every Stage 13 call, since the counters object is shared |
| `IntelligenceMetricsService.sharedServiceMetrics` | Exposes the shared instance itself, so callers/tests can assert identity, not just equal shape |
| `ServicePlatformMetrics.timed/recordQuery/snapshot` | Stage 12's own methods, unchanged |

**Naming note:** named `IntelligenceMetricsContract`, not `MetricsContract`, for the same
collision-avoidance reason as `IntelligenceValidationContract` above.

## Consuming a contract

```js
import { QueryContract, checkContractCompatibility } from "./service-contracts.js";

const result = checkContractCompatibility(QueryContract, myExpectedVersion);
if (!result.compatible) {
  // handle a stale caller expectation — see Stage 10's schema.js for the original algorithm
  // this reuses, and TITAN_STAGE10_EVIDENCE_MIGRATION_GUIDE.md for the general pattern.
}
```
