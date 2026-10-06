# Project TITAN — Implementation Authorization Report (Task 8)

**Status:** Determination only. Per this stage's FINAL EXECUTION DIRECTIVE, no Blocked
capability is implemented by this or any other Stage 7 document. This report supersedes
`TITAN_IMPLEMENTATION_READINESS.md` (Stage 6) for the four capabilities it already covered —
not by contradicting it, but by adding the two new capabilities Task 8 asks for (Customer
Portal, Enterprise APIs) and updating status where this stage's findings changed the picture
(notably Knowledge Graph, where a new fragmentation was found, and Explainable AI / Evidence
API, where ADR-0012's approval is now a named dependency).

---

## Enterprise Evidence Registry

| Field | Value |
|---|---|
| **Status** | **Blocked** (unchanged from Stage 6) |
| **Dependencies** | ADR-0008 Accepted; Evidence schema extension (Migration Roadmap Phase 3) shipped and stable in production |
| **Required ADRs** | ADR-0008 (written, Proposed) |
| **Required Refactoring** | P20 schema extension must ship first (Phase 3); registry is new infrastructure built *against* that schema, not concurrent with deciding it |
| **Migration Complexity** | High — new D1 table or KV namespace, new CRUD API, new CI certification gate, new consumers across P20/P23/P32 |
| **Implementation Risk** | Medium — the schema groundwork (Phase 3) is low-risk and additive; the registry service itself is genuinely new infrastructure with normal new-service risk (data integrity, migration of any existing evidence_chain data into the registry's authoritative store) |
| **Estimated Engineering Effort** | Large (multi-week) — not scoped to a number of days by this report, since Task 7 in Stage 6 already flagged this as the largest of the originally-assessed capabilities and nothing this stage found reduces that |

## Evidence APIs

| Field | Value |
|---|---|
| **Status** | **Blocked** |
| **Dependencies** | Evidence Registry (above) must exist first — an API without a registry behind it has nothing authoritative to serve; **additionally now blocked on ADR-0012 approval** (this stage's finding — API versioning policy must be accepted before a new API family launches under it) |
| **Required ADRs** | ADR-0008, ADR-0012 (both written, both Proposed) |
| **Required Refactoring** | None beyond the Registry's own — additive API surface once dependencies exist, per `EVIDENCE_ENGINE_DISCOVERY.md` EPIC 6's own assessment (still accurate, re-confirmed this stage) |
| **Migration Complexity** | Medium — established `/api/v1/*` route patterns to extend (per ADR-0012, launches as `/api/v1/evidence/*` under intel-platform's existing namespace, not a new namespace) |
| **Implementation Risk** | Low-Medium once unblocked — the pattern is well-precedented |
| **Estimated Engineering Effort** | Medium (1-2 weeks) once both dependencies clear |

## Knowledge Graph

| Field | Value |
|---|---|
| **Status** | **Blocked** — and the blocker is now better understood, not smaller |
| **Dependencies** | ADR-0010 Accepted (revised **twice** this stage — first to address a 4-way fragmentation, then again to add a 5th implementation, `api/_lib/graph-engine.js`, found via the same trace that produced DEBT-000); P31 persistence engineering (DEBT-004, still unestimated); identification of the `data/ai/intel_graph.json` producer (DEBT-013); **resolution of DEBT-000 generally**, since the newest graph candidate (R5) is part of the same undocumented system |
| **Required ADRs** | ADR-0010 (written, Proposed, revised twice this stage) |
| **Required Refactoring** | P31 persistence layer (large, unestimated) — **though R5 may already have the persistence property being sought, per ADR-0010's revision, which changes what "required refactoring" even means here pending the R1-vs-R5 re-decision** |
| **Migration Complexity** | High, and the target is no longer even clearly "converge everything onto P31" — ADR-0010's revision names R5 as a plausible alternative target, which this report does not resolve |
| **Implementation Risk** | High — any convergence touches a live, tier-gated, customer-facing endpoint (`api/v1/intel?action=graph`) on the blog side; must not be attempted without the blog-side compatibility layer ADR-0010 already flags as not yet built |
| **Estimated Engineering Effort** | Large (multi-week to multi-month) — increased from Stage 6's implicit estimate given the newly-found scope |

## Explainable AI

| Field | Value |
|---|---|
| **Status** | **Partially Ready** (unchanged framing from Stage 6, with one addition) |
| **Dependencies** | ADR-0007 Accepted; audit of whether `/api/v1/p38/confidence-audit` already satisfies a v1, confidence-only scope (Stage 6's finding, not re-verified this stage) |
| **Required ADRs** | ADR-0007 (written, Proposed) |
| **Required Refactoring** | Minimal for v1 (confidence-only) — most already exists. Full scope (evidence, lifecycle, relationships) inherits those capabilities' blockers, including the newly-larger Knowledge Graph blocker above |
| **Migration Complexity** | Low (v1) / High (full scope, unchanged assessment) |
| **Implementation Risk** | Low (v1) |
| **Estimated Engineering Effort** | Small (v1, days) / Large (full scope) |

## Customer Portal (new this stage)

**MAJOR CORRECTION, same stage:** this section originally stated no customer portal
implementation exists. That was written before the `api/_lib/` reachability trace returned.
It was wrong. `api/v1/customer/dashboard.js` is a real, working "Customer Self-Service
Dashboard" (purchase history, subscription status, download links, API key/tier status),
`api/v1/customer/download.js` a companion route — both very likely live, per
`TITAN_STAGE7_VALIDATION.md` §2A. The determination below is corrected accordingly, not
silently replaced — the original wrong text is preserved in this file's git history.

| Field | Value |
|---|---|
| **Status** | **Not Blocked in the sense of "doesn't exist" — Blocked in a different sense: exists, is likely live, and has zero governance.** Re-classified from Stage 6/this-stage's original "Blocked, nothing built" to "exists ungoverned, needs a retroactive ADR before further investment" |
| **Dependencies** | A retroactive ownership decision (who owns this, is it staying) rather than new-build dependencies. Overlaps DEBT-000 directly — this *is* one of DEBT-000's routes, not a separate gap |
| **Required ADRs** | **None exist**, confirmed. A new ADR (candidate: ADR-0014, "Customer Portal & Investigation Workbench Ownership," possibly merged with resolving DEBT-000 generally rather than written standalone) is required — not written this stage, same reasoning as before, but now urgent rather than speculative since real customer data (purchase history, download links) already flows through it |
| **Required Refactoring** | Unknown pending the ADR — but note any refactoring here touches **live customer purchase/subscription data**, materially higher-stakes than a greenfield build would be |
| **Migration Complexity** | Not assessable without the ADR, but starting from "already live" rather than "greenfield" changes the risk profile of whatever the ADR decides |
| **Implementation Risk** | **Elevated** relative to a greenfield assessment — any change here risks live customer-facing functionality, not hypothetical future functionality |
| **Estimated Engineering Effort** | Not assessable without the ADR |

## Enterprise APIs (new this stage)

| Field | Value |
|---|---|
| **Status** | **Partially Ready** — closer to Ready than Customer Portal, because unlike Customer Portal, the underlying route surface already exists and is already tiered |
| **Dependencies** | ADR-0012 Accepted (versioning policy must govern any new enterprise-tier route additions); resolution of DEBT-014 (TAXII dual-path) if the "enterprise API" scope includes TAXII, since shipping new enterprise capability on top of an unresolved dual-path surface would compound the ambiguity |
| **Required ADRs** | ADR-0012 (written, Proposed) |
| **Required Refactoring** | None required to continue operating the *existing* enterprise-tier surface (P34, admin, MSSP-tier rate limits already function) — refactoring is only required for *new* enterprise capability, which is not itself specified by Task 8 as a concrete deliverable, only as a readiness category |
| **Migration Complexity** | Low for continuing existing surface; not assessable for undefined "new" enterprise capability |
| **Implementation Risk** | Low for existing surface |
| **Estimated Engineering Effort** | N/A for existing (already built); not assessable for undefined future scope |

---

## Summary

| Capability | Status | Changed from Stage 6? |
|---|---|---|
| Enterprise Evidence Registry | Blocked | **New dependency added** — ADR-0008's approval now additionally gated on resolving DEBT-000 (E9–E12 found live in blog's `api/_lib/`) |
| Evidence APIs | Blocked | New dependency added (ADR-0012), plus DEBT-000 |
| Knowledge Graph | Blocked | **Blocker scope increased twice** — 4 graph implementations found, then a 5th (R5) that may already have the persistence property R1 lacks |
| Explainable AI | Partially Ready | No change |
| Customer Portal | **Corrected: exists (very likely live), ungoverned** | Originally assessed Blocked/nonexistent this stage; corrected after DEBT-000's discovery — see above, this was wrong for part of a working day and is fixed here, not silently |
| Enterprise APIs | Partially Ready | New capability this stage |

**Authorization determination, per Task 8's success criteria:** The platform is **not yet
authorized** to begin implementation of the Enterprise Evidence Registry or Provenance APIs.
Both remain explicitly Blocked. Stage 7 did not just make the blockers more precise (its
original goal) — partway through, it found a materially larger blocker than anything Stage 6
knew about (DEBT-000), which now sits upstream of ADR-0007, ADR-0008, ADR-0009, and ADR-0010
alike. **The single highest-priority action arising from this entire stage is not any of the
originally-planned migration phases — it is confirming whether DEBT-000's ~22 routes are
actually live**, since every other determination in this report is conditional on that answer.
