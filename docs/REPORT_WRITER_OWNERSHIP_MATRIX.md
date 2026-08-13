# REPORT_WRITER_OWNERSHIP_MATRIX

RX-PUB-1 §10 / RX-PUB-A0 deliverable. Audit of every code path capable of
writing into the production `reports/{year}/{month}/{intel_id}.html`
keyspace served at `https://intel.cyberdudebivash.com/reports/...`.

Compiled 2026-08-12 as part of the RX-PUB-1 publication-integrity investigation,
triggered by a confirmed live staleness incident on `intel--20282e88b1f49bf2`
and `intel--f43ac4fcc6f30452` (see `docs/RX_PUB_A0_INCIDENT_ROOT_CAUSE.md` for
the incident writeup). **Updated 2026-08-13 (RX-PUB-A0 Section 15-17):**
Writers B and C have been stripped of write authority (PRs merged/pending —
see status column). A fourth call site (§Writer A.1) was found during that
work and is documented below.

## Writers

| Writer | File | Function | Report classes | Output path pattern | Engine marker | Production reachable? | Fallback condition | Can overwrite authoritative output? | Certification gate? | Current status |
|---|---|---|---|---|---|---|---|---|---|---|
| **Primary pipeline generator** | `scripts/generate_intel_reports.py` | `render_report()` / `build_report_sections()`, invoked via `main()` | All manifest items (CVE, phishing, breach, ransomware, general intel) | `reports/{yyyy}/{mm}/{id}.html` | `CDB-REPORT-ENGINE: generate_intel_reports.py v{PLATFORM_VERSION}` | Yes — via R2 sync (STAGE 3.5) after local write | None — "Zero-skip policy," unconditionally regenerates every item in the current `data/stix/feed_manifest.json` window (~250 items) on every pipeline run | Yes — this is the canonical/authoritative writer | `STAGE 3.3 - Report Validation Gate (HARD FAIL)` checks output exists/well-formed after this writer runs | **Verified correct** as of current `main` (RX-PR1 fix confirmed via two independent reproductions, including a full 250-item manifest run matching the real CLI invocation) |
| **Internal/God-Mode generator** | `scripts/report_generator.py` | `generate_reports_from_manifest()` → ~~`generate_report()`~~ (removed) | Same manifest population, run as a second pass | Same path pattern (`REPORTS_BASE / yyyy / mm / id.html`) | `CDB-REPORT-ENGINE: report_generator.py v161.x` (function still exists, just no longer called from the batch path) | Runs in-pipeline as "STAGE 3.2 - Generate Internal HTML Reports," **after** the primary generator in current stage ordering | **GOD MODE PROTECTION GATE** unchanged for the skip decision, but the fallthrough no longer generates — it logs `[not-authoritative]` and counts, never writes | **FIXED (2026-08-13)** — `generate_reports_from_manifest()` no longer calls `generate_report()` under any condition (missing/malformed/below-threshold all now just log + count as `not_authoritative`). Regression tests: `tests/test_report_generator_not_authoritative.py`, confirmed to fail against pre-fix code. | STAGE 3.3 (`validate_reports.py`, HARD FAIL) now correctly surfaces a genuinely missing/malformed report instead of a second engine silently papering over it | **RESOLVED for the batch path.** See Writer A.1 above for a separate, still-open call site using the same underlying engine. |
| **Worker live-request fallback** | `workers/intel-gateway/src/index.js` | `generateIntelReport(item, reqPath, items)`, called from two request-handling branches | Any item resolvable via `findItemBySlug` for a requested report path with no R2 object found | Previously wrote to `reports/{yyyy}/{mm}/{filename}`; now serves only, writes nothing | **None** — no `CDB-REPORT-ENGINE` comment marker found in the Worker's HTML output | Previously: yes, via `env.REPORTS_R2.put(...)` in `ctx.waitUntil(...)`. **Now: no R2 write of any kind on this path.** | Fires whenever a request resolves to a known item but no R2 object is found under any probed year/month path | **FIXED (2026-08-13)** — both `ctx.waitUntil(env.REPORTS_R2.put(...))` calls removed. The Worker still renders and serves a live response (`Cache-Control: no-store`) so an approved item never hard-404s while waiting for its canonical artifact, but that response is never persisted into the canonical key. Confirmed zero `REPORTS_R2.put` call sites remain anywhere in `index.js`. Regression test: `workers/intel-gateway/src/__tests__/reports-canonical-write-guard.test.js` (static source-invariant + customer-behavior-preserved check), wired into the `deploy-worker.yml` HARD FAIL gate, confirmed to fail against pre-fix code. | None dedicated to this specific path; the existing publication gate (which already ran earlier in the request) is unaffected | **RESOLVED.** No longer a Single-Source-of-Truth violation — `scripts/generate_intel_reports.py` (plus the Writer A.1 initial-write path, tracked separately) are the only remaining writers of `reports/*.html`. The full Section 17 "preferred production architecture" (explicit publication-state-driven response codes for PENDING/WITHHELD/REJECTED/FAILED/UNKNOWN) remains future work — this fix satisfies the mission's non-negotiable ("no canonical R2 write from normal unauthenticated customer/crawler traffic") without it. |

## Writer A.1 — initial-write call site (found during RX-PUB-A0 Section 16 work)

`agent/export_stix.py` (inside its `_update_manifest()`-adjacent STIX entry
creation path) imports `report_generator.generate_report` directly (not
`generate_reports_from_manifest`) and calls it synchronously, with a HARD
FAIL (`RuntimeError`) if generation fails, when a **brand-new** advisory is
first ingested — a deliberate v134.0 P0 fix ("Every advisory MUST have a
valid HTML report file on disk. Non-negotiable") so a newly-ingested item's
`report_url` never 404s in the window before the next full pipeline run's
`generate_intel_reports.py` pass regenerates it.

This is a genuine, currently-live 4th writer path using `report_generator.py`'s
own separate rendering engine (`_build_html()` / `_generate_internal()` —
the same functions Writer B's batch path called, and which RX-PUB-A0
Section 16 deliberately left in place, only removing the *batch*
(`generate_reports_from_manifest`) caller's authority to invoke them). It was
**not modified in the RX-PUB-A0 Section 15-17 PR** — deliberately: ripping it
out without a replacement risks reintroducing the exact "brand-new item
404s until the next pipeline run" regression v134.0 already fixed once,
which would violate the mission's no-regression requirement. It remains
open as follow-up work, to be resolved via Option A/B/C (most likely: route
it through `generate_intel_reports.py`'s renderer instead of
`report_generator.py`'s, so there is truly one rendering engine, not two —
scoped separately since it touches the ingestion hot path, not just batch
regeneration).

## Required invariant (RX-PUB-1 §10)

> One report key has one authoritative writer for a given release/version. Fallback writers must not silently overwrite newer, higher-quality output.

**Current compliance: PARTIAL, NOT CERTIFIED.**

- `generate_intel_reports.py` is correctly the sole *intended* authoritative writer in the current stage ordering, and its output is currently verified correct.
- `report_generator.py`'s God Mode gate is currently harmless only because of an *implicit, unenforced* ordering assumption (it must run after the primary generator). Nothing in the codebase asserts or gates this ordering; a future stage reorder, a partial/retried pipeline run, or a manual invocation of `report_generator.py` alone could reintroduce silent staleness via its own skip logic.
- The Worker's `generateIntelReport()` fallback is a **second, fully independent rendering implementation with unmediated write access to the same keyspace**, reachable by ordinary customer traffic, with no certification gate, no engine marker, and no coordination with the Python pipeline's publication state. This is the most severe finding in this matrix and should be scoped as its own remediation item (candidate: gate the Worker fallback behind an explicit "authoritative pipeline has not yet published this item" signal rather than "R2 GET returned 404," and/or stamp its output with its own engine marker so `STAGE 3.6.5 - Report Engine Consistency Gate` can actually observe when it fires in production).

## Open item

The live staleness incident on `intel--20282e88b1f49bf2` (confirmed in-window,
confirmed correctly regenerated locally by the primary generator using current
`main`, confirmed **not** re-uploaded to R2 despite a clean, error-free STAGE 3.5
sync run and a content-length mismatch that should have forced re-upload under
`aws s3 sync`'s default size+mtime comparison) is **not explained by any writer
in this matrix** as of this writing. Direct R2 object-metadata inspection
(Cloudflare dashboard/API) is required to determine whether the object's actual
`Last-Modified` timestamp predates or postdates the STAGE 3.5 sync window
(2026-08-12 20:08:01-20:19:52 UTC) — see the RX-PUB-1 certification report's
incident section once that check is complete.
