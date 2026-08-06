# Project TITAN Stage 13 — Enterprise Intelligence Platform Services (EIPS), Service Architecture

## 1. Where this code lives, and why

`workers/intel-gateway/src/intelligence-platform/` — a sibling directory to Stage 8-12's
`evidence-registry/`, not a subdirectory of it. This is a deliberate architectural choice, not
an accident: `evidence-registry/`'s own zero-blast-radius boundary (enforced since Stage 8 by
`check_evidence_registry_scaffolding_boundary()` and `zero-blast-radius.test.js`) says nothing
outside that directory may reference it. Stage 13 is the first stage whose entire charter is to
compose it from outside — putting Stage 13's code inside `evidence-registry/` would have
required weakening that boundary's actual meaning ("nothing references this") rather than
adding one narrow, named, documented exception to it (which is what this stage did instead —
see `TITAN_STAGE13_COMPLETION_REPORT.md`'s Reuse Report).

Not imported by `index.js` or any `pNN-handlers.js` file. Same posture `evidence-registry/` has
held since Stage 8: real, tested, composable code with zero live request-path reachability,
verified independently from both Node (`__tests__/zero-blast-radius.test.js`) and Python
(`titan_architecture_governance_check.py`'s ten new Stage 13 checks) toolchains.

## 2. Dependency diagram

```text
                     ┌─────────────────────────────────────────────┐
                     │   workers/intel-gateway/src/index.js         │
                     │   (live Cloudflare Worker request router)    │
                     └───────────────────┬───────────────────────────┘
                                          │  imports p16-p38 handlers
                                          │  (Stage 13 is NOT in this chain)
                                          ▼
                     ┌─────────────────────────────────────────────┐
                     │   pNN-handlers.js (P16-P38)                  │
                     └─────────────────────────────────────────────┘

        ▲ never imported by, never imports ▼  (one-directional, enforced both ways)

┌───────────────────────────────┐        ┌───────────────────────────────────────────┐
│ evidence-registry/  (Stage 8-12)│◄──────│ intelligence-platform/  (Stage 13)          │
│                                 │composes│                                             │
│  registry-service.js            │        │  intelligence-service.js                    │
│    EvidenceRegistry              │        │    IntelligenceService (facade)             │
│  evidence-service.js             │        │    ThreatIntelligenceService                │
│    EvidenceService (facade)      │        │    IntelligenceLookupService                │
│  query-engine.js                 │        │    IntelligenceValidationService             │
│    EvidenceQueryEngine           │        │    IntelligenceMetricsService                │
│  provenance-engine.js            │        │  query-service.js                           │
│    EvidenceProvenanceEngine      │        │    EnterpriseQueryService                   │
│  relationship-resolution.js      │        │  correlation-engine.js                      │
│    RelationshipResolutionService │        │    IntelligenceCorrelationService            │
│  service-metrics.js              │        │  platform.js                                │
│    ServicePlatformMetrics ───────┼───┐    │    createIntelligencePlatform()             │
│  service-contracts.js            │   │    │  service-contracts.js                       │
│    5 contracts                   │   │    │    6 contracts (imports/re-exports           │
│                                   │   │    │    ProvenanceContract from the left column)  │
└───────────────────────────────┘   │    │  feature-flags.js                           │
                                       │    │    EIPS_FLAGS                                │
                          ONE shared  │    └───────────────────────────────────────────┘
                          instance,   │
                          not two ────┘
                       (metrics-sharing.test.js proves this by identity)

┌───────────────────────────────────────────┐
│ scripts/intelligence_platform_snapshot.mjs  │  Phase 10's one authorized internal consumer.
│ (standalone Node CLI, NOT part of the        │  Imports intelligence-platform/ directly.
│  Worker's request path)                      │  Gated behind INTERNAL_ADOPTION_ENABLED.
└───────────────────────────────────────────┘
```

## 3. The six modules and the "One X" principles they implement

| Module | Exports | Principle |
|---|---|---|
| `intelligence-service.js` | `IntelligenceService`, `ThreatIntelligenceService`, `IntelligenceLookupService`, `IntelligenceValidationService`, `IntelligenceMetricsService` | "One Intelligence Service" — a single facade a Stage 13 consumer imports and instantiates, exactly mirroring `EvidenceService`'s own role one layer down |
| `query-service.js` | `EnterpriseQueryService` | "One Enterprise Query Service" — 12 named dimensions, 9 delegating, 3 documenting a confirmed platform gap |
| `correlation-engine.js` | `IntelligenceCorrelationService` | "One Correlation Engine" — five real dimensions plus a pass-through-only sixth (relationship), gated on ADR-0010 |
| `platform.js` | `createIntelligencePlatform()` | "One Composition Root" — the only place the full Stage 12 + 13 dependency graph is wired together |
| `service-contracts.js` | 6 versioned contracts | "One Contract Registry" — reuses Stage 12's own compatibility algorithm unchanged |
| `feature-flags.js` | `EIPS_FLAGS`, `resolveEipsFlags()`, `rollbackEipsFlags()` | Mirrors `CEC_FLAGS`/`EER_FLAGS`'s exact per-environment shape (Single Source of Truth for the environment list itself, re-exported from `evidence-registry/feature-flags.js`) |

## 4. `IntelligenceService` — the aggregating facade

Composes, via dependency injection, exactly one `EvidenceService`, one `EvidenceQueryEngine`,
one `EvidenceProvenanceEngine`, one `RelationshipResolutionService`, and one shared
`ServicePlatformMetrics` instance — then layers `EnterpriseQueryService`,
`IntelligenceLookupService`, `IntelligenceCorrelationService`, `IntelligenceValidationService`,
`IntelligenceMetricsService`, and `ThreatIntelligenceService` on top, all sharing those same
underlying instances. No sub-service holds its own registry, metrics instance, or storage.

`ThreatIntelligenceService.getThreatProfile(dimension, value)` is this stage's one genuinely new
composed operation: lookup + confidence aggregation + a provenance sample, in one call, across
five dimensions (cve/threatActor/campaign/ioc/attackTechnique). No single Stage 12 method
already returns this shape — it is real orchestration, not a rename.

## 5. `EnterpriseQueryService` — 12 dimensions, 9 real, 3 documented gaps

A Phase 2 research pass (repo-wide audit of every `p16`-`p38` handler and the Python
ingestion/scoring tree — see this stage's completion report for the full findings table)
confirmed which of the brief's 12 named dimensions have a canonical, composable implementation
this service can delegate to, and which do not:

- **9 delegate directly** to `EvidenceQueryEngine`'s existing `lookupBy*` methods: Evidence,
  Report, CVE, Threat Actor, Campaign, IOC, Confidence, Source, ATT&CK Technique.
- **3 document a confirmed gap** rather than inventing a model: **Vendor** (zero structured
  representation anywhere in the platform), **Product** (an informal `affected_products` field
  exists elsewhere, but `CanonicalEvidence` has no `related_products` field and
  `EvidenceQueryEngine` has no corresponding method — extending Stage 11's schema is out of this
  stage's scope), **Malware** (only nested under Threat Actor as `actor_malware`; the one
  standalone normalizer, `p31-handlers.js`'s `_normalizeMalware()`, is dead code with zero call
  sites). Each throws a specific, named error rather than returning a silent empty array —
  mirroring `relationship-resolution.js`'s `NOT_WIRED` pattern, applied to a schema gap instead
  of an ADR gate.

## 6. `IntelligenceCorrelationService` — five real dimensions, one pass-through

Evidence, confidence, source, report, and IOC correlation compose `EvidenceQueryEngine` and
`EvidenceService` directly. Relationship correlation
(`correlateByRelationship`) is pass-through only, delegating verbatim to Stage 12's
`RelationshipResolutionService` — this stage's Special Governance Rule (ADR-0010 still Proposed,
confirmed against `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`) forbids any new graph logic or a
direct `p31-handlers.js` import, and none was added.

## 7. Provenance — Phase 4 fully satisfied via reuse, zero new code

`EvidenceProvenanceEngine`'s existing 6 lineage kinds (evidence, version, relationship,
confidence, source, audit) already cover all 5 kinds Phase 4's brief names. `IntelligenceService`
exposes it directly as `.provenance` — no Stage 13 wrapper class exists, because none was needed.
`service-contracts.js`'s `ProvenanceContract` is Stage 12's own object, imported and re-exported
unchanged (proven by identity assertion in `service-contracts.test.js`), not redefined.

## 8. `service-contracts.js` — six contracts, one shared compatibility algorithm, one naming fix

`isContractForwardCompatible()`/`checkContractCompatibility()` are Stage 12's own functions,
re-exported unchanged. Two of Stage 13's contracts (`ValidationContract`, `MetricsContract` in
their first draft) collided by name with two of Stage 12's own — caught by this stage's own new
`check_no_duplicate_eips_contracts()` governance check before merge, not after. Resolved by
renaming to `IntelligenceValidationContract`/`IntelligenceMetricsContract` (genuinely different
method surfaces) while `ProvenanceContract` (genuinely identical) was resolved by reuse instead
of a rename — see §7.

## 9. `ServicePlatformMetrics` — shared, not duplicated

Stage 13 introduces no new metrics class. `IntelligenceService`'s constructor builds exactly one
`ServicePlatformMetrics` instance and threads it into every component it constructs — Stage 12's
`EvidenceService`, `EvidenceQueryEngine`, `EvidenceProvenanceEngine`,
`RelationshipResolutionService`, and Stage 13's own `IntelligenceCorrelationService`. This is
the fix for the exact bug class the interrupted prior attempt at this stage found ("the metrics
instance recording the flag check never actually reaches the returned service") — codified as a
standing governance check (`check_eips_metrics_no_duplicate_instance()`) and proven behaviorally
by instance identity in `metrics-sharing.test.js`, not just documented in a comment.

## 10. Known gaps (documented, not fixed this stage)

- **Vendor/Product/Malware query dimensions** — see §5. Fixing Product/Malware would require
  extending `evidence-registry/entity.js`'s schema (a Stage 10-11 file), out of this stage's
  additive-only scope. Fixing Vendor would require inventing a new domain model from nothing,
  explicitly forbidden by this program's Reuse Before Build rule absent a canonical source.
- **Relationship correlation stays pass-through-only** pending ADR-0010 Acceptance — see §6.
  Wiring a real provider is future, separately-authorized work, same as Stage 12 left it.
- **No live consumer beyond the one Phase 10 script** — see
  `TITAN_STAGE13_OPERATIONAL_GUIDE.md`'s Migration Guidance section for what wiring a real
  `pNN-handlers.js` route would require and why this stage deliberately did not attempt it.
