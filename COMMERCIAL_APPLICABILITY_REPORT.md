# Commercial Applicability Report

**Program:** Project TITAN Stage 20A — Enterprise Commercial Quality Orchestrator (Implementation)
**Date:** 2026-08-07
**Component:** Commercial Applicability Engine — the one genuinely new computation this stage
introduces (per `COMMERCIAL_QUALITY_ORCHESTRATOR_ARCHITECTURE.md` §5 and the audit's confirmed
finding that no prior art for this pattern exists anywhere in the repository).

---

## 1. What It Does

For every commercially-relevant quality dimension, classifies the dimension
against a given item as exactly one of four states:

| State | Meaning | Denominator treatment |
|---|---|---|
| `APPLICABLE` | The dimension genuinely applies to this item; scored `PASS`/`FAIL` exactly as the relevant existing engine already would | Counts toward numerator and denominator |
| `NOT_APPLICABLE` | The dimension cannot meaningfully apply to this item type | **Excluded** from both numerator and denominator — never scored as a failure |
| `UNKNOWN` | Applicability cannot be determined from the data available (e.g. real publication lag, or producing-pipeline metadata this item alone doesn't carry) | Excluded from the composite; surfaced separately as "missing evidence," never silently dropped |
| `EXCLUDED` (whole-item) | The item itself is an unsupported report type (e.g. missing minimum identity fields) | Every dimension is skipped; the item is flagged, not silently scored zero |

This directly implements the architecture's Sec 5.3 rule:

```
composite = (sum of scores for all D where applicable(D,I)) / (count of D where applicable(D,I))
```

as opposed to every existing pattern the governance audit found repository-wide:

```
composite_today = (sum of scores for all D, missing D scored as 0) / (fixed count of all D)
```

---

## 2. The Five Dimensions (per architecture doc §5.2's worked-example table)

| Dimension | Applicability rule implemented | Independently coded in |
|---|---|---|
| MITRE ATT&CK mapping | `NOT_APPLICABLE` unless the item carries a behavioral-evidence signal (actor tag, active exploit/exploit maturity, KEV, exploit refs, PoC/Metasploit availability, kill-chain phases, or a `threat_type` other than a bare vulnerability/patch/advisory) — a bare CVE disclosure has no technique to map | `p39-handlers.js:_hasBehavioralEvidence` / `commercial_quality_orchestrator.py:_has_behavioral_evidence` |
| EPSS score | `NOT_APPLICABLE` if no CVE identifier at all; `UNKNOWN` (not a fabricated FAIL) if the CVE was disclosed < 3 days ago, honoring EPSS's real publication lag; otherwise `APPLICABLE` | `_daysSince` / `_days_since` |
| KEV listing | `NOT_APPLICABLE` only if no CVE identifier; otherwise always `APPLICABLE` — "not on KEV" is itself a meaningful, scoreable signal per the architecture's own explicit instruction that this dimension "should almost never be `NOT_APPLICABLE`" | direct field check |
| IOC presence | `NOT_APPLICABLE` for pure policy/compliance/advisory-only report types; otherwise `APPLICABLE`, scored on `ioc_count`/`iocs.length` | direct field check |
| Detection rule coverage (×7 formats: Sigma, KQL, SPL, Suricata, YARA, Elastic, Snort) | `APPLICABLE`/`PASS` if the format's rule field is present on the item; otherwise `UNKNOWN` (never a guessed `NOT_APPLICABLE`, never a false `FAIL`) — since the producing pipeline's by-design format set is not determinable from a single item in isolation | `DETECTION_FORMATS` map, per-format field lookup |

The **detection-coverage rule was deliberately made more conservative than
the architecture doc's own illustrative example**, which cited
`report_generator.py`'s confirmed Sigma/KQL/SPL-only-by-design behavior as a
basis for marking YARA/Elastic/Suricata/Snort `NOT_APPLICABLE`. This
implementation's own verification found `suricata_rule` populated on real
`api/feed.json` items — directly contradicting a blanket "YARA/Elastic/
Suricata/Snort = NOT_APPLICABLE" rule for *every* report type. Rather than
assert a rule the real data disproves, format absence is scored `UNKNOWN`,
which is itself one of the model's four first-class states and the more
honest answer given the "never fabricate evidence" constraint.

---

## 3. Real Output on This Repository's Data

Verified against the real, governed feed (`api/feed.json`, 71 items) via the
Python orchestrator's actual (non-dry-run) execution this session:

```
Feed items evaluated       : 71
Avg applicability composite: 49.5
Recommendation tiers       : {'ANALYST_REVIEW': 21, 'ENTERPRISE_READY': 8, 'INTERNAL_DRAFT': 42}
Zero-applicable-failure    : 0/71
```

Two fixture-level worked examples (from the JS and Python test suites,
identical inputs, independently-coded engines, confirmed to agree):

**A "rich" item** (CVE with KEV, actor attribution, MITRE mapping, IOCs, and
a Sigma rule): `applicable=5, not_applicable=0, unknown=6` (the 6 unpopulated
detection formats), **composite = 100/100**, tier = `PREMIUM_INTELLIGENCE`.

**A "bare vulnerability disclosure"** (CVE with no actor/exploit/KEV/kill-chain
signal, disclosed in 2020): MITRE correctly `NOT_APPLICABLE` (excluded from
the denominator, not scored as a failure), EPSS `APPLICABLE`/`FAIL` (old
enough that a real gap exists), KEV `APPLICABLE`/`PASS`, IOC
`APPLICABLE`/`FAIL`, 7 detection formats `UNKNOWN`. Applicable set = 3
(EPSS fail, KEV pass, IOC fail), 1 pass → **composite = 33/100** (verified
against the real, committed fixture this session: `{'applicable': 3,
'not_applicable': 1, 'unknown': 7, 'passed': 1, 'failed': 2}`) — correctly
excluding the inapplicable MITRE dimension rather than penalizing the item
for a technique it structurally cannot have.

---

## 4. Independence of the Two Implementations

Per the architecture's Sec 0 point 5 (symmetric-but-independent runtimes),
`computeCommercialApplicability` (JS) and `compute_commercial_applicability`
(Python) are separately written, zero-shared-code implementations of the same
specification — verified by `tests/test_commercial_quality_orchestrator.py::
TestGovernanceFixtures::test_module_never_imports_protected_engine_internals`
and by direct inspection: neither file imports, requires, or otherwise
references the other. Both were exercised against equivalent fixtures in
their respective test suites and produce matching classifications and
composite scores for the same conceptual input, confirming architectural
fidelity without code sharing.

---

## 5. What This Engine Deliberately Does Not Do

- It does not compute a new confidence, trust, or quality *score* — it
  classifies applicability. `scripts/titan_architecture_governance_check.py`'s
  new `check_commercial_orchestrator_no_new_scorer()` mechanically enforces
  that neither implementation defines a `compute*/score*/weight*/rank*`
  function targeting Confidence/Trust/Quality/Certification.
- It does not re-derive the PASS/FAIL judgment for an applicable dimension —
  that judgment mirrors what the existing engines already imply from the same
  fields (e.g. KEV presence, IOC count); it does not introduce a new
  threshold or weighting scheme of its own.
- It does not treat dimension absence as automatic inapplicability (the
  architecture's central warning in §5.2) — every rule above is explicit and
  documented, never inferred from bare absence.
