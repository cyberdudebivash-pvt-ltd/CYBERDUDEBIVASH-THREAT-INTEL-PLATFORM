# Project TITAN Stage 11 — Internal Service Guide

**Status:** Implemented, inert. **Location:**
`workers/intel-gateway/src/evidence-registry/registry-service.js`. **Internal service only — no
HTTP endpoints, no customer APIs, no authentication layer changes.** Not imported by `index.js`
or any production route.

## 1. Constructing a registry

```js
import { EvidenceRegistry } from "./evidence-registry/registry-service.js";

const registry = new EvidenceRegistry(); // uses InMemoryEvidenceRepository + defaults for everything else

// Or inject your own pieces (e.g. a test double, or — once separately authorized — a real backend):
const registry = new EvidenceRegistry({ repository: myRepository });
```

## 2. Full API surface

### Registration (Phase 1 "Register" + Phase 6 `registerEvidence()` + Phase 7 reuse)

```js
const { evidence, reused } = await registry.registerEvidence(canonicalEvidence, {
  initialState: "DRAFT",      // optional, default "DRAFT"
  skipReuseCheck: false,       // optional, default false
  actor: "migration-adapter",  // optional, recorded on the registration audit entry
});
```

Validates first (throws `EvidenceValidationError` on failure), then checks for an existing
record with the same substantive content (`content_hash`, computed automatically if not already
set) — if found, returns `{ evidence: existing, reused: true }` **without creating a duplicate**
(Phase 7). Otherwise stores the record, sets its lifecycle state, indexes it, and returns
`{ evidence: stored, reused: false }`.

### Retrieval

```js
await registry.getEvidence(uuid);                    // exact-uuid lookup, or null
await registry.findEvidence({ evidence_type: "OSINT" }); // exact-match multi-criteria
```

### Named finders (Phase 5 indexing, surfaced as Phase 6 API)

```js
await registry.findByCVE(cve);
await registry.findByThreatActor(actor);
await registry.findByCampaign(campaign);
await registry.findByAttackTechnique(technique);
await registry.findByIOC(ioc);
await registry.findByReport(reportId);
await registry.findBySource(sourceId);
await registry.findByConfidenceTier(tier);
await registry.findByRelationship(entityId); // union across every related_* dimension
```

Each returns `CanonicalEvidence[]` — fully materialized records, not bare uuids.

### Lifecycle

```js
await registry.transitionLifecycle(uuid, "COLLECTED", { reason: "feed ingested", actor: "system" });
registry.getLifecycleState(uuid);   // -> "COLLECTED"
registry.getAuditTrail(uuid);       // -> [{from, to, at, reason, actor}, ...]
```

Throws `UnregisteredEvidenceError` for an unknown uuid, `IllegalLifecycleTransitionError` for an
illegal transition. See `TITAN_STAGE11_LIFECYCLE_SPECIFICATION.md` for the full state graph.

### Content-changing operations (Phase 1 "Update" / "Supersede" / "Archive")

```js
await registry.updateEvidence(uuid, { evidence_category: "REVIEWED" }, { reason: "..." });
await registry.supersedeEvidence(uuid, { evidence_category: "CORRECTED" }, { reason: "..." });
await registry.archiveEvidence(uuid, { reason: "..." });
```

Each validates the prospective result *before* persisting (an invalid patch never reaches
storage — verified by `__tests__/registry-service.test.js`), bumps the version, reindexes, and
records the corresponding lifecycle transition + metrics in one call.

### Versions (Phase 1 "Resolve versions" + Phase 6 `resolveVersion()`)

```js
await registry.resolveVersion(uuid);        // current version
await registry.resolveVersion(uuid, 1);     // a specific version number, or null
await registry.getVersionLineage(uuid);     // full history, oldest first
await registry.getHistoricalVersions(uuid);
await registry.getSupersededVersions(uuid);
```

### Bulk operations (Phase 2, validated + tracked at this layer)

```js
const { imported, skipped, errors } = await registry.bulkImport(entities, { initialState: "DRAFT" });
const all = await registry.bulkExport();
```

Validates every entity first; invalid entities and repository-level duplicates are both counted
in `skipped`, with human-readable reasons in `errors`. Only genuinely new records get lifecycle
state, indexing, and metrics applied.

### Observability (Phase 9)

```js
registry.getMetricsSnapshot();
// { evidence_count, lifecycle_transitions, lifecycle_transitions_by_type,
//   validation_failures, version_updates, migration_events, adapter_usage,
//   feature_flag_activations }

registry.noteFeatureFlagActivation("EER_ENABLED"); // for a future integration to call
registry.noteMigrationEvent("p20-evidence-chain");  // ditto, when adapting + registering legacy data
```

## 3. Error types

| Error | Thrown by | Meaning |
|---|---|---|
| `EvidenceValidationError` | `registerEvidence`, `updateEvidence`, `supersedeEvidence`, `bulkImport` | The (prospective) evidence failed `validateCanonicalEvidence` |
| `UnregisteredEvidenceError` | `transitionLifecycle`, `updateEvidence`, `supersedeEvidence`, `archiveEvidence` | The uuid has no tracked lifecycle state (never registered, or registered in a different registry instance) |
| `IllegalLifecycleTransitionError` (from `lifecycle.js`) | Same four methods | The requested transition isn't legal from the current state |
| `DuplicateEvidenceError` / `EvidenceNotFoundError` (from `in-memory-repository.js`) | Repository methods directly, if called without going through the service | Storage-level identity conflicts |

## 4. Feature flags — what gates what

`feature-flags.js`'s `EER_FLAGS` governs only whether this directory's registry code may be
*exercised* (tests, local dev) — `development`/`testing` default enabled, `canary`/`production`
default disabled. **`EvidenceRegistry` itself does not check this flag** — it always functions
when explicitly instantiated, exactly like Stage 10's `CEC_FLAGS` precedent. The flag exists for
a *future* integration point to check before deciding whether to route to this registry at all;
nothing today makes that decision. `noteFeatureFlagActivation()` exists so that future
integration has a metric to increment once it exists.

## 5. A realistic call sequence (illustrative — not wired into any real caller today)

```js
import { generateEvidenceUuid } from "./evidence-registry/identifiers.js";
import { ReportItemAdapter } from "./evidence-registry/migration-adapters.js";
import { EvidenceRegistry } from "./evidence-registry/registry-service.js";

const registry = new EvidenceRegistry();
const adapter = new ReportItemAdapter();

const evidence = { ...adapter.adapt(reportItem), evidence_uuid: generateEvidenceUuid() };
const { evidence: stored } = await registry.registerEvidence(evidence);

await registry.transitionLifecycle(stored.evidence_uuid, "COLLECTED");
await registry.transitionLifecycle(stored.evidence_uuid, "VALIDATED");
await registry.transitionLifecycle(stored.evidence_uuid, "CORRELATED");
await registry.transitionLifecycle(stored.evidence_uuid, "PUBLISHED");

const relatedToSameCVE = await registry.findByCVE(stored.related_cves[0]);
```

See `__tests__/migration-to-registry-integration.test.js` for this exact flow, tested.
