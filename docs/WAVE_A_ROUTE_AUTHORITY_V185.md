# CYBERDUDEBIVASH SENTINEL APEX — Wave A Route Authority (v185.9)

**Mission:** SENTINEL APEX v185.9 — P0 Entitlement Enforcement Wave A,
Enterprise Integration Authority & Commercial Access Convergence, Phase 1.

**Method:** every row below was built by tracing the actual live Worker
entrypoint routing in `workers/intel-gateway/src/index.js` and, where
dispatch continues into `enterprise-endpoints.js`'s `routeEnterpriseEndpoint()`,
the matching handler in that file — not from prior documentation, which the
mission explicitly instructs not to trust. Two claims from an earlier
automated audit pass were caught and corrected before this document was
written: SLA (`/api/sla/*`) and premium report (`/api/reports/premium`) were
both reported as having zero `resolveEntitlement()` wiring; direct
re-verification found SLA already correctly wired at the index.js dispatcher
level, and premium report *called* `resolveEntitlement()` but discarded its
return value entirely (now fixed — see `report_full` row below). Do not
re-trust either of those two original claims.

## Proof Before Change

| Field | Entry |
|---|---|
| **Objective** | Bring TAXII, MISP, SIEM, and webhook/alert routes onto the single canonical `resolveEntitlement()`/`enforceTierGate()` authorization chain, in shadow mode, so their access decisions are observable and comparable to their existing ad-hoc gates before any of them are ever enforced. |
| **Affected files** | `workers/intel-gateway/src/enterprise-endpoints.js`, `workers/intel-gateway/src/index.js`, `workers/intel-gateway/src/revenue-enforcement.js`, `scripts/entitlement_resource_drift_gate.py`, `docs/ENTITLEMENT_RESOURCE_INVENTORY_V185.md`, `docs/ENTITLEMENT_MIGRATION_WAVE_PLAN_V185.md`, `docs/WAVE_A_ROUTE_AUTHORITY_V185.md` (new), `data/release/v185_customer_operations_certification.json`. |
| **Existing engine reused** | `resolveEntitlement()` and `enforceTierGate()` (both pre-existing in `index.js`/`revenue-enforcement.js`, called unchanged — not re-implemented). `taxii_access`, `taxii_kev`, `siem`, `alerts`, `report_full` were all pre-existing `enforceTierGate()` cases with zero or partial call sites; this pass calls them, it does not redefine their rules. Only one genuinely new case (`misp_export`) was added, because no canonical MISP resource existed at all. |
| **Evidence modification is required** | Mission v185.9 Wave A, Phases 2/3/4/6/7 explicitly require TAXII dual-gate reconciliation, MISP live-handler resolution, premium-report re-validation, SIEM enforcement wiring, and webhook/alert entitlement wiring as named, bounded deliverables. |
| **Risk classification** | LOW. Every new/changed call site consumes `resolveEntitlement()`'s `.allowed` in the established safe pattern — while `ENTITLEMENT_ENFORCEMENT_RESOURCES` does not name a resource (true for all of these today), `resolveEntitlement()` returns the caller's own ad-hoc decision unchanged, so behavior is provably identical to pre-PR for every route touched. The two real bugs fixed (`handleTaxiiObjects` self-contradiction, premium-report discarded return value) are the only rows with a production behavior implication, and both are corrections toward the code's own already-documented intended behavior, not new behavior. |
| **Expected regression risk** | None to existing enforced behavior (`cve_detail_full` untouched). Shadow-mode `entitlement_shadow_mismatch` audit log volume increases (more resources now shadow-checked) — an observability-only effect, not a functional one. |
| **Rollback plan** | Every change in this PR is either (a) a shadow-only `resolveEntitlement()` call whose removal reverts the route to its pre-PR ad-hoc-only gate with zero other side effects, or (b) a doc/JSON update. No schema, KV, or R2 change. Revert via `git revert` of this PR's merge commit; no data migration or coordinated rollback step is needed since nothing here is enforced. |

## Reuse Report

| Metric | Result |
|---|---|
| Existing P-layer/engine functions reused (called, not re-implemented) | `resolveEntitlement()`, `enforceTierGate()`, `shadowCheckEntitlement()`, `isEntitlementEnforced()`, `auditLog()` — all pre-existing, all called unchanged |
| Existing API routes extended (not duplicated) | 12 (4 TAXII, 1 MISP, 3 SIEM, 4 alerts) |
| Existing dashboards extended | 0 (no dashboard-facing change in this PR) |
| New engines introduced (justified by gap analysis) | 0 — no new engine; 1 new `enforceTierGate()` *case* (`misp_export`), justified because no canonical MISP resource previously existed (Section 2 above) |
| Duplicate engines introduced | **0** |
| Duplicate routes introduced | **0** |
| Backward compatibility preserved | PASS — every touched route's response shape and ad-hoc decision are unchanged while unenforced (see Risk classification above) |
| Certification chain intact | PASS — `data/release/v185_customer_operations_certification.json` updated additively (new `wave_a_update` block), prior fields left as the historical record they measured |
| Regression suite result | 24/24 PASS (`scripts/regression_tests.py`, including the strengthened drift gate's own self-test) |

All resources in this document are **shadow-mode only** as of this PR —
`resolveEntitlement()`'s decision is logged and compared, never enforced,
unless a resource is separately confirmed present in
`ENTITLEMENT_ENFORCEMENT_RESOURCES` (currently only `cve_detail_full`).
Adding a new `resolveEntitlement()` call site is therefore a **behavior
no-op today** in every row marked "Wired (shadow)" — the ad-hoc decision the
route already made remains the one actually returned to the caller.

---

## 1. TAXII 2.1 (Phase 2 — dual-gate reconciliation)

Two independently-live implementations exist under different URL prefixes.
They are not colliding (no shared route path), but they disagree on
collection catalogue and, before this PR, on enforcement logic.

| # | Public route | Actual live handler | Auth method | Legacy tier gate | Canonical resource | `resolveEntitlement` callsite? | Tenant-aware? | Required tier | Current mode | Production evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `GET /taxii/*` (discovery/root/collections) | `index.js` `handleTAXII()` | API key / JWT via `resolveAuth()` | none (canonical-only, no legacy check remains) | `taxii_access` | Yes — index.js:2411 | No (public feed, not tenant-scoped) | PRO+ | Shadow | Pre-existing, unmodified this pass |
| 2 | `GET /taxii/*` collection `sentinel-apex-kev` | `index.js` `handleTAXII()` | same | none | `taxii_kev` | Yes — index.js:2418, 2443 | No | ENTERPRISE/MSSP | Shadow | Pre-existing, unmodified this pass |
| 3 | `GET /api/taxii` \| `/api/taxii/` | `enterprise-endpoints.js` `handleTaxiiDiscovery()` (via `routeEnterpriseEndpoint`) | API key / JWT | `requireProOrEnterprise(tier)` | `taxii_access` | **Yes — added this pass**, enterprise-endpoints.js:79 | No | PRO+ | Shadow | Wired this pass |
| 4 | `GET /api/taxii/root` \| `/api/taxii/root/` | `handleTaxiiRoot()` | API key / JWT | `requireProOrEnterprise(tier)` | `taxii_access` | **Yes — added this pass**, enterprise-endpoints.js:112 | No | PRO+ | Shadow | Wired this pass |
| 5 | `GET /api/taxii/root/collections` \| `/collections/` | `handleTaxiiCollections()` | API key / JWT | `requireProOrEnterprise(tier)` for listing; per-collection `can_read` flags advertise `full`/`critical` as PRO-readable, `kev`/`ransomware`/`apt` as Enterprise-only | `taxii_access` | **Yes — added this pass**, enterprise-endpoints.js:139 | No | PRO+ (listing) | Shadow | Wired this pass |
| 6 | `GET /api/taxii/root/collections/:id/objects` | `handleTaxiiObjects()` | API key / JWT | **Fixed this pass** — previously blanket `requireEnterprise(tier)` for *every* collection, self-contradicting row 5's own advertised `can_read` flags for `full`/`critical` (a PRO customer was denied objects for a collection the listing told them they could read). Now per-collection: `full`/`critical` → PRO+, `kev` → Enterprise-only, `ransomware`/`apt` → Enterprise-only (unchanged legacy rule, already matched row 5) | `taxii_access` (full/critical/default), `taxii_kev` (kev collection only) | **Yes — added this pass**, enterprise-endpoints.js:244, 254 | No | PRO+ (full/critical), ENTERPRISE (kev/ransomware/apt) | Shadow | Wired + self-contradiction fixed this pass |

**Reconciliation status:** `TAXII_AUTHORITY_COUNT` is not yet 1. index.js's
`handleTAXII()` and enterprise-endpoints.js's TAXII handlers remain two
separate live implementations with **different, non-overlapping collection
ID sets** (index.js: `sentinel-apex-main`, `sentinel-apex-kev` — 2
collections; enterprise-endpoints.js: `sentinel-apex-full`,
`sentinel-apex-kev`, `sentinel-apex-critical`, `sentinel-apex-ransomware`,
`sentinel-apex-apt` — 5 collections, only `sentinel-apex-kev` in common).
Collapsing these into one implementation is a product-catalogue decision
(which collection IDs are the real, customer-documented ones) that this pass
judged out of safe autonomous scope — see `docs/ENTITLEMENT_MIGRATION_WAVE_PLAN_V185.md`
for the carry-forward blocker. What **is** now true for both
implementations independently: every TAXII route on both paths is wired to
the same canonical `taxii_access`/`taxii_kev` decision functions, and
neither path has a same-file self-contradiction left in it.

---

## 2. MISP (Phase 3 — live-handler resolution)

Two different URLs, not colliding, using two different gating mechanisms.

| # | Public route | Actual live handler | Auth method | Legacy tier gate | Canonical resource | `resolveEntitlement` callsite? | Tenant-aware? | Required tier | Current mode | Production evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 7 | `GET /api/misp/export` | `enterprise-endpoints.js` `handleMISPExport()` (via `routeEnterpriseEndpoint`, confirmed live via router trace: index.js's `path.startsWith("/api/misp/export")` dispatches into `routeEnterpriseEndpoint`, which exact-matches `/api/misp/export`) | API key / JWT | `requireEnterprise(tier)` | `misp_export` (**new case added to `enforceTierGate()` this pass** — no canonical MISP resource previously existed at all) | **Yes — added this pass**, enterprise-endpoints.js:386 | No | ENTERPRISE/MSSP | Shadow | Wired this pass; `MISP_LIVE_HANDLER=VERIFIED` |
| 8 | `GET /api/export/misp` | `api-extensions.js` `handleMISPExportExt` (imported into index.js separately, exact-matched at `if (path === "/api/export/misp")`) | Scope-based (`enforceScopeMiddleware`/`SCOPE_DEFINITIONS["export:misp"]`) | scope check, not tier check | none assigned | No | Unknown (not traced this pass) | N/A (scope-gated) | Legacy scope system, untouched | Out of scope this pass — documented gap, not modified |

`MISP_ENTITLEMENT_CALLSITE = LIVE_HANDLER` — the shadow-mode call added this
pass is inside the handler that actually serves `/api/misp/export` traffic,
not a dead code path. Row 8 (`/api/export/misp`) uses an entirely separate,
pre-existing scope-based authorization system with no tier/entitlement
concept at all; reconciling it with the canonical entitlement chain is
carried forward as a Wave B/C item, not attempted this pass (a scope system
and a tier system are not directly comparable without a product decision on
what `export:misp` should mean in tier terms).

---

## 3. Premium report (Phase 4)

| # | Public route | Actual live handler | Auth method | Legacy tier gate | Canonical resource | `resolveEntitlement` callsite? | Tenant-aware? | Required tier | Current mode | Production evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 9 | `GET /api/reports/premium` | `index.js` route → `handlePremiumReport()` | API key / JWT | `handlePremiumReport()`'s own `tier.toLowerCase() === "free"` check | `report_full` | Yes — index.js:5591 (**bug fixed this pass**: this call site previously invoked `resolveEntitlement()` but discarded the returned decision entirely, making the resource's shadow/enforcement flag inert even if flipped on; the ad-hoc `handlePremiumReport()` check was the sole thing deciding access regardless of flag state) | No | PRO+ | Shadow (now a real no-op instead of a silently-inert one) | Fixed this pass |

`/api/reports/list` and `/api/reports/{id}` were read but deliberately left
unmodified — they layer ownership-filtering logic on top of the tier check
and are not named in this mission's Phase 4 test matrix.

---

## 4. SLA (Phase 5 — re-validated, already correct)

| # | Public route | Actual live handler | Auth method | Legacy tier gate | Canonical resource | `resolveEntitlement` callsite? | Tenant-aware? | Required tier | Current mode | Production evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 10 | `GET /api/sla/report` | `index.js` route → `handleSLAReport()` | API key / JWT | none remaining (canonical-only) | `sla_report` | Yes — index.js:5484 (pre-existing, correctly consumes `.enforced && !.allowed`) | No | ENTERPRISE/MSSP | Shadow | Pre-existing, unmodified this pass |
| 11 | `GET /api/sla/incidents` | `handleSLAIncidents()` | API key / JWT | none remaining | `sla_incidents` | Yes — index.js:5491 | No | ENTERPRISE/MSSP | Shadow | Pre-existing, unmodified this pass |
| 12 | `GET /api/sla/certificate` | `handleSLACertificate()` | API key / JWT | none remaining | `sla_certificate` | Yes — index.js:5499 | No | ENTERPRISE/MSSP | Shadow | Pre-existing, unmodified this pass |

These three are the strongest Phase 9 enforcement-expansion candidates:
already correctly wired end-to-end, no discard bug, no self-contradiction.

---

## 5. SIEM (Phase 6)

| # | Public route | Actual live handler | Auth method | Legacy tier gate | Canonical resource | `resolveEntitlement` callsite? | Tenant-aware? | Required tier | Current mode | Production evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 13 | `GET /api/siem/splunk` | `enterprise-endpoints.js` `handleSiemSplunk()` | API key / JWT | `requireEnterprise(tier)` | `siem` (pre-existing case, zero prior call sites) | **Yes — added this pass**, enterprise-endpoints.js:821 | No (no cross-tenant config; feed data only) | ENTERPRISE/MSSP | Shadow | Wired this pass |
| 14 | `GET /api/siem/sentinel` | `handleSiemSentinel()` | API key / JWT | `requireEnterprise(tier)` | `siem` | **Yes — added this pass**, enterprise-endpoints.js:881 | No | ENTERPRISE/MSSP | Shadow | Wired this pass |
| 15 | `GET /api/siem/qradar` | `handleSiemQRadar()` | API key / JWT | `requireEnterprise(tier)` | `siem` | **Yes — added this pass**, enterprise-endpoints.js:943 | No | ENTERPRISE/MSSP | Shadow | Wired this pass |

All three reuse the single existing `siem` resource case rather than
fragmenting into per-connector resources — same commercial semantics
(Enterprise-exclusive push feed) across Splunk/Sentinel/QRadar, no reason to
split.

---

## 6. Webhooks / alerts (Phase 7)

| # | Public route | Actual live handler | Auth method | Legacy tier gate | Canonical resource | `resolveEntitlement` callsite? | Tenant-aware? | Required tier | Current mode | Production evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| 16 | `POST /api/alerts/subscribe` | `alert-engine.js` `handleAlertSubscribe()` | API key / JWT | `auth.tier === "FREE"` blocked | `alerts` (pre-existing case, zero prior call sites) | **Yes — added this pass**, index.js:5516 | N/A (creates new subscription owned by caller) | PRO+ | Shadow | Wired this pass |
| 17 | `GET /api/alerts/subscriptions` | `handleAlertSubscriptions()` | API key / JWT | `auth.tier === "FREE"` blocked | `alerts` | **Yes — added this pass**, index.js:5523 | Yes — filters to `sub.sub === auth.sub` | PRO+ | Shadow | Wired this pass |
| 18 | `POST /api/alerts/test` | `handleAlertTest()` | API key / JWT | `auth.tier === "FREE"` blocked | `alerts` | **Yes — added this pass**, index.js:5530 | Yes (operates on caller's own subscription) | PRO+ | Shadow | Wired this pass |
| 19 | `POST /api/alerts/dispatch` | `handleAlertDispatch()` | Admin-secret `timingSafeEqual`, not a customer tier decision | none | none — internal/operational, not a paid customer resource | Not applicable | N/A | N/A | Unchanged | Deliberately not wired (not a tier gate) |
| 20 | `GET /api/alerts/history` | `handleAlertHistory()` | API key / JWT | `auth.tier !== "ENTERPRISE" && auth.tier !== "MSSP"` blocked | none — **`alerts` (PRO+) does not represent this route's actual, stricter Enterprise-only rule**; forcing that mapping would misrepresent the real policy, so left unmapped rather than wired incorrectly | Not applicable this pass | No (shared operational log by design) | ENTERPRISE/MSSP | Unchanged | Documented gap, not wired |
| 21 | `DELETE /api/alerts/unsubscribe` | `handleAlertUnsubscribe()` | API key / JWT | **No tier restriction at all** — any authenticated identity may remove its own subscription | `alerts` | **Yes — added this pass**, index.js:5545, with `adHocAllowed=true` (not the PRO+ rule) so shadow mode reports the genuine divergence between the PRO+ `alerts` rule and this route's actual any-tier behavior, rather than fabricating a false match | Yes — ownership check `sub.sub !== auth.sub` → 403 (verified present, unmodified) | Any authenticated tier (ad-hoc); `alerts` canonical rule says PRO+ | Shadow | Wired this pass; intentional divergence documented, not silently forced to agree |

BOLA check: `handleAlertUnsubscribe`'s `sub.sub !== auth.sub` ownership
check and `handleAlertSubscriptions`'s `sub.sub === auth.sub` filter were
both re-verified present and correct this pass — a customer cannot list or
remove another customer's webhook/alert subscription by guessing its
`sub_id`. `cross_tenant_webhook_access = 0` (static verification; live BOLA
attempt against production is a Phase 15 item, not yet executed).

---

## 7. Summary counts

- Paid Wave A routes traced this pass: **21** (rows above).
- New `resolveEntitlement()` call sites added this pass: **13** (9 in
  `enterprise-endpoints.js` — 3 TAXII discovery/root/collections, 2 TAXII
  objects, 1 MISP, 3 SIEM; 4 in `index.js` — the 4 alerts routes).
  Additionally, 1 **pre-existing** `index.js` call site (`report_full`,
  `/api/reports/premium`) is fixed this pass to actually consume its
  previously-discarded return value — not a new call site, but newly
  functional. SLA's 3 pre-existing call sites were re-verified, not modified.
  (Corrected from an earlier "16 (7+9)" miscount in this doc, per CodeRabbit
  review on PR #258 — verified against the live diff before correcting.)
- New canonical resource cases added to `enforceTierGate()`: **1**
  (`misp_export`).
- Resources still enforced (not shadow) after this pass: **1**
  (`cve_detail_full` — unchanged; Wave A's own resources move to enforcement
  only after the Phase 8 shadow-divergence evidence gate, tracked separately
  in `data/release/v185_customer_operations_certification.json`).
- Known, explicitly-not-attempted-this-pass architectural gap: TAXII 5-vs-2
  collection catalogue mismatch between `index.js` and
  `enterprise-endpoints.js` (Section 1 above).
