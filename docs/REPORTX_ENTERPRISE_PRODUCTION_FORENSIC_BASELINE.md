# REPORTX Enterprise Production Forensic Baseline — RX-P1 Phase 0-3

Status: **Forensic baseline only, per the mission's explicit First Execution
Boundary (Phase 0-3 + RX-P1A only if trivial/reversible).** No contract
migration, no lifecycle-state rewrite, no cross-platform PR, and no
publication-gate change has been made. One live, reproducible defect was
found and root-caused; it is **not** fixed here — see Section 18 for why a
safe minimal fix does not currently exist.

All evidence below is either (a) a direct file:line citation in
`cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM` at
`origin/main`, (b) a live HTTP response captured during this session
(timestamps given), or (c) a direct read of
`cyberdudebivash-pvt-ltd/cyberdudebivash-blog` (identified below as
"Platform B"). Nothing here is inferred from a green CI run alone.

---

## 1. Executive Summary

REPORTX (the HTML intelligence-report generation → certification →
registry → R2 → Worker → customer chain) is **materially better-governed
than a naive read would suggest** — a real single-writer invariant has been
established and tested (`docs/REPORT_WRITER_OWNERSHIP_MATRIX.md`), a real
fail-open publication-gate bug was found and fixed for the *in-window*
report population (RX-PUB-A0.6A-D), and a real R2-vs-local-vs-public
identity verifier exists and runs every pipeline run.

But **the governance the RX-PUB-A0 series built only covers a narrow slice
of the actual report corpus**, and this pass found a live, reproducible gap
in the slice it doesn't cover:

**The `/reports/**` canonical-URL route serves any report whose
underlying intel record cannot be resolved by `findItemBySlug()` — which
is most of the historical corpus, not an edge case — completely
unconditionally, with zero publication-gate check. The code comment
justifying this names a specific compensating control,
`scripts/publication_gate_scan.py`, as covering that population instead.
That script does not exist anywhere in the repository and is not wired
into any CI workflow.** Confirmed live on 2/2 independently sampled
historical reports (Section 4).

Separately, run `31867366326` (the P0-MP.1A R2 diagnostic from the prior
session phase) proved facts about `intel/feed_manifest.json` in the
`sentinel-apex-data` bucket — an **upstream SSOT-layer artifact, not the
`sentinel-apex-reports` bucket or any part of the REPORTX artifact/registry/
publication chain**. Its `R2_CURRENT_ONLY_COLLAPSED` finding does not
transfer to REPORTX. It does, however, connect causally: that manifest's
narrow single-generation state is part of *why* `findItemBySlug()` can only
resolve a small window of items, which is part of *why* the gate-coverage
gap above matters as much as it does (Section 5).

Cross-platform parity (Phase 9) is **not currently achievable as
architected** — Platform B independently re-derives all scoring from 28
raw sources (treating Platform A as one of them, defensively parsed) and
rewrites `report_url` to its own domain rather than linking to Platform
A's canonical, gated artifact. This is a documented, deliberate design
choice in Platform B's own source, not an accidental bug (Section 11).

**Final decision: `INSUFFICIENT-EVIDENCE`** for full REPORTX enterprise
certification, with **one specific defect `ROOT-CAUSE-PROVEN`** (Section
17) and explicitly **not fixed** because no small/reversible repair exists
yet (Section 18).

---

## 2. Current Production Status

- Default branch: `main` @ `d4136a4fd3795f95a696734964dc779b5ddda6ca` (as of
  this pass; the P0-MP.1A PRs #199/#200 are the most recent merges).
- Live production domain confirmed by direct fetch:
  `https://intel.cyberdudebivash.com` — Cloudflare Worker
  (`workers/intel-gateway/`).
- Local checkout contains **14,705 real generated report HTML files** under
  `reports/2026/{06,07,08}/` (`find reports/2026 -name '*.html' | wc -l`).
- `api/reports/index.json` (the registry `scripts/build_reports_index.py`
  writes): 500 entries. `api/reports/latest.json`: 50 entries. `api/feed.json`
  (the narrow rolling window): 21 entries. All three checked live against
  this checkout — see Section 4.
- No CodeRabbit/CI activity yet — this pass produced no code diff.

---

## 3. Run 31867366326 Evidence — Relevance to REPORTX

Per the mission's own Phase 0 instruction: **a green workflow means the
diagnostic executed successfully, not that REPORTX persistence is
correct.** Applying that literally:

| Question | Answer |
|---|---|
| What did run `31867366326` check? | `HeadObject`/`GetObject`/`ListObjectsV2`/`ListObjectVersions` against `sentinel-apex-data`, key `intel/feed_manifest.json` (the STIX intel-manifest SSOT artifact — `scripts/r2_upload.py`'s "Upload 1" block). |
| Did it check `sentinel-apex-reports` (the REPORTX bucket)? | **No.** Zero calls against that bucket. |
| Did it check the report registry (`api/reports/*.json`)? | **No.** |
| Did it check `publication-gate.js` / `customer_ready` / entitlement? | **No.** |
| Did it check Platform A vs. Platform B parity? | **No.** |
| Does its `R2_CURRENT_ONLY_COLLAPSED` classification prove anything about REPORTX? | **No — different boundary.** See `docs/P0_R2_STIX_MANIFEST_RECOVERY_DIAGNOSTIC.md` for that finding's own scope. |

**Verdict for REPORTX specifically: `INSUFFICIENT-EVIDENCE`** — run
`31867366326` is real, valid evidence for a different, upstream part of the
mission's own truth-chain diagram (`INTELLIGENCE SSOT`, one layer above
`REPORTX GENERATOR`). It cannot be used to certify or reject any REPORTX
claim.

**The one real connection** (established this pass, not previously
documented): `intel/feed_manifest.json`'s narrow single-generation state
(22 items, ~15-minute window, per the prior diagnostic) is one of the
inputs `findItemBySlib()`'s 5-source waterfall depends on
(`FEED_MANIFEST_FALLBACK_KEY`, last-resort). Its narrowness is a
contributing cause — not the whole cause — of why most of the 14,705-report
corpus is unresolvable by that function, which is directly implicated in
Section 5's finding.

---

## 4. REPORTX End-to-End Provenance Map — Real Sample Trace

Two real, independently-selected report artifacts were traced live during
this session (not fabricated, not assumed):

**Sample 1:** `intel--10bbfa803bf28323` (CVE-2026-68247, generated
2026-08-11 per its embedded `<meta description>`, file:
`reports/2026/08/intel--10bbfa803bf28323.html`)
**Sample 2:** `intel--92bdcf53668b0fb0` (file:
`reports/2026/07/intel--92bdcf53668b0fb0.html`)

| Boundary | Sample 1 | Sample 2 |
|---|---|---|
| Local artifact exists | Yes, 94,767 bytes tracked in `reports/2026/08/` | Yes, present in `reports/2026/07/` |
| Engine marker | `<!-- CDB-REPORT-ENGINE: generate_intel_reports.py vv184.0 -->` (canonical writer, per §7) | Not individually re-checked, same generation path assumed |
| `api/reports/index.json` (500 entries) | **NOT FOUND** | Not individually re-checked |
| `api/reports/latest.json` (50 entries) | **NOT FOUND** | Not individually re-checked |
| `api/feed.json` (21 entries) | **NOT FOUND** | Not individually re-checked |
| `findItemBySlug()` resolution (via `GET /api/v1/reports/{id}/publication-status`) | `state: "UNKNOWN"`, `customer_ready: false`, `reason_codes: ["ITEM_NOT_RESOLVABLE"]` (live, 2026-08-15T06:28:22Z) | `state: "UNKNOWN"`, `customer_ready: false`, `reason_codes: ["ITEM_NOT_RESOLVABLE"]` (live, 2026-08-15T06:29:27Z) |
| `GET /reports/{path}.html` (canonical URL, live) | **HTTP 200**, `text/html`, 94,767 bytes | **HTTP 200**, 94,447 bytes |
| PASS/FAIL against "gate must authorize every serve" | **FAIL** — served despite the gate's own endpoint reporting it cannot certify the item | **FAIL** — same |

**Evidence:** both live HTTP calls captured directly via `curl` against
`intel.cyberdudebivash.com` during this session; registry-absence checked
directly against this checkout's `api/reports/index.json`,
`api/reports/latest.json`, `api/feed.json` via Python JSON parse.

The full boundary chain for the resolvable population (source →
`generate_intel_reports.py` → `r2_upload.py`'s `s3_sync` → `r2_reports_verifier.py`
→ `findItemBySlug()` → gate → serve) is code-evidenced in Section 7's field
matrix but was **not** live-traced end-to-end for a currently in-window
report in this pass (would require picking one of the ~21-500 items still
inside the narrow current window and repeating the above — not done here;
flagged as a Phase-1-continuation item, not fabricated).

---

## 5. Boundary Reconciliation Table

| Boundary | Input identity | Output identity | Evidence | State |
|---|---|---|---|---|
| Generator (`scripts/generate_intel_reports.py`) | intel item (`stix_id`/`id`) | `reports/{yyyy}/{mm}/intel--{hash}.html`, engine marker embedded | `render_report()`, `build_report_sections()` — canonical, single writer per `docs/REPORT_WRITER_OWNERSHIP_MATRIX.md` | **PASS** (writer-count question resolved) |
| Registry (`scripts/build_reports_index.py`) | scans `reports/` + cross-refs `api/feed.json` | `api/reports/{index,latest,stats}.json`, `schema_version: "1.0"` | Live-checked: samples 1/2 absent from all 3 outputs despite artifact existing on disk | **FAIL** (registry incomplete relative to the actual artifact corpus) |
| R2 upload (`scripts/r2_upload.py` reports-sync) | `reports/*.html` | `sentinel-apex-reports` bucket, same key path | `s3_sync(..., size_only=False)` (v184.2 fix, full content comparison) | Not independently re-verified this pass (accepted as code-evidenced) |
| R2 identity verifier (`scripts/r2_reports_verifier.py`) | in-window reports only (~150-250) | `data/quality/rx_pub_a0_reports_artifact_manifest.json`, `schema_version: "2"` | Explicitly bounded scope per `RX_PUB_A0_ARTIFACT_IDENTITY_SPEC.md` — **does not cover** either sample (both outside the in-window scope) | **OUT OF SCOPE for both samples** |
| Publication gate (`publication-gate.js`) | resolved item via `findItemBySlug` | `customer_ready`, `state`, `reason_codes` | Live: both samples → `ITEM_NOT_RESOLVABLE`, `customer_ready: false` | Gate correctly reports it cannot certify |
| Worker serving (`/reports/**`) | R2 key | HTTP response | Live: both samples → **HTTP 200**, full report body, despite gate's own denial | **FAIL** — gate-coverage bypass, root-caused in Section 17 |
| Entitlement (`applyTierGateV2`) | served item | masked/unmasked fields | Code-evidenced: canonical-URL branch always applies `"free"` tier masking (line ~4269 area) regardless of viewer | **PASS** for the entitlement-masking concern specifically (IOCs/detections/actor-attribution are masked even on this bypassed path) |
| Platform B (blog.cyberdudebivash.in) | fetches Platform A's `api/reports/latest.json`, `api/feed.json`, `api/v1/intel/*.json` | independently-generated blog post, own `report_url` | `fetch-live-intel.js:104-108, 892-901, 2813, 3194` | **Not a pass-through — architecturally divergent by design**, see Section 11 |

---

## 6. Failure Classification

Using only the mission's fixed taxonomy:

| Finding | Classification |
|---|---|
| `/reports/**` canonical-URL route serves unresolvable items unconditionally | **`WORKER_CONTRACT_DEFECT`** — the route's own governing comment claims a compensating control that does not exist, meaning the Worker's actual behavior does not match its documented contract. |
| Registry (`api/reports/*.json`) missing both sampled historical artifacts | **`REGISTRY_DEFECT`** — real artifact exists, registry does not reflect it. (Whether this is intentional windowing or a genuine gap was not fully distinguished this pass — see Section 19 open items.) |
| `intel/feed_manifest.json` R2 state | **Out of REPORTX classification scope** — already classified `R2_CURRENT_ONLY_COLLAPSED` in `docs/P0_R2_STIX_MANIFEST_RECOVERY_DIAGNOSTIC.md`, a different boundary. |
| Cross-platform (A/B) field parity | **`CROSS_PLATFORM_CONTRACT_DIVERGENCE`** — confirmed architectural, not incidental (Section 11). |
| Report writer duplication (3 rendering implementations) | **`NO_DEFECT_REPRODUCED`** — already resolved per `docs/REPORT_WRITER_OWNERSHIP_MATRIX.md`; re-confirmed via this pass's code reading (zero `REPORTS_R2.put(` call sites outside the canonical writer). |
| Full-corpus (14,705 reports) gate/identity verification | **`INSUFFICIENT_EVIDENCE`** — `r2_reports_verifier.py` explicitly scopes to ~150-250 in-window reports only; the other ~14,500+ have never been checked by any tool found in this repository. |

---

## 7. Field Ownership Matrix

For the fields the mission specifies, the single authoritative owner found
(file:line), or "NONE FOUND" / "MULTIPLE" where that itself is the finding:

| Field | Authoritative owner | Notes |
|---|---|---|
| `customer_ready` | `workers/intel-gateway/src/publication-gate.js:211` `isCustomerReady()`, computed fresh inside `evaluatePublicationGate()` (line 145) | Explicitly documented as "the ONLY field callers should branch on" (module's own comment, lines 140-141). Correctly the single source. |
| `publication_status`/`state` | Same module, same function | Consistent. |
| `report_url` (Platform A canonical) | `scripts/generate_intel_reports.py` at write time; served via `/reports/**` | Not independently duplicated within Platform A. |
| `report_url` (as seen by Platform B) | **Overwritten** — `fetch-live-intel.js:2813,3194` rewrites it to `${CFG.baseUrl}/posts/${slug}.html` (Platform B's own domain) | Confirmed divergence, Section 11. |
| `severity`/`risk_score`/`cvss_score`/`epss_score`/`confidence`/`kev` | Computed by Platform A's P20/P21/P23/P25/P26 engines (not re-audited field-by-field this pass — out of this pass's bounded scope) | Platform B does **not** trust these as authoritative — re-derives its own via S2N/detection/reasoning engines (Section 11). |
| `schema_version` | **MULTIPLE, independently versioned, by design** — `STABLE_CONTRACT_VERSION = "stable-v1.0-apex"` (intel-item JSON, `scripts/validate_manifest_schema.py:73`), artifact-manifest `"schema_version": "2"` (`r2_reports_verifier.py:732`), registry `"schema_version": "1.0"` (`build_reports_index.py`), `PUBLICATION_GATE_VERSION = "1.1.0"` (`publication-gate.js:54`), `RX_PUB_A0_VERSION = "a0.5"` (`rx-pub-a0-handlers.js:25`) | `RX_PUB_A0_ARTIFACT_IDENTITY_SPEC.md` (lines 71-79) documents this as **intentional** — avoiding "a second, driftable copy of a value that already has one authoritative source" per field. Not a defect; each version number governs a genuinely distinct contract. |
| Entitlement/tier masking | `workers/intel-gateway/src/revenue-enforcement.js:712` `applyTierGateV2()` | Single implementation, consistently applied on both `/reports/**` branches. |
| No unified `REPORTX_CONTRACT_VERSION` | **NONE FOUND** — confirmed by repo-wide grep, zero matches for `CONTRACT_VERSION`/`REPORTX_CONTRACT` | This is Phase 4's starting condition, not evaluated further per the First Execution Boundary (Phase 4 is out of scope for this pass). |

---

## 8. Duplicate/Conflicting Implementations

- **Report rendering: RESOLVED, not duplicate in practice.** Three code paths exist (`generate_intel_reports.py::render_report()`, `report_generator.py::generate_report()`, `index.js::generateIntelReport()`) but only the first ever persists to the canonical R2 key — the other two are confirmed non-authoritative, live-render-only fallbacks with explicit comments (`index.js:4205-4216, 4271-4274`) stating they must never write to `REPORTS_R2`. Verified: zero `REPORTS_R2.put(` call sites repo-wide.
- **`schema_version`: multiple, by design, not a defect** — see Section 7.
- **The compensating-control gap is itself a "missing" implementation, not a duplicate one** — `scripts/publication_gate_scan.py` is referenced by name in a production code comment (`index.js:4166`) but does not exist. This is the inverse failure mode from "duplicate" — a documented dependency with zero implementations.

---

## 9. R2 Persistence Verdict

**Not independently re-verified this pass for `sentinel-apex-reports`**
(the REPORTX bucket) — the only live R2 diagnostic run to date
(`31867366326`) targeted `sentinel-apex-data` only. Per Phase 7's own
instruction ("Only execute this phase if Phase 1/2 proves an R2-related
defect... If R2 is correct, DO NOT MODIFY R2"), and since this pass's
proven defect (Section 17) is a Worker-serving-logic defect, not an R2
persistence defect, **Phase 7 is correctly out of scope for this pass.**
A future pass should run an equivalent read-only diagnostic against
`sentinel-apex-reports` before touching it.

---

## 10. Worker/API Verdict

- `findItemBySlug()`'s 5-source waterfall is code-correct and matches its
  documentation.
- `handlePublicationStatus()` (backing `/api/v1/reports/{id}/publication-status`)
  is **correct and honest** — it reported `ITEM_NOT_RESOLVABLE` accurately
  for both samples.
- The `/reports/**` route's canonical-URL branch **does not honor** its own
  gate's verdict for the unresolvable population — this is the proven
  defect (Section 17).
- `applyTierGateV2()` entitlement masking is applied consistently on every
  serving branch checked.

---

## 11. Platform A Verdict

Platform A (`intel.cyberdudebivash.com`, this repository) has real,
working, previously-hardened governance for the population it can resolve:
single-writer invariant enforced, fail-closed gate for in-window resolvable
items (RX-PUB-A0.6 fixes), honest publication-status API. Its gap is
narrow but real: the unresolvable population (Section 17).

## 12. Platform B Verdict

**Platform B = `blog.cyberdudebivash.in`
(`cyberdudebivash-pvt-ltd/cyberdudebivash-blog`), confirmed by direct
source inspection** (`fetch-live-intel.js:104-108`: `sentinelApexLatestUrl`,
`sentinelApexFeedUrl`, `sentinelApexReportsUrl` all point at
`intel.cyberdudebivash.com`). This resolves an explicitly-unresolved
question from `docs/RX_PUB_A0_EXECUTION_PATH.md` and closes the
never-completed RX-PUB-1 §12-14 task ("Repo B publication identity +
Blogger idempotency audit").

Platform B's own source comment (`fetch-live-intel.js:892-901`) states
Platform A is "a first-party structured CTI source, not a third-party
vendor" but is nonetheless ingested through the exact same defensive,
schema-agnostic path (`sapexPick()`, candidate-key lookups) as NVD, CISA
KEV, MSRC, exploit-db, and 24 other sources. Platform B:
- Does **not** treat Platform A's `customer_ready`/`publication_status` as
  authoritative — it has no concept of Platform A's gate at all.
- Independently re-scores everything through its own `S2N` (signal-to-noise),
  `detection-engine`, and `reasoning-engine` modules
  (`Sentinel-APEX/engine-node/`).
- **Rewrites `report_url`** to its own domain/slug
  (`fetch-live-intel.js:2813,3194`: `${CFG.baseUrl}/posts/${slug}.html`)
  rather than linking to Platform A's canonical, certified, gated report.

**This is a deliberate, self-documented architectural choice in Platform
B's own codebase, not an accidental bug.** Achieving the mission's Phase 9
parity requirement would mean changing Platform B's fundamental trust
model (treat Sentinel APEX specially vs. treat it as one of 28 generic
feeds) — a cross-repository architectural decision explicitly matching the
mission's own Stop Condition: *"the two platforms intentionally use
different contracts."* **Escalating, not attempting, per that stop
condition.**

---

## 13. Customer Access Verdict

Entitlement masking (`applyTierGateV2`) is consistently applied. The
publication-status API correctly distinguishes `NOT_ENTITLED`-adjacent
states from `PROCESSING`/`WITHHELD` in its `reason_codes` design (not
exhaustively tested against all mission-listed states this pass — flagged
as an open item, Section 19). The proven defect (Section 17) means a
customer *can* currently reach a report the gate cannot vouch for — this is
a customer-trust concern, not a customer-blocked-from-valid-content
concern (the opposite of Phase 10's worst case, but still a real gap).

---

## 14. Security Impact

The proven defect (Section 17) is an **authorization-gap**, not an
authentication or entitlement bypass — masking still applies, and nothing
indicates the *specific* sampled content is actually bad (their true
certification scores are unknown, not proven-failing). The risk is
**unbounded, unverified exposure of the ~14,500-report population the
gate cannot reach**, not a confirmed leak of specific rejected content.
Severity: real and worth fixing, but not an active incident.

## 15. Reliability Impact

None of this pass's findings affect availability. The gap, if anything,
currently biases toward *more* availability (serving more than it should)
rather than less.

## 16. Revenue/Commercial Impact

Entitlement masking held throughout — no premium content (IOCs, detection
rules, actor attribution) was exposed on the bypassed path. The commercial
risk is trust/compliance-adjacent (an unrejected historical report being
citable/linkable indefinitely with no re-certification), not direct
revenue leakage.

---

## 17. Root Cause

**`WORKER_CONTRACT_DEFECT` — `REPORTX_PUBLICATION_GATE_COVERAGE_GAP`.**

`workers/intel-gateway/src/index.js`, `/reports/**` route, lines
4150-4182: the P0 Customer Publication Authorization Gate only blocks
serving when `gateItem` (resolved via `findItemBySlug`) is non-null **and**
the gate rejects it. When `findItemBySlug` cannot resolve the item at all
— which live testing confirms is the outcome for reports outside a narrow
discovery window — `gateItem` is `null`, the block condition is false by
construction, and execution falls through to serve the cached R2 object
unconditionally (line 4233, canonical branch; line 4189, legacy branch).

The route's own comment (lines 4160-4166) states this is intentional,
citing `scripts/publication_gate_scan.py` as the compensating control for
that population. **That script does not exist in this repository and is
referenced nowhere else** (confirmed: `ls` fails, zero grep matches in any
`.github/workflows/*.yml`). The documented compensating control is a
phantom — either planned and never built, or removed without updating the
comment that justifies the gap.

**Root cause status: `ROOT-CAUSE-PROVEN`** for this specific defect, live-
reproduced on 2/2 independently sampled reports.

---

## 18. Recommended Minimal Fix — Why Not Shipped This Pass

Two candidate fixes were considered and both rejected for this pass:

1. **Build `scripts/publication_gate_scan.py`.** Not small — requires
   re-implementing or calling `evaluatePublicationGate()`'s logic against
   ~14,500 historical reports, deciding a remediation action for
   gate-failing ones (quarantine? delete? mark withheld?), and handling
   the scale/rate-limit/cost concerns the mission's own Section 36-adjacent
   cost-governance pattern (seen throughout the RX-PUB-A0 series) would
   require. This is RX-P1C/RX-P1G-scale work, not RX-P1A.
2. **Flip the Worker to fail-closed for unresolvable items.** Small in
   diff size, but **unbounded and unverified blast radius**: with no scan
   ever having run, there is no evidence for what fraction of the
   ~14,500-report unresolvable population would actually fail the gate if
   evaluated — flipping this default could 404 thousands of legitimately
   fine, already-published, possibly-bookmarked/linked/indexed reports.
   This directly violates the mission's own P0 Operating Rule ("evidence
   first, root cause second, minimal production fix third") and its Stop
   Condition ("production differs from repository assumptions").

**Neither is safe to ship without first running a read-only scan to learn
the actual gate-failure rate in the unresolvable population** — exactly
the P0-MP.1A pattern already used successfully for the R2 diagnostic.
**Recommended next step (not implemented here): a bounded, read-only
`scripts/publication_gate_scan.py --report-only` pass** that evaluates a
sample of the unresolvable corpus against the gate and reports the
failure rate, before any decision about serve-time enforcement is made.

---

## 19. Open Items (honest gaps, not fabricated closure)

- Whether the registry's absence of both sampled reports (Section 5) is
  intentional windowing (matching `api/feed.json`'s known narrow-window
  design) or a genuine `REGISTRY_DEFECT` was not conclusively distinguished
  this pass.
- `sentinel-apex-reports` R2 persistence/versioning characteristics were
  not independently diagnosed (Section 9).
- No in-window (currently-resolvable) report was live-traced end-to-end in
  this pass — only the unresolvable-population defect was confirmed.
- The pre-existing `docs/REPORT_WRITER_OWNERSHIP_MATRIX.md` "open item"
  (the `intel--20282e88b1f49bf2` staleness incident, never explained by any
  writer) is **plausibly explained** by this pass's finding (an aged-out
  report served from a stale R2 cache with no re-verification path) but
  this was not confirmed against that specific record ID.
- Full Phase 10-20 (customer-access state matrix, link integrity across
  all CTA types, freshness contract, last-known-good, observability
  build-out, synthetic monitor, adversarial test matrix, Playwright
  certification, performance, full security audit, commercial assessment)
  are explicitly **out of the First Execution Boundary** and not attempted.

---

## 20. Proposed RX-P1A...P1H PR Plan

| PR | Scope | Status |
|---|---|---|
| RX-P1A | Read-only `publication_gate_scan.py --report-only`: sample the unresolvable-population failure rate before any enforcement decision. | **Recommended next PR — not this one.** |
| RX-P1B | Canonical REPORTX contract (Phase 4) — only after RX-P1A's data informs what "state" needs to mean for the unresolvable population. | Deferred. |
| RX-P1C | Lifecycle/publication-state contract (Phase 5) + serve-time enforcement decision, informed by RX-P1A's scan data. | Deferred. |
| RX-P1D | Worker/BFF truth contract hardening. | Deferred. |
| RX-P1E | Cross-platform (A/B) consumer migration — requires Platform B repo changes; explicitly a cross-repo architectural decision (Section 11), needs its own mandate. | Deferred, flagged for escalation per Stop Condition. |
| RX-P1F | Entitlement/CTA hardening. | Deferred (no defect found here this pass). |
| RX-P1G | Observability + synthetic monitor. | Deferred. |
| RX-P1H | Production certification. | Deferred — blocked on the above. |

---

## Final Decision

**`INSUFFICIENT-EVIDENCE`**

One specific defect (Section 17) is `ROOT-CAUSE-PROVEN` but intentionally
not fixed this pass (Section 18 — no safe minimal repair exists yet).
Cross-platform parity is architecturally not achievable without a
cross-repo mandate (Section 11, Stop Condition triggered — escalating).
The bulk of the historical report corpus (~14,500 of ~14,705 reports) has
never been checked by any verification tool in this repository. Enterprise
GA certification cannot be claimed on this evidence.
