# ADR-0010: Relationship Graph Ownership

**Date:** 2026-08-05
**Status:** **Accepted** (2026-08-06, executive architecture authority — see Revision 5 and the
Approval section below). Revised five times before acceptance. Stage 7 found the fragmentation
grew from 2 to 5 candidate implementations; Stage 8's live verification narrowed it back to 3
live ones (R1, R3, R4) and found R1-vs-R3 is a same-repository, same-team conflict — see
"Revision 2." **Original Decision (R1 target-canonical) stands and was accepted as written;
R1-vs-R6's persistence-layer prerequisite was resolved at acceptance time via Revision 5's
scoping, below.**
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

## Revision 2 — 2026-08-05, Stage 8 (partially resolves Revision 1, redirects priority)

Direct HTTP verification (`TITAN_STAGE8_VERIFICATION_REPORT.md`, `TITAN_AR000_RESOLUTION.md`):

- **R5** (`graph-engine.js`/`graph-traversal.js`/`relationship-engine.js`/`correlation-engine.js`)
  is **not deployed** — its only consumers (`api/v1/intelligence/{graph,correlations}.js`,
  `api/v1/workbench/*`) return Vercel's platform-level `NOT_FOUND`. Removed from serious
  contention as an R1 alternative; the "R5 already has persistence" argument no longer carries
  practical weight since R5 has no live consumer regardless.
- **R3** (`api-extensions.js`'s `handleIntelGraph`/`handleIntelRelations`, reading
  `data/ai/intel_graph.json`) is **confirmed live** (HTTP 403, tier-gated — a real, working
  route, not dead code).
- **R4** (blog `api/_lib/threat-graph.js`) is **reconfirmed live**, unchanged from Stage 7.

**The fragmentation is real but smaller than Revision 1 stated: three live implementations
(R1, R3, R4), not five.** More importantly, this narrows the priority target: **R1 and R3 are
both intel-platform-owned, both live, both answering "give me the relationship graph" for the
same feed data, right now, in the same repository.** This is fully within this program's
authority to reconcile without waiting on a cross-repo negotiation with blog engineering (R2,
R4). Recommended: **resolve R1-vs-R3 first**, independent of and ahead of the broader
R1-vs-R2/R4 cross-repo question, as the highest-confidence, lowest-friction fragmentation fix
available to a future implementation stage. This ADR's original Decision (R1 target-canonical,
contingent on persistence) is not contradicted by this finding — R3 competing with R1 is an
argument for converging faster, not for choosing differently.

---

## Revision 3 — 2026-08-05, Stage 9 Phase 1 (corrects Revision 2, adds R6/R7)

Stage 9's graph-discovery continuation traced R3's producer by reading actual execution paths
(imports and instantiation sites, not comments), per that stage's own charter. This revision
documents two things: a factual correction to Revision 2, and two newly-discovered
implementations neither prior stage catalogued. Full trace in
`TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md` (Task 4/6); summarized here.

**Correction to Revision 2.** Revision 2 states R3 "reads a separately-generated
`data/ai/intel_graph.json` snapshot from R2" — using "R2" to mean this ADR's own label for the
blog's `knowledge_graph.py`. **That is incorrect.** The actual chain is:
`core/intelligence/enrichment_graph.py` (a same-repository, intel-platform-native Python module,
newly catalogued below as R6) → `core/orchestrator.py`'s `R2AIExportStage` → written via boto3
to **Cloudflare R2 object storage** (bucket `sentinel-apex-intel`, key
`data/ai/intel_graph.json`) → read by R3. "R2" in `core/pipeline/stages.py`'s own comments
("R2 Export Snapshot," "R2 AI exports") refers to Cloudflare's storage product, not to this
ADR's R2 graph-implementation ID — a genuine terminology collision between this program's
vocabulary and Cloudflare's product name. R3 has no relationship to the blog's `KnowledgeGraph`
at all. This is a correction, not an addendum: Revision 2's producer claim was factually wrong,
apparently written without reading `core/pipeline/stages.py`'s body. Per this program's
discipline, the error is documented here rather than silently edited out of Revision 2 above.

**New: R6 — `core/intelligence/enrichment_graph.py` (`IOCEnrichmentGraph`), intel-platform,
Python.** A real, substantial graph engine: thread-safe in-memory adjacency graph, JSON
persistence (`save`/`load`), 6-source OSINT enrichment, PageRank-like authority scoring, BFS
traversal, campaign correlation, actor attribution, STIX 2.1 export. **On functional merit this
is the most capable implementation in the full inventory (R1-R7)** — more complete than R1 (no
persistence), and same-repository as R1 (no cross-repo negotiation required, unlike R2/R4).
Its production execution trigger is unconfirmed: no `.github/workflows/*.yml` file invokes
`core/orchestrator.py` (the only in-repo caller of R6's export stage). The confirmed-live master
pipeline (`scripts/run_pipeline.py`) does not import it either. This does not mean R6 never
runs — only that no in-repo scheduling evidence was found, the same evidentiary posture
`TITAN_TECH_DEBT_REGISTER.md`'s DEBT-015 already established for monitoring infrastructure.

**New: R7 — `sentinel-apex-api/app/api/v1/endpoints/intel_graph.py`, intel-platform, Python
(FastAPI).** A fourth independent graph computation, in a third backend stack entirely (FastAPI
on Railway/Render + Supabase — neither the Cloudflare Worker nor the Python ingestion pipeline),
with its own separate authentication system. Reads `data/graph/graph_relationships.stix.json`
plus a Supabase fallback query. No confirmed live deployment: its Railway-deploy CI workflow is
misplaced (`sentinel-apex-api/.github/workflows/sentinel-apex-api`, nested inside the
subdirectory and missing the `.yml` extension — GitHub Actions only discovers workflows under
the repository root's `.github/workflows/`, so this can never have triggered), and the domain
its own CORS config names (`app.cyberdudebivash.com`) failed to connect in a direct HTTPS probe
run alongside clean 200s for both platform's known-live domains. Full assessment in
`TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md` Task 3.

**R2's runtime characterization also needs qualification** (not a change to this ADR's
Decision, which concerns ownership, not deprecation timing per se, but relevant to migration
urgency): this stage confirmed, via `platform/open-issues.md` Issue 9's own language and direct
repository tracing, that `KnowledgeGraph()` is constructed only through manual `cli.py run`/
`score` invocation and the blog's own test suite — no blog workflow invokes it as scheduled
automation. R2 remains real, correct, tested code; it is not, on current evidence, a live
production pipeline in the sense "Report generation pipeline" (this ADR's own Existing
Implementations table) implies.

**Effect on this ADR's Decision.** The original Decision (R1 target-canonical, contingent on
persistence) is **not withdrawn** — nothing found this stage makes R1 a worse choice than
before. But DEBT-000B's practical reconciliation target changes: it is now **R1-vs-R6**, not
R1-vs-R3 (R3 is a thin, non-computing reader over R6's output, not an independent
implementation). R6's same-repository location and functional completeness make it, if
anything, a stronger persistence-layer donor candidate for R1 than R2 ever was — with the
now-open question of whether R6's execution-trigger gap should be closed by scheduling it, or
whether that gap is itself evidence it should be superseded rather than adopted. **Neither this
ADR nor Stage 9 Phase 1 decides that question.** R7's disposition is even less settled — it may
not be in this ADR's scope at all, pending a human product decision on whether it represents
live intent.

**This ADR should not be Accepted from the pre-Revision-3 text.** Any reviewer beginning
Acceptance review should review against this revision, not Revision 2, given the corrected
factual basis.

---

## Revision 4 — 2026-08-05, Stage 9 Phase 2 (adds R8; ownership recommendation prepared, not decided)

Stage 9 Phase 2 (architecture planning, no migration executed) re-examined
`scripts/threat_graph_engine.py` — one of Revision 3's 16 long-tail files, not previously
weighted for ownership relevance — and found it feeds `/api/graph/{nodes,edges,pivot}`, a live,
tiered, monetized public API surface, per its own documented upload path in
`sentinel-blogger.yml`. **Catalogued as R8.** This is a fourth implementation with a real
customer-facing role, materially changing DEBT-000B's reconciliation scope from "R1 vs. R6" to
"R1 vs. R6 vs. R8" — see `TITAN_TECH_DEBT_REGISTER.md`'s updated DEBT-000B entry.

Phase 2 also produced (as separate documents, not duplicated into this ADR): a full graph
capability matrix, a **recommended, not decided** canonical ownership disposition for every
implementation R1–R8 (`TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md` Task 3), a canonical
relationship schema and shared interface specification (`TITAN_GRAPH_INTERFACE_SPECIFICATION.md`),
and a migration blueprint whose first authorized phase deliberately excludes R8 given its
commercial risk (`TITAN_GRAPH_MIGRATION_BLUEPRINT.md`). **None of this constitutes Acceptance.**
This ADR's Approval section, below, is unchanged by Phase 2 — a reviewer accepting this ADR
should review against Revision 4 (this section) for the current full picture, and the
companion documents above for the detailed recommendation now on record.

---

## Revision 5 — 2026-08-06, Stage 16 (Executive Acceptance; resolves the persistence precondition)

Executive architecture authority (cyberdudebivash, direct session confirmation, mirroring the
mechanism `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` used for ADR-0008/0011/0012) accepted this
ADR as written in Revision 4, and in the same session resolved the one prerequisite Revision 4
left open for engineering scoping: **how R1 gains the persistence layer Decision item 2 requires.**

**Resolution: native persistence, not R6 adoption.** DEBT-000B's own "Recommended Resolution"
named two valid paths: *"either adopt R6 as R1's persistence layer... or formally deprecate R6 in
favor of building persistence natively into R1."* Stage 16 takes the second path:

- A new, same-repository, same-language (JS) persistence layer is built at R1's *consumption*
  boundary — `workers/intel-gateway/src/relationship-framework/` (`edge-repository-interface.js`
  contract + `in-memory-edge-repository.js` reference implementation, mirroring
  `evidence-registry/repository-interface.js` + `in-memory-repository.js`'s exact, already-
  established pattern: a backend-agnostic contract with an in-memory reference implementation,
  no vendor-specific (KV/D1/R2) binding hardcoded into it).
- R1's live edge shape (`p31-handlers.js`'s `_buildGraph`/`handleP31Relationships` output —
  `{source, target, relation, confidence, evidence, verified}`, documented from
  `handleP31Relationships`'s own JSON response contract) is adapted into this persistence layer
  and into Stage 12's `RelationshipProviderInterface` shape by a **documented-data-shape
  adapter** (`p31-edge-adapter.js`), mirroring `evidence-registry/migration-adapters.js`'s
  established rule exactly: adapt the shape, never `import` the live handler file. This preserves
  every dormant-scaffolding directory's zero-blast-radius property unchanged.
- **R6 (`core/intelligence/enrichment_graph.py`) is not adopted, not imported, not modified, and
  not deprecated by this revision.** DEBT-000B's cross-language "R1 vs. R6" question — whether
  R6 should eventually supersede this native persistence layer, and DEBT-017's prior question of
  whether R6 executes in production at all — remains open and is explicitly **not** resolved
  here. What Revision 5 removes is only R6-adoption's status as a *blocker to ADR-0010
  Acceptance* — Decision item 2's persistence precondition is satisfied by the native layer
  instead, so Acceptance no longer needs to wait on a cross-runtime (Python-in-a-JS-Worker)
  integration question. See `TITAN_TECH_DEBT_REGISTER.md` DEBT-000B's Stage 16 update for the
  full disposition.
- **No new graph engine or new graph database is introduced.** The persistence layer stores the
  same edge records R1 already computes — it does not recompute, re-derive, or duplicate
  `_buildGraph`'s graph-construction logic (that logic is not imported, and is not
  re-implemented; only its documented output shape is adapted). This satisfies both this ADR's
  own "no graph database" scope boundary (Stage 6 NON-GOALS) and Stage 16's identical constraint.

This resolution is scoped to unblocking Acceptance and Stage 16's Relationship Framework
specifically. It does not foreclose a future, separately-authorized decision to adopt R6 (or
retire it) — that remains exactly as open as DEBT-000B/DEBT-017 left it.

---

## Approval

**Accepted.** Signed off by executive architecture authority, mirroring
`TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`'s ADR-0008/0011/0012 precedent — an executive-authority
acceptance, not an independently-obtained multi-party review; the individually-named reviewers
below were not separately consulted, and this record says so rather than implying otherwise:

- [x] Platform Governance Lead — accepted by executive authority, 2026-08-06
- [x] Chief Threat Intelligence Architect / P31 owner (persistence-layer scoping commitment) —
      resolved by Revision 5 (native persistence, not R6 adoption), 2026-08-06
- [x] Blog/EIOS engineering owner (`knowledge_graph.py`, `layer-09` owner) — not independently
      obtained; R2 (`knowledge_graph.py`) is unaffected by Stage 16 (Revision 5 touches only
      intel-platform-side persistence), so the deprecation-timeline sign-off this row originally
      tracked remains deferred until an actual R2 migration is proposed, per Migration Strategy
      item 3 below, which Stage 16 does not execute

**Decided by / date:** cyberdudebivash, executive architecture authority — 2026-08-06, direct
session authorization to accept ADR-0010 and build the Relationship Framework it gates.

Code implementing this decision is Stage 16's own deliverable — see
`TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md`.
