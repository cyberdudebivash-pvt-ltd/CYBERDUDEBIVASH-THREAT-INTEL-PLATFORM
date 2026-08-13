# REPORT_WRITER_OWNERSHIP_MATRIX

RX-PUB-1 §10 deliverable. Audit of every code path capable of writing into the
production `reports/{year}/{month}/{intel_id}.html` keyspace served at
`https://intel.cyberdudebivash.com/reports/...`.

Compiled 2026-08-12 as part of the RX-PUB-1 publication-integrity investigation,
triggered by a confirmed live staleness incident on `intel--20282e88b1f49bf2`
and `intel--f43ac4fcc6f30452` (see `REPORT_X_RX_PUB1_PRODUCTION_CERTIFICATION.md`
for the incident writeup once published).

## Writers

| Writer | File | Function | Report classes | Output path pattern | Engine marker | Production reachable? | Fallback condition | Can overwrite authoritative output? | Certification gate? | Current status |
|---|---|---|---|---|---|---|---|---|---|---|
| **Primary pipeline generator** | `scripts/generate_intel_reports.py` | `render_report()` / `build_report_sections()`, invoked via `main()` | All manifest items (CVE, phishing, breach, ransomware, general intel) | `reports/{yyyy}/{mm}/{id}.html` | `CDB-REPORT-ENGINE: generate_intel_reports.py v{PLATFORM_VERSION}` | Yes — via R2 sync (STAGE 3.5) after local write | None — "Zero-skip policy," unconditionally regenerates every item in the current `data/stix/feed_manifest.json` window (~250 items) on every pipeline run | Yes — this is the canonical/authoritative writer | `STAGE 3.3 - Report Validation Gate (HARD FAIL)` checks output exists/well-formed after this writer runs | **Verified correct** as of current `main` (RX-PR1 fix confirmed via two independent reproductions, including a full 250-item manifest run matching the real CLI invocation) |
| **Internal/God-Mode generator** | `scripts/report_generator.py` | `generate_reports_from_manifest()` → `generate_report()` → `_generate_internal()` | Same manifest population, run as a second pass | Same path pattern (`REPORTS_BASE / yyyy / mm / id.html`) | `CDB-REPORT-ENGINE: report_generator.py v161.x` | Runs in-pipeline as "STAGE 3.2 - Generate Internal HTML Reports," **after** the primary generator in current stage ordering | **GOD MODE PROTECTION GATE**: skips (does not overwrite) any existing file that is either (a) an `id` in the 2-entry `GODMODE_PROTECTED_IDS` allowlist (permanent skip), or (b) `>= GODMODE_MIN_SIZE_BYTES` (**60,000 bytes**) **and** less than `GODMODE_MAX_AGE_DAYS` (**7 days**) old — also skips any file `> 2000 bytes` that passes a basic valid-HTML signature check, independent of the God Mode gate | **Yes, in principle** — if this script's own pass ever ran *before* `generate_intel_reports.py` in a different ordering (or under a race), its 60KB/7-day skip logic would leave a stale, oversized report untouched even though a fresher, correct, but differently-sized report was about to be written by the primary generator. In the *current* stage ordering this is a no-op (it correctly finds an already-fresh file and skips it) | None dedicated — relies on the primary generator's `STAGE 3.3` gate having already run first | **Not implicated** in the current live incident (traced: runs after the primary generator in the current stage order, so it only ever sees already-fresh files) but **flagged as a structural risk** — its skip logic is silent (info-level log only) and has no gate verifying its precondition (that the primary generator already ran) actually held |
| **Worker live-request fallback** | `workers/intel-gateway/src/index.js` | `generateIntelReport(item, reqPath, items)`, called from two request-handling branches (~line 4183, ~line 4244) | Any item resolvable via `findItemBySlug` for a requested report path with no R2 object found | `reports/{yyyy}/{mm}/{filename}` (Worker-computed) | **None** — no `CDB-REPORT-ENGINE` comment marker found in the Worker's HTML output | Yes — **directly and immediately**, via `env.REPORTS_R2.put(r2Key, html, ...)` inside `ctx.waitUntil(...)`, triggered synchronously by an ordinary customer/crawler HTTP GET | Fires whenever a request resolves to a known item but no R2 object is found under any probed year/month path | **Yes** — this is a live, independent, JavaScript re-implementation of report rendering that writes directly to the same R2 bucket/prefix the Python pipeline targets, entirely outside CI, CI gates, and the RX-PR1 fix (confirmed: no "PATCH WITHIN"/"WHAT TO DO TODAY" text exists anywhere in this function, so it is not a byte-for-byte duplicate of the Python template, but it independently owns the same keyspace with no coordination) | **None** — this path has no certification/validation gate of any kind; it is a live-serving fallback, not a pipeline stage | **Confirmed live and independently addressable** — ruled out as the source of the *current* stale-content incident (its output doesn't match the buggy Python text pattern seen live), but it is an **unmitigated Single-Source-of-Truth violation**: any transient R2 read miss for an otherwise-published report can cause this path to silently overwrite the pipeline's authoritative output with a different rendering, with zero observability and zero certification coverage |

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
