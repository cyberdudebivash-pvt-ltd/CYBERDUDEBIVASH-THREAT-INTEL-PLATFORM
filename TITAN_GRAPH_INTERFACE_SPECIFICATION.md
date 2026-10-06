# Project TITAN — Canonical Graph Interface & Relationship Schema Specification

**Date:** 2026-08-05
**Status:** Design specification. **No implementation exists yet.** These are interface
contracts and a data schema for future implementation, not code changes. Language-neutral
(TypeScript-style signatures used as notation only — this repository spans JS/Cloudflare
Workers and Python; any real implementation must satisfy the same logical contract in whichever
runtime it's written in, per Stage 9's Phase 5 instruction to design shared interfaces without
vendor- or language-specific implementations).
**Produced by:** Stage 9 Phase 2 (Tasks 4–5). See `TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md` for
the ownership recommendations this design supports.
**Grounding:** every field and interface below is checked against real, currently-existing code
shapes (R1's `p31-handlers.js`, R6's `enrichment_graph.py`, R7's `intel_graph.py`, the Stage 8
Evidence Registry scaffolding) rather than invented from the abstract task list — see inline
citations. Per Principle 4 (Reuse Before Build), this is a reconciliation of what already exists,
not a from-scratch design.

---

## Part A — Canonical Relationship Schema (Task 5)

### A.1 — Why a new schema, not just picking one implementation's shape

Three implementations currently define an edge/relationship shape, and **no two of them agree**,
including two different shapes inside the *same file*:

| Source | Type key | Type value casing | Evidence shape | Confidence/weight key | Confidence type |
|---|---|---|---|---|---|
| R1 `buildP31RelationshipBlock` | `rel` | `UPPER_SNAKE_CASE` (e.g. `ATTRIBUTED_TO`) | Single pipe-joined string | `confidence` | float 0.0–1.0 |
| R1 `_buildGraph` (same file, different function) | `relation` | `lowercase_snake_case` (e.g. `attributed_to`) | Single string | `confidence` | float 0.0–1.0 |
| R6 `IOCEdge` (`enrichment_graph.py`) | `type` | `UPPER_SNAKE_CASE` (e.g. `ATTRIBUTED_TO`) | Array of strings | `weight` | float 0.0–1.0 |
| R7 `intel_graph.py` correlation graph | `relationship` | `lowercase_snake_case` (e.g. `contains_ioc`) | None (no evidence field at all) | `weight` | float 0.0–1.0 (implied, not always populated) |
| ADR-0010's description of R2's vocabulary | (implicit) | `lowercase_snake_case` (`mentions`, `references`, `maps_to`, `observed`, `associated_with`, `linked_to`) | Not specified in the ADR text | — | — |

This is not a hypothetical fragmentation risk — it is four *currently shipping* shapes. The
canonical schema below is a **reconciling superset**, not a new invention: every field maps to
something that already exists in at least one implementation, and every existing implementation's
current output can be losslessly represented via the `compat` block (§A.4) during the transition
period defined in `TITAN_GRAPH_MIGRATION_BLUEPRINT.md`.

### A.2 — Canonical entity type vocabulary

Reused verbatim from the original Stage 9 charter's Phase 2 taxonomy (not redesigned here):
`ThreatReport`, `CVE`, `ThreatActor`, `Campaign`, `Malware`, `IOC`, `Infrastructure`, `Exploit`,
`Vendor`, `Product`, `Country`, `Industry`, `Victim`, `DetectionRule`, `MitreTechnique`,
`Reference`, `Evidence`, `Source`, `ConfidenceObject`, `ExecutiveAdvisory`, `BusinessRisk`,
`RegulatoryRequirement`, `Asset`, `Organization`. R6's five node types (`IP`, `DOMAIN`, `HASH`,
`URL`, `EMAIL`) map onto `IOC` with a `entity_subtype` discriminator (added below) rather than
becoming top-level types — R6's `CVE`, `ACTOR`, `CAMPAIGN`, `MALWARE_FAMILY` node types map
directly onto the existing taxonomy's `CVE`/`ThreatActor`/`Campaign`/`Malware`.

### A.3 — Canonical relationship type vocabulary

Union of R1, R6, and R2's documented vocabularies (per ADR-0010's Existing Implementations
table), normalized to `UPPER_SNAKE_CASE` (R1's `buildP31RelationshipBlock` and R6's `IOCEdge`
already agree on this casing — the reconciliation adopts the majority convention rather than
inventing a third):

```
ATTRIBUTED_TO        USES_TECHNIQUE       REFERENCES           RESOLVES_TO
COMMUNICATES_WITH     HOSTS                PART_OF              SHARES_INFRASTRUCTURE
DROPS                 EXPLOITS             MENTIONS             MAPS_TO
OBSERVED              ASSOCIATED_WITH      LINKED_TO            CONTAINS_IOC
MAPS_TO_TECHNIQUE      INVOLVES
```

`MENTIONS`, `MAPS_TO`, `OBSERVED`, `ASSOCIATED_WITH`, `LINKED_TO` are R2's vocabulary
(blog `knowledge_graph.py`), included per ADR-0010's own Future Considerations section, which
already flagged R2's edge vocabulary as "more developed than anything currently documented for
R1 and is a candidate for direct reuse." `CONTAINS_IOC`, `MAPS_TO_TECHNIQUE`, `INVOLVES` are R7's
and `investigation-graph.js`'s vocabulary, included for completeness even though R7/R5 are not
canonical candidates (§Task 3 of the Architecture Plan) — a relationship type observed in a
non-canonical implementation is still a real type that migrated data may need to represent.

This list is **open, not closed** — `relationship_type` is a validated string against a registry
(§B, `RelationshipValidator`), not a hard enum, so a new legitimate type can be added by
extending the registry without a schema version bump. Adding an entirely new *field* is what
requires a version bump (§A.5).

### A.4 — The schema (v0.1-draft)

Naming convention matches the Stage 8 Evidence Registry scaffolding's own precedent
(`EVIDENCE_ENTITY_SCHEMA_VERSION = "evidence-registry.0.1-scaffolding"`) for consistency:

```typescript
/** schema_version for this definition */
const CANONICAL_RELATIONSHIP_SCHEMA_VERSION = "canonical-relationship.0.1-draft";

interface CanonicalRelationship {
  // ---- Identity ----
  relationship_uuid: string;        // RFC 4122 UUID v4, via crypto.randomUUID() -- same
                                     // generation mechanism as evidence-registry/identifiers.js,
                                     // reused not reinvented
  schema_version: string;           // "canonical-relationship.0.1-draft"

  // ---- Relationship Type ----
  relationship_type: string;        // validated against the registry in §A.3 (open vocabulary)

  // ---- Source / Target ----
  source_entity: EntityRef;
  target_entity: EntityRef;

  // ---- Evidence References ----
  evidence_references: string[];    // array of evidence_uuid (see evidence-registry/entity.js);
                                     // EMPTY until the Evidence Registry is Accepted and live --
                                     // not a defect, an explicit precondition (see Migration
                                     // Blueprint Phase 3)
  evidence_summary: string | null;  // human-readable fallback -- populated during the transition
                                     // period from whichever legacy string/array existed; null
                                     // once evidence_references is the source of truth

  // ---- Confidence ----
  confidence: number;               // 0.0-1.0, edge-level -- NOT the same concept as P25's
                                     // computeEnterpriseTrustScore (that is item-level trust,
                                     // a different, already-canonical concept this schema does
                                     // not duplicate or compete with)
  confidence_source: string;        // free-text provenance, e.g. "R1:buildP31RelationshipBlock"
                                     // or "R6:IOCEnrichmentGraph.authority_score" -- required for
                                     // the transition period so a reviewer can trace which
                                     // engine asserted a given confidence value

  // ---- Relationship Strength ---- (Stage 6 Phase 3's original charter field, distinct from
  // confidence: "how sure are we this edge is real" vs. "how significant is it")
  relationship_strength: number | null;  // 0.0-1.0, optional -- no current implementation
                                          // populates this distinctly from confidence; null is
                                          // valid and expected until a producer does

  // ---- Lifecycle ----
  lifecycle_state: "PROPOSED" | "ACTIVE" | "VERIFIED" | "DEPRECATED" | "ARCHIVED";
                                     // mirrors this program's own Deprecation-Instead-of-Deletion
                                     // philosophy applied at the edge level, not just the
                                     // implementation level

  // ---- Origin ----
  relationship_origin: "PIPELINE_AUTOMATED" | "ANALYST_ASSERTED" | "AI_INFERRED" | "COMMUNITY_IMPORTED";
                                     // R6 already distinguishes "external_merge" /
                                     // "community_feed" sources informally; this formalizes it

  // ---- Version ---- (record revision, distinct from schema_version)
  version: number;                  // starts at 1, increments on any field change

  // ---- Audit Metadata ----
  created_at: string;                // ISO-8601
  updated_at: string;                // ISO-8601
  audit: {
    producer_implementation: string; // e.g. "R1", "R6", "R2" -- critical during the multi-
                                      // engine transition period defined in the Migration
                                      // Blueprint; required, not optional
    ingestion_run_id: string | null; // ties back to a pipeline run_id where applicable
                                      // (core/pipeline/stages.py's PipelineContext.run_id
                                      // is the existing precedent this reuses)
  };

  // ---- Analyst Validation ----
  analyst_validation: {
    validated: boolean;
    validated_by: string | null;
    validated_at: string | null;     // ISO-8601
  };

  // ---- AI Contribution Metadata ----
  ai_metadata: {
    ai_generated: boolean;
    generation_method: string | null; // e.g. "pagerank_authority_propagation" (R6),
                                       // "cvss_kev_threshold_heuristic" (R1)
  };

  // ---- Compatibility fields (mandatory per Task 5) ----
  compat: {
    legacy_rel_key: string | null;         // R1 buildP31RelationshipBlock's original `rel` value, verbatim
    legacy_relation_key: string | null;    // R1 _buildGraph's / R6's `relation`/`type` value, verbatim
    legacy_evidence_string: string | null; // R1's original pipe-joined evidence string, verbatim
    legacy_weight: number | null;          // R6's/R7's `weight` value, verbatim, if it differed
                                            // from `confidence` after normalization
  };
}

interface EntityRef {
  entity_type: string;    // from §A.2's taxonomy
  entity_subtype: string | null;  // e.g. R6's IP/DOMAIN/HASH/URL/EMAIL under entity_type=IOC
  entity_id: string;      // stable identifier -- reuses R6's _make_node_id() deterministic
                           // hash-based scheme (sha256(type:value)[:16]) as the reference
                           // implementation, since it already solves dedup correctly
  entity_label: string;   // human-readable display value (R1's current "This Advisory" /
                           // actor-name style values map here)
}
```

### A.5 — Backward compatibility

Per this task's explicit requirement ("Backward compatibility is mandatory"):

- **Every field beyond `relationship_uuid`, `schema_version`, `relationship_type`,
  `source_entity`, `target_entity` is either nullable or has a defined default.** A minimal
  record satisfying only the required fields is valid — this matters because none of R1/R3/R6/R7
  currently populate `analyst_validation`, `ai_metadata`, or (for most of them) `evidence_references`
  at all.
- **The `compat` block exists specifically so no existing consumer's current field names are
  ever silently unavailable** during the transition — a consumer reading `compat.legacy_rel_key`
  gets exactly what `buildP31RelationshipBlock` produces today.
- **Schema version bumps are additive-only within `0.x`**: a new optional field is a patch, a new
  value in an open vocabulary (§A.3) is not a version bump at all, and no field is ever removed
  or repurposed without a major version bump *and* a deprecation period, per the Deprecation
  Instead of Deletion policy applied to schema design itself.

---

## Part B — Canonical Interfaces (Task 4)

All nine interfaces are versioned independently (`<interface-name>.0.1-draft`), following the
same per-artifact versioning precedent as the Evidence Registry scaffolding and the schema above.
**No implementation of any interface exists yet.** Each entry names which existing implementation
is the most likely *first* real implementer, per Reuse Before Build — this is a design note, not
a migration order (that's the Migration Blueprint's job).

### B.1 `GraphProvider` — `graph-provider.0.1-draft`

The root abstraction: something that can answer "give me a graph" for a scope (item, corpus, or
entity).

```typescript
interface GraphProvider {
  getGraphForItem(itemId: string, opts?: TraversalOptions): Promise<GraphSnapshot>;
  getFullGraph(opts?: { limit?: number; minConfidence?: number }): Promise<GraphSnapshot>;
  getProviderIdentity(): { implementation: string; version: string };  // "R1" / "R6" / etc. --
                                                                        // required so a caller
                                                                        // during the transition
                                                                        // period can log which
                                                                        // backend actually answered
}

interface GraphSnapshot {
  nodes: EntityRef[];
  edges: CanonicalRelationship[];
  generated_at: string;   // ISO-8601
  node_count: number;
  edge_count: number;
}
```

Likely first implementer: **R1**, since it is the ADR-0010 target-canonical and already exposes
the closest thing to this shape (`_buildGraph`'s nodes/edges output).

### B.2 `RelationshipProvider` — `relationship-provider.0.1-draft`

Narrower than `GraphProvider`: relationships for a single entity, not a full graph.

```typescript
interface RelationshipProvider {
  getRelationshipsForEntity(entityId: string, opts?: { types?: string[] }): Promise<CanonicalRelationship[]>;
  getRelationshipById(relationshipUuid: string): Promise<CanonicalRelationship | null>;
}
```

Likely first implementer: **R1** (via `buildP31RelationshipBlock`, already scoped to a single
item/entity).

### B.3 `RelationshipResolver` — `relationship-resolver.0.1-draft`

Resolves a *proposed* relationship (e.g., from ingestion) against existing state — dedup, merge,
or reject.

```typescript
interface RelationshipResolver {
  resolve(proposed: Partial<CanonicalRelationship>): Promise<{
    action: "CREATE" | "MERGE" | "REJECT";
    resolvedRelationship?: CanonicalRelationship;
    reason?: string;         // required when action === "REJECT"
    mergedWithUuid?: string; // required when action === "MERGE"
  }>;
}
```

Likely first implementer: **R6**, since `link_iocs()` already implements dedup-and-reinforce
logic (`if ioc_b in self._adj[ioc_a]: existing["weight"] = max(existing["weight"], weight)`) —
this interface formalizes an already-real capability rather than inventing one.

### B.4 `RelationshipValidator` — `relationship-validator.0.1-draft`

The governance-facing counterpart — used both at write-time and by the CI governance check
(Task 8).

```typescript
interface RelationshipValidator {
  validate(rel: CanonicalRelationship): ValidationResult;
  validateBatch(rels: CanonicalRelationship[]): { valid: CanonicalRelationship[]; invalid: ValidationResult[] };
}

interface ValidationResult {
  valid: boolean;
  errors: string[];   // e.g. "relationship_type 'FOO' not in registry", "confidence out of [0,1] range"
  warnings: string[]; // e.g. "evidence_references empty for a VERIFIED lifecycle_state"
}
```

No existing implementation. This is the one interface in this set with no direct precedent to
build on — flagged honestly rather than forcing a false "likely first implementer."

### B.5 `GraphExporter` — `graph-exporter.0.1-draft`

```typescript
interface GraphExporter {
  exportStix21(nodeIds: string[]): Promise<StixBundle>;
  exportSnapshotForWorker(): Promise<GraphSnapshot>;  // the shape R3 currently expects
  exportJson(): Promise<string>;
}
```

Likely first implementer: **R6** — `export_stix_bundle()` and `export_snapshot()` already exist
and are the most complete export logic found in the entire inventory (Phase 1's own assessment).
This interface is close to a direct extraction of R6's existing public methods.

### B.6 `GraphImporter` — `graph-importer.0.1-draft`

```typescript
interface GraphImporter {
  importFromJson(payload: string, opts?: { sourceTrust?: number }): Promise<{ imported: number; skipped: number }>;
  importCommunityFeed(feed: object): Promise<{ imported: number }>;  // R6's community-sharing path
}
```

Likely first implementer: **R6** — `merge_external_graph()` / `import_community_feed()` already
implement this.

### B.7 `TraversalProvider` — `traversal-provider.0.1-draft`

```typescript
interface TraversalProvider {
  findRelated(entityId: string, depth: number): Promise<EntityRef[]>;
  findPath(fromEntityId: string, toEntityId: string, maxDepth: number): Promise<CanonicalRelationship[] | null>;
  computeAuthority(entityId: string): Promise<number>;  // 0.0-1.0
}

interface TraversalOptions {
  maxDepth?: number;
  relationshipTypes?: string[];
}
```

Likely first implementer: **R6** — `find_related()` (BFS) and `authority_score()`
(PageRank-like) already exist and are, per Phase 1's assessment, more sophisticated than any
traversal logic found elsewhere in the inventory.

### B.8 `EvidenceRelationshipProvider` — `evidence-relationship-provider.0.1-draft`

The explicit bridge between this schema and the Stage 8 Evidence Registry scaffolding — **this is
new**, since no current implementation links relationships to evidence at all (R1's evidence is a
free-text string, not a reference).

```typescript
interface EvidenceRelationshipProvider {
  getEvidenceForRelationship(relationshipUuid: string): Promise<EvidenceEntity[]>;  // EvidenceEntity
                                                                                      // from evidence-registry/entity.js
  attachEvidence(relationshipUuid: string, evidenceUuid: string): Promise<void>;
}
```

No existing implementer. Explicitly gated on Evidence Registry activation (ADR-0008 Acceptance) —
this interface can be specified now but cannot be meaningfully implemented until that
precondition clears, same gating logic as Task 9's Stage 10 Authorization determination.

### B.9 `ConfidenceRelationshipProvider` — `confidence-relationship-provider.0.1-draft`

```typescript
interface ConfidenceRelationshipProvider {
  computeRelationshipConfidence(rel: Partial<CanonicalRelationship>): Promise<number>;
  explainConfidence(relationshipUuid: string): Promise<{ factors: { name: string; contribution: number }[] }>;
}
```

Likely first implementer: **R1**'s existing CVSS/KEV-threshold heuristic
(`isKev || cvss >= 9 ? 0.92 : cvss >= 7 ? 0.83 : 0.65`) is the closest existing logic, though it
is a simple threshold ladder rather than a weighted-factor model — `explainConfidence`'s
`factors` breakdown has no current precedent and would be new logic, explicitly noted as such
rather than falsely attributed to an existing implementation.

---

## Part C — Explicit non-goals for this specification

Per Stage 9 Phase 5's own charter ("Do not introduce vendor-specific implementations") and this
phase's engineering rules ("Do NOT implement new graph engines... Do NOT rewrite production
logic"):

- No interface above is implemented by this document.
- No existing file is modified by this document.
- The "likely first implementer" notes are design guidance for the Migration Blueprint, not a
  commitment — the Canonical Ownership Decision Package (`TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md`
  Task 3) governs actual disposition, and that document is itself a recommendation pending human
  Acceptance.
