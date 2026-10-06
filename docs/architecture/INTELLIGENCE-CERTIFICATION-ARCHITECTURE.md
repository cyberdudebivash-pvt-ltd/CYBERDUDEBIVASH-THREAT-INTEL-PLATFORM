# Intelligence Certification Architecture

**Status:** current as of Phase 2 (2026-08-21). Documents the actual code, not aspirational design — every claim below traces to a specific file and function.

---

## 1. Why this document exists

Phase 1 (PR #219) found the platform's primary release gate, `p33_production_certification.py`, silently measuring a 3-month-stale feed snapshot instead of the live production feed. Phase 2 found the identical defect, independently, in 12 more scripts — including `p25_enterprise_trust_gate.py`, whose name doesn't even match the naming convention used to search for the others. The root cause both times was structural: every certification script decided for itself which file was "the feed," with no shared, canonical definition to get right or wrong consistently.

This document describes the canonical resolution architecture Phase 2 introduced to close that class of bug, and the schema-compatibility and freshness conventions that go with it.

---

## 2. Canonical feed registry

Single source of truth: **`scripts/p38_shared_validators.py`**, `FEED_REGISTRY`.

Every known feed file in the repository is registered under a short key, with its path, purpose, and an explicit `deprecated` flag:

| Key | Path | Role |
|---|---|---|
| `live` | `api/feed.json` | **The production feed.** What `intel.cyberdudebivash.com` actually serves. This is what every certification/release gate must measure. |
| `root` | `feed.json` (repo root) | A periodically-regenerated snapshot. **Not the live production feed** — structurally different from `live` even when its item count and dates look similar (missing deep-enrichment fields present in `live`). Historically the source of the stale-feed bug class. |
| `research` | `data/feed.json` | A broader, non-CVE-primary research feed. Was 3 months stale at time of the Phase 1 finding; not guaranteed fresh. |
| `baseline`, `gold`, `silver`, `standard`, `executive`, `trial`, `enterprise`, `mssp`, `public` | various | Commercial-tier derived feeds. Legitimate, intentionally-different datasets — a script reading one of these on purpose is not the stale-feed bug. |

A certification script must never hardcode a path to any of these files directly. It resolves its input through the accessor below.

---

## 3. Canonical feed resolver

```python
from p38_shared_validators import get_certification_feed, StaleFeedError

feed = get_certification_feed("live")   # default key is "live"
feed.items          # List[Dict] — the feed content
feed.item_count      # len(feed.items)
feed.generated_at    # from the feed's own metadata, or the max per-item timestamp
feed.age_hours        # None if generated_at couldn't be determined
feed.is_fresh          # age_hours <= freshness_tolerance_hours (default 48h)
feed.schema_version   # if present
feed.fingerprint       # sha256 of the sorted id set, first 16 hex chars — for drift detection
```

**Contract:**
- `feed_key` defaults to `"live"`. A script that intentionally measures a different registered feed (a commercial tier, for example) must pass that key explicitly and say why in its own header comment.
- **Explicit failure, never silent fallback.** If the resolved path is missing or unreadable, `get_certification_feed` raises `StaleFeedError`. It does **not** fall back to a different file. This is the direct fix for the original defect class: the old pattern (`try: load(live) except: load(fallback)`, or a candidate list that tried the stale file first) is exactly what let a script silently start measuring the wrong dataset with no signal that anything had changed.
- Callers that want graceful degradation (e.g. a gate that should report "0 items" rather than crash when the feed is genuinely absent) catch `StaleFeedError` explicitly at the call site and decide what "no feed" means for that gate — the resolver itself never decides that silently.

**Who uses it today:** all 13 scripts fixed in Phase 2 (`p25`, `p27`–`p32`, `p34`–`p36`, `manifest_integrity_system.py`, `source_diversity_checker.py`, `confidence_calibrator.py`), plus `p38_production_certification.py` (which originated the pattern this was generalized from). `p33` and `p37` resolve `api/feed.json` directly with their own inline freshness comment predating this module — functionally equivalent, not yet migrated (Principle 1: don't touch working, already-correct code without cause).

---

## 4. Freshness

`get_certification_feed` computes `age_hours` from, in order of preference:
1. A top-level `generated_at` field on the feed file itself.
2. The maximum of `processed_at` / `timestamp` / `published_at` across all items, if no top-level field exists.

`is_fresh` compares this against `freshness_tolerance_hours` (default 48h, overridable per call). A script that wants to hard-block on stale input checks `feed.is_fresh` after resolving and fails its own gate explicitly — freshness enforcement is a per-caller decision, not baked into the resolver, because different certification scripts have legitimately different tolerance (a real-time trust gate and a weekly source-fabric audit don't need the same threshold).

No certification script currently hard-blocks on `is_fresh == False`. This is a known gap (see §8).

---

## 5. Schema compatibility — current vs. legacy fields

Some fields were renamed as the schema evolved; the old names are kept populated on older items (Deprecation Instead of Deletion) rather than removed. Certification logic must check current fields first and fall back to legacy ones — never the legacy field alone, which is exactly the bug Phase 1 and Phase 2 both found repeatedly.

Canonical accessors, `scripts/p38_shared_validators.py`:

| Accessor | Current field(s) | Legacy fallback |
|---|---|---|
| `has_mitre_coverage(item)` | `attck_technique_ids`, `attck_techniques` | `mitre_tactics`, `ttps` |
| `has_source_url(item)` | `source_url` | — (`source` is a *different* field: a short display label, not a link; never a fallback for `source_url`) |
| `get_detection_rules_total(item)` / `has_detection_rules(item)` | `detection_rules_total` (int, coerced defensively — observed as both int and string) | `detection_bundle` (confirmed dead: never written anywhere in the codebase as of Phase 2, kept as a fallback only in case older data resurfaces it) |
| `is_detection_eligible(item)` | `cve_id` / `cve_ids` present, or `vuln_class` present | — (heuristic; see §7) |

`scripts/p38_shared_validators.py`'s `SCHEMA_REGISTRY` additionally documents every known field's type, domain, and `deprecated`/`replacement` metadata (e.g. `actor` deprecated in favor of `actor_tag`, `epss_score` deprecated in favor of `epss`) for scripts that need broader schema-drift detection (`detect_schema_drift()`).

**Rule:** if you are writing a new gate that checks MITRE, source, or detection presence, call the shared accessor. Do not re-derive the current-vs-legacy OR-chain inline — that is precisely how six scripts independently ended up checking only the legacy field.

---

## 6. Stale-feed recurrence guard

`scripts/certification_feed_guard.py`, wired into CI as `sentinel-blogger.yml` STAGE 5.6.2 (hard-fail).

An AST-based static scan over every production certification/quality/validator script: it reconstructs `pathlib` `/` chains and `Path()`/`open()` call arguments, and fails if any resolve to the stale `root` or `research` feed paths without going through the canonical resolver.

Deliberately **not** a text/regex scan. An early draft that flagged any string literal containing `"feed.json"` produced 260 false positives — ordinary log messages like `"Loaded %d items from api/feed.json"` — because it couldn't distinguish code from text. Comments are already invisible to the AST (the tokenizer strips them before parsing), so this version doesn't even trip on `p33`'s own explanatory comment about the bug it already fixed.

**Scope:** the same glob patterns used for the Phase 2 inventory (`*_production_certification.py`, `*certification*.py`, `*validator*.py`, `*quality*.py`), plus an explicit `EXTRA_SCAN` list for confirmed release gates that don't match those patterns (currently: `p25_enterprise_trust_gate.py`, `manifest_integrity_system.py`, `confidence_calibrator.py`, `source_diversity_checker.py`). **This list is a known limitation, not a solved problem** — any future release gate with an unconventional name is invisible to this guard until someone adds it here. There is no fully general fix for this within static analysis; the mitigation is process (any new certification-shaped script should be added to `EXTRA_SCAN` on introduction).

**`EXEMPT_FILES`** documents every case where the guard's static reconstruction produces a false positive on code that is actually correct (a variable like `_API = _ROOT / "api"` the guard can't trace, or a script that deliberately and transparently processes multiple feeds as separately-labelled entries rather than substituting one for another) — each entry has a one-line justification in the script itself, verified by direct reading, not assumed.

---

## 7. Detection eligibility

There is no first-class `report_type` or `detection_applicable` field in the current schema. `is_detection_eligible()` uses CVE-reference or `vuln_class` presence as a proxy — confirmed, by direct inspection during the Phase 2 detection-coverage investigation, to track which items the real generator (`detection_bundle_injector.py`) actually treats as in-scope. This is a heuristic, not a guarantee: a generic/news item could theoretically carry a `vuln_class` without genuinely warranting a detection rule, and vice versa. Certification gates that report detection coverage publish **both** the raw percentage (over the full feed) and the eligible-subset percentage, rather than picking one — see `p33` G20 and the equivalent gates in `p29`–`p32`.

A real `report_type`/`detection_applicability` field, set at ingestion or enrichment time, would make this exact instead of inferred. Not implemented — flagged as a P2 gap.

---

## 8. P25 / P33 relationship

`p25_enterprise_trust_gate.py` and `p33_production_certification.py` are independent code paths that both certify the live feed, from different angles: P25 is a 10-gate enterprise trust check (confidence, severity distribution, IOC/TTP coverage, report-URL completeness, plus chained checks against P21–P24's own reports); P33 is a 26-gate production certification with its own overlapping-but-not-identical set of checks, and additionally chains to P25, P28, P30, P31, P32's certification reports as gates in its own right (`G10`–`G14`).

This chaining means a real data-quality regression in one script can cascade through several downstream tiers' pass/fail status — this is intentional (a genuinely broken upstream signal should propagate), not a bug, but it means a single root-cause content issue can appear as multiple simultaneous gate failures across P27–P33. When investigating a cluster of failures, check whether they share a common upstream cause (as documented in the Phase 2 audit, §10.7) before treating them as independent defects.

Neither script is more "authoritative" than the other for a given dimension they both measure — they are corroborating, independently-coded evidence. When Phase 1 found P33 falsely certifying and P25 was later found to have the identical stale-feed bug, the two facts corroborated the same conclusion (a systemic measurement-integrity gap) via two different code paths — which is part of why the Phase 2 fix targeted the pattern generally rather than patching one script.

---

## 9. Generated certification reports

Every certification script writes its report to `data/quality/<script>_report.json` (or a script-specific filename — see each script's own `_OUT`/`OUTPUT_PATH` constant). Reports are never hand-edited; they are regenerated by re-running the script against the current feed. `scripts/ci_stats_extract.py` provides a stable `(tier, blocker_count, item_count, ...)` extraction tuple per P-layer key for CI steps that need a compact summary without parsing the full report — this shape is part of each script's backward-compatibility contract and was preserved unchanged by every Phase 2 fix (verified per script: same top-level keys, same meaning, only the underlying feed source changed).

---

## 10. CI enforcement

- `sentinel-blogger.yml` STAGE 5.6.2 — stale-feed recurrence guard (§6), hard-fail.
- `sentinel-blogger.yml` STAGE 5.5 — `validate_repo.py`, the hard schema-validation gate (encoding, YAML, Python syntax, JSON validity, intel-schema V1–V11 including the report/source URL contract from Phase 2 §10.2). Deliberately kept dependency-free and untouched by the certification-resolver refactor — it is a "NO AUTO-HEAL" final gate, and `regression_tests.py` T03 asserts its exact output string, so its risk profile does not justify importing the shared module for what would be a pure style consolidation.
- `sentinel-blogger.yml` STAGE 5.6 — `regression_tests.py`, the 21-test permanent anti-regression suite (T01–T21).
- Each individual P-layer certification stage (STAGE 3.93.x for P21–P29, 3.96 for P31, 3.97 for P32, 3.98 for P33, 3.99–4.04 for P34–P38, 5.9.5 for P40) runs `continue-on-error: true` at the workflow level — a certification gate reporting BLOCKED does not by itself fail CI. This is intentional: certification gates are observability, not deployment blockers, except for the two hard gates above (`validate_repo.py` and `regression_tests.py`) and the new stale-feed guard, which are structural-integrity checks rather than content-quality scores.

---

## 11. Production verification

Repository canonical feed (`api/feed.json`) is verified against `https://intel.cyberdudebivash.com/api/feed.json` by fetching the live endpoint and comparing item count, id-set fingerprint, and `generated_at`. As of the last Phase 2 verification: identical (500 items, same fingerprint, same `generated_at`). The live *public* API response additionally strips premium fields (`report_url`, `pdf_url`, `internal_report_url`, etc.) and adds paywall markers — this is intentional commercial tier-gating in the Cloudflare Worker, not a data-sync discrepancy, and should not be mistaken for one in future verification passes.
