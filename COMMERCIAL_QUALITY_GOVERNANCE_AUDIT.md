# Commercial Quality Governance Audit

## Phases A, C, D, E — Repository-Wide Quality/Trust/Confidence/Certification Ownership Audit

**Program:** Architecture Governance (originally requested as "Project TITAN Stage 20")
**Date:** 2026-08-07
**Status:** Audit and design only. **No production code was modified, deprecated, or deleted to
produce this document.** No implementation has begun.
**Companion document:** `COMMERCIAL_QUALITY_ORCHESTRATOR_ARCHITECTURE.md` (Phase B — design-only
architecture for a composing orchestrator; read after this document)

---

## 0. Executive Summary

### 0.1 Naming — why this is not `TITAN_STAGE20_*.md`

The TITAN product lineage (`evidence-registry/` → `intelligence-platform/` → `enterprise-gateway/`
/ `knowledge-platform/` → `product-platform/`) already reserves the label **"Stage 20"** for a
different, specific scope: *"versioned enterprise APIs, customer authentication/authorization,
tenant isolation, API keys, usage metering, subscription enforcement, partner SDKs"* —
`product-platform/README.md` and `TITAN_STAGE19_PRODUCT_PLATFORM_REPORT.md` both cite this
verbatim and mark it **"Stage 20 Preview (DO NOT IMPLEMENT)."** This governance work is a
different program entirely (platform-wide — the P16-P38 Cloudflare Worker handler stack, the
Python `scripts/`/`agent/`/`core/` pipeline, and the TITAN JS lineage's own quality layers), so
naming it "TITAN Stage 20" would collide with an already-reserved, already-documented number for
unrelated future work. **This is flagged for an executive naming decision in §8, not resolved
unilaterally.** Every document produced this session uses **"Commercial Quality Governance"**
instead of a stage number.

### 0.2 Headline findings

1. **Extensive pre-existing fragmentation, confirmed by direct evidence, not assumption.** At
   least **30 independently-built implementations** compute a quality score, trust score,
   confidence score, or certification/publication tier somewhere in this repository — roughly
   evenly split between the live JS P-layer handler stack (`workers/intel-gateway/src/p*.js`) and
   the Python pipeline (`scripts/`, `agent/`, `core/`). This was not previously catalogued in one
   place; `scripts/titan_architecture_governance_check.py`'s own advisory findings and
   `sentinel-blogger.yml`'s inline engineering notes independently confirm parts of this sprawl
   were already known and deliberately left unresolved pending a product decision — this audit is
   the first attempt to catalogue the *whole* picture.
2. **A relevant governance decision already exists and is unapproved.** `docs/adr/0007-canonical-
   confidence-framework.md` (Project TITAN Stage 6-8) catalogued 10 independent confidence-scoring
   systems in the JS lineage, designated `computeEnterpriseTrustScore()` (P25) canonical, and
   states **"No new independent scorer may be introduced"** and **"No implementation may begin
   against this decision until it is explicitly approved."** ADR-0007 is **Proposed, not
   Accepted**, and its own audit scope explicitly excludes the Python pipeline — so it does not
   govern most of what this audit found, but its unresolved status and its rule against new
   scorers apply directly to any new implementation this program might propose. See §8.
3. **Despite the scale of apparent overlap, very few pairs meet a strict "genuine duplicate" bar.**
   Applying the required test (same responsibility AND same consumers AND same outputs AND same
   lifecycle AND same production purpose) to every candidate this audit could obtain direct
   consumer evidence for, most "looks similar" pairs turn out to have different, non-overlapping
   consumers, different output artifacts, or different scopes (item-level vs. feed-level vs.
   platform-level) — i.e., they are **duplicated concepts, not duplicated systems**. See §4 for
   the full test-by-test reasoning; only one pair was confirmed to run redundantly against the
   same data in the same pipeline with unclear output differentiation.
4. **The closest existing canonical composer on the JS side is `computeP26Grade()`**
   (p26-handlers.js) — it already imports and weights P20/P21/P22/P23/P25 into one composite
   score, grade, tier ladder, and certification gate, exactly the shape of composition this
   program should extend rather than re-derive. On the Python side, no single script plays an
   equivalent unifying role; `commercial_readiness_governor.py` is the closest analog for
   *publication enforcement* but is explicitly an enforcement/sanitization layer that *consumes*
   scores computed elsewhere, not a scorer itself.
5. **A genuine, confirmed gap exists**: nowhere in the repository does "exclude unavailable
   intelligence from a score's denominator rather than penalize it as a failure" actually happen.
   The dominant existing pattern is the opposite (zero-contribution-with-an-N/A-comment). This is
   the one area this audit found with no prior art to compose from at all — see §7 (P36-DIM,
   applicability model).

### 0.3 What this document is and is not

This document, together with its architecture companion, is the **complete Phase A/C/D/E
deliverable set**: Commercial Quality Audit, Duplication Matrix, Runtime Consumer Matrix,
Ownership Matrix, Migration Candidates, Risk Matrix, and Executive Recommendation-per-implementation
(§0.1's naming note plus §8 stand in for a dedicated "Architecture Recommendation" section, which
otherwise duplicates the companion document's own opening section). **No implementation follows
this document.** Per explicit instruction, this program stops here for executive approval.

---

## 1. Audit Methodology and Scope

Three independent research passes, plus direct first-hand verification of the highest-stakes
findings before they were written down as conclusions:

1. **JS P-layer stack** (`workers/intel-gateway/src/p16-handlers.js` through `p38-handlers.js`,
   `index.js` routing) — every function computing a score, grade, or tier; every route exposing
   one; direct verbatim citation of every tier-label string found.
2. **Python pipeline** (`scripts/`, `agent/`, `core/`) — every function/class matching
   quality/trust/confidence/certification/readiness/publication-decision name patterns; full-text
   read of the two most consequential files (`commercial_readiness_governor.py`,
   `agent/dossier_quality_engine.py`); CI-workflow cross-reference for each.
3. **Detection coverage, evidence-source completeness, and executive-content generation** — where
   Sigma/YARA/KQL/SPL/Elastic/Suricata/Snort rules are actually generated; where (if anywhere)
   NVD/GHSA/CISA/EPSS/MITRE/vendor-advisory/release-notes/patch citation is tracked; where
   Executive Summary/Business Impact/Board Guidance/etc. content is generated.
4. **Direct verification** (this session, after the three passes above): for the four highest-
   stakes "possible duplicate" candidates the research surfaced, `grep`-confirmed the actual
   consumer set of each side of the pair (who imports/calls it, in which CI workflow), rather than
   relying on filename or docstring similarity alone. Results are in §4.

**Known incompleteness, stated rather than hidden:** the Python-side sweep surfaced roughly 100
raw name-pattern matches; approximately 30 of the most CI-relevant, best-evidenced ones received
full characterization in this document (§2). The remainder (mostly narrow sub-scorers — per-IOC,
per-TTP, per-attribution-claim confidence helpers with no CI wiring found) are named in §2.4 with
a lighter "insufficient evidence for a stronger disposition yet" treatment rather than asserted
conclusions this audit cannot actually support. This is a deliberate scoping choice, not an
oversight — see §2.4's own note.

---

## 2. Canonical Ownership Matrix

Ten dimensions requested (Owner, Purpose, Consumers, Runtime usage, Reachability, Production
status, Deprecation candidate, Migration risk, Business impact, Customer impact) are collapsed
into table columns where a column would otherwise repeat across every row in a subsection (e.g.
"Owner" is the subsection heading; "Deprecation candidate" and "Migration risk" are covered in §4
and §5 for the items where they're not simply "no"). Full per-item prose for the highest-stakes
entries follows each table.

### 2.1 JS P-Layer score/tier engines (`workers/intel-gateway/src/p*.js`)

**Owner:** Sentinel APEX Cloudflare Worker backend (live production, imported by `index.js`).
**Reachability:** All rows below are production-reachable — this is the live serving path.

| Engine | File:Lines | Purpose | Consumers | Output |
|---|---|---|---|---|
| `computeP20QualityScore(item)` | p20-handlers.js:105-174 | Per-item 8-component quality score | Internal input to P21/P22/P26/P27/P33/P35/P36/P37/P38 | `{total:0-100, breakdown{...}}` |
| `getPublicationStage(score)` / `PUB_STAGES` | p20-handlers.js:36-42,177-182 | Score→tier mapping | Imported by p21, p22, p33 | 5 tiers: PREMIUM_INTELLIGENCE(90)/ENTERPRISE_READY(72)/EVIDENCE_VERIFIED(55)/ANALYST_REVIEW(38)/DRAFT(0) |
| `getP21CertificationLevel(score)` / `CERT_LEVELS` | p21-handlers.js:31-40 | Score→tier mapping (2nd scheme) | `/api/v1/p21/certify` route | 4 tiers: PREMIUM_CERTIFIED(90)/ENTERPRISE_READY(75)/INTERNAL_DRAFT(38)/BELOW_MINIMUM(0) |
| `computeCertificationLevel()` | p19-handlers.js | Score→tier mapping (3rd scheme, 7 levels) | P19 SOC/executive views | PRODUCTION_CERTIFIED(92)/PREMIUM_INTELLIGENCE(85)/ENTERPRISE_READY(75)/ANALYST_VERIFIED(65)/EVIDENCE_VERIFIED(55)/INTERNAL_REVIEW(45)/DRAFT(0) |
| `computeEnterpriseTrustScore(item)` | p25-handlers.js:336-412 | 12-dimension trust score — **ADR-0007's designated canonical confidence scorer (A1)** | `/api/v1/p25/trust-score` route; composed by P26 | `{dims[12], pct:0-100, tier}`; tier: ENTERPRISE CERTIFIED(85)/ENTERPRISE READY(70)/ANALYST VALIDATED(50)/INTERNAL DRAFT(30)/BELOW THRESHOLD |
| `computeP26Grade(item)` | p26-handlers.js:89-161 | **Composite of P20+P21+P22+P23+P25** — closest existing canonical composer | `/api/v1/p26/grade` route; composed by P27/P33/P35/P36/P37/P38 | `{composite:0-100, grade:A-F, gradeLabel, certTier, certFlags}` |
| `buildP26TrustBadgesBlock(item)` | p26-handlers.js:294-386 | Badge labels incl. literal "Commercial Certified"/"Enterprise Ready" | HTML block in P26 report output | 8 badges |
| `_computeP36Scorecard()` / `_maturityLabel()` | p36-handlers.js:35-42,292-324 | Feed-wide maturity/excellence scorecard, reuses P26 | `/api/v1/p36/dashboard` | `tier`: WORLD_CLASS(90)/ENTERPRISE_READY(75)/MATURE(60)/BASIC(40)/DEVELOPING |
| `_computeCustomerValueScores()` | p36-handlers.js:184-250 | Per-feature customer-value score (35/30/20/15 weighted) | **`/api/v1/p36/customer-value`** — live route | `customer_value_score:0-100` |
| `handleP29CustomerValueAnalytics` | p29-handlers.js:692-752 | **A second, independent, differently-shaped "customer value" engine** | **`/api/v1/p29/customer-value`** — live route | platform-wide aggregate, hours-saved/risk-mitigated estimates |
| `_computeIQScore()` | p37-handlers.js:253-338 | 7-dim weighted score, reuses P26 | `/api/v1/p37/iq-score` | `iq_tier`: WORLD_CLASS(85)/ENTERPRISE_READY(70)/MATURE(55)/BASIC(40)/DEVELOPING — **same 5 label strings as P36's scorecard tier, different thresholds** |
| `_computeIQIndex()` | p38-handlers.js:113-152 | Reuses P20/P25/P26 directly | `/api/v1/p38/iq-index` | bare `iq_index:0-100`, no tier labels |
| `_evaluateAssuranceGates` | p34-handlers.js:74-324 | CI/platform release-gate status, NOT a per-item tier | `/api/v1/p34/{...}` | `release_tier: WORLDWIDE_RELEASE / BLOCKED` |
| `_computeScorecard()` (P35) | p35-handlers.js:255-297 | Feed-wide engineering scorecard | `/api/v1/p35/scorecard` | `release_readiness`: PRODUCTION_READY(80)/CONDITIONAL_RELEASE(65)/NEEDS_IMPROVEMENT — **its own, third, distinct vocabulary** |

**Every one of the five tier labels this program's own brief proposed ("Internal Draft," "Analyst
Review," "Enterprise Ready," "Commercial Certified," "Premium Intelligence") already exists
verbatim in this subsection alone** (p20:37-40, p21:32-34, p26:311/332, p25:408). See §4 for
whether any of these constitute genuine duplicates of each other.

### 2.2 Python certification gate chain (`scripts/p*_production_certification.py`, `p21/p24_*`)

**Owner:** CI/CD release-gating pipeline (`sentinel-blogger.yml`, `generate-and-sync.yml`).
**Reachability:** CI-wired and confirmed active — this is the pipeline that gates real releases.

| Engine | Purpose | Scope | Output | CI wiring (confirmed) |
|---|---|---|---|---|
| `scripts/p21_certification_gate.py` | Python port of JS P21's weights | Per-item | PREMIUM_CERTIFIED(90)/ENTERPRISE_READY(75)/INTERNAL_DRAFT(38)/BELOW_MINIMUM | `sentinel-blogger.yml:1756` |
| `scripts/p24_commercial_certification.py` | **Literally emits the label `COMMERCIAL_CERTIFIED`** at ≥90 | Whole-platform release gate (8 dims incl. P21/P22/P23 outputs, regression, security) | COMMERCIAL_CERTIFIED(90)/ENTERPRISE_READY(75)/INTERNAL_RELEASE(55)/RELEASE_BLOCKED | `sentinel-blogger.yml:1838` |
| `scripts/p27_production_certification.py` through `p32_production_certification.py` (6 files) | Chained per-P-layer gate, each references the previous stage's report | Whole-feed | Tier per file, `gNN_pXX_certification` chain pattern | Part of the certification chain (this repo's own CLAUDE.md documents `p33 → p32 → ... → p25`) |
| `scripts/p33_production_certification.py` | **Verified directly this session (used throughout Stages 17-19 as the mandatory pre-push gate)** | Whole-feed, G01-G26 gates | WORLDWIDE_RELEASE/CONTROLLED_RELEASE/BLOCKED | Required gate, this repo's CLAUDE.md |
| `scripts/commercial_readiness_governor.py` | **Enforcement/sanitization layer, NOT a scorer** — consumes `intelligence_grade`/`risk_score`/`attck_verification` as pre-existing input fields; 10 "Mandates": attribution nulling, ATT&CK clearing, risk floors, real-IOC counting, premium-content tiering by input grade, contract validation, publication BLOCK/QUARANTINE decision, tier-split feed generation, dashboard KPIs, feed-level GO-LIVE score (sum of 6 pass/fail booleans, 20/20/20/20/10/10) | Per-item enforcement + feed-level aggregate | `enforce_publication_decision()` → bool + quarantine record; feed-level `commercial_readiness_score:0-100` | `generate-and-sync.yml` STAGE 6.94 **and** 6.101 (runs twice per pipeline) |

### 2.3 Python trust/confidence/quality engines (`scripts/`, `agent/`, `core/`)

**Owner:** Fragmented — no single owning program; each appears independently authored.
**Reachability:** Mixed — see Runtime column; several are confirmed CI-wired, several appear
dormant (no consumer found by grep, which is a strong signal but not proof of non-existence for
dynamically-imported code).

| Engine | File | Purpose | Runtime status |
|---|---|---|---|
| `agent/dossier_quality_engine.py` | `DossierQualityEngine` | Per-advisory A-F grade: narrative quality (0.4) + confidence calibration (0.4) + IOC/TTP suppression cleanliness (0.2); **`is_publishable` hardcoded `True` always — explicitly informational, never gates publication** | **CI-wired** (`production-hardening-final.yml`) **and has a real runtime caller**: `agent/apex_engine.py:159-160,334-336` calls `process_advisory()` directly. This is one of only two Python engines confirmed both CI-wired and live-called |
| `agent/explainable_confidence_engine.py` | `ExplainableConfidenceEngine` | D1-D7 dimension confidence explainability | **CI-wired** (`enterprise-intel-quality.yml`) and **confirmed 6 real consumers**: `agent/apex_engine.py`, `agent/intelligence_reproducibility_engine.py`, `agent/apex_intelligence_upgrade.py`, `agent/enterprise_pipeline_orchestrator.py`, `scripts/ai_validation_runner.py` — the most widely-consumed confidence engine found in this audit |
| `scripts/explainable_confidence_engine.py` | same class name, verified-different 977-line implementation (contributor/penalty model, not D1-D7) | Same stated purpose as the `agent/` version | **Zero consumers found** by this session's direct grep verification (no import of `scripts.explainable_confidence_engine` or `scripts/explainable_confidence_engine.py` anywhere) — appears orphaned. See §4.1 |
| `scripts/intel_trust_governance.py` | `compute_trust_certificate(item)` | 7-dimension weighted composite trust, independent of P25/A1 | Not CI-wired directly; only consumer found is `scripts/ocios_coordinator.py`, which itself has no CI wiring found — **likely dormant** |
| `scripts/apex_sovereign_trust_orchestrator.py` | `ApexSovereignTrustOrchestrator` | Self-described "master governance brain" wiring **8 more independent "sovereign trust engines" (S1-S8)** | Not CI-wired; only reference found is as an inventory entry in `titan_architecture_governance_check.py` (not a caller) — **appears orphaned/dormant** |
| `agent/enterprise_trust_engine.py` | `EnterpriseTrustEngine`, `TrustScore`, `TrustDimension` | Another independent multi-dimension trust engine | Not directly CI-wired in this audit's search |
| `scripts/apex_confidence_engine.py` | `compute_confidence(item)` | Confidence scoring | **CI-wired** (`sentinel-blogger.yml`) with **5 additional script consumers** (`ai_validation_runner.py`, `detection_engineering_orchestrator.py`, `enterprise_intelligence_integrator.py`, `apex_intelligence_quality_gates.py`, `p38_shared_validators.py`) — broadly consumed |
| `scripts/enterprise_confidence_engine.py` | `compute_confidence(item)` (same signature) | Confidence scoring | **Exactly one consumer found**: `scripts/sentinel_quality_pipeline.py`. Not CI-wired directly in this audit's search |
| `scripts/source_trust_engine.py` | `compute_trust_score(domain, stats)` | Per-domain source trust | **CI-wired** (`enterprise-governance.yml`) + consumed by `scripts/run_pipeline.py` |
| `scripts/source_trust_scorer.py` | `SourceTrustScorer._compute_trust()` | Per-domain source trust (2nd implementation) | **Consumed by `agent/explainable_confidence_engine.py` itself** (the canonical, widely-used engine above) plus `scripts/enterprise_trust_infrastructure.py` — i.e. this is a real, live sub-component of the canonical confidence chain, not a rogue duplicate |
| `scripts/confidence_corroboration_engine.py` | `score_item_evidence()` | 17-signal weighted confidence | **CI-wired in 3 workflows** (`enterprise-governance.yml`, `generate-and-sync.yml` STAGE 6.102, `sentinel-blogger.yml`) | 
| `scripts/intelligence_grade_engine.py` (v1) | `assign_grade()` | Output-contract grading | **CI-wired, STAGE 6.93**, `generate-and-sync.yml:857` — confirmed actively invoked, not vestigial |
| `scripts/intelligence_grade_engine_v2.py` | `assign_grade_v2()`/`grade_item()` | Narrower "Grade B: CVSS≥8.0 + 2 sources + evidence-based ATT&CK" rule | **CI-wired, STAGE 6.100**, `generate-and-sync.yml:964` — **runs in the same workflow as v1, sequentially, both with `--apply` against the same `api/feed.json`, but writing to two different report files** (`data/health/intel_grade_engine_report.json` vs `data/governance/intelligence_grade_v2.json`). See §4.2 |

### 2.4 Long tail — named but not individually characterized in depth

The Python-side sweep additionally surfaced (non-exhaustive, ~15 more): `scripts/intel_quality_engine.py`
(`IntelQualityEnricher`, `FeedQualityBalancer`), `scripts/feed_quality_engine.py`
(`FeedQualityEngine.score_quality()`), `scripts/apex_intelligence_quality_gates.py`
(`QualityGateSystem`), `agent/ioc_quality_metrics_engine.py` (`IOCQualityMetricsEngine`),
`core/intelligence/ioc_confidence.py` (`IOCConfidenceEngine` singleton), `scripts/enterprise_governance_engine.py`
(its own `TrustScore` class, distinct from `agent/enterprise_trust_engine.py`'s), `scripts/sentinel_convergence_certifier.py`
(`compute_confidence()`, `certify()`), `scripts/business_readiness_certifier.py` (dimension-scored
business readiness), `scripts/commercial_saas_validator.py`, `scripts/commercial_readiness_auditor.py`
(a *second*, separate "commercial readiness" concept distinct from `commercial_readiness_governor.py`),
`scripts/production_health_check.py`'s `phase6_commercial_readiness()`, `scripts/p26_intelligence_excellence.py`'s
`_a11_commercial_readiness()` audit item.

**Why these did not receive full ownership-matrix treatment:** the research budget for this audit
prioritized depth (full-text reads, consumer verification) on the ~20 entries in §2.1-2.3 that are
either confirmed CI-wired, confirmed live-called, or directly relevant to the tier-vocabulary and
"commercial certification" question this program is actually about. The remainder are named here
so they are not silently omitted from the record, with a placeholder disposition of **"Retain —
insufficient evidence for a stronger disposition; recommend a dedicated follow-up audit before any
of these are touched, composed, or migrated."** Per this program's own standing rule, this
limitation is documented, not hidden.

---

## 3. Runtime Consumer Matrix

Consolidating the "who actually calls this" evidence gathered across §2 into one lookup, for the
items where a real consumer (not just a name match) was confirmed:

| Engine | Confirmed real consumer(s) | Evidence |
|---|---|---|
| `computeP26Grade` (JS) | p27/p33/p35/p36/p37/p38-handlers.js (imports), `/api/v1/p26/grade` route | Direct source read |
| `computeEnterpriseTrustScore` (JS) | `/api/v1/p25/trust-score` route; composed into P26 | Direct source read |
| `p21_certification_gate.py` | `sentinel-blogger.yml:1756` | Agent-verified workflow grep |
| `p24_commercial_certification.py` | `sentinel-blogger.yml:1838` | Agent-verified workflow grep |
| `p33_production_certification.py` | This repo's own CLAUDE.md mandatory pre-push gate; used by every TITAN stage 17-19 session this program is aware of | Direct, repeated, first-hand use |
| `commercial_readiness_governor.py` | `generate-and-sync.yml` STAGE 6.94 + 6.101 (CLI subprocess only — zero Python files `import` it) | Full-text read + workflow grep |
| `agent/dossier_quality_engine.py` | `production-hardening-final.yml` (CI) + `agent/apex_engine.py:159-160,334-336` (runtime import) | Full-text read + grep |
| `agent/explainable_confidence_engine.py` | `enterprise-intel-quality.yml` (CI) + `agent/apex_engine.py`, `agent/intelligence_reproducibility_engine.py`, `agent/apex_intelligence_upgrade.py`, `agent/enterprise_pipeline_orchestrator.py`, `scripts/ai_validation_runner.py` | This session's direct grep verification |
| `scripts/explainable_confidence_engine.py` | **None found** | This session's direct grep verification |
| `scripts/apex_confidence_engine.py` | `sentinel-blogger.yml` (CI) + 5 scripts | This session's direct grep verification |
| `scripts/enterprise_confidence_engine.py` | 1 script (`sentinel_quality_pipeline.py`) only | This session's direct grep verification |
| `scripts/source_trust_engine.py` | `enterprise-governance.yml` (CI) + `run_pipeline.py` | This session's direct grep verification |
| `scripts/source_trust_scorer.py` | `agent/explainable_confidence_engine.py` (i.e., feeds the canonical confidence chain) + `enterprise_trust_infrastructure.py` | This session's direct grep verification |
| `scripts/intelligence_grade_engine.py` (v1) | `generate-and-sync.yml:857`, STAGE 6.93 | This session's direct grep + workflow read |
| `scripts/intelligence_grade_engine_v2.py` | `generate-and-sync.yml:964`, STAGE 6.100 | This session's direct grep + workflow read |
| `scripts/apex_sovereign_trust_orchestrator.py` | Named only in `titan_architecture_governance_check.py`'s inventory (not called) | Agent-verified |
| `scripts/intel_trust_governance.py` | `scripts/ocios_coordinator.py` only (itself apparently uncalled) | Agent-verified |
| `evidence-registry/provenance-engine.js` (TITAN JS lineage) | **None in production** — confirmed not imported by `index.js`; only reachable from its own test suite | This program's own prior-session finding (Stage 19), independently re-confirmed by this audit's agent |

---

## 4. Duplication Matrix — strict 5-criteria test

**Test applied to every candidate pair below:** classified as a genuine duplicate ONLY if the
pair shares (a) responsibility, (b) consumers, (c) outputs, (d) lifecycle, and (e) production
purpose. A pair failing any one of the five is **not** classified as a duplicate, regardless of
how similar its name or general concept is.

### 4.1 `agent/explainable_confidence_engine.py` vs. `scripts/explainable_confidence_engine.py`

| Criterion | Result |
|---|---|
| Same responsibility (stated) | Yes — both claim confidence explainability |
| Same consumers | **No** — `agent/`'s version has 6 confirmed consumers incl. a live CI workflow; `scripts/`'s version has **zero** confirmed consumers |
| Same outputs | No — verified-different implementations (831 vs. 977 lines; D1-D7 dimension model vs. a contributor/penalty model) |
| Same lifecycle | No — one is actively maintained/called, the other shows no evidence of being touched by any live path |
| Same production purpose | N/A — one has no production purpose currently exercised |

**Verdict: NOT a genuine duplicate under the strict test — despite the identical class name and
stated purpose, they fail on consumers, outputs, and lifecycle.** `scripts/explainable_confidence_engine.py`
is better characterized as an **orphaned/dormant file** than as a duplicate of a canonical
implementation, since nothing currently depends on it. See §7 for disposition.

### 4.2 `scripts/intelligence_grade_engine.py` (v1) vs. `scripts/intelligence_grade_engine_v2.py`

| Criterion | Result |
|---|---|
| Same responsibility | Yes, broadly — both grade items from feed data |
| Same consumers | **Ambiguous-to-No** — both are invoked from the same workflow file, but as two separate, sequential CI steps (STAGE 6.93 and STAGE 6.100), not by any shared calling code |
| Same outputs | **No** — v1 writes `data/health/intel_grade_engine_report.json` with broad Output Contract fields; v2 writes a *different* file, `data/governance/intelligence_grade_v2.json`, implementing a narrower, explicitly-scoped rule ("Grade B: CVSS≥8.0 + 2 independent sources + evidence-based ATT&CK") |
| Same lifecycle | No — v2's narrower docstring suggests it was designed as an additional refinement pass, not a full v1 replacement, though this session cannot confirm original intent |
| Same production purpose | Partially — both mutate the same shared `api/feed.json` via `--apply` in the same pipeline run, which is the one piece of real evidence for overlap |

**Verdict: Confirmed active, redundant execution against the same input in the same pipeline, but
does NOT cleanly satisfy "same outputs" or "same consumers" under the strict test.** This is the
single strongest duplication *candidate* this audit found — flagged as a **Migration Candidate
requiring further investigation** (§5), not asserted as a confirmed duplicate, since the two
scripts' actual grading rules were not diffed line-by-line in this session.

### 4.3 `scripts/apex_confidence_engine.py` vs. `scripts/enterprise_confidence_engine.py`

| Criterion | Result |
|---|---|
| Same responsibility (stated) | Yes |
| Same consumers | **No** — `apex_confidence_engine.py` has 6 confirmed consumers incl. a live CI workflow; `enterprise_confidence_engine.py` has exactly 1 |
| Same outputs | Not verified (function signatures match; bodies not diffed) |
| Same lifecycle | No — vastly different adoption/consumer footprint suggests different maintenance trajectories |
| Same production purpose | No — one is broadly load-bearing, the other is narrowly scoped to a single downstream script |

**Verdict: NOT a genuine duplicate under the strict test.** `enterprise_confidence_engine.py` reads
as a narrower, single-purpose implementation for `sentinel_quality_pipeline.py` specifically, not
a competing general-purpose scorer.

### 4.4 `scripts/source_trust_engine.py` vs. `scripts/source_trust_scorer.py`

| Criterion | Result |
|---|---|
| Same responsibility | Yes, broadly (per-domain source trust) |
| Same consumers | **No** — completely disjoint consumer sets, and `source_trust_scorer.py` is itself a confirmed dependency *of* the canonical `agent/explainable_confidence_engine.py` |
| Same outputs | Not verified |
| Same lifecycle | No |
| Same production purpose | **No — `source_trust_scorer.py` is a live sub-component feeding the canonical confidence chain, not a competing top-level engine** |

**Verdict: NOT a duplicate. Different roles in the pipeline; `source_trust_scorer.py` should be
treated as infrastructure the canonical chain already depends on, not a migration target.**

### 4.5 Commercial-certification tier vocabularies (P20/P21/P25/P26/P36/P37 JS; p21/p24/p33/commercial_readiness_governor.py Python)

| Criterion | Result |
|---|---|
| Same responsibility (concept) | Yes — all map a score to a human-readable release/trust tier |
| Same consumers | **No** — each is scoped differently: P20/P21 are per-item publication-stage/certification-level (different routes); P25 is trust-specific; P26 is the cross-P-layer composite; P36/P37 are feed-wide maturity/IQ scorecards; P34/P35 are CI/platform release gates (not per-item at all); Python's p21_certification_gate.py is a direct *port* of JS P21 (same origin, different runtime, arguably the closest thing to a true duplicate pair in this whole set, but they run in different environments — JS Worker vs. Python CI — serving different real-time vs. batch purposes); p24/p33 are whole-platform/whole-feed gates, not per-item; `commercial_readiness_governor.py` is enforcement, not scoring |
| Same outputs | No — different score ranges, different label sets, different granularity (item vs. feed vs. platform) |
| Same lifecycle | No — independently versioned, independently CI-wired at different pipeline stages |
| Same production purpose | No — SOC-facing certification (P21), executive trust framing (P25/P26), platform engineering scorecards (P35/P36/P37), and release-blocking CI gates (P33/P34) are genuinely different consumers with genuinely different purposes, even though the English-language label they choose ("Enterprise Ready," etc.) frequently coincides |

**Verdict: This is the central finding of the whole audit — NOT genuine duplication under the
strict test, but severe, confirmed, real vocabulary fragmentation.** Eight-plus independent
schemes use overlapping label strings ("Enterprise Ready" alone is independently defined at 10
different code sites per the JS-audit agent) with different thresholds and different scopes. This
is exactly the failure mode the user's own instruction anticipated: *"Do not classify
implementations as duplicates merely because they calculate similar concepts."* None of these
should be deprecated or merged. **What they need is a composing layer that can explain, for any
given customer-facing "Enterprise Ready" claim, which of the 8+ underlying systems produced it and
why the others may disagree** — precisely the Explainability Flow specified in the companion
architecture document.

### 4.6 `agent/dossier_quality_engine.py` vs. `scripts/intel_trust_governance.py`

Both independently claim comprehensive/enterprise-wide scope and both independently implement a
fix for what the research agent identified as the same underlying data-quality bug (a confidence
floor and source-URL IOC pollution issue), in different files, with no shared code.

| Criterion | Result |
|---|---|
| Same responsibility (stated) | Yes, both claim comprehensive advisory-quality authority |
| Same consumers | **No** — `dossier_quality_engine.py` is CI-wired and live-called by `agent/apex_engine.py`; `intel_trust_governance.py`'s only found consumer (`ocios_coordinator.py`) appears itself dormant |
| Same outputs | No — A-F grade + narrative/confidence/IOC-cleanliness sub-scores vs. a 7-dimension CERTIFIED-CRITICAL/HIGH/STANDARD/BELOW-THRESHOLD composite |
| Same lifecycle | No |
| Same production purpose | No — one is live and explicitly informational (never gates publication); the other appears dormant |

**Verdict: NOT a genuine duplicate under the strict test** (fails consumers, outputs, lifecycle) —
but the fact that both independently re-solved the same specific data-quality bug is itself
evidence of the coordination gap this program exists to close, even without meeting the technical
bar for "duplicate."

---

## 5. Migration Candidates

Per the strict test in §4, exactly **one** item qualifies for this section — everything else in §4
was found to be overlapping-but-distinct, not a migration target:

| Candidate | Why flagged | Recommended next step | NOT recommended |
|---|---|---|---|
| `scripts/intelligence_grade_engine.py` (v1) vs. `_v2.py` | Both actively run in the same CI pipeline against the same shared `api/feed.json`, both with `--apply` (mutating), with unclear differentiation between v1's broad Output Contract role and v2's narrower CVSS/source/ATT&CK-specific role | A dedicated, narrowly-scoped follow-up investigation: line-by-line diff of what each actually changes on `api/feed.json`, confirmation of whether v2 was intended to fully supersede v1 or to layer a narrower refinement on top of it, before any consolidation decision is made | Do NOT merge, deprecate, or modify either script based on this audit alone — the evidence is suggestive, not conclusive |

`scripts/explainable_confidence_engine.py` (§4.1) is **not** listed here as a migration candidate
because there is nothing to migrate *from* it (zero confirmed consumers) — see §7 for its
recommended disposition (Archive, pending a repo-wide dynamic-import check this audit could not
perform).

---

## 6. Risk Matrix — current fragmented state

This assesses the risk of the *status quo* (the fragmentation this audit found), not of any
proposed change, since no change is proposed yet.

| Risk dimension | Assessment | Evidence |
|---|---|---|
| **Commercial/customer trust risk** | **Medium-High.** A customer or auditor asking "why is this piece of intelligence 'Enterprise Ready'?" could get 8+ different, non-cross-checked answers depending on which system's output they're shown, with no existing mechanism to reconcile them | §4.5 |
| **Governance risk** | **Medium.** ADR-0007 already documents this exact failure mode for the JS/confidence-scoring slice and remains unapproved; the Python-side fragmentation is worse in scale and has never been formally catalogued or governed at all until this audit | §0.2, §2.3 |
| **Engineering/maintenance risk** | **Medium.** At least one pair (v1/v2 grade engine) runs redundantly in production CI today with unclear differentiation; the two same-named `explainable_confidence_engine.py` files are a live example of the "same name, different code" failure mode this repo's own CLAUDE.md Principle 3 exists to prevent | §4.1, §4.2 |
| **Regression risk of doing nothing** | **Low in the short term.** Every engine catalogued here continues to run exactly as it does today; nothing in this audit requires or implies an urgent fix | — |
| **Regression risk of a naive "consolidate now" response** | **High.** Given how many pairs in §4 turned out NOT to be genuine duplicates on inspection, a rushed consolidation driven by surface-level name matching would very likely break real, distinct, independently-load-bearing production consumers (e.g. collapsing P25's trust score into P26's composite would remove the one ADR-0007-designated canonical scorer that P26 itself depends on) | §2.1, §4 |
| **Cost of continued non-action on the applicability gap** | **Medium, commercial-facing.** The confirmed absence of any "exclude unavailable intelligence" scoring pattern (§0.2 point 5) means every item lacking, e.g., MITRE mapping or EPSS today is scored as if it *failed* that dimension — a customer-visible quality-perception cost, not just an internal cleanliness issue | Python-audit agent's finding 4 |

---

## 7. Executive Recommendation per Implementation

One of the eight required dispositions (Retain / Compose / Deprecate Later / Archive /
Experimental / Internal Only / Commercial Only / Future Migration) for every implementation given
full treatment in §2.1-2.3. Nothing here is an instruction to act — these are recommendations for
the pending executive-approval decision.

| Implementation | Recommendation | Rationale |
|---|---|---|
| `computeP20QualityScore` (JS) | **Retain** | Foundational input to P21/P26/P33/P35-38; no evidence of a competing implementation at the same layer |
| `computeEnterpriseTrustScore` / P25 (JS) | **Retain — protect as ADR-0007's canonical A1** | Explicitly designated canonical by an existing (unapproved but unrebutted) ADR; must not be superseded informally |
| `computeP26Grade` (JS) | **Compose** | This is the strongest existing candidate for the orchestrator's primary JS-side input — see architecture companion |
| P36 `_computeCustomerValueScores` / P29 `handleP29CustomerValueAnalytics` | **Compose (both), do not merge** | Two customer-value engines with different shapes; the orchestrator should surface both explicitly rather than picking a winner without a product-owner decision |
| P34/P35 CI/platform release gates | **Internal Only** | These are platform-engineering release gates, not customer-facing commercial certification — keep the distinction explicit per §0.2's own warning against conflating them |
| `scripts/p33_production_certification.py` | **Retain** | Mandatory, load-bearing production gate; out of scope for any consolidation |
| `scripts/commercial_readiness_governor.py` | **Compose** | The closest Python-side analog to an orchestrator input for the *publication decision* axis specifically (it already owns that decision); should be a primary composed input, never re-implemented |
| `agent/dossier_quality_engine.py` | **Compose** | Live-called, CI-wired, explicitly informational (doesn't gate publication) — ideal composable input for a "narrative/IOC quality" signal |
| `agent/explainable_confidence_engine.py` | **Retain** | Most widely-consumed confidence engine found in this audit; do not touch |
| `scripts/explainable_confidence_engine.py` | **Archive (pending confirmation)** | Zero confirmed consumers; recommend a repo-wide dynamic-import/importlib check before physical archival, since static grep cannot fully rule out reflective imports |
| `scripts/intelligence_grade_engine.py` (v1) & `_v2.py` | **Future Migration** | Per §5, needs a dedicated diff-level investigation before any disposition stronger than "keep both running as-is" |
| `scripts/apex_confidence_engine.py` | **Retain** | Broadly consumed, CI-wired |
| `scripts/enterprise_confidence_engine.py` | **Internal Only / Experimental** | Single-consumer, narrow scope — not wrong, just not general-purpose; do not present as equivalent to `apex_confidence_engine.py` |
| `scripts/source_trust_engine.py` | **Retain** | CI-wired, independently consumed |
| `scripts/source_trust_scorer.py` | **Retain** | Live dependency of the canonical confidence chain |
| `scripts/intel_trust_governance.py` | **Experimental / Deprecate Later** | Appears dormant (single, likely-uncalled consumer); do not build on it, but do not delete without confirming `ocios_coordinator.py`'s true status first |
| `scripts/apex_sovereign_trust_orchestrator.py` | **Archive (pending confirmation)** | Appears fully dormant — an 8-engine "master orchestrator" with zero confirmed live callers is itself informative about how not to build this program's own orchestrator (see architecture companion §1) |
| `agent/enterprise_trust_engine.py` | **Experimental** | Not CI-wired in this audit's search; insufficient evidence for a stronger disposition |
| §2.4 long-tail items (≈15 engines) | **Retain, all** | Insufficient evidence for any disposition beyond "leave running"; recommend a dedicated follow-up audit |
| `evidence-registry/provenance-engine.js` (TITAN JS lineage) | **Internal Only / Experimental** | Confirmed not production-reachable; independent, single-record version-history concept, not source-completeness — a genuinely different capability from what §0.2 point 5's Evidence Completeness gap needs, so it should be *extended*, not treated as prior art to compose from directly |

---

## 8. Stage Numbering and ADR-0007 — flagged for executive decision, not resolved here

Two governance questions this audit cannot and should not resolve unilaterally:

1. **Naming.** Per §0.1, this work cannot be called "TITAN Stage 20" without colliding with
   already-reserved, already-documented scope. Options for an executive decision: (a) a new,
   non-TITAN-numbered program name (this document's working choice), (b) folding the eventual
   orchestrator into the P-layer stack as **P39** (the next open slot per this repo's own
   CLAUDE.md), as the JS-audit agent independently suggested, (c) renumbering the TITAN lineage's
   reserved "Stage 20" scope to a different number to free up "Stage 20" for this work — the
   highest-blast-radius option since it touches prior published reports, not recommended without
   explicit sign-off.
2. **ADR-0007.** Proposed since Project TITAN Stage 6-8, still not Accepted, already says "no new
   independent scorer may be introduced." This audit's own finding (§0.2 point 2) is that the
   Python pipeline's fragmentation is at least as severe as what ADR-0007 catalogued for the JS/blog
   side, but was never in its scope. An executive decision is needed on whether to (a) leave
   ADR-0007 exactly as scoped and let this program's eventual orchestrator work strictly within its
   existing "compose, never replace" spirit without touching the ADR itself (this document's
   working assumption throughout — see companion architecture document), or (b) commission a
   Python-pipeline-scoped companion ADR before any orchestrator implementation begins.

Both are presented as options, not recommendations this document is authorized to make.

---

*This audit is complete. No production code was read for the purpose of modifying it, and none
was changed. See `COMMERCIAL_QUALITY_ORCHESTRATOR_ARCHITECTURE.md` for the Phase B design-only
architecture that composes from — and never replaces — everything catalogued above. Per explicit
instruction, this program stops after both documents are complete and awaits executive approval
before any implementation.*
