# ADR-0007: Canonical Confidence Framework

**Date:** 2026-08-05
**Status:** Proposed — **REVISED 2026-08-05 (Stage 7), see "Revision" section — a new blocking
finding (A10) must be resolved before this ADR can be Accepted.** Not Accepted. No
implementation may begin against this decision until it is explicitly approved (see
"Approval" at the end of this document).
**Deciders (proposed reviewers):** Platform Governance Lead, Chief Threat Intelligence
Architect, Intelligence Engineering (P-layer stack owner), Blog/EIOS Engineering, Governance
Team (`lib/governance` owner, if that initiative has an active owner)
**Program:** Project TITAN, Stage 6
**Supersedes:** No prior ADR. `CONFIDENCE_FRAMEWORK_DISCOVERY.md` (Stage 4) explicitly
declined to write this ADR and left the question open; this is the first attempt at closing it.
**Related:** ADR-0009 (Source Reliability Ownership) is a narrower, dependent decision —
source reliability is one input to canonical confidence, not a synonym for it.

---

## Context

The CYBERDUDEBIVASH® Threat Intelligence ecosystem computes "confidence" in more than one
place, for more than one purpose, in two repositories. Project TITAN Stage 1 first flagged
this (`platform/open-issues.md` Issue 15, `cyberdudebivash-blog`), Stage 4 catalogued it in
depth (`CONFIDENCE_FRAMEWORK_DISCOVERY.md`), and this stage's own validation
(`TITAN_STAGE6_VALIDATION.md`) extends that catalogue with two systems Stage 4's scoped search
did not reach. No canonical owner has ever been designated. Every prior stage that touched
this question explicitly declined to decide it and left it as the single most-repeated open
item in this program's history.

The absence of a decision is not neutral. `EVIDENCE_ENGINE_DISCOVERY.md` §3 documents a live,
in-production consequence: the same item can carry a P20 reliability grade of "B," a P18
attribution string of "D — Unknown," and a P25 trust percentage, computed three different ways,
none cross-checked. `TITAN_STAGE6_VALIDATION.md` §3 adds a fourth and fifth independent "has
evidence" heuristic (P37, P35) discovered since. This is the fragmentation failure mode this
ADR exists to stop, not a hypothetical risk.

---

## Problem Statement

**Which system is the authoritative source of intelligence-item confidence for the
CYBERDUDEBIVASH® ecosystem, and what is every other existing confidence-computing system's
relationship to it?**

A canonical framework must specify, for each existing implementation: adopt as-is, adopt as an
input dimension, keep as a distinct concept in a different layer (not competing), deprecate
with a migration path, or exclude from canonical status pending a separate disposition
decision.

---

## Existing Implementations

Restated from `CONFIDENCE_FRAMEWORK_DISCOVERY.md` Part A and `TITAN_STAGE6_VALIDATION.md` §2–3,
verified current as of this stage:

| ID | System | Repo | Shape | Consumers | Status quo role |
|---|---|---|---|---|---|
| A1 | `computeEnterpriseTrustScore()` | intel-platform, `p25-handlers.js` | 12-dimension, 0–100 composite, named rationale per dimension | 12 files direct import (`p26`–`p38`) + `p26_intelligence_excellence.py`, **+ P37.3's `_confidenceAudit` (new consumer found this stage)** | De facto most-relied-upon signal in the P-layer stack |
| A2 | `evidence_chain.reliability_code` | intel-platform, `p20-handlers.js` | A–F source-type grade (external NATO/Admiralty-style convention) | `computeP20QualityScore`, `buildEvidenceChainBlock` | Source-type signal; **not read by A1** |
| A3 | EIOS Layer 7 Mechanism 1 | blog, `Sentinel-APEX/eios/layer-07-confidence-model.md` | 7 named dimensions, analyst-authored prose, VERY LOW→VERY HIGH | Human readers of published reports; loosely gated by `quality.py::_gate_confidence` | The literal reader-facing confidence statement on every published report |
| A4 | `scoring.py::_analyst_confidence()` | blog, `Sentinel-APEX/engine/sentinel_engine/scoring.py` | Deterministic 0–100, one of 9 (now 14, per Issue 15 item 4) dimensions | Commercial-tier gate (Layer 10) | Independent of A1, disjoint inputs, disjoint consumers |
| A7 | `ai_confidence` fallback sprawl | intel-platform, 8 sites | 0–100 scale | Various | Stage 4 already normalized the 3 genuinely-wrong constants to 50.0; 2 genuine formulas correctly left untouched; 1 marketing constant (99.9) explicitly excluded as a business decision, not engineering |
| **A8 (new this stage)** | `ConfidenceEngine` / `MultidimensionalConfidence` | blog, `lib/governance/confidence-engine.ts` | 5 components (sourceReliability, observationQuality, technicalValidation, analystVerification, independentCorroboration), weighted average, full audit trail | **None outside its own module tree and test suite** (verified — see `TITAN_STAGE6_VALIDATION.md` §2) | Fully built, "Accepted" ADR (its own `docs/adr/0002`), zero production integration |
| **A9 (found via this stage's CI tooling, §4)** | `computeTransparentConfidence()` | intel-platform, `p18-handlers.js:173` | 7 independent factors (source_quality, evidence_count, cross_validation, data_freshness, consistency, ioc_quality, mitre_completeness), 0–100 | `buildTrustIndicatorBlock()` (same file, a renderer, not a second scorer) | Calls neither P20, P25, nor P26 — the **same file** that independently computes A2's sibling (`buildEvidenceAttribution`'s A–E grade) also independently computes a full second, differently-shaped confidence score |

**Also found via this stage's CI tooling, not added as a table row because it is a partial,
not clean-duplicate, case:** `_computeConfidenceGraph()` (`p29-handlers.js:155`) delegates 2 of
its 7 dimensions to canonical engines (P20, P26) but independently reinvents the other 5
(Source, Detection, IOC, Attribution, Executive Confidence) with their own thresholds. Logged as
**DEBT-012** in `TITAN_TECH_DEBT_REGISTER.md` rather than decided here — see this ADR's Future
Considerations.

---

## Decision

**`computeEnterpriseTrustScore()` (P25, A1) is designated the canonical machine-computed
confidence/trust score for intelligence items across the ecosystem**, subject to the migration
actions below. Specifically:

1. **A1 (P25) is canonical.** All new capability that needs a numeric, per-item confidence or
   trust signal calls A1. No new independent scorer may be introduced (enforced going forward
   per `TITAN_CI_GOVERNANCE.md`).
2. **A2 (P20 `reliability_code`) becomes an input dimension to A1, not a competing score.**
   P20 measures source-type trustworthiness; A1 measures item-level composite trust, of which
   source trustworthiness is one legitimate input. Migration: A1 gains a 13th dimension (or
   reweights an existing one, see ADR-0009) that reads `item.evidence_chain.reliability_code`
   when present. This directly closes the "A1 and A2 don't reference each other" gap
   `CONFIDENCE_FRAMEWORK_DISCOVERY.md` Part A2 flagged.
3. **A3 (EIOS prose) remains canonical for the human-facing narrative confidence statement.**
   This is not a competing system to deprecate — it is analyst judgment expressed in prose for
   a Markdown report, a fundamentally different artifact than a machine score. Its relationship
   to A1 is defined as advisory-adapter: where a published report's subject item has an A1
   score available, the analyst-authored A3 rating should be informed by it (not silently
   contradict it without explanation), but A3's authorship remains human. No code change to A3.
4. **A4 (blog `scoring.py::_analyst_confidence`) is marked Deprecated — Pending Migration.**
   It is the clearest duplicate of A1's role (deterministic 0–100 "how much do we trust this
   evidence," per `CONFIDENCE_FRAMEWORK_DISCOVERY.md` Part C). It is not deprecated
   immediately — removing it today would leave the blog's commercial-tier gate with no
   confidence signal at all, since the blog does not yet consume the intel-platform API for
   this purpose (see `TITAN_MIGRATION_ROADMAP.md` Phase 3, gated on the not-yet-built Evidence
   API). A4 is retired only once that consumption path exists.
5. **A7's Stage 4 fix stands.** No further action.
6. **A9 (P18 `computeTransparentConfidence`) is marked Deprecated — Pending Migration**, on the
   same basis as A4: a full independent 0–100 confidence computation with no consumer beyond a
   same-file rendering helper, sitting in the same file as another independent scorer (A2/S2).
   Migration path: fold into the same P18 migration ADR-0009 already specifies for
   `buildEvidenceAttribution` — once P18 consumes A1 (and S1, per ADR-0009) instead of
   independently computing, `computeTransparentConfidence`'s role is superseded by the same
   change, not a second migration project.
7. **A8 (`lib/governance/confidence-engine.ts`) is excluded from canonical candidacy**, not
   because its design is poor — it is arguably the most explicitly-structured of any candidate
   — but because a system with zero production consumers cannot be "the authoritative source of
   truth" for anything currently running. Its disposition (integrate its 5-component model as a
   future refinement of A1's dimension set, formally shelve it, or delete it) is a distinct
   question logged in `TITAN_TECH_DEBT_REGISTER.md`, not decided by this ADR. Its ADR-0002
   ("Accepted") is not superseded or altered by this document — that is outside this ADR's
   authority and would require the blog repo's own architecture-review process to act on.

---

## Rationale

- **Consumer count is corroborating evidence, not the sole basis.** A1 has the largest
  consumer footprint (13 files/functions after this stage's finding) of any live candidate,
  including organic adoption by the newest layer (P37) reaching for it rather than building a
  sixth scorer — a revealed preference this ADR ratifies rather than invents.
- **A1 already has the richest external-facing contract**: public API routes
  (`/api/v1/p25/trust-score`, `/api/v1/p38/confidence-audit`, `/api/v1/p38/iq-index`), a named
  per-dimension rationale structure enterprise customers can be shown, and it feeds P38's
  certification gate G14. Canonicalizing around it requires no new public surface — it already
  has one.
- **A2 and A1 are not actually in conflict** — they measure different things at different
  grains (source-type vs. item-composite). Treating A2 as an input rather than a rival avoids
  a false "pick a winner" framing where both are partially right.
- **A3 cannot be replaced by a machine score without changing what the product is.** The
  blog's entire commercial value (per its own CLAUDE.md) rests on analyst-grade, human-authored
  narrative content. Forcing A3 into a machine-computed shape would be a product regression
  framed as an architecture cleanup — rejected on that basis alone.
- **A4's deprecation is sequenced, not immediate**, honoring Level 2 (Production Stability) and
  Level 3 (Backward Compatibility) of both repos' Engineering Decision Order: no capability may
  be removed before its replacement is actually reachable by its consumers.
- **A8 is excluded on evidentiary grounds consistent with how Stage 4 already treats A7**:
  "consumer count is evidence for a decision, not a substitute for one" cuts both ways — A1's
  high count is evidence *for* it, and A8's zero count is evidence *against* its candidacy
  today, independent of code quality.

---

## Alternatives Considered

1. **Make A8 (`lib/governance`) canonical, migrate everything else to it.** Rejected for this
   stage: it would require building integration into a Cloudflare Workers production
   environment (intel-platform) from a currently-standalone Node/TypeScript library with no
   deployment path, a materially larger and riskier undertaking than extending an
   already-deployed, already-consumed function, and there is no evidence anyone currently
   intends to deploy it. Revisit only if a future ADR decides to operationalize `lib/`.
2. **Introduce a brand-new canonical confidence object from scratch** (the Part D draft shape
   in `CONFIDENCE_FRAMEWORK_DISCOVERY.md`). Rejected: violates Reuse Before Build (Principle 4,
   both repos) when A1 already satisfies the great majority of the same requirements with a
   live consumer base; three of the draft's ten proposed dimensions (Collection, Campaign,
   Forecast) have no existing owner anywhere and would be new capability, not consolidation —
   out of scope for an ownership decision.
3. **Leave the fragmentation as-is, document but don't decide (repeat every prior stage's
   posture).** Rejected: this task's explicit charter is to convert discovery into decisions;
   repeating "not now" a fifth time was assessed as itself the higher-risk path given the
   concrete three-signals-disagreeing example already in production.
4. **Make A2 (P20) canonical instead of A1.** Rejected: A2's actual consumer base is narrower
   (feeds only `computeP20QualityScore`), it measures a narrower concept (source type, not
   item-composite trust), and CI evidence shows it is rarely populated in practice (`p38`
   certification gate G19, "Evidence Chain Coverage >= 80%," currently at 0% on the live feed)
   — canonicalizing around a field that is mostly absent from live data was assessed as
   introducing more risk than it resolves.

---

## Migration Strategy

See `TITAN_MIGRATION_ROADMAP.md` Phase 1–3 for the sequenced, dated plan. Summary:

1. **Phase 1 (low risk, additive):** Add a `sourceReliabilityDimension` to A1 that reads
   `item.evidence_chain.reliability_code` when present, defaulting to today's behavior when
   absent (zero behavior change for the ~0% of live items where `evidence_chain` is populated
   today; forward-compatible for when Evidence Chain coverage improves). No existing dimension
   removed, no existing consumer's response shape changes except an additive field.
2. **Phase 2 (documentation + consumer signal):** Mark A4 `@deprecated` in code comment and in
   blog-side documentation, pointing at A1 as the eventual replacement, per both repos'
   Deprecation Instead of Deletion policy. No behavior change.
3. **Phase 3 (gated on Evidence API, EPIC 6):** Once the blog can consume intel-platform
   confidence via API, migrate the commercial-tier gate from A4 to the consumed A1 value.
   Remove A4 only after a documented migration period with zero remaining internal callers.

---

## Compatibility Impact

- **No existing API response shape changes** in Phase 1 — the new dimension is additive to
  A1's `dims[]` array, which all 13 consumers already iterate generically.
- **No existing route, schema, or CI gate is removed or renamed.**
- **A3 is untouched** — zero compatibility impact, by design.
- **A4's eventual removal is the only breaking change in this plan**, and it is explicitly
  sequenced behind a replacement being reachable, per the Migration Strategy above.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A1's new dimension double-counts source quality already partially captured elsewhere in its 12 dimensions | Medium | Low–Medium (score drift, not breakage) | Reweight during Phase 1 implementation with before/after score comparison on the live feed; documented in the Phase 1 PR, not silently absorbed |
| Blog stakeholders read A4's deprecation as blog losing autonomy over its own commercial gate | Low | Medium (organizational, not technical) | Migration is explicitly gated on the blog consuming, not being force-fed, and A4 stays live until that's true |
| `lib/` initiative owner (if one still exists) objects to A8's exclusion | Low | Low | This ADR does not alter or supersede blog ADR-0002; exclusion is scoped to "not canonical today," not "wrong" |

---

## Rollback Strategy

Phase 1's addition to A1 is a single additive field behind no flag requirement (default-off
behavior when `evidence_chain` is absent, which is ~100% of current live items) — rollback is
a revert of that one commit. Phase 2 is a comment/doc change — trivially revertible. Phase 3
is not authorized to begin until its prerequisite (Evidence API) exists and has its own
rollback plan defined at that time.

---

## Future Considerations

- `_computeConfidenceGraph()` (`p29-handlers.js:155`, DEBT-012) partially duplicates this
  decision's intent — 2 of its 7 dimensions already delegate correctly to canonical engines,
  but its Source/Detection/IOC/Attribution/Executive dimensions were independently invented.
  A future pass should evaluate replacing each of those five with a read from the equivalent
  existing A1 dimension (P25 already has "IOC Operational Quality" and "MITRE ATT&CK Coverage,"
  plausible replacements for two of the five) rather than assuming all five are genuinely novel
  — not resolved here because it requires dimension-by-dimension comparison this ADR did not do.
- If `lib/`'s A8 is ever operationalized, its 5-component shape (particularly
  `independentCorroboration` as a named, separately-weighted dimension) is a stronger,
  more explicit treatment of multi-source corroboration than A1 currently has and should be
  evaluated as a future enhancement to A1's dimension set on its own merits — independent of
  A8's own disposition.
- A3's "should be informed by A1" relationship is currently a documentation-level expectation,
  not a system integration. A future stage could explore surfacing A1's score to analysts at
  draft time as a decision aid, without removing analyst authorship.
- The A–F (A2) vs. A–E (A18, per ADR-0009) letter-scale mismatch is out of this ADR's scope
  and is resolved in ADR-0009.

---

## Revision — 2026-08-05, Stage 7

**A10 (new): `api/v1/intelligence/confidence.js` + `api/_lib/confidence-exposure.js` /
`confidence-scorer.js` — blog repository, very likely live** (see
`TITAN_STAGE7_VALIDATION.md` §2A for full evidence; confidence in "live" is high but not
independently confirmed via traffic/dashboard access). Verified by reading the route's own
header documentation: scores the same class of object (CVEs, threat articles) this ADR already
governs, 5-dimension multidimensional score (source_reliability, evidence_quality,
analyst_assessment, temporal_relevance, corroboration — different dimension names than A1's 12
but substantial conceptual overlap), with a `governance` block (status/version/reviewed_by)
suggesting a live publication-workflow system this ADR's discovery never catalogued either.

**This is a materially different situation than A8 or A9.** A8 (`lib/governance`) and A9
(P18's `computeTransparentConfidence`) were excluded from canonical candidacy on zero-consumer
grounds — a fact, not a judgment call. A10 does not have zero consumers; if the "very likely
live" assessment holds, it has a real, customer-facing, documented consumer this ADR's original
Decision never weighed. **This ADR's Decision (A1/P25 as canonical) is not withdrawn, but it
is no longer complete** — a canonical-confidence decision that doesn't account for the
platform's actual customer-facing confidence API is not the decision Stage 6 believed it was
making.

**What this means for approval:** This ADR should **not** be Accepted as originally written.
Before it can be, one of the following must happen, and is out of this stage's authority to
decide unilaterally:
1. Confirm A10 is *not* actually live (contradicts the routing-convention evidence above), in
   which case the original Decision stands unmodified; or
2. If A10 is live, the Decision must be extended to address it explicitly — either designating
   A10 the canonical confidence API for blog-domain customer-facing responses specifically
   (a Compatibility Adapter relationship to A1, mirroring how A3 was already treated) while A1
   remains canonical for the P-layer stack's internal composite score, or reopening the
   canonical-owner question entirely if A10's live customer traffic outweighs A1's internal
   consumer count. **This stage does not make that call** — it is exactly the kind of decision
   point this program's own rules require surfacing to a human rather than resolving by
   assumption, and it is now the single most consequential open question this ADR set has
   produced.

Reviewers evaluating this ADR's Approval checklist below should treat A10 as a blocking
open item, not a footnote.

---

## Approval

This ADR is **Proposed**, not Accepted. Per this program's own instruction ("if architectural
decisions require human approval, stop at the ADR stage and clearly identify the decision
points rather than making assumptions"), the following sign-offs are required before any
Migration Strategy phase begins:

- [ ] Platform Governance Lead
- [ ] Chief Threat Intelligence Architect / P-layer stack owner
- [ ] Blog/EIOS engineering owner (for the A3 relationship and A4 deprecation timeline)
- [ ] Owner of the `lib/governance` initiative, if one is designated (for A8's exclusion to be
      acknowledged, not merely asserted)

No code implementing this decision exists yet. `TITAN_STAGE7_PLAN.md` treats Phase 1 above as
a candidate Stage 7 deliverable, contingent on this ADR's approval.
