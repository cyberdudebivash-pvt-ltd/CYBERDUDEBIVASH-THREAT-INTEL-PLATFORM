# Project TITAN Stage 12 — Internal Query Engine Documentation

Source: `workers/intel-gateway/src/evidence-registry/query-engine.js`, `EvidenceQueryEngine`.
Twelve lookup dimensions, one naming convention (`lookupBy*`), each delegating to
`EvidenceRegistry` (Stage 11) — no new index structures; `indexes.js`'s ten Maps (Stage 11 Phase
5) remain the only index storage in this codebase.

| Dimension | Method | Delegates to | Returns |
|---|---|---|---|
| UUID | `lookupByUuid(uuid)` | `registry.getEvidence(uuid)` | `CanonicalEvidence \| null` |
| Evidence ID | `lookupByEvidenceId(id)` | `registry.findEvidence({evidence_id: id})` | `CanonicalEvidence[]` — **see gap below** |
| Report | `lookupByReport(id)` | `registry.findByReport(id)` | `CanonicalEvidence[]` |
| CVE | `lookupByCve(cve)` | `registry.findByCVE(cve)` | `CanonicalEvidence[]` |
| Campaign | `lookupByCampaign(id)` | `registry.findByCampaign(id)` | `CanonicalEvidence[]` |
| Threat Actor | `lookupByThreatActor(id)` | `registry.findByThreatActor(id)` | `CanonicalEvidence[]` |
| IOC | `lookupByIoc(value)` | `registry.findByIOC(value)` | `CanonicalEvidence[]` |
| ATT&CK | `lookupByAttackTechnique(id)` | `registry.findByAttackTechnique(id)` | `CanonicalEvidence[]` |
| Relationship | `lookupByRelationship(entityId)` | `registry.findByRelationship(entityId)` | `CanonicalEvidence[]` — evidence's own `related_*` union, **not** P31/ADR-0010's graph |
| Confidence | `lookupByConfidence(tier)` | `registry.findByConfidenceTier(tier)` | `CanonicalEvidence[]` |
| Source | `lookupBySource(id)` | `registry.findBySource(id)` | `CanonicalEvidence[]` |
| Version | `lookupByVersion(uuid, versionNumber?)` | `registry.resolveVersion(uuid, versionNumber)` | `CanonicalEvidence \| null` |

Every dimension records its own call count via `ServicePlatformMetrics.recordQuery(dimension)`
(injected at construction) — `metrics.snapshot().query_counts` gives a per-dimension usage
breakdown.

## Known gap: `lookupByEvidenceId`

`indexes.js` (Stage 11 Phase 5) builds a `byEvidenceId` index, but no `EvidenceRegistry` finder
method has ever surfaced it — `registry-service.js` calls `_indexes.byCve`/`byThreatActor`/
`byReport`/`byCampaign`/`byAttackTechnique`/`byIoc`/`byRelatedEntity`/`bySource`/
`byConfidenceTier`, but never `byEvidenceId`. This predates Stage 12; it was found while writing
this engine, not introduced by it. `lookupByEvidenceId` therefore uses
`registry.findEvidence({evidence_id})` — a linear scan over current records via
`InMemoryEvidenceRepository.lookup()`, functionally correct but not index-accelerated.

Fixing this properly means adding a method to `registry-service.js` (a Stage 11 file) — out of
Stage 12's additive-only, "no duplicated logic" scope. Phase 8's benchmark
(`__tests__/service-performance-smoke.test.js`) measured this dimension alongside the other
eleven at 1,000-record scale and found no material difference (all twelve dimensions combined,
100 samples each, completed in ~147ms) — the gap is real but not currently performance-relevant
at this scale.

## Usage

```js
import { EvidenceRegistry } from "./registry-service.js";
import { EvidenceQueryEngine } from "./query-engine.js";
import { ServicePlatformMetrics } from "./service-metrics.js";

const registry = new EvidenceRegistry();
const metrics = new ServicePlatformMetrics();
const query = new EvidenceQueryEngine(registry, metrics);

const byUuid = await query.lookupByUuid("...");
const byCve = await query.lookupByCve("CVE-2026-0001");
```
