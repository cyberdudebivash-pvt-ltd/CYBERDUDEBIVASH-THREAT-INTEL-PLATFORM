# Relationship Framework — Stage 16 (Project TITAN)

**This directory is not imported by `index.js` or any other production route. It has zero
production runtime effect on the live Cloudflare Worker.** It is, however, the first stage in
this lineage (Stage 8 → 16) whose consumption contract is backed by a **real, wired provider**
instead of a `Null*` default — ADR-0010 (Relationship Graph Ownership) is Accepted, and this
directory is that acceptance exercised.

## What this is

Canonical entity-relationship services, composing (not re-implementing) prior TITAN stages:

- **Relationship Registry** (`relationship-types.js` + `relationship-registry.js`) — a versioned,
  confidence-aware catalog of relationship types across Evidence/Threat/IOC/Campaign/ATT&CK,
  sourced from R1's (`p31-handlers.js`) own verified edge vocabulary plus ADR-0010's own
  recommended R2 vocabulary reuse.
- **Persistence** (`edge-repository-interface.js` + `in-memory-edge-repository.js`) — the
  persistence layer ADR-0010 Decision item 2 named as R1's missing prerequisite, resolved via
  Revision 5 (native persistence, not R6 adoption). In-memory reference implementation only, per
  this platform's established "contract + in-memory reference, no vendor-specific backend"
  convention (mirrors `evidence-registry/repository-interface.js` +
  `in-memory-repository.js` exactly).
- **The P31 adapter** (`p31-edge-adapter.js`) — pure functions over R1's **documented edge
  shape** (`{source, target, relation, confidence, evidence, verified}`, verified against
  `p31-handlers.js`'s own `_buildGraph()`/`handleP31Relationships()` source, not assumed). Never
  imports `p31-handlers.js`.
- **The concrete provider** (`relationship-provider.js`) — `P31RelationshipProvider`, the
  concrete `RelationshipProviderInterface` implementation Stage 12's own module docstring named
  as future, separately-authorized wiring. That authorization is ADR-0010's Acceptance.
- **Traversal** (`relationship-traversal.js`) — bounded, cycle-safe BFS (`traverse`,
  `shortestPath`) over persisted edges. No new graph engine.
- **Validation** (`relationship-validation.js`) — per-edge validation against the registry
  (known type, entity-class pairing, confidence range, self-loop rejection) plus corpus-level
  cycle/orphan detection, closing the gap ADR-0010's own text explicitly deferred to "Stage 6
  Phase 8."
- **Metrics** (`relationship-metrics.js`) — in-memory counters (traversal latency, correlation
  counts, validation failures, confidence propagation), same passive-accumulator idiom as every
  prior stage's own metrics class.
- **Lookup** (`relationship-lookup.js`) — thin wrapper enriching Stage 12's
  `RelationshipResolutionService.resolveRelationships()` output with registry metadata.
- **The facade** (`relationship-service.js`) — `RelationshipService`, "One Relationship Service,"
  composing everything above plus a **real, wired** instance of Stage 12's
  `RelationshipResolutionService`.

## What this is not

- **Not a new graph engine, registry, or traversal engine competing with R1.** Every relationship
  this directory persists originates from R1's own documented edge shape, adapted, not
  recomputed. `_buildGraph()`'s construction logic is never imported or re-implemented.
- **Not a new graph database.** `InMemoryRelationshipEdgeRepository` is a plain in-process Map,
  matching R2's own "no-DB-dependency approach" the ADR cites as proven at this platform's scale.
- **Not wired into `index.js` or any live route.** Composing this directory into the actual
  Cloudflare Worker request path is a distinct, not-yet-authorized future step — see
  `TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md`'s Deferred section.
- **Not a public API, customer portal, or GraphQL surface.** Explicitly out of this stage's scope
  per its own NON-GOALS.
- **Not R6 adoption.** `core/intelligence/enrichment_graph.py` is untouched — see ADR-0010
  Revision 5 for why this directory's persistence layer is a distinct, same-repository,
  same-language alternative, not a decision about R6's fate.

## How real data reaches the Gateway

```
P31-shaped edges (fixture, or a future live-env source)
  -> RelationshipService.ingestEdges()
       -> RelationshipValidationService.validateBatch()   (reject invalid, report why)
       -> P31RelationshipProvider.ingestEdges()
            -> InMemoryRelationshipEdgeRepository.putMany()
  -> RelationshipService.resolution   (a REAL, wired evidence-registry/ RelationshipResolutionService)
  -> inject into IntelligenceService via createIntelligencePlatform({ deps: { relationshipResolution } })
  -> new EnterpriseGateway({ platform })
  -> gateway.dispatch({ capability: "evidence.relationships", method: "resolveRelationships", ... })
       or
     gateway.dispatch({ capability: "intelligence.correlation", method: "correlateByRelationship", ... })
```

See `__tests__/integration.test.js` for this exact chain, executed and asserted end-to-end.

## File layout

```
relationship-types.js              Phase 2 -- canonical relationship type catalog (data only)
relationship-registry.js           Phase 2 -- RelationshipRegistry service
edge-repository-interface.js       Phase 3 -- persistence contract
in-memory-edge-repository.js       Phase 3 -- persistence reference implementation
p31-edge-adapter.js                Phase 3 -- documented-shape adapter (no p31-handlers.js import)
relationship-provider.js           Phase 3 -- P31RelationshipProvider (concrete Stage 12 provider)
relationship-traversal.js          Phase 1/3 -- RelationshipTraversalService (BFS, shortest path)
relationship-validation.js         Phase 1/3/8 -- RelationshipValidationService
relationship-metrics.js            Phase 1/7 -- RelationshipMetricsService
relationship-lookup.js             Phase 1 -- RelationshipLookupService
relationship-service.js            Phase 1 -- RelationshipService (the facade)
service-contracts.js               Phase 1 -- versioned internal contracts
__tests__/                         node:test suite -- unit, integration, negative-path, perf smoke
```

## Running the tests

```
cd workers/intel-gateway/src/relationship-framework
node --test
```

110 tests, 0 failures (Stage 16). Zero new dependencies — Node's built-in `node:test`/`node:assert`.

## The one design rule that makes this directory low-risk to extend

Same rule every prior TITAN-stage scaffolding directory in this repository follows: files here
operate on **documented data shapes**, not live imports of `pNN-handlers.js`/`index.js`. This
means the directory can grow more capable without changing its zero-blast-radius property.
Guarded by three independent mechanisms, mirroring the established convention exactly:

1. `__tests__/zero-blast-radius.test.js` — nothing outside this directory references it, except
   the documented sibling-directory exceptions (each named and justified in that test itself and
   in the corresponding sibling's own zero-blast-radius test).
2. `__tests__/zero-blast-radius.test.js`'s own boundary tests — nothing inside this directory
   imports a handler/router file, or imports `intelligence-platform/`/`enterprise-gateway/`
   (composition happens the other way: those directories inject a relationship-framework-backed
   provider into themselves).
3. `scripts/titan_architecture_governance_check.py`'s
   `check_relationship_framework_files_present_and_isolated()`,
   `check_no_duplicate_relationship_engine()`, and
   `check_relationship_framework_provider_wiring_intact()` — the same properties, checked in CI
   (advisory), plus a positive-state check that the ADR-0010 wiring itself hasn't silently
   regressed.

## Extending this directory further

1. Read `TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md` and
   `TITAN_STAGE16_OPERATIONAL_GUIDE.md` first.
2. Add tests in `__tests__/` before considering a change done — `node --test` should stay green.
3. Never import a `pNN-handlers.js` file or `index.js` from anywhere in this directory. A future
   task that genuinely requires that (wiring this whole subsystem into the live Worker) is its
   own architectural event, requiring its own explicit authorization — mirrors this repo's
   established precedent for every prior scaffolding directory.
4. Run `python3 scripts/titan_architecture_governance_check.py` after any change — the Stage 16
   checks exist to catch exactly the categories of drift this directory is most exposed to
   (a silent bypass of the Gateway, a duplicate engine, or the ADR-0010 wiring quietly reverting
   to unwired).
