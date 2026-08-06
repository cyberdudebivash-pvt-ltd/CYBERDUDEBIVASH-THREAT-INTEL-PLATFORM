# Project TITAN Stage 12 — Internal Contract Documentation

Source: `workers/intel-gateway/src/evidence-registry/service-contracts.js`. Five versioned
contracts, all currently at `1.0.0`. "Versioned" means: each contract carries a `history` array
(oldest first), and `isContractForwardCompatible(history, fromVersion, toVersion)` /
`checkContractCompatibility(contract, callerExpectedVersion)` answer whether a caller written
against an older version can safely assume the current one, by walking the history exactly the
way `schema.js` (Stage 10) already walks `SCHEMA_VERSION_HISTORY` for `CanonicalEvidence` itself
— same algorithm, generalized, not reimplemented per contract.

These are internal, source-level contracts (this codebase's convention for "interface" —
abstract classes with `NOT_IMPLEMENTED` methods, or in this case frozen descriptor objects — not
a schema-validated wire format). `check_contract_drift`-equivalent enforcement is
`check_no_duplicate_service_contracts()` + `check_contract_version_drift()`
(`titan_architecture_governance_check.py`, Phase 7), which check the *real* exported method
list and version history against what each contract claims, not the other way around.

## EvidenceServiceContract — v1.0.0

Source: `evidence-service.js`.

| Method | Behavior |
|---|---|
| `EvidenceService.registerEvidence` | Delegates to `EvidenceRegistry.registerEvidence` verbatim |
| `EvidenceService.updateEvidence` | Delegates to `EvidenceRegistry.updateEvidence` verbatim |
| `EvidenceService.supersedeEvidence` | Delegates to `EvidenceRegistry.supersedeEvidence` verbatim |
| `EvidenceService.archiveEvidence` | Delegates to `EvidenceRegistry.archiveEvidence` verbatim |
| `EvidenceLookupService.getEvidence` / `findEvidence` / `findByCVE` / `findByThreatActor` / `findByReport` / `findByCampaign` / `findByAttackTechnique` / `findByIOC` / `findBySource` / `findByConfidenceTier` | Each a 1:1 wrap of the identically-named `EvidenceRegistry` method |
| `EvidenceLifecycleService.getLifecycleState` / `getAuditTrail` / `transitionLifecycle` | Each a 1:1 wrap of the identically-named `EvidenceRegistry` method |

## RelationshipContract — v1.0.0

Source: `relationship-resolution.js` + `evidence-service.js`'s `EvidenceRelationshipService`.

| Method | Behavior |
|---|---|
| `EvidenceRelationshipService.findByRelationship` | Evidence's own `related_*` index (Stage 11) — "which evidence cites this entity" |
| `RelationshipResolutionService.resolveRelationships` | Throws (`NullRelationshipProvider`) unless a concrete provider is injected — see Service Architecture §6 |
| `RelationshipResolutionService.isWired` | Reports whether a concrete provider has been injected — always `false` in this stage's shipped state |

## ProvenanceContract — v1.0.0

Source: `provenance-engine.js`. Six lineage methods — see
`TITAN_STAGE12_PROVENANCE_SPECIFICATION.md` for the full field-level reference.

## ValidationContract — v1.0.0

Source: `evidence-service.js`'s `EvidenceValidationService`.

| Method | Behavior |
|---|---|
| `EvidenceValidationService.validateEvidence` | Delegates to `EvidenceRegistry.validateEvidence` → `validation.js`'s `validateCanonicalEvidence` (Stage 10, unmodified) |
| `EvidenceValidationService.validateBatch` | Calls `validation.js`'s `validateEvidenceBatch` directly (pure function, no registry state involved — not a bypass) |

## MetricsContract — v1.0.0

Source: `service-metrics.js` + `evidence-service.js`'s `EvidenceMetricsService`.

| Method | Behavior |
|---|---|
| `EvidenceMetricsService.snapshot` | Merges `EvidenceRegistry.getMetricsSnapshot()` (Stage 11, unmodified) with `ServicePlatformMetrics.snapshot()` (Stage 12, new) |
| `ServicePlatformMetrics.timed` | Wraps an async operation, recording call count + latency under a given name |
| `ServicePlatformMetrics.recordQuery` / `recordRelationshipResolution` / `recordProvenanceLookup` | Per-category counters, called by `query-engine.js` / `relationship-resolution.js` / `provenance-engine.js` respectively |
| `ServicePlatformMetrics.snapshot` | Point-in-time copy — count/mean/p50/p95/max latency per operation, plus every counter above |

## Compatibility checking, worked example

```js
import { checkContractCompatibility, EvidenceServiceContract } from "./service-contracts.js";

const result = checkContractCompatibility(EvidenceServiceContract, "1.0.0");
// { compatible: true, currentVersion: "1.0.0", callerExpectedVersion: "1.0.0" }
```

A caller written against a version not present in a contract's own `history` (a typo, or a
version that was never actually shipped) gets `compatible: false` — the same "unknown version is
never compatible with anything" rule `schema.js`'s `isForwardCompatible` already enforces for
`CanonicalEvidence` itself.
