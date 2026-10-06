# Project TITAN Stage 12 — Enterprise Evidence Service Platform (EESP), Service Architecture

**Status:** Implementation complete, inert (zero HTTP surface, zero customer-visible
functionality). Activates Stage 11's Enterprise Evidence Registry with an internal service
layer — the platform "every future intelligence capability will consume," per the stage's own
executive directive — without adding any persistence, validation, or lifecycle logic Stage 11
didn't already define.

## 1. Where this code lives, and why

Every Stage 12 file lives inside `workers/intel-gateway/src/evidence-registry/`, alongside
Stage 8/10/11's files — **not** a new sibling directory. Two reasons, both load-bearing:

1. **`zero-blast-radius.test.js`'s first test** treats any file *outside* `evidence-registry/`
   that contains the string `"evidence-registry"` as a boundary violation. A sibling directory
   whose files `import ... from "../evidence-registry/..."` would trip that check the moment it
   existed — not because the import is wrong, but because the test's exemption list is
   directory-based. Living inside the existing directory keeps this stage automatically exempt,
   with zero changes to that test.
2. **Precedent.** Stage 8 → Stage 10 → Stage 11 all grew the same directory rather than spinning
   up parallel ones. Stage 12 continues that pattern rather than introducing a new one.

## 2. The six modules and the "One X" principles they implement

| Principle (stage brief) | File | Class(es) |
|---|---|---|
| One Evidence Service | `evidence-service.js` | `EvidenceService` (facade) + 6 focused sub-services |
| One Query Engine | `query-engine.js` | `EvidenceQueryEngine` |
| One Provenance Provider | `provenance-engine.js` | `EvidenceProvenanceEngine` |
| One Relationship Provider | `relationship-resolution.js` | `RelationshipResolutionService` + `RelationshipProviderInterface` |
| One Service Layer | `service-contracts.js` | `ALL_SERVICE_CONTRACTS` (5 versioned contracts) |
| (Observability) | `service-metrics.js` | `ServicePlatformMetrics` |

**One Registry, One Source of Truth**: every class above takes an `EvidenceRegistry` (Stage 11)
instance as a constructor dependency and calls only its **public** methods
(`getEvidence`, `findEvidence`, `findByCVE`, ..., `resolveVersion`, `getVersionLineage`,
`getAuditTrail`, `transitionLifecycle`, `registerEvidence`, `updateEvidence`,
`supersedeEvidence`, `archiveEvidence`). None reach into `EvidenceRegistry`'s private
`_repository`/`_versionManager`/`_indexes`/`_metrics` fields — verified by
`check_no_registry_private_field_bypass()` (Phase 7). This is deliberate: two independent
instances of `EvidenceVersionManager` over two different repository instances would silently
diverge; going through the registry's own public API is the only way every Stage 12 component
sees identical state.

## 3. `EvidenceService` — the aggregating facade

```
EvidenceService
├── .lookup      EvidenceLookupService      (getEvidence, findEvidence, findByCVE, ...)
├── .version     EvidenceVersionService     (resolveVersion, getVersionLineage, ...)
├── .lifecycle   EvidenceLifecycleService   (getLifecycleState, transitionLifecycle, ...)
├── .validation  EvidenceValidationService  (validateEvidence, validateBatch)
├── .relationship EvidenceRelationshipService (findByRelationship — evidence's own related_* fields)
├── .metrics     EvidenceMetricsService     (snapshot: registry + service metrics merged)
└── .registry    → the one EvidenceRegistry instance every sub-service shares
```

`EvidenceService` also exposes `registerEvidence`/`updateEvidence`/`supersedeEvidence`/
`archiveEvidence` directly, as thin passthroughs — it does not wrap them in additional
validation or lifecycle logic (that would duplicate `registry-service.js`).

Each of the six sub-services remains independently importable — a consumer that only ever
validates evidence has no reason to import lookup/version/lifecycle machinery it will never
call.

## 4. `EvidenceQueryEngine` — twelve lookup dimensions, one naming convention

`EvidenceRegistry`'s own finder methods are inconsistently named (`getEvidence` vs. `findByCVE`
vs. `resolveVersion`). `EvidenceQueryEngine` exposes the same underlying data through one
uniform `lookupBy*` convention across all twelve dimensions (UUID, Evidence ID, Report, CVE,
Campaign, Threat Actor, IOC, ATT&CK, Relationship, Confidence, Source, Version). See
`TITAN_STAGE12_QUERY_DOCUMENTATION.md` for the full method reference, including the one
documented gap (`lookupByEvidenceId` uses a linear scan, not `indexes.js`'s unused
`byEvidenceId` index — a pre-existing Stage 11 gap, not something this stage introduced or
fixed).

## 5. `EvidenceProvenanceEngine` — six lineage views over Stage 11's existing history

Every lineage method projects specific fields across `EvidenceRegistry.getVersionLineage()`'s
already-stored, already-deep-frozen version history, or reads `getAuditTrail()` directly. No new
storage. See `TITAN_STAGE12_PROVENANCE_SPECIFICATION.md`.

## 6. `RelationshipResolutionService` — deliberately scoped narrower than the brief asked

The stage brief's Phase 4 asks this component to "Consume: Canonical Relationship Framework"
(P31 / ADR-0010's subject). **ADR-0010 is not part of this stage's Acceptance** — only
ADR-0008, ADR-0011, and ADR-0012 were Accepted (see `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`).
Two independent reasons block a direct P31 import here, not one:

1. **Governance**: this program has already tightened, not loosened, its rule against
   "internal-only, so it doesn't need the ADR" reasoning — `DEBT-021` documents exactly that
   pattern from Stage 10-11, and Stage 11.5 exists specifically to stop it from recurring.
2. **Architecture**: `check_evidence_registry_scaffolding_boundary()`/
   `zero-blast-radius.test.js` forbid any file in this directory importing a live
   `pNN-handlers.js` file, independent of ADR status. Importing `buildP31RelationshipBlock`
   directly would be this directory's first-ever production import since Stage 8.

`RelationshipResolutionService` therefore takes a `RelationshipProviderInterface` as an
**injected dependency**, mirroring `interfaces.js`'s `EvidenceProviderInterface` pattern exactly.
The default (`NullRelationshipProvider`) throws a clearly-labelled error naming the actual
blocker (ADR-0010 Acceptance) rather than silently returning `[]`, which could be mistaken for
"this entity has no relationships." Wiring a concrete, P31-backed provider is explicitly future,
separately-authorized work — not something this stage does, and not something a later stage
should do without re-checking ADR-0010's status first.

## 7. `service-contracts.js` — five versioned contracts, one shared compatibility algorithm

Each contract (`EvidenceServiceContract`, `RelationshipContract`, `ProvenanceContract`,
`ValidationContract`, `MetricsContract`) is documentation-as-data: a frozen object naming its
source file, its declared method surface, and a version history. `isContractForwardCompatible()`
reuses `schema.js`'s exact "every step must be recorded additive" walk (Stage 10), generalized
to any version-history array rather than five copy-pasted implementations. See
`TITAN_STAGE12_CONTRACT_DOCUMENTATION.md`.

## 8. `ServicePlatformMetrics` — service-layer observability, not a duplicate of Stage 11's

`registry-metrics.js`'s `EvidenceRegistryMetrics` (Stage 11) is unmodified and uncopied. This
class tracks concerns Stage 11 has no equivalent for: per-operation call counts and latency
(`timed()`), query counts by dimension, relationship-resolution outcomes, provenance-lookup
counts. `EvidenceMetricsService.snapshot()` merges both into one read rather than either class
duplicating the other's counters.

## Known gaps (documented, not fixed this stage)

- `lookupByEvidenceId` doesn't use `indexes.js`'s `byEvidenceId` index (pre-existing Stage 11
  gap — that index has never been surfaced by any `EvidenceRegistry` finder method). Fixing it
  means adding a method to `registry-service.js`, a Stage 11 file, out of this stage's
  additive-only scope.
- `EvidenceVersionService` does not expose `EvidenceVersionManager`'s
  `checkSchemaCompatibility()`/`migrateIfNeeded()` — those aren't part of `EvidenceRegistry`'s
  public surface, and reaching into its private `_versionManager` to get them would itself be
  the "registry bypass" Phase 7 exists to catch.
- `RelationshipResolutionService` has no concrete provider — by design, pending ADR-0010.
