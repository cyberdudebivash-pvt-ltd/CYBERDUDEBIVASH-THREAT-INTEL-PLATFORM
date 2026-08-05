# ADR-0010: Relationship Graph Ownership

**Date:** 2026-08-05
**Status:** Proposed — **REVISED 2026-08-05 (Stage 7), see "Revision" section — the fragmentation
this ADR addresses grew from 2 implementations to 5; the original R1-vs-R2 recommendation may
no longer be correct. Highest-priority open question in this document set.** Not Accepted.
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

## Revision — 2026-08-05, Stage 7

This ADR's original Decision compared 2 relationship-graph implementations. Stage 7 found 3
more. Restated in full for clarity — this is now a **five-way** fragmentation:

| ID | System | Repo | Persistence | Status this stage |
|---|---|---|---|---|
| R1 | `p31-handlers.js` `_buildGraph` | intel-platform | None (rebuilt per-request) | Original ADR-0010 subject, target-canonical |
| R2 | `knowledge_graph.py` `KnowledgeGraph` | blog, Python | Persistent, JSON-backed | Original ADR-0010 subject |
| **R3** | `api-extensions.js` `handleIntelGraph`/`handleIntelRelations` | intel-platform | Reads a separately-generated `data/ai/intel_graph.json` snapshot from R2 | Found this stage (§DEBT-013) — **same repository as R1, different data source, unreconciled** |
| **R4** | `api/_lib/threat-graph.js` | blog, Vercel/JS | Unknown (Redis-adjacent, not independently confirmed) | Found this stage — confirmed live via `api/v1/intel.js` |
| **R5** | `api/_lib/graph-engine.js` + `graph-traversal.js` + `relationship-engine.js` + `correlation-engine.js` | blog, Vercel/JS | Redis-backed (`GraphEngine` stores entities/relationships in Redis directly, per the reachability trace) | Found this stage, very likely live via `api/v1/intelligence/{graph,correlations}.js`, `api/v1/workbench/*` |

R5 is, on paper, the most capable of all five: 34 named entity types, 31 named relationship
types, Redis-backed persistence (a real advantage over R1's no-persistence and arguably a more
production-grade choice than R2's flat JSON files), plus BFS traversal (`graph-traversal.js`)
and correlation (`correlation-engine.js`) built on top of it. **If R5 is confirmed live, it is
not obviously inferior to R1 as a persisted-graph target** — it already has the persistence
property this ADR's original Decision named as R1's missing prerequisite (Decision item 2).

**This ADR's Decision (R1 as target-canonical, contingent on persistence) is not withdrawn, but
the contingency it was written around — "R1 lacks persistence, which R2 has" — is now a
three-way comparison (R1 vs. R2 vs. R5) instead of two, and R5 already clears the bar R1 was
being asked to clear.** This is the clearest case among all four revised ADRs where the new
evidence could plausibly change the actual recommendation, not just add a footnote to it.

**This ADR should not be Accepted as originally written.** Required before approval, all
outside this stage's authority to resolve unilaterally:
1. Confirm R5's live status and actual persistence characteristics (Redis TTL/durability
   guarantees — not verified this stage).
2. Identify what generates R3's `data/ai/intel_graph.json` (DEBT-013, still open).
3. With R3 and R5 in view, re-decide whether R1 (intel-platform, no persistence, but
   system-of-record precedent) or R5 (blog, persisted, but violates blog's own CLAUDE.md
   "STRICT SEPARATION" rule by existing at all) should be the actual target — this is now a
   genuine architectural trade-off between "correct precedent, missing property" and "wrong
   location, has the property," not a clear-cut call this stage can make responsibly without
   human input on how strictly the separation rule should bind against a system that may
   already represent significant sunk engineering investment.

This is the single highest-priority open question this entire two-stage program has produced —
see `TITAN_TECH_DEBT_REGISTER.md`'s new top entry.

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
