# Intelligence Detection-Content Architecture

**Status:** current as of Phase 4 (2026-08-22). Documents the actual code, not aspirational design — every claim below traces to a specific file and, where possible, a line number. This document is descriptive: it records what exists and how it behaves today. Fixing the gaps it identifies is out of scope for this pass — see §12.

---

## 1. Why this document exists

The platform generates detection content (Sigma/YARA/Suricata rules, KQL/SPL/EQL queries) through **multiple independent implementations that grew up separately**, each added to solve a specific need without a single owning architecture. This document is the first attempt to inventory all of them in one place, with evidence, so that future work builds on what actually runs in production rather than on what a comment or docstring claims runs.

The single most consequential finding: the platform's own public `/api/v1/detections` API endpoint does not read from any of the four real detection generators (§13). That fact alone justifies this document existing before any further detection-related feature work.

---

## 2. The four detection generators

Four independent rule-synthesis engines exist, matching the enumeration in `sentinel-blogger.yml`'s own STAGE 3.1.11 comment block:

| Key | File | Artifact types | Trigger |
|---|---|---|---|
| **A** | `scripts/apex_real_detection_engine.py` (`generate_rules_for_advisory`) | Sigma, KQL (+ SPL/YARA per class) | `detection_engineering_orchestrator.py` Stage 1 → `stage_3_1_11_detection_engineering_core.py` → `generate-and-sync.yml` "STAGE 3.1.11" |
| **B** | `agent/v51_detection_engine/engine.py` (`DetectionEngine`) | Sigma, YARA, Suricata | `.github/workflows/detection-engine.yml`, independent cron every 12h (`30 */12 * * *`) |
| **C** | `scripts/detection_bundle_injector.py` | `sigma_rule`, `kql_query`, `suricata_rule` (flat fields on the item itself) | `sentinel-blogger.yml` "STAGE 3.1.12 — Detection Bundle Injector" |
| **D** | `scripts/detection_content_generator_v2.py` (`DetectionContentGeneratorV2.generate_pack`) | 6 formats: Sigma, YARA, Suricata, KQL (Sentinel), SPL (Splunk), EQL (Elastic) | `generate-and-sync.yml` "STAGE 3.1.21 — Detection Content Generator v2" |

Two more scripts are commonly mistaken for generators and are documented here specifically to prevent that:

- **`scripts/behavioral_detection_generator.py`** publishes a fixed, hardcoded library of Sigma rules (`SIGMA_RULES` list literal) every run — it does not read the feed or generate per-item content. It is wired as `run_pipeline.py`'s Stage "2.3.behavioral_detection" (the *only* detection-related script actually invoked from `run_pipeline.py` — everything else is a direct GitHub Actions workflow step).
- **`scripts/generate_detection_pack.py`** is a **packager**, not a generator — its own docstring says it "extracts and packages" `sigma_rule`/`kql_query` values C already wrote, for the $149/mo premium detection-pack add-on (`data/premium_staging/detections/`, gitignored, uploaded to R2).

A seventh candidate, `agent/detection_forge.py`, is dead code — see §13.

**Eligibility gating is inconsistent across the four.** Only generator C consults `is_detection_eligible()` (§4) before running. A (via its orchestrator), B, and D all generate content unconditionally for every item/IOC they are given — including, for D specifically, NEWS items, since `generate_pack()` has no eligibility check anywhere in its body. This is a direct architectural gap the eligibility fix (§4) did not reach.

---

## 3. Consumers

| Field / artifact | Written by | Read by |
|---|---|---|
| `sigma_rule`, `kql_query`, `suricata_rule`, `vuln_class` (flat, on the item) | C | `detection_quality_engine.py` (§6); `api/paywall_filter.py`'s `FREE_STRIP_TOP_LEVEL` (note: that list uses the *plural* `detection_rules`/`sigma_rules`, which does not exactly match these singular field names — see §11); marketing pages (`index.html`, `docs/quickstart.html`) |
| `detection_rules_total`, `detection_quality_status`, `detection_production_ready` | `detection_quality_engine.py`, **not** C itself (§6) | `p38_shared_validators.get_detection_rules_total()` → P29–P33 certification gates, `report_type_contracts.py`, `quality_rubric_scorer.py` |
| `api/detections/*.json` (index + per-advisory) | A, via the orchestrator's `enterprise_rule_packager` | **Not** `api/v1_router.py`'s live `/detections` route — see §13, the central finding of this document |
| `data/detection/{id}/detection_pack.json` | D | No consumer found anywhere in `api/`, `agent/`, or templates during this investigation — only D's *summary* object (`detection_pack_v2`) merges back onto the manifest; the pack files themselves appear to be write-only |

---

## 4. Eligibility

`scripts/p38_shared_validators.py`, `is_detection_eligible(item)` (confirmed unchanged since the Phase 2 investigation that introduced it, see `INTELLIGENCE-CERTIFICATION-ARCHITECTURE.md` §7):

```python
def is_detection_eligible(item: Dict) -> bool:
    if item.get("cve_id") or item.get("cve_ids"):
        return True
    if item.get("vuln_class"):
        return True
    return False
```

This is the same heuristic (CVE reference or `vuln_class` presence) documented in the certification architecture doc, confirmed by direct inspection to still track generator C's own in-scope logic exactly. Sibling functions `attck_eligible()` and `is_ioc_eligible()` apply the identical pattern to ATT&CK and IOC coverage respectively.

**Note the field-name gap already flagged in `INTELLIGENCE-REPORT-QUALITY.md` §7**: `is_detection_eligible` checks `cve_id`/`cve_ids` but not the third variant, `cves` — meaning an item that only populates `cves` is scored as detection-ineligible by every consumer of this function, even when it genuinely is CVE-referenced. Not fixed in this pass (documented, not touched, per the same reasoning as the other field-name-inconsistency instances).

**Only generator C, and the certification/scoring layer that measures after the fact, actually consult this function.** It gates generation for exactly one of the four generators; for the other three it is purely a measurement lens applied downstream, not a control on whether content gets produced.

`scripts/report_type_contracts.py`'s `REQUIRED`/`CONDITIONAL`/`OPTIONAL`/`NOT_APPLICABLE` contract system (see `INTELLIGENCE-REPORT-QUALITY.md` §2) marks `detection_rules_total` `NOT_APPLICABLE` for `NEWS` and `INDICATOR_FEED`, `CONDITIONAL` for `CVE_VULNERABILITY`. This registry is consumed by `validate_intelligence_content()`/`validate_batch()`, which is wired into a live CI gate (`report-generator-regression-gate.yml`) — but, per the paragraph above, it governs *scoring*, not whether D actually generates a 6-format pack for a NEWS item it was never eligible to receive one for.

---

## 5. Orchestration

`scripts/detection_engineering_orchestrator.py` (`DetectionEngineeringOrchestrator`) is a real orchestrator, but its authority is scoped to generator A only — it has no relationship to B, C, or D, each of which is a standalone script invoked directly from workflow YAML with no shared coordination layer between them.

Its own docstring claims 14 subsystems; `_init_subsystems()` actually wires 11 (`apex_real_detection_engine`, `apex_mitre_attack_engine`, `detection_validation_engine`, `fp_suppression_engine`, `coverage_gap_analyzer`, `detection_drift_monitor`, `multi_siem_normalization_layer`, `retro_hunt_engine`, `telemetry_dependency_mapper`, `enterprise_rule_packager`, `detection_quality_benchmarker`). Three named subsystems (`regression_tests`, `apex_confidence_engine`, `threat_actor_profiler`) are never imported — stale/aspirational docstring content, flagged here rather than silently trusted.

`process_advisory()` runs 9 numbered internal stages per advisory (rule generation → ATT&CK mapping → FP suppression → validation → multi-SIEM normalization → retro-hunt → telemetry mapping → benchmark → coverage-gap), each independently exception-isolated. It performs **no eligibility check of its own** — the caller (`stage_3_1_11_detection_engineering_core.py`) passes every item in the feed through unconditionally, consistent with §2/§4's finding that A does not gate on `is_detection_eligible`.

---

## 6. Validation

Two independent validators exist, each scoped to a different generator's output, with no shared validation layer between them:

1. **`scripts/detection_validation_engine.py`** (`DetectionValidationEngine`) — the orchestrator's Stage 4, validating generator A's output only. 10 gates (6 mandatory): syntax, ATT&CK-technique presence, telemetry-dependency presence, false-positive-probability score, tuning recommendations, log-source mapping, uniqueness fingerprint, coverage score ≥ 30, retro-hunt presence, deployment-environment tagging. **The syntax gate is keyword/regex presence-checking, not a real parser** — a Sigma rule is validated by regex-matching `^title:`, `^id:`, `condition:`, `falsepositives:`, never by an actual YAML parse — so a structurally-broken-but-keyword-complete rule passes.
2. **`scripts/detection_quality_engine.py`** — a separate, simpler validator over generator C's flat fields. Classifies each of `sigma_rule`/`suricata_rule`/`kql_query`/`yara_rule` as `DETECTION_PRODUCTION_READY` / `DETECTION_CVE_SPECIFIC` / `DETECTION_NOT_PRODUCTION_READY` via regex pattern lists distinguishing generic boilerplate (the literal templates C itself produces for generic `vuln_class` values) from CVE-specific artifacts. Wired live as `generate-and-sync.yml` "STAGE 6.99", run with `--apply` — **this script, not C, is the actual writer of `detection_rules_total`** and the other fields §3 lists as consumed by the certification chain.

Generators B, D, and the static-library script have **no validation step at all** — their output is trusted as-produced.

---

## 7. Priority / rotation / budget

`MAX_DETECT_ITEMS` has exactly one definition in the repository: `scripts/detection_bundle_injector.py`, `int(os.environ.get("MAX_DETECT_ITEMS", "200"))`. It applies **only to generator C** — A, B, and D have no comparable budget cap.

The rotation fix (documented in-line as "v185.0 P0 FIX") replaced a positional-slice bug with an eligibility-and-recency-aware selection:

- **Before:** `items[:MAX_ITEMS]` over the raw, timestamp-sorted array — an eligible item ranking below position 200 was *permanently* excluded from ever receiving detection content, run after run.
- **After:** (1) filter to `is_detection_eligible(item)`; (2) exclude items that already have all three rule fields populated (`_has_all_rules()`); (3) sort the remainder by `-risk_score`, then `stix_id` as a deterministic tiebreak; (4) take the first `MAX_ITEMS`. The budget is now a rotating "new work" allowance rather than a fixed window that starves low-recency items forever.

Telemetry for this selection is written to `data/telemetry/detection_bundle_report.json`: `eligible_items`, `already_processed_before_run`, `unprocessed_before_run`, `selected_this_run`, `max_items_budget`, `remaining_unprocessed_eligible` — a full numerator/denominator accounting rather than a single opaque percentage.

---

## 8. Artifact states

**There is no single, unified state model.** Three incompatible vocabularies coexist:

| Owner | Vocabulary |
|---|---|
| Generator A / orchestrator | `pipeline_status` ∈ `PENDING\|PASS\|WARN\|FAIL\|SKIP`, plus `quality_grade` ∈ `S/A/B/C/D/F`, plus a `production_ready: bool` |
| `detection_quality_engine.py` (governs C's fields) | `detection_quality_status` ∈ `DETECTION_PRODUCTION_READY\|DETECTION_PARTIALLY_READY\|DETECTION_NOT_PRODUCTION_READY` |
| Generator C itself | No state field — `_has_all_rules()` is a plain boolean over 3 fields being non-empty, nothing richer |
| Generator D | A bare `quality_score` integer 0–100, no pass/fail state at all |

Nothing resembling a "generated → validated → published / rejected" lifecycle exists. Each generator/validator pair produces its own independent boolean-or-score snapshot, fully recomputed on every run, with no persisted state transition between runs.

---

## 9. Coverage metrics

Four separate coverage reports exist, none unified into a single canonical number:

1. `data/audit/stage_3_1_11_detection_engineering.json` (`stage_3_1_11_detection_engineering_core.py`) — `advisories_processed`, `production_ready_count`, `average_quality_score`, `platforms_covered`.
2. `api/detections/detection-index.json` (orchestrator's `_build_index()`) — grade distribution, techniques/platforms covered, per-advisory entries.
3. `api/detection_quality.json` (`detection_quality_engine.py`) — `production_ready` / `partially_ready` / `not_production_ready` / `no_detection_rules` counts.
4. **The certification gate**: `scripts/p33_production_certification.py` Gate G20, "Detection bundle coverage >= 40%". Reports both the raw full-feed percentage (the actual pass/fail basis) **and** an eligible-only percentage as added context (`eligible (CVE or vuln_class): N/M = X%`) — the direct product of the Phase 2 eligibility investigation, and the pattern this document's own eligibility section follows. As of the final Phase 4 snapshot (post-rebase regeneration against current `main`): 0.0% raw, 0/86 eligible (0/84 on an earlier, mid-phase checkpoint against a smaller manifest — the eligible count moves with the underlying feed). **G20 only warns — it never fails the certification.** p29–p33's own certification scripts are not superseded by one another; all five independently re-check `is_detection_eligible` and each write their own report.

---

## 10. Persistence — every path a detection artifact reaches

| Path | Writer |
|---|---|
| `api/feed.json`, `data/stix/feed_manifest.json` (fields `sigma_rule`, `kql_query`, `suricata_rule`, `vuln_class`, `detection_generated_at`) | C |
| `api/feed.json` (fields `detection_quality_status`, `detection_production_ready`, `detection_rules_total`, `detection_rules_production_ready`) | `detection_quality_engine.py` |
| `api/v1/detections/{stix_id}.json` (Pro-tier-gated payload) | C |
| `api/detections/detection-index.json`, `{id}.json`, `{id}_full.json`, plus packaged bundles (`apex-sentinel-arm-template.json`, `apex-splunk-content-bundle.json`, `apex-sigma-rules.zip`, `apex-yara-rules.yar`, `apex-suricata.rules`, `apex-package-manifest.json`) | A, via the orchestrator's `enterprise_rule_packager` |
| `data/audit/detection_drift_report.json`, `detection_drift_state.json`, `detection_drift_history.json` | `detection_drift_monitor.py` (orchestrator subsystem) |
| `data/intelligence/detection_rules/{sigma,yara,suricata}/*`, `rule_manifest.json` | B |
| `data/detection/{advisory_id}/detection_pack.json` + `item["detection_pack_v2"]` summary on the manifest | D |
| `data/detection_rules/*.yml`, `index.json`, `api/detection_rules.json` | The static-library script |
| `data/premium_staging/detections/*` (gitignored → R2) | The packager script |
| `api/detection_quality.json` | `detection_quality_engine.py` |
| `data/quality/p29`–`p33_certification_report.json` | Certification scripts |
| `data/telemetry/detection_bundle_report.json` | C |

At least **six separate top-level output locations** exist for what is conceptually a single idea ("this item has a detection rule"). No canonical `detections/` directory exists — see §13 for why this matters most.

---

## 11. Workflow ordering

Detection generation is **not primarily a `run_pipeline.py` concern.** Of the six scripts in §2, only the static-library one is invoked from `run_pipeline.py` (Stage "2.3.behavioral_detection"). Generators A, B, C, D and the packager are direct GitHub Actions steps, split across **three independently-scheduled workflow files**:

- **`sentinel-blogger.yml`** (3×/day cron + push-to-main): ... → STAGE 3.1.10b Actor Attribution → **STAGE 3.1.12 Detection Bundle Injector (C)** → STAGE 3.2 report generation → ... → the packager, further down the same file.
- **`generate-and-sync.yml`** (a separate schedule; its own header explicitly states it exists "SEPARATE from sentinel-blogger... to ELIMINATE race conditions", own concurrency group `sentinel-ai-writer`): STAGE 4.3 IOC enrichment → **STAGE 3.1.11 Detection Engineering Core (A)** → ... → **STAGE 3.1.21 Detection Content Generator v2 (D)** → ... → **STAGE 6.99 Detection Quality Engine**, which validates C's fields.
- **`detection-engine.yml`** (independent 12-hour cron): B only, self-contained.

Generator A documents its own required ordering relative to MITRE mapping directly in its stage-runner file ("After STAGE 3.1.10 — MITRE ATT&CK Actor Attribution"). Certification/quality gates (STAGE 6.9x) run after detection generation in both workflows that contain them.

**Open question, not a confirmed defect:** `generate-and-sync.yml`'s STAGE 6.99 reads `sigma_rule`/`kql_query`/`suricata_rule` — fields written by C, which runs in the *other* workflow file, `sentinel-blogger.yml`. Both workflows are push-triggered on `main` in addition to their independent crons, with separate concurrency groups. Nothing in either file guarantees STAGE 6.99 only runs after a given run of C has committed. This investigation found no direct evidence this race has actually occurred, only that the current architecture makes it structurally possible. Recorded here as a P2 item for future verification, not asserted as a live bug.

**Stage-numbering collision, confirmed:** `sentinel-blogger.yml` and `generate-and-sync.yml` independently reuse the identical labels `"STAGE 3.1.11"` and `"STAGE 3.1.21"` for two completely different scripts each (CVE Title Enricher vs. Detection Engineering Core; the packager vs. Detection Content Generator v2, respectively). Separately, a comment inside `sentinel-blogger.yml` refers to the detection bundle injector as "STAGE 3.1.20 above" when its actual step label, 200+ lines earlier in the same file, is "STAGE 3.1.12" — a stale renumbering artifact. Neither collision affects execution (workflow step names are labels, not identifiers CI dispatches on), but both are documentation-hygiene defects worth fixing opportunistically rather than trusting either file's stage comments as authoritative without cross-checking the actual step content.

---

## 12. Failure behavior

**Workflow level: uniformly zero-failure.** Every detection-related step wraps its Python invocation such that a non-zero exit is caught, annotated with a GitHub Actions `::warning::`, and the job continues (`continue-on-error: true` and/or an explicit `set +e ... exit 0` guard). No detection-generation failure can fail a CI job.

**Python level: inconsistent between generators.**
- **A** (via the orchestrator) is fine-grained: each of the 9 internal stages in `process_advisory()` is individually exception-isolated, and each advisory in the batch loop is also individually isolated — one advisory's failure never stops the batch.
- **C** has **no per-item exception isolation** in its main injection loop, and its atomic write happens exactly once, after the entire loop completes. A mid-loop exception on any single item propagates and aborts the script — and because the write-back is all-or-nothing, **the run's entire detection-content progress for that invocation is discarded, not partially applied.** The workflow-level `continue-on-error` hides this from ever failing CI, so a silent full-run data loss on C is possible with no operator-visible signal beyond a `::warning::` line in a job log nobody is required to read.
- **B and D** wrap only their top-level `main()`/engine entry point — no per-item granularity, same all-or-nothing exposure as C in practice.

This is a real, evidenced gap: **C is the one generator with eligibility gating and budget rotation (§4, §7) — i.e., the one most load-bearing for honest coverage measurement — and it is also the one with the weakest per-item failure isolation.** Not fixed in this pass; recorded in §14 as a P1 finding.

---

## 13. The central finding: the live detections API is disconnected from all four generators

`api/v1_router.py`'s `GET /api/v1/detections` route — the endpoint documentation elsewhere in this codebase describes as the live consumer of generator A's packaged output — actually calls `api/engine_connector.py`'s `get_detections()`, which reads exclusively from `data/ttp_engine/{ttp_matrix,ttp_correlations,ttp_siem_rules,ttp_meta}.json`.

**That directory does not exist in the repository.** Its only would-be producer, `agent/ttp_engine.py` (`TTPEngine`, which has its own independent Sigma-rule generator and would write `sigma_rules.yml` + `kql_query` fields), is never invoked anywhere — confirmed by a repository-wide search of every workflow YAML and `run_pipeline.py`.

**Consequence:** the platform's own public detections API endpoint is currently serving empty or default data, structurally disconnected from generators A, B, C, and D — none of which write to any path `engine_connector.py` reads. A customer or integration calling this endpoint today receives nothing meaningful regardless of how much detection content the four real generators produce.

This is the most consequential fact this investigation surfaced, and is called out here separately from the rest of the architecture inventory because it is a live, customer-facing defect, not merely an internal-architecture untidiness. See §14 for its priority classification. Fixing it is explicitly **not** attempted in this pass — see §15.

---

## 14. Dead and disconnected code, confirmed

Confirmed by direct reading and repository-wide grep, not inferred from absence alone:

- `scripts/run_ai_and_detection.py` claims in its own header comment to be "Called by: `.github/workflows/sentinel-blogger.yml` (Stage 6c)." This is false — no workflow file or `run_pipeline.py` invokes it. Its only effect, `agent/detection_forge.py` (candidate generator "G"), is therefore never exercised in production.
- `agent/ttp_engine.py` — never invoked; the sole would-be fix for §13.
- `core/detection/detection_engine.py` (`SigmaRuleExecutor`, a real `yaml.safe_load`-based rule parser — notably a *better*-built validator than anything in §6) is reachable only through the dead `detection_forge.py` path, and is therefore also dead in production.
- `generate_intel_reports.py` imports `apex_real_detection_engine.generate_rules_for_advisory` but never calls it — consistent with that same file's own documented decision (its own "SEC-2026-07-18" section) that public HTML reports deliberately never render synthesized detection rules, to avoid the wasted compute of generating content that would never be shown. The import itself is stale, not a bug with a live consequence.

---

## 15. Field-name inconsistencies (a further instance of the pattern documented in `INTELLIGENCE-REPORT-QUALITY.md` §7)

Confirmed, not assumed: at least four incompatible naming schemes for "this is a detection rule" coexist with no canonical mapping between them —

- Generator C writes singular `sigma_rule` / `kql_query` / `suricata_rule`.
- `api/schemas.py`'s `DetectionRule` Pydantic model declares `splunk_query` / `kql_query` — no `sigma_rule` field at all.
- `api/paywall_filter.py`'s `FREE_STRIP_TOP_LEVEL` strips the plural `detection_rules` / `sigma_rules`, which matches none of the above exactly.
- `detection_validation_engine.py`'s `run_validation_on_advisory` looks for a fifth set of aliases (`sigma_rule|sigma|kql_rule|kql|spl_rule|spl|yara_rule|yara`) that don't match any actual writer's field name precisely (no generator anywhere writes `kql_rule` or `spl_rule`).

Not fixed here — recorded as a further, concrete data point for the eventual repo-wide canonical-accessor sweep already flagged as out-of-scope-for-this-pass in `INTELLIGENCE-REPORT-QUALITY.md` §7/§10.

---

## 16. Summary of findings and priority

| # | Finding | Class | Fixed this pass? |
|---|---|---|---|
| 1 | `/api/v1/detections` reads from a non-existent, never-written data source, disconnected from all 4 real generators | **P0 — live customer-facing defect** | No — §17 |
| 2 | Generator C has no per-item exception isolation and an all-or-nothing write; a mid-loop failure silently discards the entire run's progress, masked by workflow-level `continue-on-error` | P1 | No |
| 3 | Only generator C applies eligibility gating; A/B/D generate unconditionally, including D producing full 6-format packs for NEWS items | P1 | No |
| 4 | `is_detection_eligible()` checks `cve_id`/`cve_ids` but not the third field-name variant `cves` | P2 (same class as `INTELLIGENCE-REPORT-QUALITY.md` §7) | No |
| 5 | No unified artifact-state model (3 incompatible vocabularies) | P2 | No |
| 6 | No unified coverage metric (4 separate reports) | P2 | No |
| 7 | At least 4 incompatible field-name schemes for the same concept | P2 | No |
| 8 | Possible cross-workflow read/write race between `generate-and-sync.yml` STAGE 6.99 and `sentinel-blogger.yml`'s generator C | P2 — structurally possible, not confirmed to have occurred | No |
| 9 | Stage-numbering label collisions across two workflow files | P3 — documentation hygiene, no execution impact | No |
| 10 | `detection_validation_engine.py`'s Sigma "syntax" gate is regex presence-checking, not a real parse (unlike the dead-but-better-built `core/detection/detection_engine.py`) | P2 | No |

---

## 17. Recommended next step

Findings 1–3 are architecturally significant enough to warrant their own dedicated investigation-and-fix pass rather than a patch appended to this already-large quality-architecture PR: finding 1 requires deciding whether to point `engine_connector.py` at one of the four real generators' output (and reconciling their four incompatible field/state/schema conventions first, per findings 5–7, or the fix just relocates the disconnection) or to resurrect and wire `agent/ttp_engine.py`; finding 2 requires adding per-item isolation to `detection_bundle_injector.py`'s main loop plus a partial-write strategy, which touches the same file this document's Checkpoint E already modified once this phase — a second surgical pass, not a bundled one, keeps that change auditable. Recommended as explicit, prioritized Phase 5 (or an earlier dedicated hotfix, given finding 1's customer-facing severity) scope rather than rushed into Phase 4's remaining budget.
