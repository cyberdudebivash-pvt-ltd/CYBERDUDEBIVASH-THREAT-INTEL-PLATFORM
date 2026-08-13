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
work and is documented below. **Updated 2026-08-13 (RX-PUB-A0.4 Phase 3):**
Writer A.1 is now closed — see the updated §Writer A.1 section.

## Writers

| Writer | File | Function | Report classes | Output path pattern | Engine marker | Production reachable? | Fallback condition | Can overwrite authoritative output? | Certification gate? | Current status |
|---|---|---|---|---|---|---|---|---|---|---|
| **Primary pipeline generator** | `scripts/generate_intel_reports.py` | `render_report()` / `build_report_sections()`, invoked via `main()` | All manifest items (CVE, phishing, breach, ransomware, general intel) | `reports/{yyyy}/{mm}/{id}.html` | `CDB-REPORT-ENGINE: generate_intel_reports.py v{PLATFORM_VERSION}` | Yes — via R2 sync (STAGE 3.5) after local write | None — "Zero-skip policy," unconditionally regenerates every item in the current `data/stix/feed_manifest.json` window (~250 items) on every pipeline run | Yes — this is the canonical/authoritative writer | `STAGE 3.3 - Report Validation Gate (HARD FAIL)` checks output exists/well-formed after this writer runs | **Verified correct** as of current `main` (RX-PR1 fix confirmed via two independent reproductions, including a full 250-item manifest run matching the real CLI invocation) |
| **Internal/God-Mode generator** | `scripts/report_generator.py` | `generate_reports_from_manifest()` → ~~`generate_report()`~~ (removed) | Same manifest population, run as a second pass | Same path pattern (`REPORTS_BASE / yyyy / mm / id.html`) | `CDB-REPORT-ENGINE: report_generator.py v161.x` (function still exists, just no longer called from the batch path) | Runs in-pipeline as "STAGE 3.2 - Generate Internal HTML Reports," **after** the primary generator in current stage ordering | **GOD MODE PROTECTION GATE** unchanged for the skip decision, but the fallthrough no longer generates — it logs `[not-authoritative]` and counts, never writes | **FIXED (2026-08-13)** — `generate_reports_from_manifest()` no longer calls `generate_report()` under any condition (missing/malformed/below-threshold all now just log + count as `not_authoritative`). Regression tests: `tests/test_report_generator_not_authoritative.py`, confirmed to fail against pre-fix code. | STAGE 3.3 (`validate_reports.py`, HARD FAIL) now correctly surfaces a genuinely missing/malformed report instead of a second engine silently papering over it | **RESOLVED for the batch path, and for Writer A.1** (RX-PUB-A0.4 Phase 3, see §Writer A.1 below) — no remaining production call site invokes this engine's rendering functions at all. |
| **Worker live-request fallback** | `workers/intel-gateway/src/index.js` | `generateIntelReport(item, reqPath, items)`, called from two request-handling branches | Any item resolvable via `findItemBySlug` for a requested report path with no R2 object found | Previously wrote to `reports/{yyyy}/{mm}/{filename}`; now serves only, writes nothing | **None** — no `CDB-REPORT-ENGINE` comment marker found in the Worker's HTML output | Previously: yes, via `env.REPORTS_R2.put(...)` in `ctx.waitUntil(...)`. **Now: no R2 write of any kind on this path.** | Fires whenever a request resolves to a known item but no R2 object is found under any probed year/month path | **FIXED (2026-08-13)** — both `ctx.waitUntil(env.REPORTS_R2.put(...))` calls removed. The Worker still renders and serves a live response (`Cache-Control: no-store`) so an approved item never hard-404s while waiting for its canonical artifact, but that response is never persisted into the canonical key. Confirmed zero `REPORTS_R2.put` call sites remain anywhere in `index.js`. Regression test: `workers/intel-gateway/src/__tests__/reports-canonical-write-guard.test.js` (static source-invariant + customer-behavior-preserved check), wired into the `deploy-worker.yml` HARD FAIL gate, confirmed to fail against pre-fix code. | None dedicated to this specific path; the existing publication gate (which already ran earlier in the request) is unaffected | **RESOLVED.** No longer a Single-Source-of-Truth violation — `scripts/generate_intel_reports.py` is now the sole remaining writer of `reports/*.html` (Writer A.1's initial-write path was closed in RX-PUB-A0.4 Phase 3, see §Writer A.1 below — it no longer writes anything). The full Section 17 "preferred production architecture" (explicit publication-state-driven response codes for PENDING/WITHHELD/REJECTED/FAILED/UNKNOWN) remains future work — this fix satisfies the mission's non-negotiable ("no canonical R2 write from normal unauthenticated customer/crawler traffic") without it. |

## Writer A.1 — initial-write call site (found during RX-PUB-A0 Section 16 work, closed in RX-PUB-A0.4 Phase 3)

**RESOLVED (2026-08-13).** `agent/export_stix.py`'s `_update_manifest()` no
longer imports or calls `report_generator.generate_report` at all — the
entire synchronous-generation-with-HARD-FAIL block is removed. It was Option
B from the mission's own remediation menu: rather than rerouting this call
site to a *different* rendering engine (Option A/C, which would still leave
two call sites invoking rendering logic from two different places in the
pipeline), the call is removed outright, because the availability guarantee
it existed for is already covered by mechanisms this mission's earlier PRs
established:

- `agent/sentinel_blogger.py`'s "Stage 2" (which owns this ingestion path)
  runs **before** "Stage 3.6 html_reports" (`generate_intel_reports.py`) in
  the same `run_pipeline.py` run — see
  `.github/workflows/sentinel-blogger.yml`'s own architecture comment.
  `generate_intel_reports.py`'s "Zero-skip" policy unconditionally
  regenerates every manifest entry, including a brand-new one, moments later
  in that same run — so the canonical engine, not this one, produces the
  real HTML almost immediately regardless of what this block did.
- For the narrow window before that later stage runs (or the rarer case a
  customer requests the URL before the run completes), the Worker's
  live-render fallback (`workers/intel-gateway/src/index.js`,
  RX-PUB-A0 Section 17 / PR #182) already serves a live-rendered response for
  any publication-gate-approved item with no R2 object yet — without
  persisting it, so it never competes with the canonical writer.

`entry["validation_status"]` is now set to `"pending"` (was hardcoded
`"valid"`, which was a false claim once the physical-file guarantee this
block provided was removed) — `scripts/update_validation_status.py`
(STAGE 3.3.5) is the existing, already-documented mechanism that flips it to
`"valid"` once `validate_reports.py` (STAGE 3.3) confirms the file exists on
disk. `report_url` / `internal_report_url` are unaffected — they were always
computed as the prospective canonical path, independent of the removed
generation call.

Regression tests: `tests/test_export_stix_single_writer.py` — proves a new
manifest entry is written with zero HTML files existing anywhere on disk (not
just none at the expected path), proves `report_generator` is unreachable
from the module's source at all (static guard, not just a runtime check), and
proves a burst of new items all succeed the same way. All three confirmed to
fail against pre-fix code via `git stash`.

There is now exactly one call site anywhere in the codebase that invokes
`report_generator.py`'s `_build_html()`/`_generate_internal()` rendering
engine: **none.** Both of that engine's former callers (Writer B's batch path,
closed in RX-PUB-A0 Section 15-17; Writer A.1, closed here) have been removed.
`report_generator.py`'s rendering functions remain defined but are now
fully dead code from a production-write-path perspective — left in place
rather than deleted, per the Deprecation Instead of Deletion policy, since
`generate_report()` is still a plausible target for direct manual/debug
invocation and removing it is not required to close this finding.

## Required invariant (RX-PUB-1 §10)

> One report key has one authoritative writer for a given release/version. Fallback writers must not silently overwrite newer, higher-quality output.

**Updated compliance (2026-08-13, RX-PUB-A0.4 Phase 3): all four writer-count
findings below are now resolved.** Retained as history — do not delete per
the Deprecation Instead of Deletion policy — with each bullet's resolution
noted inline.

- `generate_intel_reports.py` is correctly the sole *intended* authoritative writer in the current stage ordering, and its output is currently verified correct. *(unchanged — always compliant)*
- ~~`report_generator.py`'s God Mode gate is currently harmless only because of an *implicit, unenforced* ordering assumption...~~ **RESOLVED** — moot as a silent-staleness risk now that both of `report_generator.py`'s former callers (Writer B's batch path, and Writer A.1) have been closed; there is no remaining production call site that can trigger its rendering engine at all, ordering-dependent or otherwise.
- ~~The Worker's `generateIntelReport()` fallback is a **second, fully independent rendering implementation with unmediated write access to the same keyspace**...~~ **RESOLVED (PR #182)** — the Worker still renders and serves live responses (customer-facing behavior unchanged, no 404 regression), but no longer writes to R2 on any code path. See the Writers table row above for the regression test that guards this.
- Writer A.1 (`agent/export_stix.py`'s initial-write call site, found after this section was first written) — **RESOLVED (RX-PUB-A0.4 Phase 3)**, see §Writer A.1 above.

**Remaining, still-open item**: this matrix accounts for every writer with a
*known* silent-overwrite mechanism. It does not by itself certify that
`reports/*.html` in R2 and the public HTTP response always match the local
canonical artifact byte-for-byte — that is the separate, ongoing concern
`scripts/r2_reports_verifier.py` (RX-PUB-A0 Phase 9 / RX-PUB-A0.4 Phase 2)
measures, currently in observability-only bake-in, not yet enforced. See
`docs/RX_PUB_A0_R2_VERIFIER_BAKEIN.md`.

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
