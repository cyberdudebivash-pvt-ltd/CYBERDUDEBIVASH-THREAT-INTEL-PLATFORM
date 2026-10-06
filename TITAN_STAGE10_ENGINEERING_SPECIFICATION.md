# Project TITAN — Stage 10 Engineering Specification

**Date:** 2026-08-05
**Status:** **Contingent planning document. Stage 10 is currently BLOCKED for all four
capabilities in scope** (see `TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md` Task 9). This
specification describes the plan that would execute *once* the preconditions below clear — it
is not an authorization to begin, and no part of it should be implemented from this document
alone. Per Stage 9 Phase 2 Task 10's own instruction: "Produce a production implementation plan
only. Do not implement."
**Preconditions (all currently unmet):** ADR-0010 Acceptance (with R8 added), ADR-0008
Acceptance, `TITAN_GRAPH_MIGRATION_BLUEPRINT.md` Phases 1–2 executed and verified stable in
production, DEBT-017 and DEBT-020 root causes resolved.

---

## 1. Scope

Four capabilities, each independently gated (clearing one does not clear the others):

| Capability | In scope | Explicitly out of scope |
|---|---|---|
| Enterprise Evidence Registry | Activating the Stage 8 scaffolding (`workers/intel-gateway/src/evidence-registry/`) as a real, imported, routed capability | Any change to the scaffolding's already-designed shape (`EvidenceEntity`, `evidence_uuid`/`content_hash` scheme) — that was Stage 8's design work, reused not redone |
| Relationship APIs | Exposing `CanonicalRelationship`-shaped data (per `TITAN_GRAPH_INTERFACE_SPECIFICATION.md`) through R1's now-canonical `GraphProvider`/`RelationshipProvider` | Public (non-authenticated, non-platform) API exposure — Stage 9's own charter excludes this explicitly ("No public API exposure yet") |
| Provenance APIs | Linking `CanonicalRelationship.evidence_references` to live `EvidenceEntity` records via `EvidenceRelationshipProvider` | Any new evidence *sourcing* mechanism — provenance here means linking already-captured evidence to relationships, not capturing new evidence types |
| Knowledge Graph | **Nothing.** Remains excluded per Stage 6's original Non-Goals, unchanged through Stage 9 Phase 1's own STAGE 10 PREVIEW section, unchanged by this document | Everything — this capability has no scope defined anywhere in this program yet |

---

## 2. Deliverables (per capability, contingent on authorization)

### 2.1 Enterprise Evidence Registry activation
- Wire `evidence-registry/` into `index.js`'s import chain (currently deliberately unwired,
  per the Stage 8 boundary the governance check enforces).
- A real repository backing `repository-interface.js`'s contract (KV, D1, or R2 — not decided
  by this document; that is itself a Proof Before Change decision for whoever executes this).
- Route(s) exposing evidence CRUD, gated by the same tier system already governing every other
  P-layer route (Principle 4: reuse, don't reinvent auth).

### 2.2 Relationship API
- R1 (`p31-handlers.js`) extended (not replaced) to serve `CanonicalRelationship`-shaped
  responses alongside its existing shape (additive, per Principle 2).
- `RelationshipValidator` implemented and wired into the write path.
- `RelationshipResolver` implemented (R6's `link_iocs()` dedup logic is the reference
  implementation, per the Interface Specification's own "likely first implementer" notes).

### 2.3 Provenance API
- `EvidenceRelationshipProvider` implemented, connecting 2.1 and 2.2's outputs.
- No new deliverable beyond the interface already specified — this capability is compositional,
  not a new subsystem.

### 2.4 Knowledge Graph
- No deliverables. Out of scope (§1).

---

## 3. Migration strategy

Delegates entirely to `TITAN_GRAPH_MIGRATION_BLUEPRINT.md` — this specification does not define
a second, competing migration plan. Stage 10 work does not begin until that Blueprint's Phase 1
and Phase 2 have both landed and been observed stable, per this document's own preconditions.
Any Stage 10-specific migration steps (e.g., backfilling `evidence_references` for
already-existing relationships) would be a Phase 3+ addition to that same Blueprint, not a
parallel document, to keep migration planning in one place (Single Source of Truth).

---

## 4. Testing

| Layer | Requirement |
|---|---|
| Unit | `RelationshipValidator`, `RelationshipResolver`, `EvidenceRelationshipProvider` each need a dedicated test suite — none exists yet since none is implemented |
| Integration | End-to-end: ingest → relationship created → evidence attached → retrievable via API, matching the full Provenance API round-trip |
| Regression | The existing 21-test suite must stay 21/21 — no Stage 10 deliverable is permitted to touch or weaken it |
| Schema validation | Every relationship written by any code path must pass `RelationshipValidator.validate()` — enforced in CI, not just at write-time, mirroring this repo's existing certification-gate pattern |
| Shadow-mode | Same discipline as the Migration Blueprint's phases: run Stage 10 write paths in shadow (write but don't yet serve) before any read-path exposure |

---

## 5. Rollback

Every deliverable in §2 must be feature-flagged (extending, not duplicating, the
`GRAPH_CANONICAL_PERSISTENCE_ENABLED`/`GRAPH_R3_USES_CANONICAL_PROVIDER` flags the Migration
Blueprint already establishes, plus new flags for Evidence Registry activation specifically —
e.g. `SCAFFOLDING_ENABLED` already exists and defaults false; Stage 10 would be the first work
that could responsibly consider flipping it, and only after ADR-0008 Acceptance). No Stage 10
deliverable may be a one-way door — this mirrors every gate this program has applied since
Stage 6.

---

## 6. Observability

Per this repository's CLAUDE.md Principle 7 (Observable Everything), unconditionally required
regardless of Stage 10's own scope decisions:
- A certification report in `data/quality/` for whichever new capability ships.
- A new CI gate in `sentinel-blogger.yml`, sequenced after STAGE 3.98 (P33) per this repo's
  existing stage-numbering convention, with its actual assigned number confirmed against
  `sentinel-blogger.yml`'s live state at implementation time (not assumed from CLAUDE.md's own
  admittedly-stale numbering table — see DEBT-011, still open).
- An `/observability` endpoint for any new P-layer-shaped capability, matching P34-P38's existing
  precedent.
- Given this stage's specific subject matter (a canonicalization program born from finding
  CI-green-but-silently-broken pipelines — DEBT-020), Stage 10's observability requirement is
  held to a **higher bar than the template above**: any new scheduled/automated component must
  have an explicit "this ran AND its output was verified non-empty/non-trivial" check, not just
  "this ran and exited 0." DEBT-020 exists precisely because that distinction wasn't enforced
  anywhere in this platform before Phase 1 found it.

---

## 7. Performance validation

- API response time budget: reuses this repository's existing P-layer baseline (`< 500ms p95
  for cached, < 2s p95 for computed`, per CLAUDE.md) — Stage 10 does not get a special exemption.
- R1's Phase 1 persistence-read addition (Migration Blueprint) must be re-measured once real
  Evidence/Relationship read paths are added on top of it — cumulative latency across all of
  Stage 9+10's additions, not just each piece measured in isolation.
- Cold-start budget (`< 50ms`, per CLAUDE.md) applies to any new Worker-side code.

---

## 8. Operational readiness

- On-call/ownership assignment for each new capability — not decided by this document (an
  organizational decision, consistent with this program's precedent for similar items, e.g.
  DEBT-001's "requires blog repo's architecture-review authority to claim").
- Runbook for the specific failure mode this program now knows to watch for: a scheduled job
  reporting success while producing no real output (DEBT-020's pattern). Any Stage 10 automation
  should have a documented "how would we know if this silently broke" answer before it ships,
  not after.

---

## 9. Acceptance criteria

Stage 10 (any capability) is acceptance-ready only when:
- Its governing ADR (0008 for Evidence Registry, 0010 for Relationship/Provenance APIs) is
  **Accepted**, not Proposed.
- The Migration Blueprint's Phases 1–2 have executed and been stable in production for a defined
  observation period (not specified here — an operational decision for whoever executes the
  Blueprint, informed by its own success metrics).
- DEBT-017 and DEBT-020 are both closed with documented root causes, not just "no longer
  reproducing."
- Full regression suite passing, certification WORLDWIDE_RELEASE/0 blockers, governance check
  clean against its then-current allowlist — the same floor every prior stage has held.

---

## 10. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Stage 10 work begins before ADR-0010/0008 Acceptance (process failure, not technical) | Medium — this program has a documented history of stages proceeding on "Proposed, ready for review" ADRs without confirming Acceptance actually happened (Stage 8/9's own readiness assessments both flagged this as unresolved) | High — would repeat the exact process gap this specification's own preconditions exist to close | `check_adr0010_graph_ids_present()`-style governance checks are necessary but not sufficient; this is fundamentally a human-process risk, not a code risk, and this document says so plainly rather than implying a check can fully substitute for a human sign-off |
| R8's commercial exposure gets folded into Stage 10 scope creep (e.g., "while we're at it, let's also migrate the graph API") | Medium | High (real customer traffic) | The Migration Blueprint's explicit "Deferred, not forgotten" table for R8 is the guardrail — Stage 10 planning work should re-read that table before any scope discussion, not re-litigate it |
| A new Stage 10 automated component repeats the DEBT-020 pattern (green CI, silent no-op) | Medium — this platform has now found this exact failure mode twice in unrelated pipelines, suggesting it's a systemic gap, not a one-off | High (undermines trust in every future "confirmed production" claim this program makes) | §6's elevated observability bar exists specifically for this; treat it as non-negotiable for Stage 10, not aspirational |
| Evidence Registry activation reveals the scaffolding's Stage 8 design has a gap under real load/data (untested against production data by design, per its own authorization) | Low-Medium | Medium | Shadow-mode testing (§4) before any real write path opens is the mitigation; the scaffolding's `README.md` and Stage 8's own authorization report already anticipate this |

---

## Closing note

This specification exists so that, when its preconditions genuinely clear, Stage 10 does not
have to re-derive its own shape from nothing — the plan is ready, the interfaces are specified,
the migration path is sequenced. What it cannot do, and does not attempt to do, is make the
preconditions clear faster. That remains explicitly a human Acceptance decision on ADR-0010 and
ADR-0008, plus real engineering time on DEBT-017 and DEBT-020 — none of which this document,
or any document, can substitute for.
