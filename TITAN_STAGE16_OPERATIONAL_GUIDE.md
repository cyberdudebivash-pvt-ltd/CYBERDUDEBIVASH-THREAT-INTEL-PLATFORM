# Project TITAN — Stage 16 Operational Guide

## Traversal Guide, Correlation Guide, and Runbook

Consolidated into one document per Stage 15's own precedent ("3 substantive docs rather than 6
thin ones, noted explicitly"). Covers Phase 9's Traversal Guide, Correlation Guide, and
Operational Runbook deliverables together, since each is short and they share the same reader.

---

## 1. Quick Start

```js
import { RelationshipService } from "./relationship-framework/relationship-service.js";

const service = new RelationshipService();

// 1. Ingest edges in R1's documented shape (source, target, relation, confidence, evidence?, verified?)
await service.ingestEdges([
  { source: "advisory:CVE-2026-0001", target: "actor:fin7", relation: "attributed_to", confidence: 0.85 },
]);

// 2. Look up
const related = await service.lookupRelationships("advisory:CVE-2026-0001");
// -> [{ relatedEntityId: "actor:fin7", relationshipType: "ATTRIBUTED_TO", confidence: 0.85, category: "threat", ... }]
```

A zero-arg `new RelationshipService()` is **already wired** to a real, in-memory-backed
`P31RelationshipProvider` — unlike Stage 12's own `RelationshipResolutionService`, which stays
unwired by default (dependency injection, not this stage's job to change). Check
`service.resolution.isWired()` to confirm (`true` for `RelationshipService`'s own facade
instance).

---

## 2. Traversal Guide

`RelationshipTraversalService` (`relationship-traversal.js`), reached via
`service.traverse()`/`service.shortestPath()`.

### `traverse(startEntityId, options)`

Bounded, cycle-safe breadth-first walk outward from one entity.

| Option | Default | Meaning |
|---|---|---|
| `maxDepth` | 3 | Maximum hops from the start entity |
| `maxNodes` | 500 | Maximum distinct entities visited before truncating |
| `minConfidence` | 0 | Skip edges below this confidence |

Returns `{ startEntityId, visited: string[], edges: RelationshipEdge[], truncated: boolean,
depthReached: number }`. `truncated: true` means `maxNodes` was hit before the walk would have
naturally terminated — treat the result as a partial view, not a complete one, when that flag is
set.

**Cycle safety:** a visited-set guarantees termination regardless of cycles in the underlying
edge set. This is a termination guarantee, not corpus-quality reporting — for the latter, see
§3's `findCycles()`.

**Example — 2-hop blast radius of an advisory:**
```js
const result = await service.traverse("advisory:CVE-2026-0001", { maxDepth: 2, minConfidence: 0.7 });
```

### `shortestPath(fromEntityId, toEntityId, options)`

BFS shortest path (fewest hops) between two entities. Returns `{ path: string[], edges:
RelationshipEdge[] }` or `null` if unreachable within `maxDepth` (default 3). `path[0]` is always
`fromEntityId`, `path[path.length - 1]` is always `toEntityId`.

**Example — how is this actor connected to that CVE?**
```js
const result = await service.shortestPath("actor:fin7", "cve:CVE-2026-0002", { maxDepth: 4 });
if (result) console.log(`${result.path.length - 1} hops:`, result.path.join(" -> "));
```

---

## 3. Validation Guide

`RelationshipValidationService` (`relationship-validation.js`), reached via
`service.validation` or through `ingestEdges()`'s automatic pre-persistence validation.

- **`validateEdge(edge, { sourceEntityClass?, targetEntityClass? })`** — checks: known type
  (registry lookup, alias-normalized), permitted entity-class pairing (only if classes are
  supplied), confidence present when the type requires it, confidence in `[0, 1]`, no bare
  self-loop. Returns `{ valid, errors: string[] }` — error codes are prefixed
  (`SCHEMA:`, `SELF_LOOP:`, `UNKNOWN_TYPE:`, `ENTITY_CLASS:`, `MISSING_CONFIDENCE:`,
  `CONFIDENCE_RANGE:`) for programmatic handling.
- **`validateBatch(edges)`** — per-edge results plus `validCount`/`invalidCount`.
- **`findOrphanEntities(edges)`** — entities appearing in exactly one edge (degree 1). A
  **finding**, not an error — a CVE referenced exactly once is often legitimate.
- **`findCycles(edges)`** — corpus-level directed-cycle detection (DFS, three-color marking).
  Returns one representative cycle path per cycle found. Also a **finding**, not an error —
  traversal already terminates safely regardless (§2).

`ingestEdges()` on `RelationshipService` runs `validateBatch()` automatically and only persists
the valid subset — always inspect the returned `validation` object rather than assuming every
input edge was stored.

---

## 4. Correlation Guide

Relationship correlation is **not** a new capability this stage builds — it is Stage 13's
existing `IntelligenceCorrelationService.correlateByRelationship(entityId)`, which has always
delegated verbatim to Stage 12's `RelationshipResolutionService.resolveRelationships()`. What
Stage 16 changes is only *which provider* backs that resolution:

```js
import { createIntelligencePlatform } from "./intelligence-platform/platform.js";

const relationshipService = new RelationshipService();
await relationshipService.ingestEdges(myEdges);

const { platform } = createIntelligencePlatform({
  environment: "testing", // or "production", subject to EIPS_FLAGS
  deps: { relationshipResolution: relationshipService.resolution },
});

const correlated = await platform.correlation.correlateByRelationship("advisory:CVE-2026-0001");
```

This also means `platform.threatIntelligence.getThreatProfile(...)` (Stage 13's
`ThreatIntelligenceService`, which composes `correlation.aggregateConfidence`) automatically sees
real relationship-derived correlation once composed this way — no separate wiring needed there.

---

## 5. Gateway Access (the only sanctioned path for a new consumer)

**Never import `relationship-framework/` directly from a new consumer.** Compose it into
`IntelligenceService`, then reach it exclusively through `EnterpriseGateway.dispatch()`:

```js
import { EnterpriseGateway } from "./enterprise-gateway/gateway-service.js";

const gateway = new EnterpriseGateway({ platform }); // platform composed as in SS4

const relationships = await gateway.dispatch({
  capability: "evidence.relationships",
  method: "resolveRelationships",
  args: ["advisory:CVE-2026-0001"],
  caller: { id: "my-consumer", kind: "script" },
  grantedCapabilities: ["evidence.relationships"], // required -- capability-name-as-its-own-grant, secure by default
});

const correlated = await gateway.dispatch({
  capability: "intelligence.correlation",
  method: "correlateByRelationship",
  args: ["advisory:CVE-2026-0001"],
  caller: { id: "my-consumer", kind: "script" },
  grantedCapabilities: ["intelligence.correlation"],
});
```

Omitting `grantedCapabilities` for the capability you're calling raises
`CapabilityAuthorizationError` — this is Gateway-level authorization, unrelated to and unweakened
by Stage 16's own wiring.

---

## 6. Runbook

### Ingesting real P31 data (not yet built — see below)

`RelationshipService.ingestEdges()` accepts an already-fetched array of P31-shaped edges. This
stage does **not** build the step that fetches those edges from a live Cloudflare Worker `env`
(that would require `_loadFeed(env)`, an actual KV binding, and importing something adjacent to
`p31-handlers.js` — deliberately out of scope; see the completion report's Deferred section). A
future composition root wiring live data in would look like:

```js
// Illustrative -- not implemented by Stage 16. Would run somewhere with a real Worker `env`.
const rawResponse = await fetch(new Request("https://internal/api/v1/p31/relationships?..."));
const { relationships } = await rawResponse.json(); // R1's documented shape
await relationshipService.ingestEdges(relationships);
```

### Diagnosing "no RelationshipProviderInterface has been supplied"

This means a `RelationshipResolutionService` instance was constructed without a `provider` —
either you're calling a bare `new RelationshipResolutionService()` directly, or a composition
root built `IntelligenceService`/`createIntelligencePlatform()` without injecting
`deps.relationshipResolution`. Fix: inject `relationshipService.resolution` (§4).

### Diagnosing a `CapabilityAuthorizationError` from the Gateway

Add the capability name to `grantedCapabilities` in your `dispatch()` call (§5). This is
independent of whether the underlying provider is wired.

### Checking whether ADR-0010's wiring has regressed

Run `python3 scripts/titan_architecture_governance_check.py` —
`check_relationship_framework_provider_wiring_intact()` fails loudly if
`relationship-service.js` stops constructing `RelationshipResolutionService` with a real
`provider`, or if `relationship-provider.js` grows a direct `p31-handlers.js` import.

### Regenerating the metrics snapshot

`relationshipService.getMetricsSnapshot()` — plain object, safe to `JSON.stringify()` and log or
attach to a future report.

### Running the full Stage 16 verification locally

```bash
cd workers/intel-gateway/src/relationship-framework && node --test
cd ../evidence-registry && node --test        # regression, expect 196/196
cd ../intelligence-platform && node --test     # regression, expect 68/68
cd ../enterprise-gateway && node --test        # regression, expect 95/95
cd ../../../../..
python3 scripts/titan_architecture_governance_check.py   # expect 6 findings, unchanged baseline
python3 scripts/test_titan_stage14_governance_checks.py  # expect 50/50
python3 scripts/regression_tests.py                       # expect 21/21
python3 scripts/p33_production_certification.py           # expect WORLDWIDE_RELEASE, 0 blockers
```

### Known limitations

- In-memory persistence only — a `RelationshipService` instance's ingested edges do not survive
  process restart. Expected: this mirrors every prior stage's own "in-memory reference
  implementation, vendor-specific backend is a separate future step" convention.
- No live feed ingestion (see above).
- Not reachable from any HTTP route yet.
