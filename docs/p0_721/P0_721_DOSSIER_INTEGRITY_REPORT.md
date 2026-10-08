# P0 #721 — Enterprise Dossier Intelligence Integrity

Branch `cyberdudebivash/stoic-lovelace-insrcn` · base `241cce7fb` (= `origin/main`, clean tree at start) · 2026-10-08

## 0. Release decision

| | |
|---|---|
| **Decision** | **BLOCKED — do not promote.** Source-level fixes are implemented and tested; nothing is deployed, and the *published* artifacts are unchanged (see §5). |
| Not met | Golden-eight regeneration (originals unavailable) · STIX/MISP exporter validation (not in scope of this change) · detection-rule validation pipeline (§7) · live regeneration + redeploy · operator authorization |
| Rollback | `git revert` the merge commit. No schema, KV, D1, R2, auth, billing or workflow change is included; published artifacts are untouched. |

### The eight named dossiers — BLOCKED / UNVERIFIED
CVE-2026-71183, -89191, -12260, -4894, -105110, -107466, -87426, -107510 **do not exist anywhere in this repository** (full-text search of every file; the only hit, `CVE-2026-4894`, was a substring of `CVE-2026-48946`), and issue #721 contains no report text. They were *not* reconstructed or simulated. Instead the same defect classes were reproduced on **verbatim production feed records** (`tests/fixtures/dossier_p0_721_real_records.json`, 8 records from `data/apex_enriched_manifest.json`). A harness is in place: drop the eight feed records into `tests/fixtures/golden_721/*.json` and `test_golden_eight_dossiers` enforces every invariant on them (currently skipped with the reason).

## 1. Forensic register — root cause per file

| # | File (function) | Defect | Evidence |
|---|---|---|---|
| 1 | `scripts/generate_intel_reports.py::build_report_sections` | `ioc_count = len(raw iocs)` with no qualification; then overwrites `item["iocs"]` with the raw list | Real manifest: 1,528 raw IOC entries → 498 qualified; **1,030 (67%) are not indicators** (703 bare domains incl. the platform's own `cyberdudebivash.com`/`.in`, 243 filenames e.g. `composer.js`, 75 advisory URLs e.g. cisa.gov, 9 malformed) |
| 2 | same, `_mask_item_for_public_report` + `agent/apex_intelligence_upgrade.py` (3 sites) | Public mask sets `iocs=[]`; narrative engines read `len(item["iocs"])` → "0" | **Root cause of the 7/0/1 split**: headline = raw count (render_report reads the overwritten list), executive/narrative = masked 0, enhancer = placeholder row |
| 3 | `scripts/report_enhancer.py::build_ioc_table_section` | Inserts a `"No IOCs in current data feed"` row, then `len(iocs)` counts it → "Total IOCs: 1"; every non-generated IOC labelled `OBSERVED` | Reproduced: before = `IOCs: 0` and `IOCs: 1` on the same page |
| 4 | `generate_intel_reports.py` S1 | Internal report key rendered as **"STIX ID"** | 22,379 / 22,433 published pages; keys are `intel--<hex>` or `intrusion-set--<uuid>` |
| 5 | `scripts/apex_mitre_attack_engine.py` | Library key `T1190.001` ("SQL Injection") and `CWE-89 → T1190.001`; hard-coded "ATT&CK v16"; hypothesis text stored in a field named `observed_behavior` | Pinned dataset: `T1190` has no sub-techniques. Published in 282 report pages + 23 `api/*.json` files |
| 6 | `scripts/apex_sigma_templates.py` (+ byte-identical root duplicate) | Sigma tag built with `.replace(".", "")` → `attack.t1059001` (invalid); unknown IDs passed through | verified by test |
| 7 | `generate_intel_reports.py` S9 → `agent/apex_intelligence_upgrade.py::_KILL_CHAIN_TEMPLATES`; `report_enhancer.py::build_kill_chain_section` | Fixed 7-step templates (implant, persistent C2, **60-second beacon**, DoH, exfiltration) for every advisory | 21,191 pages |
| 8 | `report_enhancer.py::build_defensive_matrix_section` / `_mitre_name` | Falls back to T1566.001 / T1078 / T1041 when none mapped; every row `HIGH`; non-official names ("LSASS Memory Credential Dump") | code |
| 9 | `generate_intel_reports.py` (severity/exec/urgency/S4) | Pipeline composite label shown as severity; `INFORMATIONAL — apply patch in routine cycle` for any CVE at LOW/UNKNOWN; S4 deadline from composite risk | Real manifest: **206 of 226 CVSS-scored vulnerabilities (91%) carry a severity label contradicting their own CVSS band**, incl. 22 labelled LOW with CVSS ≥ 9.0; **no record carries a CVSS vector**, so `severity_epss_truth` (which requires a verifying vector) cannot correct any of them. 909 unrated vulnerability records carry a severity label |
| 10 | `generate_intel_reports.py::render_report` | Header KEV via `bool()`; body via canonical `_kev_confirmed_check` | legacy `"NO"` string read as confirmed in the header |
| 11 | `generate_intel_reports.py` regulatory (`_reg_flag`, `reg_note`, `_render_regulatory_matrix`) | "YES — Breach notification obligations may apply", `APPLIES` badge on GDPR/DPDP/NIS2 unconditionally; invented KEV "3–14 days" | 22,379 pages |
| 12 | `generate_intel_reports.py` S11/S18/S20 | Unattributed cluster presented as "tracking cluster"; "Rules are syntax-validated" / "validated rule packs"; BIS "FAIR-aligned" with `float(cvss or 0)` | code |
| 13 | `report_enhancer.py::_tier_gate` | "Gating" = CSS `filter:blur` over **content still in the served HTML** (view-source/print/scrape bypass); IOC values ungated | 21,187 pages |
| 14 | `report_enhancer.py` | Unescaped feed text in HTML; `float(x or 0)` for CVSS/EPSS; EPSS treated as 0–1 while generator uses percent; "CVSS v3.1" asserted though no version is recorded; non-idempotent (2 stray newlines per re-run) | tests |
| 15 | `agent/apex_intelligence_upgrade.py` narrative bank | Unsupported predictions stated as fact: "lateral movement … within 4–6 hours", "dark web within 24–48 hours", "200+ days on average", "treat as CRITICAL regardless of CVSS" (keyword severity override); "attribution maintained across prior campaign activity" for `CDB-UNATTR-*` | code |

**Found, not changed (decisions for the operator):**
* `scripts/ioc_truth_engine.py` classifies *every* bare lowercase two-label domain (`evil.com`, `c2.evil.ru`) as `software_component` → fail-closed, genuine malicious bare domains are also dropped (recall loss). Left as is: a domain in an advisory body is not evidence of malice, and fixing recall needs a provenance/maliciousness signal, not a syntax rule.
* Apex upgrade module's static technique table contains `T1562`, `T1562.001`, `T1574.002`, which are **absent from the pinned dataset** (it uses the newer `stealth`/`defense-impairment` tactic names; likely restructured upstream). They are now suppressed from published output if ID-shaped; the table itself is untouched pending a remap review.
* The ATT&CK sync (`data/attck/enterprise-attack.json`) records no release number, so **no version is claimed anywhere**; Navigator `versions.attack:"15"` remains and is unverified. Recommend recording `x_mitre_version` in `true_intel_ingestor.py`.
* `sentinel-blogger.yml`, `p*_production_certification.py`, KV/D1/R2, auth, payment: untouched.
* A byte-identical duplicate `apex_sigma_templates.py` sits at the repo root (no importers; certifier checks existence). Classified MERGE; not deleted (deprecation policy).

## 2. Architecture (what changed, what was reused)

```
feed record ─► dossier_integrity (single authority, stdlib, side-effect free)
                 ├─ qualify_iocs()      ► reuses ioc_truth_engine.classify_ioc   (no new classifier)
                 ├─ validate_technique() ► reads pinned data/attck/enterprise-attack.json
                 ├─ severity_basis()    ► reuses severity_epss_truth.cvss_rating / verified_cvss
                 ├─ valid_stix_id(), tlp_public_conflict(), source_stated_conditions()
                 ▼
   generate_intel_reports.py (20-section page) ─► report_enhancer.py (appended cards)
        both consume the SAME qualified collection ⇒ one IOC count per record
```
No new reporting engine was created (the Python dossier lineage and the JS Evidence-Registry lineage remain uncoupled — that unification is **not** done here and is the recommended next architectural step; see §8).

Behaviour contract introduced:
* IOC count = `len(qualified)`; empty = 0; no placeholder rows; AI-generated candidates never counted; evidence state is `SOURCE_REPORTED` / `UNVERIFIED` — `OBSERVED` only with an explicit marker **and** a source.
* Severity: non-vuln → pipeline label; KEV → pipeline label (may only be *raised* to the CVSS band); CVSS present → CVSS band of the reported score (labelled "vector unavailable to verify") with the composite label disclosed when it disagrees; otherwise **UNRATED** + "PRIORITY NOT DETERMINED … CUSTOMER EXPOSURE: UNKNOWN", quoting the source's own stated attack conditions. CVSS 0/blank = missing.
* ATT&CK: ID-shaped values validated against the pinned dataset; undefined sub-technique → parent; unknown → suppressed; names pass through; all mappings flagged `ANALYST_INFERENCE` / `HYPOTHESIS_NOT_OBSERVED`.
* Kill chain: only source-provided phases; else "OBSERVED ACTIVITY: NONE REPORTED" + a labelled hypothetical limited to what the advisory states.
* Gating is server-side (content not emitted below tier); feed text HTML-escaped.
* TLP: GREEN/AMBER/RED on a public page is flagged "PUBLICATION REVIEW REQUIRED" and the source label is preserved (not silently relabelled; not blocked — policy decision for the operator).

## 3. Before / after (same extractor, original vs fixed code, 8 real records)
Full data: `before_after_comparison.json`. Examples: `examples/*.html.txt` (rated + KEV-listed; unrated low-evidence) — full rendered pages stored as `.html.txt` so the repo-wide commercial-contract verifier (which scans every `*.html`) does not treat evidence artifacts as site pages; rename to `.html` to view in a browser.

| Record | CVSS | IOC count shown (before → after) | Severity shown | Action shown after |
|---|---|---|---|---|
| FortiGate CVE-2025-59718 (KEV) | 9.8 | 5 → 0 | HIGH → **CRITICAL** | IMMEDIATE PATCH REQUIRED |
| CVE-2026-3300 Everest Forms (unauth RCE) | — | 0 and **1** → 0 | LOW → **UNRATED** | PRIORITY NOT DETERMINED; source states “Unauthenticated Remote Code Execution…” |
| Magento PolyShell (unauth upload/RCE) | — | 0 and **1** → 0 | LOW → UNRATED | same |
| WordPress unauth SQLi (400k sites) | — | 0 and **1** → 0 | LOW → UNRATED | same |
| PHP Composer flaws → command exec | — | 2 → 0 | CRITICAL → UNRATED | same |
| GPL Odorizers / Contemporary Controls / org page | — | 5→3, 4→1, 5→0 | MEDIUM (non-vuln) | unchanged |

All 8 before-pages carried the fixed kill-chain text, 3× `APPLIES`, CSS-blur gating and `STIX ID intrusion-set--…`; all 8 after-pages carry none of them.

## 4. Validation (actual commands)

| Command | Result |
|---|---|
| `pytest tests/test_dossier_integrity_p0_721.py tests/test_generate_intel_reports_financial_impact.py` | 137 passed, 2 skipped (skips = golden-eight harness, BLOCKED) |
| same new module run against the **original** source (5 files stashed) | 83 of the then-117 tests failed → tests discriminate (suite has grown since) |
| `python3 scripts/regression_tests.py` | **41/41 PASS** (CLAUDE.md still says 21) |
| `python3 scripts/p33_production_certification.py` / `ci_stats_extract.py p33` | WORLDWIDE_RELEASE, 0 blockers, 21/26 (5 pre-existing warnings) |
| `pytest tests` (≈4,360 collected; 2 modules ignored: need `boto3`, absent here) | 4,324 passed · 24 failed · 1 collection error · 12 skipped — **identical failing set to the original source (§4a)** |
| `pyflakes` on all modified/new files | no undefined names |
| `python3 scripts/p0_721_dossier_integrity_audit.py --reports` | §5 |

Test content (not smoke): negative controls for empty/None/non-list IOCs, CVE refs, advisory URLs, filenames, software/platform domains, private/malformed IPs, duplicates across case/defang/root-dot, AI-generated, forged `observed` markers; ATT&CK valid/sub-technique/malformed/unknown + a sweep over every library keyword and CWE; Sigma tags; Navigator layer; STIX-id grammar (9 cases); severity matrix incl. CVSS band edges, zero/blank CVSS, KEV-raise; TLP; legacy KEV strings; HTML/script injection in title/description/IOC/kill-chain; 6 000-char + NUL + RTL titles; empty/partial records; idempotency; server-side gating; **sweep of 43 sampled production records** + the 8 fixtures, each asserting: one IOC count across every section, no template fabrications, no invalid ATT&CK id (incl. the Navigator data-URI), no internal key as STIX id, severity/action never contradictory, CVSS never shown below its band.

**One existing test was changed**, deliberately: `test_genuine_cve_item_keeps_its_patch_directive` asserted a hard "PATCH WITHIN 14 DAYS" for a CVE with *no CVSS and no KEV* (composite label only). It now supplies `cvss_score: 8.1` (still asserts the deadline) and a new sibling test asserts the unrated variant gets triage, not a deadline.

### 4a. Full-suite comparison
The 24 failures + 1 collection error (`tests/platform_services/test_billing_engine.py`) are **pre-existing**: the same 25 fail identically when the five modified source files are restored to `241cce7fb` (brand-identity strings, dashboard/workflow-pinning contracts, v27/v29 module tests, etc. — unrelated to dossier rendering). Net regressions from this change: **0**. During development the full-suite run also surfaced one isolation bug of mine (a module-level `logging.disable` breaking 8 later `caplog` tests), which was fixed.
Method: full run on changed code → list failures → re-run exactly those ids on stashed original source → set difference. Test side-effects on 4 tracked data files were reverted (not part of this PR).

## 5. Measured state of what is *already published* (not fixed by this PR)
`data/quality/p0_721_dossier_integrity_report.json` (read-only audit; `--strict` exits 1 on any defect):
* 22,380 of 22,433 report pages carry ≥1 pre-fix signature: placeholder IOC row 9,483 · internal key as "STIX ID" 22,379 · unconditional `APPLIES` 22,379 · fixed kill-chain text 21,191 · CSS-blur-gated content 21,187.
* 282 pages and 23 API JSON files contain invalid ATT&CK ids (`T1190.001`, `T1574.002`).
* Manifest: 1,030 non-indicator IOC entries in 456 items; 206/226 severity-vs-CVSS contradictions.

These change only when the pipeline regenerates and redeploys. A passing local test does not certify the live site.

## 6. Reuse report (CLAUDE.md)
| Metric | Result |
|---|---|
| Existing engines reused (called, not re-implemented) | `ioc_truth_engine.classify_ioc`, `severity_epss_truth` (`cvss_rating`, `verified_cvss`, `epss_percent`, `kev_confirmed`), `_kev_confirmed_check`, pinned `data/attck` |
| Routes extended / duplicated | 0 / 0 (no route touched) |
| New modules | `dossier_integrity.py` (thin composition layer), `p0_721_dossier_integrity_audit.py` (observability) — gap: no shared evidence rules existed; 3 renderers each had their own |
| Duplicate engines introduced | 0 |
| Backward compatibility | field names/shapes kept (`observed_behavior`, `iocs` shape, `ioc_count`); `T1190.001` library entry kept as documented deprecated alias → `T1190` |
| Certification chain | intact (P33 WORLDWIDE_RELEASE, 0 blockers) |
| Regression suite | 41/41 |

## 7. Not done / honest limits
* **Detection engineering (Phase 7)**: the public artifact now makes *no* readiness claim and says per-rule validation states are separate (syntax / offline-fixture / customer-environment). No rule generator, fixture harness or `PRODUCTION_READY` gate was built or changed; no Sigma/KQL/SPL/EQL/Suricata/YARA output was validated.
* **STIX / MISP / TAXII exports, PDF, entitlement/tenant paths, payment, Workers**: not audited or changed here (beyond the HTML gate). No interoperability claim is made or supported.
* **Claim ledger / lifecycle states / correction notices / four-product (FLASH…STRATEGIC) dossier architecture / unified contract with the JS lineage**: not implemented. `agent/dynamic_dossier_engine.py` was not wired.
* **KEV/EPSS lookup state** ("not listed" vs "lookup unavailable") is not recorded in the data, so the report says "no KEV listing found" and that absence is not proof of non-exploitation; it cannot say "lookup unavailable".
* Remote CI was not run. `GATE 1` pyflakes undefined-name check was reproduced locally only.
* Pre-existing failures (identical on original source) are listed in §4a.

## 8. Recommended next steps (priority order)
1. Supply the 8 originals → golden harness; regenerate + redeploy (operator-authorized) and run the audit with `--reports --strict` against the regenerated tree; wire `--strict` into CI after regeneration.
2. Record `cvss_vector`, CVSS version, `x_mitre_version`, and KEV/EPSS lookup status in the feed so severity can be *verified* rather than band-derived.
3. TLP policy decision for GREEN/AMBER/RED items on public URLs (block vs relabel after review).
4. Decide the `ioc_truth_engine` bare-domain policy with a provenance signal; remap the 3 obsolete technique ids.
5. Detection-pack validation pipeline, then STIX 2.1 / MISP validator tests on real serialized bundles.
6. Couple the Python dossier lineage to the JS Evidence Registry via a versioned record (ADR), and wire `dynamic_dossier_engine`.
