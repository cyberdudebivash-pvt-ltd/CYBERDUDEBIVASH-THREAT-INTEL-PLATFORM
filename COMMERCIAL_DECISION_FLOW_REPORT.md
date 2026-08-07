# Commercial Decision Flow Report

**Program:** Project TITAN Stage 20A — Enterprise Commercial Quality Orchestrator (Implementation)
**Date:** 2026-08-07

---

## 1. The Approved Flow

Per the Stage 20A implementation directive and
`COMMERCIAL_QUALITY_ORCHESTRATOR_ARCHITECTURE.md`:

```
Existing engines (P20/P21/P25/P26/P29/P35/P36/P37,
commercial_readiness_governor.py, dossier_quality_engine.py)
        │  (read-only; never invoked to mutate, never re-derived)
        ▼
Commercial Quality Orchestrator      buildCommercialQualityView / build_commercial_quality_view
        │
        ▼
Applicability Engine                 computeCommercialApplicability / compute_commercial_applicability
        │
        ▼
Commercial Readiness Summary         buildCommercialReadinessSummary / build_commercial_readiness_summary
        │
        ▼
Commercial Certification Recommendation   buildCommercialRecommendationLayer / build_commercial_recommendation_layer
        │
        ▼
Publication Recommendation           buildCommercialPublicationDecision + buildCommercialReleaseDecision
                                      (build_commercial_publication_decision + build_commercial_release_decision)
```

Every arrow is a **read**, never a write into an upstream engine, and every
step's output is a superset that carries the previous step's data forward —
nothing is discarded, and every claim is traceable to a cited source
(`inputs_cited[]`/`explainability_trace`).

---

## 2. Worked End-to-End Trace (real repository data)

Using a synthetic-but-representative "rich" item (identical fixture in both
test suites) so the trace below is exact and reproducible via
`node --test workers/intel-gateway/src/__tests__/p39-handlers.test.js` and
`pytest tests/test_commercial_quality_orchestrator.py`:

**Step 1 — Existing engines (read-only):**
`computeP20QualityScore(item)` → `{ total: <p20 score> }`
`getP21CertificationLevel(p20.total)` → `{ id: <tier> }`
`computeEnterpriseTrustScore(item)` → `{ tier: 'ANALYST VALIDATED', pct: <n> }`
`computeP26Grade(item)` → `{ grade: 'C', composite: 62, gradeLabel: 'ENTERPRISE READY' }`
(real values from this session's smoke run against the fixture in §3 of
`COMMERCIAL_APPLICABILITY_REPORT.md`)

**Step 2 — Commercial Quality Orchestrator:**
`buildCommercialQualityView(item, {})` composes the above into `inputs_cited`
(4 entries, each naming its source engine verbatim), runs the Applicability
Engine, and computes `applicability_adjusted_composite`.

**Step 3 — Applicability Engine:**
`{ applicable: 5, not_applicable: 0, unknown: 6, passed: 5, failed: 0 }` →
`applicability_adjusted_composite = 100`.

**Step 4 — Commercial Readiness Summary:**
`{ applicable_gates: 5, non_applicable_gates: 0, unknown_gates: 6,
zero_applicable_failures: true, missing_evidence: [6 detection formats] }`.

**Step 5 — Commercial Certification Recommendation:**
`buildCommercialRecommendationLayer(view)` → composite 100 + zero applicable
failures → `tier: 'PREMIUM_INTELLIGENCE'`, explicitly `presentation_only: true`.

**Step 6 — Publication Recommendation:**
`buildCommercialPublicationDecision(item, view, {})` → no
`publication_decision` field on this synthetic item →
`status: 'UNKNOWN — not supplied for this request; never fabricated'` (proves
the flow does not invent a publication verdict it cannot source). When the
item's own `publication_decision` field is set (e.g. by
`commercial_readiness_governor.py` upstream), it is cited verbatim instead —
covered by `p39-handlers.test.js`'s
`"cites the item's own publication_decision field verbatim when present"`.
`buildCommercialReleaseDecision(view, publication)` packages steps 3–6 into
one object.

---

## 3. Where the Flow Deliberately Stops

- **Disagreement is surfaced, never arbitrated.** If P26 says grade C/62
  ("ENTERPRISE READY" label) while the Applicability Model's composite is
  100, `agreement_summary.positive_signals` lists exactly which of the
  systems agree (`['P26', 'Applicability Model']` in the worked example,
  `2` out of `4` evaluated) — the orchestrator does not pick a winner or
  average them into a new number.
- **Publication is never decided here.** `commercial_readiness_governor.py`'s
  `enforce_publication_decision()` remains the sole owner of BLOCK/QUARANTINE/
  PUBLISH; this flow's "Publication Recommendation" step is a citation
  surface, not a second vote (architecture doc §3).
- **The 5-tier ladder is a 9th, explicitly-labeled presentation layer**, never
  presented as replacing P20/P21/P25/P26/P36/P37's own 8+ existing tier
  systems (architecture doc §7 / governance audit §4.5's central finding).

---

## 4. Outputs Produced, Mapped to the Required Deliverable List

| Required output | Produced by |
|---|---|
| Commercial Quality Summary | `buildCommercialQualityView` / `build_commercial_quality_view` |
| Commercial Readiness Summary | `buildCommercialReadinessSummary` / `build_commercial_readiness_summary` |
| Applicable Gates | `readiness.applicable_gates` / `readiness["applicable_gates"]` |
| Non-Applicable Gates | `readiness.non_applicable_gates` / `readiness["non_applicable_gates"]` |
| Missing Evidence | `readiness.missing_evidence` / `readiness["missing_evidence"]` |
| Commercial Risks | Surfaced via `failed_applicable_gates` + `agreement_summary` disagreement flags |
| Publication Recommendation | `buildCommercialPublicationDecision` + `buildCommercialReleaseDecision` |
| Executive Explanation | `buildCommercialExplanation` / `build_commercial_explanation` |
