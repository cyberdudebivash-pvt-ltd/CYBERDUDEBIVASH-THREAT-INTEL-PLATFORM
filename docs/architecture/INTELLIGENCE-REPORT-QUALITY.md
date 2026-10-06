# Intelligence Report Quality Architecture

**Status:** current as of Phase 4 (2026-08-22). Documents the actual code, not aspirational design — every claim below traces to a specific file and function.

---

## 1. Why this document exists

Phase 3 found P21 (`p21_certification_gate.py`) reporting the large majority of the feed BELOW_MINIMUM — a "quality crisis" — and deferred the root cause. Phase 4's investigation (see §9) found two separate causes: a temporary measurement artifact from an incomplete pipeline run, and a genuine, permanent design gap — **P21 has no concept of report type.** It scores a one-paragraph phishing-URL indicator against the same 8-component rubric built for a deep CVE/ransomware analytical report, and structurally fails anything that isn't the latter.

That gap could not be patched inside P21 without first answering a harder question: **what does a production-grade CyberDudeBivash intelligence report have to contain, and how do we prove it, per report type?** This document describes the answer Phase 4 built — a canonical, evidence-based content-quality layer that report-type-aware scoring (and eventually P21 itself) is meant to build on, not duplicate.

---

## 2. Report-type contract registry

**File:** `scripts/report_type_contracts.py`.

A news brief, a CVE advisory, and a ransomware campaign report are held to different standards by design — this repository has no single "intelligence report" template, and building a quality gate as if it did is precisely how P21 ended up penalizing 76% of feed volume for not being something it never claimed to be.

### 2.1 Report types

Ten types, derived from the platform's actual `threat_type` values (not an aspirational taxonomy):

```
CVE_VULNERABILITY  RANSOMWARE   MALWARE       INCIDENT_BREACH  SECURITY_ADVISORY
NEWS                INDICATOR_FEED  THREAT_ACTOR  CAMPAIGN         UNKNOWN
```

`classify_report_type(item)` maps an item's `threat_type` (lower-cased) through `REPORT_TYPE_MAP` — e.g. `"kev"`/`"remote code execution"`/`"web application attack"` → `CVE_VULNERABILITY`; `"malware-url"`/`"phishing-url"`/`"phishing"` → `INDICATOR_FEED`; `"threat-intel"`/`"threat intelligence"` → `NEWS`. If `threat_type` doesn't match, it falls back to CVE_VULNERABILITY when `cve_id`/`cve_ids`/`cves` is populated (checking all three legacy/current field-name variants — see §7), else `UNKNOWN`. `UNKNOWN` is a legitimate, non-error classification: it means the content contract runs its universal checks only, with no type-specific applicability narrowing.

### 2.2 Field requirement levels

Every `ReportContract` declares each field at one of four levels via `FieldRequirement`:

| Level | Meaning |
|---|---|
| `REQUIRED` | Absence is a defect for this report type. |
| `CONDITIONAL` | Required only when a related field/condition is present (e.g. a Sigma rule is conditional on the item claiming host-based detection relevance). |
| `OPTIONAL` | Nice to have; absence is never flagged. |
| `NOT_APPLICABLE` | This report type does not carry this concept at all — absence must never be scored as a defect. |

`NOT_APPLICABLE` is the mechanism that makes the whole system report-type-aware instead of penalizing every type against every field, which is the exact defect this layer exists to correct. Concretely: `CVE_VULNERABILITY` marks `iocs` `NOT_APPLICABLE` (a vulnerability advisory describes a flaw, not campaign infrastructure); `NEWS` marks `iocs`, `attck_technique_ids`, `detection_rules_total`, `cvss_score`, and `epss_score` all `NOT_APPLICABLE` (a news brief is not automatically operational intelligence — 0 IOC/0 ATT&CK/0 detection is a *valid* state, not a gap); `INDICATOR_FEED` marks `iocs` `REQUIRED` but `attck_technique_ids`/`detection_rules_total`/`cvss_score` `NOT_APPLICABLE` (a malicious-URL entry is exactly its indicator, nothing more is owed).

`get_contract(report_type)` / `contract_for_item(item)` are the accessors; `ReportContract.requirement_for(field)`, `.required_fields()`, `.conditional_fields()` are the query surface consumers use instead of re-deriving per-type rules inline.

---

## 3. Canonical content validation

**File:** `scripts/intelligence_content_contract.py`. Entry point: `validate_intelligence_content(item, report_type=None, publication_context=None) -> ValidationResult`.

### 3.1 Composition, not duplication

This engine does not re-implement fabrication detection. It imports and calls `scripts/anti_hallucination_engine.py`'s `HallucinationEngine` (its `TEMPLATE_EXEC_RE` platform-boilerplate patterns and its audit checks) and Phase 3's `is_pseudo_ioc()` / `strip_markdown_artifacts()` helpers, then adds report-type-applicability awareness and the PASS/WARN/HOLD publication decision on top. Reuse-before-build: the underlying "is this fabricated" logic has exactly one implementation, in `anti_hallucination_engine.py`; this module composes it rather than forking it.

### 3.2 `ValidationResult`

```python
@dataclass
class ValidationResult:
    item_id: str
    report_type: str
    valid: bool
    severity: str            # "PASS" | "WARN" | "HOLD"
    hold_publication: bool
    violations: List[Violation]
    quality_dimensions: Dict[str, Any]
    applicability: Dict[str, str]   # field -> requirement level actually applied
    evidence: Dict[str, Any]
    engine_version: str
```

### 3.3 Violation taxonomy

`PLACEHOLDER`, `TEMPLATE_LEAK`, `BROKEN_MARKDOWN`, `INTERNAL_INSTRUCTION`, `UNSAFE_HTML`, `GENERIC_FILLER`, `DUPLICATE_CONTENT`, `TRUNCATED_CONTENT`, `MALFORMED_REFERENCE`, `UNSUPPORTED_ASSERTION`, `INVALID_IOC_CONTEXT`, `INVALID_ATTACK_MAPPING`, `MISSING_CRITICAL_SECTION`, `REPORT_TYPE_MISMATCH`, plus `REPORT_URL_IS_SOURCE_URL` (Phase 2's T09 invariant, re-surfaced here as a first-class HOLD-eligible violation rather than a separate ad hoc check).

### 3.4 PASS / WARN / HOLD

`_HOLD_CODES` (line 196) is the fixed set of violation codes that force `hold_publication = True`:

```
PLACEHOLDER, TEMPLATE_LEAK, INTERNAL_INSTRUCTION, UNSAFE_HTML,
INVALID_IOC_CONTEXT, INVALID_IOC, PSEUDO_IOC,
MALFORMED_REFERENCE, REPORT_URL_IS_SOURCE_URL,
MISSING_CRITICAL_SECTION
```

Everything else that reaches hard-fail severity in the underlying checks (e.g. `INVALID_CONFIDENCE` — a missing rationale) is surfaced as WARN, not HOLD, per the module's own header comment: a real defect worth flagging, but not one that makes the item unsafe or misleading to publish. Note `MISSING_CRITICAL_SECTION` — a REQUIRED field absent for the item's report type — is itself HOLD-eligible, not merely WARN; this is stricter than "cosmetic" and is exercised directly by the `INDICATOR_HOLD` golden fixture (§4). Missing `OPTIONAL` or `NOT_APPLICABLE` data is never an error at any severity — that is the applicability system in §2.2 doing its job.

WARN means "real defect, not unsafe to publish" — e.g. broken Markdown that degrades readability but doesn't mislead. A `WARN` fixture is deliberately allowed to reach `PASS`-adjacent severity in tests only in the sense that "valid" (§3.5) permits it; the defect is still surfaced in `violations`, it just doesn't block.

### 3.5 `valid` vs. `severity`

`valid` means *safe and honest to publish*, not *perfect*. A `WARN` item is `valid = True`; only `HOLD` sets `valid = False`. This distinction is deliberate and tested (`test_valid_fixtures_never_hold`, `test_warn_fixtures_not_hold`) — conflating "has a defect" with "unsafe to publish" is exactly the kind of false-positive quality gate this layer was built to avoid.

### 3.6 Known false positives found and fixed during construction

Both found by running the engine against the real 500-item production feed before trusting it, not by inspection alone:

- **UNSAFE_HTML on `javascript:` in prose.** The pattern `javascript\s*:` matched Firefox's own CVE component-naming convention ("the JavaScript: GC component") — 3 real items. Fixed with a negative lookahead (`javascript\s*:(?!\s)`) that still catches `javascript:alert(1)` / `javascript:void(0)` but not prose ending in "JavaScript: ").
- **PLACEHOLDER on REST route syntax.** The pattern `\{token\}` matched literal API paths quoted inside vulnerability descriptions (`GET /api/transaction/{id}`) — 4 real items, all false positives. Fixed with a negative lookbehind (`(?<!/)\{[a-zA-Z_]...\}`) excluding the URL-path-parameter shape.

Verified result against the real production feed at time of construction: 343 PASS / 152 WARN / 5 HOLD (500 items).

---

## 4. Golden fixture suite

**Files:** `tests/fixtures/golden_intelligence_reports.py` (21 fixtures), `tests/test_intelligence_content_contract.py` (36 tests).

Minimum coverage: VALID / WARN / HOLD for CVE, ransomware, malware, incident/breach, advisory, and news (18 fixtures), plus an INDICATOR_FEED VALID/WARN/HOLD set (3 more) added because that report type carries the platform's own IOC-required contract and deserved direct coverage. No live network calls; deterministic (`test_deterministic` runs each fixture twice and asserts identical severity and violation-code set, order-independent).

Coverage includes: report-type classification per fixture, VALID-never-HOLDs, WARN-never-HOLDs-but-is-flagged, HOLD-fixtures-block-with-the-expected-code, applicability (`test_news_missing_ioc_is_not_a_violation`, `test_cve_missing_iocs_is_not_a_violation` — the mandate's core assertion that 0 IOC/0 ATT&CK/0 detection is valid for news, encoded as an executable test rather than a comment), and the T09 report-url/source-url invariant.

---

## 5. CI enforcement

`.github/workflows/report-generator-regression-gate.yml`, step "Run intelligence content contract regression tests (Phase 4)":

```yaml
- name: Run intelligence content contract regression tests (Phase 4)
  run: |
    python -m pytest tests/test_intelligence_content_contract.py -v --tb=short
```

Added after the existing GATE E (frontend integrity) step, following the file's established one-step-per-regression-class convention. Deliberately a fixture-based unit-test gate, not a full-feed processing job — the mandate is explicit that CI should fail on placeholder/template leakage/unsafe HTML/unsupported URLs/fabricated IOCs/invalid mandatory structure via deterministic fixtures, not re-score the entire live feed on every PR.

---

## 6. 12-dimension commercial quality rubric

**File:** `scripts/quality_rubric_scorer.py`. Entry point: `score_item(item) -> Dict`.

Separate from the PASS/WARN/HOLD publication-safety gate (§3) — this is a *commercial quality* scorer, used for benchmarking (§7), not a publish/block decision. `DIMENSION_WEIGHTS` (asserted to sum to 100):

| Dimension | Weight | Dimension | Weight |
|---|---|---|---|
| Intelligence integrity | 15 | IOC quality | 8 |
| Evidence / provenance | 12 | ATT&CK quality | 7 |
| Technical depth | 12 | Detection value | 10 |
| Executive usefulness | 8 | Mitigation / response | 7 |
| SOC actionability | 10 | Confidence / uncertainty | 5 |
| Readability / presentation | 3 | Machine-readable consistency | 3 |

**Applicability-aware:** a dimension whose underlying field is `NOT_APPLICABLE` for the item's report type (§2.2) is excluded from the denominator rather than scored as zero — a news item does not lose IOC-quality points for having no IOCs, because it was never eligible for them. This reuses `report_type_contracts.py`'s applicability levels rather than re-deriving report-type rules a second time.

**Bug found and fixed during construction:** `_score_technical_depth` checked `item.get("cve_id") or item.get("cve_ids")` and scored `intel--813df2b89f3b1b8e` as 0/12 despite the item genuinely having a CVE — because that specific item only populated the third, less-common field name, `cves`. Fixed by adding `or item.get("cves")`, matching the same three-field-name pattern already handled correctly elsewhere (`p38_shared_validators.py`, `intelligence_content_contract.py`) — see §7 for why this field-name inconsistency recurs across the codebase.

---

## 7. The recurring field-name-inconsistency pattern

Found independently at least three times during Phase 4 (quality rubric scoring, ATT&CK CWE-mapping input, EII bridge output — see `INTELLIGENCE-DETECTION-ARCHITECTURE.md` §5) and once in Phase 2 (`has_mitre_coverage`, current-certification-architecture doc §5): this codebase stores the same concept under multiple field names without one canonical accessor, and code that checks only one variant silently under-counts.

Confirmed variants as of Phase 4:
- **CVE identifiers:** `cve_id`, `cve_ids`, `cves` — three different fields, no single canonical one. Every new check in this quality layer checks all three explicitly (see `report_type_contracts.classify_report_type()`, `quality_rubric_scorer._score_technical_depth`).
- **IOC counts:** `ioc_count` (`len(item's own iocs list)`) vs. `indicator_count` (STIX-bundle indicator-object count, from `agent/export_stix.py`) — legitimately different metrics conflated under one "IOC" label by at least one HTML report template. `ioc_count` itself is now guaranteed internally consistent with `len(iocs)` (Phase 4 Checkpoint E, `scripts/clean_feed_manifest.py`); the template mislabeling is a separate, unresolved defect — see §9.

This is not fixed generally in Phase 4 (would require a repo-wide canonical-accessor sweep well beyond this pass's scope) but is documented here so it stops being independently rediscovered.

---

## 8. Relationship to P21

**Not yet unified — this is the primary documented gap in this architecture.**

`scripts/p21_certification_gate.py` predates this content-quality layer and has its own independent 8-component scoring rubric (Evidence/IOC Quality/Multi-source/MITRE/Detection/Executive/Freshness/Consistency) with no report-type awareness. Phase 4's root-cause investigation (§9) found this is the actual mechanism behind the "quality crisis": P21 structurally fails PHISHING-URL and THREAT-INTEL items (76% of feed volume) for not being deep CVE/ransomware analysis, which is not what those report types are.

The correct fix — repairing P21 to consult `report_type_contracts.py`'s applicability levels before scoring a dimension, ideally via a thin adapter rather than a rewrite, per the mandate's own preference for stability over a wholesale replacement of a live certification gate — is **not implemented in this pass**. `validate_intelligence_content()` and `score_item()` exist and are independently wired into CI and the benchmark; P21 itself still runs its original, report-type-blind scoring. This is called out explicitly rather than silently left inconsistent: there are now two content-quality authorities in the codebase (P21's rubric and this layer) until that adapter is built. Single Source of Truth is not yet achieved for "is this report good" — it is achieved for "is this report safe/honest to publish" (§3, the only authority for PASS/WARN/HOLD) and "how good is this report commercially" (§6, the only authority for the 12-dimension score).

---

## 9. P21 root cause (for reference)

Full detail lives in the Phase 4 PR description; summarized here because it motivated this entire document:

1. **Measurement artifact (fixed):** a Phase 3 regeneration pass called `stage_sync_root_feed_json()` directly, bypassing `p20_evidence_chain_enricher.py` and `confidence_corroboration_engine.py` — so every item scored 0/25 on Evidence for a reason that had nothing to do with the item's actual quality. Fixed by running both enrichers for real.
2. **Design gap (documented, not yet fixed in P21 itself — see §8):** even after fixing (1), P21's other 7 dimensions remained structurally low for indicator-shaped content, because the rubric has no concept that a phishing-URL entry was never supposed to carry deep MITRE/detection/executive analysis. This is a `REPORT_TYPE_APPLICABILITY_DEFECT` / `THRESHOLD_DESIGN_DEFECT` in the taxonomy this investigation used to classify every failure class, not a `REAL_CONTENT_QUALITY_DEFECT` — the content is not bad, the rubric is asking it a question it was never supposed to answer.

---

## 10. Known gaps (P2, not blockers)

- P21 unification (§8) — the primary open item.
- Field-name canonicalization (§7) — a repo-wide accessor sweep, out of scope for this pass.
- HTML report template `ioc_count`/`indicator_count` mislabeling (§7) — root-caused to a specific template but the template itself was not located/fixed in this pass; the underlying `ioc_count` field was hardened instead (Checkpoint E) so it can never independently drift regardless of which label a future template fix chooses.
- `intelligence_content_contract.py`'s HOLD-code set is fixed at construction time (§3.4) — as new report types or violation classes are added to the registry, `_HOLD_CODES` needs an explicit, evidenced decision per new code, not an automatic default in either direction.
