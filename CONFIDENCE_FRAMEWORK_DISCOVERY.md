# Canonical Confidence Framework — Phase 1 Discovery & Phase 2 Draft Design

Project TITAN Stage 4. Covers Phase 1 (Discovery) in full and a **draft, non-binding** Phase 2
(Canonical Model Design). Phase 3 (Ownership Decision / ADR) is explicitly out of scope for this
document — Stage 4 itself says "do not silently merge conflicting systems," and three prior
Project TITAN stages independently reached the same conclusion each time they touched this
territory. This document ends at the decision point, not past it.

Companion reading: `ARCHITECTURE_DECISIONS.md` (this repo's established ADR home — "records
decisions already made, not a proposal list") and `platform/open-issues.md` Issue 15 in
`cyberdudebivash-blog` (first flagged this exact fragmentation).

---

## Scope and method

A repo-wide search for confidence-computing code (`function.*[Cc]onfidence`, `def.*confidence`,
`_confidence\s*=`) returns **116 files** in this repo's `workers/`, `agent/`, and `scripts/`
directories, plus 2 in the blog repo's `engine/sentinel_engine/`. Cataloguing all 118 individually
is not the right unit of work for a canonical framework decision — most are call sites or
one-off internal variables, not independent confidence *systems*. This document instead
inventories the systems with real external consumers (API routes, CI gates, rendered reports, or
their own documented methodology), and separately quantifies the long tail so the true scope
isn't understated.

**Every entry below was verified by reading the actual function body or config**, not inferred
from a name or docstring — consistent with this repo's own "governance documentation being wrong
is worse than stale" standard (Issue 15).

---

## Part A — Comparison Matrix: systems with real external consumers

### A1. `computeEnterpriseTrustScore()` — P25, this repo

| Field | Value |
|---|---|
| Owner / Repository | `workers/intel-gateway/src/p25-handlers.js`, this repo |
| Purpose | Composite 0–100 "trust score" for a single intelligence item, with a named, explained per-dimension breakdown |
| Inputs | `item.source_quality`, `item.enrichment_score`, `cvss_score`/`risk_score`, `kev_present`/`active_exploit`/`zero_day`, `epss_score`, `ioc_count`, `ttp_count`, `cve`, `stix_bundle`, `sources_reporting`, `confidence` (pipeline-declared), `report_url` |
| Outputs | `{ dims[12], totalEarned, totalMax, pct, tier, tierColor }` — 12 named dimensions (Source Authenticity, Enrichment Completeness, Severity Accuracy, Exploitation Verification, EPSS Probability Score, IOC Operational Quality, MITRE ATT&CK Coverage, CVE Reference Integrity, STIX 2.1 Interoperability, Multi-Source Consensus, Pipeline Confidence, Enterprise Report Access), each with `earned`/`max`/`rationale` |
| **Consumers** | **Imported directly by 12 files**: `p26`, `p27`, `p29`, `p30`, `p31`, `p32`, `p33`, `p35`, `p36`, `p37`, `p38`-handlers.js, and `scripts/p26_intelligence_excellence.py` — the single most-consumed confidence-shaped function in the P-layer stack |
| Dependencies | None (pure function of `item`) |
| CI usage | Indirectly, via P38 certification (`p38_production_certification.py` G14 "P25 Trust Gate: 0 Blockers") |
| Runtime usage | `/api/v1/p25/trust-score`, embedded in P32.7, P32.13, P38's confidence-audit and IQ Index |
| Public exposure | Yes — `/api/v1/p25/trust-score`, `/api/v1/p38/confidence-audit`, `/api/v1/p38/iq-index` |
| Serialization | Ad hoc JS object, not versioned, not schema-registered (P38's `SCHEMA_REGISTRY` documents *fields that carry a value*, like `confidence`, but not this function's *output shape*) |

### A2. `evidence_chain.reliability_code` — P20, this repo

| Field | Value |
|---|---|
| Owner / Repository | `workers/intel-gateway/src/p20-handlers.js`, this repo |
| Purpose | Source-reliability grade for a single piece of evidence, using an A–F scale that reads as NATO/Admiralty-System-style (an external convention, not CDB-invented) |
| Inputs | `item.evidence_chain.reliability_code` (upstream-populated; this layer does not compute the letter grade itself, it consumes and scores it) |
| Outputs | `{A:25, B:22, C:18, D:12, E:6, F:0}` points (feeds `computeP20QualityScore`'s 100-pt total), plus a rendered block with `source_reliability`, `source_category`, `chain_of_custody[]`, `known_limitations[]`, `iq_breakdown` |
| Consumers | `computeP20QualityScore` (used by P32.8 maturity, P38 IQ Index); rendered directly via `buildEvidenceChainBlock` |
| Dependencies | None |
| CI usage | `p38_production_certification.py` G19 "Evidence Chain Coverage >= 80%" (currently 0% on the live feed — `evidence_chain` is rarely populated in practice) |
| Runtime usage | Embedded HTML block, no dedicated API route found |
| Public exposure | Indirect (embedded in report HTML) |
| Serialization | Ad hoc, undocumented shape |
| **Note** | **Not currently read by `computeEnterpriseTrustScore` (A1) at all** — P20's reliability grade and P25's trust score are computed from disjoint input fields. A source graded "F" by P20 does not lower the P25 trust score unless the same weakness happens to also show up in P25's own `source_quality` field independently. |

### A3. EIOS Layer 7, Mechanism 1 — analyst-declared prose, `cyberdudebivash-blog`

| Field | Value |
|---|---|
| Owner / Repository | `Sentinel-APEX/eios/layer-07-confidence-model.md`, blog repo |
| Purpose | Human-judgment confidence rating an analyst assigns per claim while drafting a report |
| Inputs | Analyst judgment (not machine-computed) |
| Outputs | 7 named dimensions — Source, Evidence, Technical, Attribution, Detection, Operational, Business Impact Confidence — each rated `VERY LOW`/`LOW`/`MEDIUM`/`HIGH`/`VERY HIGH` with a required stated rationale |
| Consumers | Human readers of published reports; loosely gated by `quality.py::_gate_confidence` (checks a confidence tag exists, not which dimension) |
| Dependencies | None (this is a prose convention, not code) |
| CI usage | `quality.py::_gate_confidence` blocks publication if hedge language (`LIKELY`, `UNCONFIRMED`, etc.) appears without *some* `(LOW\|MEDIUM\|HIGH CONFIDENCE)` tag — dimension-name-agnostic |
| Runtime usage | None — this is authored text, not a runtime value |
| Public exposure | Yes — this is literally what readers of `blog.cyberdudebivash.in` reports see |
| Serialization | None — free text with a controlled vocabulary, not a data object |
| **Note** | Already documented as v2, explicitly superseding a v1 8-dimension list (Source/Collection/Attribution/Detection/IOC/Exploit/Business Impact/Overall). This system has been revised in place once already, using exactly the deprecate-don't-silently-replace pattern this stage's Phase 3 asks for. |

### A4. `scoring.py::_analyst_confidence()` — EIOS Layer 7, Mechanism 2, `cyberdudebivash-blog`

| Field | Value |
|---|---|
| Owner / Repository | `Sentinel-APEX/engine/sentinel_engine/scoring.py`, blog repo |
| Purpose | Deterministic 0–100 cross-check computed from the same report's own structured evidence, independent of what the analyst declared in prose (A3) |
| Inputs | Extracted `TechniqueMapping` confidence average, CVE enrichment success, source URL+name attribution strength |
| Outputs | Single 0–100 score, one of 9 dimensions feeding `scoring.py::score()`'s overall commercial-readiness composite |
| Consumers | `score()`'s commercial-tier gate (Layer 10) |
| Dependencies | `TechniqueMapping`, `CVEEnrichment` (blog's `models.py`) |
| CI usage | `test_scoring.py::test_scoring_is_deterministic` |
| Runtime usage | Commercial packaging brief generation |
| Public exposure | Indirect (feeds a pass/fail commercial gate, not directly rendered) |
| Serialization | Python function return value, no schema |

### A5. `quality.py::_gate_confidence` — publication gate, `cyberdudebivash-blog`

Not a confidence *scorer* — a **validator** that a confidence tag is present wherever hedge
language appears. Listed because Stage 4's Phase 6 ("CI should reject invalid confidence
objects") already has a working precedent here, just scoped to prose, not structured objects.

### A6. `severity` enum — `report_parser.SEVERITIES`, `cyberdudebivash-blog`

Adjacent, not itself a confidence dimension, but worth noting: `CRITICAL|HIGH|MEDIUM|LOW`,
already documented and enforced (fixed in `Sentinel-APEX/eios/sentinel-intelligence-standard.md`
§1 during this program's Stage 1). A future canonical confidence object should not re-invent a
parallel severity scale.

### A7. The `ai_confidence` sub-fragmentation (this repo)

Distinct from A1–A6: not one system, but **at least 8 independently-computed or independently-
defaulted sites**, found by direct grep, each disagreeing on what an unknown item's default
`ai_confidence` should be:

| Site | Default / behavior when unknown |
|---|---|
| `p25-handlers.js:164` | No default — reads `confScore`, a pre-computed input |
| `index.js:1443` | Hardcoded `81` |
| `revenue-enforcement.js:828` | `item.confidence * 100`, else `50` |
| `agent/sentinel_ai_engine.py` | Computed via `_compute_ai_risk_score`, no single default |
| `agent/explainable_confidence_engine.py:569` | `advisory.get("ai_confidence") or advisory.get("confidence") or 30.0` |
| `agent/apex_intelligence_upgrade.py:1580` | `item.get("ai_confidence") or item.get("confidence") or 21.3` |
| `agent/ai_learning_engine.py:638` | `(ai_record or {}).get("ai_confidence") or 0.50` |
| `agent/v30_apex/apex_marketing_matrix.py` | Reads an externally-supplied `confidence` var, no default shown |

Four different fallback defaults (81, 50, 30.0, 21.3, 0.50) for what is nominally the same field
name. **This is the single clearest concrete argument for Stage 4's existence** — not the five
well-structured systems above, which mostly *coexist* reasonably, but this kind of silent,
undocumented disagreement about what "AI confidence" means when data is missing.

---

## Part B — What Phase 1's search did *not* individually catalog

`correlation_confidence` (bucketed LOW/MED/HIGH in `agent/scoring/scoring_engine.py`;
threshold-only in `agent/v26/config_v26.py`), `campaign_confidence` (`agent/export_stix.py`,
`agent/ai_learning_engine.py`, `agent/graph_operations_engine.py`), and roughly 100 further files
with a `confidence`-shaped local variable or field read. None of these were found to have their
own documented methodology, dedicated API route, or CI gate — they read or locally derive a
confidence value for a single internal purpose. They are candidates to *consume* a canonical
object once one exists, not candidates to *be* canonical themselves. A full line-by-line audit of
all ~118 sites is future work, not a blocker to Phase 2/3.

---

## Part C — Preliminary overlap analysis (informative, not a decision)

- **Unique, not overlapping — likely survive as-is or as adapters:**
  - A3 (analyst prose) — fundamentally human-authored judgment for a Markdown article; no
    machine object replaces the act of an analyst rating their own claim.
  - A2's reliability-code *concept* (source-type trustworthiness, A–F) — genuinely different
    from A1's item-level composite; measures the *source*, not *this specific item's* evidence
    strength. A2 and A1 currently don't reference each other at all (Part A2's note) — that's the
    overlap that actually needs resolving: not "which one wins" but "should A1 read A2's grade
    as one of its dimensions instead of re-deriving source quality independently."
- **Overlapping, real duplication:**
  - A1 vs. A4: both compute a deterministic 0–100 "how much do we actually trust this
    evidence" score, in two different repos, from mostly-disjoint inputs, for mostly-disjoint
    consumers (P-layer stack vs. blog commercial gate). Once the blog consumes the intel
    platform's API (established direction, Stage 2), A4 is the clearer deprecation candidate —
    but only once that API integration actually exists; deprecating it first would leave the blog
    with no confidence signal at all.
  - A7: not overlapping with A1–A6 conceptually, but overlapping *with itself* eight times over.
    Highest-priority, lowest-risk consolidation target — no existing consumer depends on any
    *specific* one of the four disagreeing defaults being correct, since they already disagree.

---

## Part D — DRAFT Phase 2: proposed canonical confidence object (non-binding)

Sourced from A1's already-tested 12-dimension shape (the most-consumed existing system) plus
A2's reliability-code concept and A3's 7-dimension prose naming, reconciled rather than
reinvented. **Not adopted — a starting point for the Phase 3 conversation.**

```
CanonicalConfidence {
  version: "1.0-draft",
  overall: { value: 0-100, tier: string },        // ~= A1.pct / A1.tier
  dimensions: {
    source:      { value: 0-100, rationale: string },  // reconciles A2 reliability_code + A1's Source Authenticity
    evidence:    { value: 0-100, rationale: string },  // ~= A3's Evidence Confidence
    collection:  { value: 0-100, rationale: string },  // new -- no direct existing owner found
    correlation: { value: 0-100, rationale: string },  // currently only bucketed LOW/MED/HIGH anywhere (Part B)
    attribution: { value: 0-100, rationale: string },  // ~= A1's Multi-Source Consensus + A3's Attribution Confidence
    campaign:    { value: 0-100, rationale: string },  // currently only in Python STIX export (Part B), not scored
    detection:   { value: 0-100, rationale: string },  // ~= A3's Detection Confidence; A1 has no direct equivalent
    forecast:    { value: 0-100, rationale: string },  // no existing owner found anywhere in either repo
    analyst:     { value: 0-100, rationale: string },  // ~= A3 (prose) + A4 (machine cross-check) -- two sources, unreconciled
    ai:          { value: 0-100, rationale: string },  // ~= A7, currently 8 disagreeing implementations
  },
  provenance: { computed_by: string, computed_at: timestamp, source_system: "P25" | "EIOS-L7" | ... },
}
```

Three of ten suggested dimensions (Collection, Campaign, Forecast) have **no existing owning
implementation** in either repo today — these would be new capability, not consolidation, and
should be scoped separately from the reconciliation work.

---

## What this document deliberately does not do

- Does not pick a canonical owner (Phase 3).
- Does not write an ADR (Phase 3 explicitly asks for one once ownership is decided).
- Does not touch any compatibility layer, shared library, CI validation, report, or API code
  (Phases 4–8).
- Does not treat A1 as "obviously correct" merely because it has the most consumers — consumer
  count is evidence for a decision, not a substitute for one.
