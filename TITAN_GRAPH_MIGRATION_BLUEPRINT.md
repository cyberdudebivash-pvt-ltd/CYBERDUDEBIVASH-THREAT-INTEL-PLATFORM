# Project TITAN — Canonical Graph Migration Blueprint

**Date:** 2026-08-05
**Status:** Design only. **Zero production behavior changes result from this document.** No
phase described below has been executed. This is Stage 9 Phase 2 Task 6 — migration planning,
not migration.
**Depends on:** `TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md` (ownership recommendations),
`TITAN_GRAPH_INTERFACE_SPECIFICATION.md` (interfaces and schema this plan migrates *toward*).
**Authorization status:** Not authorized to execute. ADR-0010 Acceptance (with R8 folded in) is
a precondition for Phase 1 below, and DEBT-017/DEBT-020 root-cause resolution are preconditions
for trusting R6's data at all. See Task 9's BLOCKED determination in the Architecture Plan.

---

## Guiding constraint

Per Stage 9's original charter: **"Migrate one low-risk graph consumer behind the canonical
interface... Stop after one successful migration."** This blueprint is deliberately structured
so that even its *first executable phase*, once authorized, touches exactly one consumer (R3),
chosen specifically because Task 3's ownership analysis found it to be the lowest-external-risk
candidate (same-repo, already a thin reader, no direct customer contract on its own beyond what
R1 already exposes). R8 — despite being architecturally similar in shape to R3 (also a
snapshot-reading pattern) — is deliberately **excluded from this blueprint's first phase**
because it is commercially tiered, monetized, live traffic. Folding R8 in prematurely would
violate the "stop after one" instruction in substance even if not in literal consumer count.

---

## Phase 0 — Preconditions (not migration, gating only)

| Precondition | Owner | Blocks |
|---|---|---|
| ADR-0010 Acceptance, with R8 explicitly added to its Existing Implementations table (this blueprint's Phase 1 assumes R8 is named in an Accepted ADR, not just this planning document) | Platform Governance Lead, Chief Threat Intelligence Architect | All phases below |
| DEBT-017 resolved: confirm whether `core/orchestrator.py` executes anywhere (external scheduler, manual run, or genuinely never) | Intelligence Engineering | Phase 1 (cannot build a persistence bridge on an unconfirmed producer) |
| DEBT-020 resolved: root cause of the zombie-pipeline pattern found (unrelated pipelines, but the same root-cause class — "is this scheduled script's output actually landing anywhere" — directly informs how much to trust R6's own scheduling once Phase 1 wires it up) | Intelligence Engineering | Phase 1 (confidence-building, not a hard blocker, but strongly recommended to resolve first given the adjacent failure mode) |

**No phase below begins until Phase 0 clears.**

---

## Phase 1 — R6 becomes R1's persistence layer (foundational, zero consumer-facing change)

**Objective:** R1 gains the persistence ADR-0010 has always named as its missing prerequisite,
by reading R6's existing R2-storage export (`data/ai/intel_graph.json`, written by
`R2AIExportStage` — infrastructure that **already exists**, per DEBT-013's Phase 1 resolution)
rather than building a new persistence mechanism from scratch.

**Why this shape, not a live RPC bridge:** R1 runs in a Cloudflare Worker (V8 isolate); R6 runs
as a Python batch process. A synchronous in-process call between them is not possible, and a new
live HTTP bridge would introduce a new network dependency and latency cost into R1's per-request
path — a Level 6 (Performance) violation this repository's engineering order explicitly ranks
above Level 7 (Commercial Value). Reading an already-produced R2 object is the lower-risk,
already-proven-pattern option (R3 already does exactly this today).

**Migration order:**
1. R1 gains a new, additive code path (`GraphProvider`-conformant, per the Interface
   Specification) that reads `data/ai/intel_graph.json` from R2 storage **in addition to** its
   existing per-request corpus computation, and merges the two (R6's persisted, enriched data
   augments R1's live corpus view; R1's live view remains authoritative for anything R6 hasn't
   seen yet).
2. This path is feature-flagged off by default (`GRAPH_CANONICAL_PERSISTENCE_ENABLED`, mirroring
   the Evidence Registry's `SCAFFOLDING_ENABLED` precedent).
3. Existing R1 behavior (`_buildGraph`, `buildP31RelationshipBlock`) is **not modified** —
   the new path is additive, called only when the flag is on.

**Consumer order:** none yet — this phase has no consumer-facing effect while the flag is off.
Enabling the flag in a non-production environment for shadow comparison is the verification step
(below), not a migration step.

**Compatibility adapters:** not yet needed in this phase — R1's existing response shape is
unchanged whether the flag is on or off; the new data only augments internal graph-building
logic, and the schema mapping (native R1 shape → `CanonicalRelationship`) happens inside the new
code path, invisible to callers.

**Feature flags:** `GRAPH_CANONICAL_PERSISTENCE_ENABLED` — boolean, defaults `false`. Off in
production until the verification gates below pass in a non-production environment.

**Rollback point:** flip the flag off. No code revert required — this is the entire reason the
path is additive rather than a modification of existing functions.

**Success metrics:**
- R1's response shape is byte-identical for any request where R6 has no additional data (proves
  the new path is truly additive, not a silent behavior change for the common case).
- For requests where R6 *does* have additional enriched data, the response includes it without
  breaking existing consumers' parsing (additive fields only, per the schema's backward
  compatibility rules).
- No latency regression beyond a documented, accepted budget (R2 storage reads are fast, but this
  must be measured, not assumed).

**Verification gates:**
- Full existing regression suite (21/21) unchanged.
- New: a `RelationshipValidator`-based test asserting every relationship R1 emits with the flag
  on is schema-valid.
- Shadow-mode comparison: run both paths in parallel in a non-production environment, diff
  outputs, require zero unexplained divergence before flag flip is even considered.

---

## Phase 2 — R3 becomes the single pilot consumer (the "one low-risk consumer" migration)

**Objective:** R3 (`handleIntelGraph`/`handleIntelRelations`) stops reading `data/ai/
intel_graph.json` directly and instead calls R1's now-canonical `GraphProvider` implementation
(from Phase 1). This is the literal "migrate one low-risk consumer behind the canonical
interface" instruction.

**Migration order:**
1. R3's handler gains a feature-flagged branch: `GRAPH_R3_USES_CANONICAL_PROVIDER`.
2. When on, R3 calls R1's `GraphProvider.getGraphForItem()`/`getFullGraph()` instead of its own
   `data/ai/intel_graph.json` read.
3. When off (default), R3's existing behavior is fully preserved, byte-for-byte.

**Consumer order:** R3 only. No other consumer (R8, R4, R2) is touched in this phase, per the
guiding constraint above.

**Compatibility adapters:** R3 itself *is* the compatibility adapter, per Task 3's ownership
recommendation — this phase is the literal implementation of that recommendation, once
authorized.

**Feature flags:** `GRAPH_R3_USES_CANONICAL_PROVIDER` — boolean, defaults `false`, independent
of Phase 1's flag (Phase 1 can be on in production — R1 serving richer data — while this flag
stays off, decoupling the two risk surfaces).

**Rollback point:** flip the flag off; R3 reverts to its current, already-proven data path
instantly.

**Success metrics:**
- R3's response shape (`/api/v1/intel/graph`, `/api/v1/intel/relations`) is unchanged for
  existing consumers — this is the customer-facing contract and the highest-scrutiny success
  metric in this entire blueprint.
- R3's data freshness problem (DEBT-017's downstream symptom) is resolved as a side effect: once
  R3 calls R1 directly instead of reading a possibly-stale R2 snapshot, "is the snapshot fresh"
  stops being a meaningful question — R1 is always current by construction (Phase 1's design).
- No regression in R3's existing tier-gating (403 for unauthorized, 200/403 behavior unchanged).

**Verification gates:**
- Full regression suite.
- A diff-based comparison of R3's old-path vs. new-path output across a representative sample of
  real advisory IDs, run in shadow mode before the flag flips.
- Explicit sign-off that Phase 1's shadow-mode verification (above) has been clean for a defined
  observation period before Phase 2 begins — these phases are sequential, not parallel.

**Stop here.** Per the guiding constraint, this blueprint does not sequence R8, R4, or R2's
migration — those are explicitly **out of scope for the first authorized migration** and would
require their own future planning pass (see "Deferred, not forgotten" below), each starting from
its own fresh Proof Before Change table per this repository's CLAUDE.md, since each is a
materially different risk profile (R8: commercial/tiered; R4/R2: cross-repo).

---

## Deferred, not forgotten (explicitly out of scope for this blueprint's executable phases)

| Item | Why deferred | What unblocks it |
|---|---|---|
| R8 (`scripts/threat_graph_engine.py`) | Highest commercial risk in the entire inventory (live, tiered, monetized customer traffic) — the guiding constraint's "stop after one" instruction exists specifically to prevent bundling a high-risk consumer into the first migration | Phase 1 and Phase 2 both landing cleanly, observed stable in production for a defined period, plus its own dedicated Proof Before Change / Blast Radius assessment given its distinct static-file-serving infrastructure pattern |
| R4 (`api/_lib/threat-graph.js`, blog) | Cross-repo — requires blog engineering coordination and negotiation ADR-0010 has always sequenced *after* same-repo convergence | Same-repo convergence (this blueprint) completing; a cross-repo Cross-Repo Consumption pattern proposal (Stage 2 precedent) |
| R2 (`knowledge_graph.py`, blog) | Confirmed manual-invocation-only (Phase 1 finding) — no live traffic forces urgency; its edge vocabulary is already folded into the canonical schema (§A.3 of the Interface Specification) independent of the engine's own migration timeline | Blog engineering owner decision on whether manual runs still occur operationally; not commercially urgent |
| `agent/graph_correlation_engine.py` + `agent/graph_integrity_validator.py` (DEBT-020 pair) | Cannot migrate a data flow whose root cause is unknown — migrating a broken pipeline just relocates the breakage | DEBT-020 root-cause resolution |
| Evidence Registry integration (`EvidenceRelationshipProvider`) | Gated on ADR-0008 Acceptance, an independent precondition this blueprint does not control | ADR-0008 Acceptance |

---

## Cross-cutting rollback strategy

Every phase in this blueprint is reversible via feature flag alone — **no phase requires a code
revert to roll back**, which is itself a design constraint this blueprint was held to, not an
incidental property. If a rollback is needed after a flag has been on in production for a period
(e.g., a subtle data-quality issue found after some real traffic has flowed through the new
path), the rollback plan is:
1. Flip the relevant flag off immediately (restores prior behavior in the next request cycle,
   no deploy needed if flags are runtime-configurable per this repo's existing KV/env-var
   pattern).
2. Investigate the issue against the shadow-mode comparison data already collected (Phase 1/2's
   verification gates produce this data as a byproduct, not an afterthought).
3. Do not re-attempt the flag flip until the root cause is understood and a new verification
   pass is clean — matching this repository's Production Stability First principle.

## Success metrics, program-wide

- **Zero regression in either repository's existing regression/certification suites** at every
  phase boundary — the non-negotiable floor, not an aspirational target.
- **DEBT-000B closed** (or formally re-scoped with documented reason) once Phase 2 lands.
- **DEBT-013's residual freshness concern (DEBT-017) resolved as a structural side effect**, not
  through additional scheduling work — proof that fixing ownership can retire an operational
  debt item as a side effect, which is itself evidence the ownership recommendation was correctly
  targeted.
