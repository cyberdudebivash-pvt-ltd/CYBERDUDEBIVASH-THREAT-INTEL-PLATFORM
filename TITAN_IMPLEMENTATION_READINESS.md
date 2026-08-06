# Project TITAN — Implementation Readiness Assessment (Task 7)

**Status:** Assessment only. Per this task's explicit instruction, **implementation of any
Blocked capability does not begin.** Where a capability is Ready, that means its prerequisite
governance is in place, not that this document authorizes starting work — the ADRs it depends
on are themselves still Proposed, not Accepted (see `docs/adr/README.md`).

---

## Enterprise Evidence Registry

| Field | Value |
|---|---|
| **Status** | **Blocked** |
| **Blocked By** | ADR-0008 not yet Accepted; Evidence schema (with Integrity field group) not yet shipped (Migration Roadmap Phase 3) |
| **Required ADR** | ADR-0008 (Canonical Evidence Framework) — written, Proposed, awaiting approval |
| **Required Refactoring** | Migration Roadmap Phase 3 (P20 schema extension) must ship and run in production long enough to validate the schema before a Registry is built against it — building a registry against an unvalidated schema risks the registry itself needing a breaking migration shortly after launch |
| **Estimated Complexity** | High. A true registry (EPIC 2: centralized creation/update/validation/dedup/versioning) is new infrastructure — likely a new D1 table or KV namespace, new API routes, new CI certification gate, new consumers across P20/P23/P32. This is explicitly the largest of the four capabilities assessed here. |

**Path to Ready:** ADR-0008 Accepted → Migration Roadmap Phase 3 shipped and stable →
dedicated design pass for the Registry itself (schema is necessary but not sufficient — a
registry is a service, not just a shape).

---

## Intelligence Provenance APIs

| Field | Value |
|---|---|
| **Status** | **Blocked** |
| **Blocked By** | Depends on the Evidence Registry existing (an API without a registry behind it has nothing authoritative to serve) — doubly blocked, since the Registry itself is Blocked |
| **Required ADR** | ADR-0008 (schema) — Proposed. A dedicated "API versioning" ADR was named in Stage 5's original six but not included in this stage's five (ADR-0007–0011 cover Confidence, Evidence, Source Reliability, Relationship Graph, Evidence Lifecycle — API versioning was the sixth Stage 5 subject and remains unwritten *as of this stage*). **This is a gap this assessment surfaces rather than silently fills** — a sixth ADR (candidate number ADR-0012) covering API versioning strategy is required before Provenance APIs can be built, and is not in this stage's scope. **Update, Stage 7 (2026-08-05):** ADR-0012 was drafted, closing this gap — see `docs/adr/0012-api-versioning-interface-governance.md`. It carries `Status: Proposed`, same as ADR-0007–0011; the ADR now exists but Acceptance is still pending, tracked in `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` (Stage 11.5). |
| **Required Refactoring** | None beyond what the Registry itself requires — this capability is additive API surface once its dependencies exist |
| **Estimated Complexity** | Medium, once unblocked — this repository already has an established pattern for versioned, paginated `/api/v1/p*` routes to extend, per `EVIDENCE_ENGINE_DISCOVERY.md` EPIC 6's own assessment ("blocked on EPIC 1/2 existing first," not architecturally novel) |

**Path to Ready:** Evidence Registry reaches Ready/ships → a dedicated API-versioning ADR
(ADR-0012, drafted Stage 7 — see update above, no longer "not written") is proposed **and
accepted** → route design against `P38`'s existing `SCHEMA_REGISTRY` versioning convention
(`version_introduced` per field), the closest existing precedent, per ADR-0008's Rationale.

---

## Knowledge Graph

| Field | Value |
|---|---|
| **Status** | **Blocked** |
| **Blocked By** | ADR-0010 not yet Accepted; **P31 has no persistence layer today** (verified this stage — it rebuilds from the feed corpus on each request), a genuine engineering prerequisite, not a paperwork one |
| **Required ADR** | ADR-0010 (Relationship Graph Ownership) — written, Proposed, awaiting approval. Note ADR-0010 itself only decides *target ownership*; it does not authorize or scope the persistence work. |
| **Required Refactoring** | P31 gains a persistence layer (Migration Roadmap Phase 5, deliberately left unestimated in this stage — see that phase's own text for why). This is real, non-trivial engineering: choosing a storage approach compatible with Cloudflare Workers (R2/KV/D1, or a JSON-backed approach matching the blog's `KnowledgeGraph` precedent per ADR-0010's Rationale), migrating `_buildGraph`'s current per-request derivation to a read/write model, and adding an `Evidence` node type once ADR-0008 ships |
| **Estimated Complexity** | High. Two sequential blockers (ownership decision, then a real persistence-engineering project) stack before this is buildable. Of the four capabilities assessed, this has the least-specified path forward, by design — see Migration Roadmap Phase 5. |

**Path to Ready:** ADR-0010 Accepted → dedicated engineering-estimation pass for P31
persistence (not done by this stage) → persistence ships and proves stable → Evidence node
type added (depends on ADR-0008 also being live).

---

## Explainable AI

| Field | Value |
|---|---|
| **Status** | **Partially Ready** — the only capability in this assessment with a credible near-term path, though not unconditionally Ready |
| **Blocked By** | Nothing structural blocks a first version. The prerequisite work already exists in production: A1 (`computeEnterpriseTrustScore`) already returns named, per-dimension `rationale` strings (this is, functionally, explainability) with a real API surface (`/api/v1/p25/trust-score`, `/api/v1/p38/confidence-audit`, `/api/v1/p38/iq-index`). P22 already has a dedicated `buildConfidenceExplanationBlock`. |
| **Required ADR** | ADR-0007 (Canonical Confidence Framework) — written, Proposed. Since A1 is the recommended canonical source, and A1 already exposes rationale, Explainable AI as "explain the canonical confidence score" is largely ADR-0007 away from Ready, not a separate large build. |
| **Required Refactoring** | Minimal for a v1: consolidate A1's existing per-dimension rationale strings into a single, dedicated explainability endpoint if one doesn't already effectively exist (P38's `/confidence-audit` may already substantially serve this — not fully assessed here, flagged as the first thing to check before scoping new work). A richer version (explaining evidence lifecycle state, relationship-graph reasoning) is blocked on ADR-0008/0010/0011 the same as the other capabilities, since it would need to explain concepts that don't have a canonical form yet. |
| **Estimated Complexity** | Low for a v1 scoped to "explain the confidence score" (mostly already exists). Medium-High for a full version covering evidence, lifecycle, and relationships (inherits those capabilities' blockers). |

**Path to Ready (v1, confidence-only):** ADR-0007 Accepted → audit whether
`/api/v1/p38/confidence-audit` already satisfies "explainable" for A1, or needs a thin
dedicated wrapper → ship. **Path to Ready (full scope):** additionally requires ADR-0008,
ADR-0010, and ADR-0011 Accepted and their respective migrations shipped.

---

## Summary

| Capability | Status | Primary Blocker |
|---|---|---|
| Enterprise Evidence Registry | Blocked | Schema must ship and stabilize first (ADR-0008 dependent) |
| Intelligence Provenance APIs | Blocked | Depends on Registry; also needs an unwritten API-versioning ADR (candidate ADR-0012) |
| Knowledge Graph | Blocked | P31 has no persistence layer — a real engineering gap, not just a decision gap |
| Explainable AI | **Partially Ready** (v1, confidence-only) | ADR-0007 approval + a scoping check against existing `/p38/confidence-audit` |

No capability in this assessment is unconditionally Ready. This is the expected, honest output
of an assessment run immediately after its prerequisite ADRs were drafted rather than accepted
— per this task's own charter, Stage 6 establishes governance, it does not clear the runway by
itself. `TITAN_STAGE7_PLAN.md` scopes what actually becomes actionable once the ADRs are
approved.
