# ADR-0010: Relationship Graph Ownership

**Date:** 2026-08-05
**Status:** Proposed — pending executive/architecture-review approval. Not Accepted.
**Deciders (proposed reviewers):** Platform Governance Lead, Chief Threat Intelligence
Architect, Intelligence Engineering (P31 owner), Blog/EIOS Engineering (`knowledge_graph.py`
owner)
**Program:** Project TITAN, Stage 6
**Depends on:** ADR-0008 (Canonical Evidence Framework) for the Evidence entity this graph will
eventually need a node type for — not built by this ADR.

---

## Context

`EVIDENCE_ENGINE_DISCOVERY.md` §2 (EPIC 4) found two independent relationship-graph
implementations, one per repository, neither with a first-class `Evidence` node type. Unlike
ADR-0007/0008/0009, this is a genuinely close call: the two candidates differ on the two
dimensions that matter most (persistence vs. system-of-record precedent) in opposite
directions, and this ADR says so explicitly rather than presenting a one-sided case.

---

## Problem Statement

**Which relationship-graph implementation becomes the canonical, authoritative graph for
entity relationships (Report/Actor/Malware/CVE/Technique/IOC, and eventually Evidence) across
the ecosystem?**

---

## Existing Implementations

| ID | System | Repo | Persistence | Design intent | Consumers |
|---|---|---|---|---|---|
| R1 | `p31-handlers.js` (`_buildGraph`, `buildP31RelationshipBlock`) | intel-platform | **Rebuilt from the feed corpus on each request** — no persisted graph store found | Operational, API-facing, part of the live P-layer stack | P31's own routes; consumed as part of the standard P-layer response chain |
| R2 | `KnowledgeGraph` (`engine/sentinel_engine/knowledge_graph.py`) | blog | **Persistent, JSON-backed** | Explicitly documented in `Sentinel-APEX/eios/layer-09-intelligence-relationships.md` as the intended convergence point for future object types ("future object types should upsert into this same graph rather than build a second mechanism") | Report generation pipeline; already relates Report/Actor/Malware/CVE/Technique/IOC via `mentions`/`references`/`maps_to`/`observed`/`associated_with`/`linked_to` edges |

Neither has an `Evidence` node type today. Both relate the same broad entity classes to each
other; the difference is architectural (ephemeral/derived vs. persisted/authored), not
conceptual.

---

## Decision

**R1 (`p31-handlers.js`, intel-platform) is designated canonical for the live, operational,
API-facing relationship graph — contingent on R1 gaining persistence, which does not exist
today and is a genuine prerequisite, not a formality.**

1. **R1 is canonical for the target state**, consistent with Stage 2's already-settled
   cross-repo precedent that intel-platform is system of record for core intelligence data and
   the blog consumes via API — the same precedent `EVIDENCE_ENGINE_DISCOVERY.md` §4 already
   applied to Registry responsibilities. A second, blog-owned system of record for
   relationships would invert that precedent specifically for this one capability, which this
   ADR declines to do without a stronger reason than "R2 happens to persist already."
2. **This designation does not take effect until R1 has a persistence layer.** R1 as it exists
   today — rebuilt per-request from the feed corpus — cannot durably hold Evidence-node
   relationships (or any relationship an ingestion cycle might not naturally reconstruct,
   such as an analyst-asserted link). This is marked **Blocked** in
   `TITAN_IMPLEMENTATION_READINESS.md` for exactly this reason. This ADR decides *who owns the
   target*, not that the target is ready today.
3. **R2 is marked Deprecated — Pending Migration**, not deprecated immediately. It continues to
   serve the blog's report-generation pipeline unchanged until R1 exposes an equivalent,
   consumable relationship API (itself gated on the not-yet-built Evidence API, EPIC 6, per
   `EVIDENCE_ENGINE_DISCOVERY.md` §2's own sequencing).
4. **EIOS Layer 9's documented convergence instruction ("future object types should upsert into
   this same graph") is superseded by this ADR for anything intended to be the ecosystem's
   canonical graph** — but not for the blog's own internal report-generation needs in the
   interim, which may continue to use R2 as documented until the migration in item 3 completes.
   This is flagged explicitly as a change to a standing instruction in a live document, not
   silently overridden — see Compatibility Impact.

---

## Rationale

- **System-of-record consistency has compounding value.** Every other TITAN ADR in this set
  (0008's Registry-adjacent reasoning, 0009's source of S1) places intel-platform as the
  canonical home for structured intelligence data, with the blog as a consumer. Placing the
  canonical relationship graph in the blog instead would require the *rest* of the platform to
  reach into the blog repo for relationship data, backwards from every other data-ownership
  decision in this program.
- **R2's persistence is real, valuable prior art**, not dismissed — it directly informs *how*
  R1 should be extended (a JSON-backed or equivalent lightweight persisted store, "no graph
  database" being explicitly out of scope per Stage 6's NON-GOALS, and R2 already proves a
  no-DB-dependency approach works at this platform's scale).
- **Declining to pick a winner outright** (unlike ADR-0007/0008/0009, where one candidate had a
  clearly larger consumer base) reflects that this genuinely is closer than the others — R1
  wins on architectural placement, R2 wins on current technical completeness for the one
  property (persistence) that matters most for an Evidence-relationship graph. Making
  persistence an explicit precondition, rather than asserting R1 is simply better, is the
  intellectually honest form of this decision.

---

## Alternatives Considered

1. **Make R2 (blog) canonical, have intel-platform consume it via API.** Rejected: inverts the
   system-of-record precedent every other ADR in this set relies on, for a capability
   (relationships among Actor/Malware/CVE/IOC — all intel-platform-native concepts) that is not
   obviously blog-shaped. R2's persistence advantage doesn't outweigh this.
2. **Run both permanently, R1 for live API responses and R2 for report-time graph queries.**
   Considered — this is close to the status quo — but rejected as a long-term answer because
   it re-creates the identical fragmentation risk `EVIDENCE_ENGINE_DISCOVERY.md` §3 already
   found for source reliability: two systems computing/storing the same relationships, capable
   of silently disagreeing, is the exact failure mode this program exists to close, not
   preserve.
3. **Defer this decision entirely until R1's persistence question is separately resolved.**
   Considered, since the persistence gap is real — but rejected in favor of deciding ownership
   now *and* naming the precondition explicitly, since leaving ownership undecided is what every
   prior stage already did and this task's charter is to stop doing that. Naming R1 as the
   target with a named blocker is more actionable than leaving the question fully open.

---

## Migration Strategy

See `TITAN_MIGRATION_ROADMAP.md` Phase 5 (latest-sequenced phase in this ADR set, appropriately,
given the persistence prerequisite).

1. **Prerequisite (not part of this ADR's approval, tracked separately in
   `TITAN_IMPLEMENTATION_READINESS.md`):** R1 gains a persistence layer. Estimated complexity
   and scoping is Stage 7+ work, not decided here.
2. **Once persisted:** R1 gains an `Evidence` node type (dependent on ADR-0008's schema).
3. **Once R1 exposes a relationship-query API:** blog migrates report-generation queries that
   currently hit R2 to consume R1's API instead, per the same Cross-Repo Consumption pattern
   already established (Stage 2).
4. **Only after a documented migration period with zero remaining R2 callers:** R2 is marked
   fully deprecated per Deprecation Instead of Deletion; it is not deleted by this ADR or its
   migration plan.

---

## Compatibility Impact

- **No immediate change to either R1 or R2.** This ADR sets direction; it does not modify code.
- **EIOS Layer 9's "upsert into this graph" instruction is affected for future *ecosystem-wide*
  object types** (i.e., anything intended to be canonical going forward should target R1's
  eventual persisted form, not R2) — but R2 remains valid for the blog's own report-generation
  use until migration completes. Recommend `Sentinel-APEX/eios/layer-09-intelligence-
  relationships.md` be updated with a "Correction (Project TITAN ADR-0010)" note, in the same
  style Issue 15 already used for its Layer 3 correction — **not done by this ADR**, flagged as
  a required follow-up action for whoever owns that file, consistent with Zero Unnecessary
  Modification (this ADR does not touch blog repo files).
- **No API route or response schema changes today.**

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| R1's persistence layer is underestimated in scope, stalling the whole migration | Medium–High | Medium | `TITAN_IMPLEMENTATION_READINESS.md` marks Knowledge Graph work "Blocked" rather than assuming a timeline; Stage 7 planning treats persistence as its own estimable unit of work |
| Blog engineering reads R2's deprecation as a directive to stop maintaining it immediately | Low | Medium | Explicit "not deprecated immediately" language in this ADR and its migration gating |
| Two graphs continue drifting further apart while R1's persistence work is pending, making eventual reconciliation harder | Medium | Medium | Named explicitly in `TITAN_TECH_DEBT_REGISTER.md` with priority tied to how long Stage 7+ takes to start the persistence work |

---

## Rollback Strategy

No code changes ship under this ADR alone — rollback is moot until the migration phases begin.
Each future migration phase (persistence layer, node-type addition, blog query migration) will
require and document its own rollback plan at implementation time, per both repos' Architecture
Preservation Rule for architectural changes.

---

## Future Considerations

- Once R1 is persisted and holds an `Evidence` node type, revisit whether R2's edge-type
  vocabulary (`mentions`/`references`/`maps_to`/`observed`/`associated_with`/`linked_to`) should
  be adopted as R1's canonical edge taxonomy — it is more developed than anything currently
  documented for R1 and is a candidate for direct reuse rather than reinvention.
- This ADR does not address relationship cycles, orphan detection, or other graph-validation
  rules — those are Stage 6 Phase 8 (Validation) concerns, tracked in
  `TITAN_CI_GOVERNANCE.md`, not decided here.

---

## Approval

**Proposed**, not Accepted. Required sign-offs, with the persistence precondition specifically
flagged as needing engineering estimation before this ADR's migration plan can be scheduled:

- [ ] Platform Governance Lead
- [ ] Chief Threat Intelligence Architect / P31 owner (for the persistence-layer scoping
      commitment)
- [ ] Blog/EIOS engineering owner (`knowledge_graph.py`, `layer-09` owner — for the deprecation
      timeline and the recommended Layer 9 correction note)

No code implementing this decision exists yet.
