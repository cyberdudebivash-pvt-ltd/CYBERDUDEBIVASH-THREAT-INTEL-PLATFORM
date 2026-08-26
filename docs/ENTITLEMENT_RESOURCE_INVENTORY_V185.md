# CYBERDUDEBIVASH SENTINEL APEX — Entitlement Resource Inventory (v185)

**Mission:** SENTINEL APEX v185.0 — Final Entitlement Lifecycle, Subscription
Expiry & Commercial Customer Operations Certification, Phase 3.

**Correction to the mission's stated baseline:** the mission brief describes
canonical entitlement coverage as "previously covered only `cve_detail_full`".
That is not what the live code shows. A canonical entitlement engine already
exists and is wired into 12 call sites across `index.js` (11 of them shadow-
mode only, 1 — `cve_detail_full` — actually enforced), plus a 28-case (now
31, see below) `enforceTierGate()` policy switch in `revenue-enforcement.js`.
This document reports what is actually true in the code as of this pass, not
the mission's assumed starting point, per this repository's own "verify
actual production, do not fabricate results" standing rule.

---

## 1. The existing entitlement engine (what it is, exactly)

`workers/intel-gateway/src/index.js`:

- `resolveEntitlement(ctx, env, resource, auth, adHocAllowed)` (~line 476) —
  the canonical decision gateway. Every call site passes in the resource
  name, the caller's resolved `auth`, and the ad-hoc boolean the handler
  already independently computes.
- `shadowCheckEntitlement(...)` — calls `enforceTierGate(resource, tier)`
  (the real policy engine, in `revenue-enforcement.js`) and audit-logs a
  `entitlement_shadow_mismatch` event if its decision differs from the ad-hoc
  one. Never changes the response.
- `isEntitlementEnforced(env, resource)` — per-resource feature flag, gated
  by `env.ENTITLEMENT_ENFORCEMENT_ENABLED` (bool) and
  `env.ENTITLEMENT_ENFORCEMENT_RESOURCES` (comma-separated allowlist).
- `resolveEntitlement()` composes both: always shadow-logs; only lets the
  engine's decision override the ad-hoc one when the resource's flag is on,
  logging a distinct `entitlement_enforced_override` event when it does.

This is exactly the shadow-then-cutover architecture Mission v185.0 Phase 6
("Shadow Entitlement Comparison") and Phase 8 ask to be built. **It already
exists.** What's incomplete is coverage (most paid routes aren't wired to it
at all) and enforcement (only 1 of 31 defined resources is actually flipped
on).

**Current `wrangler.toml` state (both `[vars]` and `[env.production.vars]`,
confirmed identical, zero drift):**

```
ENTITLEMENT_ENFORCEMENT_ENABLED = "true"
ENTITLEMENT_ENFORCEMENT_RESOURCES = "cve_detail_full"
```

---

## 2. `enforceTierGate()` resource catalogue (`revenue-enforcement.js`)

31 resources defined (28 pre-existing + 3 added this pass — `sla_report`,
`sla_incidents`, `sla_certificate`, mirroring `sla-monitor.js`'s own
`ENTERPRISE`-or-`MSSP` ad-hoc gate exactly). `default:` falls through to
`{ allowed: true }` — deliberate fail-open for any unrecognized resource
name, so a typo never hard-blocks a real customer. (This is exactly why
`scripts/entitlement_resource_drift_gate.py`, added this pass and wired into
CI as STAGE 4.065, hard-fails if `ENTITLEMENT_ENFORCEMENT_RESOURCES` ever
names something outside this list — that combination is a silent fail-open
on a resource an operator believed was enforced.)

| Resource | Rule | Wired to `resolveEntitlement`? | Enforced? |
|---|---|---|---|
| `cve_detail_full` | FREE blocked | Yes (index.js:4706) | **Yes** |
| `taxii_access` | FREE blocked | Yes (index.js:2266) | Shadow only |
| `taxii_kev` | ENTERPRISE/MSSP only | Yes (index.js:2273, 2298) | Shadow only |
| `brand_protection` | FREE blocked | Yes (index.js:3387) | Shadow only |
| `vendor_risk` | FREE blocked | Yes (index.js:3495) | Shadow only |
| `vendor_risk_bulk` | ENTERPRISE/MSSP only | Yes (index.js:3512) | Shadow only |
| `geopolitical_risk` | FREE blocked | Yes (index.js:3591) | Shadow only |
| `nlq` | FREE blocked | Yes (index.js:3732) | Shadow only |
| `incident_response` | FREE blocked | Yes (index.js:3784) | Shadow only |
| `incident_delete` | ENTERPRISE/MSSP only | Yes (index.js:3867) | Shadow only |
| `intel_manifest_full` | FREE blocked | Yes (index.js:4151) | Shadow only |
| `sla_report` | ENTERPRISE/MSSP only | **Yes — added this pass** (index.js ~5217) | Shadow only |
| `sla_incidents` | ENTERPRISE/MSSP only | **Yes — added this pass** (index.js ~5221) | Shadow only |
| `sla_certificate` | ENTERPRISE/MSSP only | **Yes — added this pass** (index.js ~5228) | Shadow only |
| `report_full` | FREE blocked | **Yes — added v185.5** (index.js `/api/reports/premium` route) | Shadow only |
| `ioc_full`, `stix_bundle`, `ai_full`, `siem`, `alerts`, `api_keys`, `ioc_confidence_detail`, `stix_export_full`, `ai_predict`, `ai_campaigns`, `ai_anomalies`, `intel_graph`, `intel_graph_full`, `intel_relations`, `detection_rules`, `actor_attribution` | various (see file) | **No call sites anywhere in `src/`** | N/A — dead policy |

The 16 resources in the last row are defined logic with zero callers. Most
map conceptually to real ad-hoc-gated routes (`ai_predict` ↔ `/api/predict`,
`intel_graph` ↔ `/api/v1/intel/graph`, `siem` ↔ `/api/siem/*`, etc.) but
those handlers use their own inline `tier === "..."` checks in
`api-extensions.js` / `enterprise-endpoints.js`, not this switch. Wiring them
is the Phase 8 migration backlog (§4).

---

## 3. Every paid/gated route found (full inventory, not wired vs. wired)

### 3a. Wired to the canonical engine (13 resources, listed above in §2)

### 3b. Gated ad-hoc, zero engine coverage, zero shadow observability

| Route | Min tier | File:Line |
|---|---|---|
| `/api/taxii/*` discovery/root/collections | PRO (+ENT for KEV/write) | enterprise-endpoints.js:78,108,132 — **separate tier helper from index.js's own `taxii_access`; two independent TAXII gates exist today** |
| `/api/taxii/*` object ingest (STIX write) | ENTERPRISE | enterprise-endpoints.js:218 |
| `/api/misp/export` (enterprise-endpoints.js's handler — note `/api/misp/export` in production actually routes through a *different* `handleMISPExportExt` in api-extensions.js; the enterprise-endpoints.js one may be dead code, needs confirming before migration) | ENTERPRISE | enterprise-endpoints.js:345 |
| `/api/sigma/bulk` | PRO (50 rules) / ENT (2000 rules) | enterprise-endpoints.js:474 |
| `/api/yara/bulk` | ENTERPRISE | enterprise-endpoints.js:544 |
| `/api/scoring`, `/api/scoring/kev`, `/api/scoring/ransomware`, `/api/scoring/velocity` | ENTERPRISE | enterprise-endpoints.js:583,640,683,730 |
| `/api/siem/splunk`, `/api/siem/sentinel`, `/api/siem/qradar` | ENTERPRISE | enterprise-endpoints.js:777,834,893 |
| `/api/stream` (SSE threat stream) | ENTERPRISE | enterprise-endpoints.js:956 |
| `/api/mssp/tenants/{tenant_id}/feed` | ENTERPRISE | enterprise-endpoints.js:1045 — **see §5, tenant_id is not verified against the caller's identity** |
| `/api/search` | scope-gated (`applyTierGateV2`) | api-extensions.js:246 |
| `/api/actors` | PRO (full); ENT (+ttp_detail) | api-extensions.js:378 |
| `/api/cves` | scope-gated (`read:cves`) | api-extensions.js:38 |
| `/api/export/csv` | scope-gated (`export:csv`) | api-extensions.js:40 |
| `/api/intel/correlate` | scope-gated | api-extensions.js |
| `/api/predict` | PRO (FREE blocked) | api-extensions.js:1320 |
| `/api/v1/campaigns/intel` | PRO (FREE blocked; ENT full `member_titles`) | api-extensions.js:1420 |
| `/api/v1/anomalies` | PRO (FREE blocked; ENT zero-day fields) | api-extensions.js:1514 |
| `/api/v1/intel/graph` | PRO (summary) / ENT (full nodes) | api-extensions.js:1588 |
| `/api/v1/intel/relations` | PRO (depth1, 5 results) / ENT (full) | api-extensions.js:1675 |
| `/api/alerts/subscribe` | PRO (FREE blocked) | alert-engine.js:102 |
| `/api/alerts/dispatch` | PRO | alert-engine.js:178 |
| `/api/alerts/history` | ENTERPRISE/MSSP | alert-engine.js:375 |
| `/api/reports/premium`, `/api/reports/list`, `/api/reports/{id}` | PRO / ENT (item caps differ) | premium-reports.js:266,504,578 — **already does real per-customer ownership checks (`meta.key_id === auth.sub`) on list/detail, see §5** |
| `/api/dark-web/scan`, `/api/dark-web/status`, `/api/leak-check` | N/A — **disabled, returns 503** | index.js:5228 — was PRO+/ENT before being disabled for serving simulated data; not a live gap |

### 3c. Free/preview routes (correctly ungated, listed for completeness)

`/api/feed` (preview/redacted for FREE), `/api/v1/apex.json` FREE-preview
path, `GET /api/sla/status`, `POST /api/sla/ping` (internal/cron), health
and status endpoints.

---

## 4. Phase 8 migration backlog (priority order per the mission brief)

Not attempted this pass beyond SLA (§2) — each of the following is real,
bounded, multi-file work requiring the same shadow-first pattern used for
SLA, sequenced to avoid a single oversized change:

1. **Premium feed** (`/api/feed` full-tier paths, `intel_manifest_full`
   already partially covers this — confirm full overlap)
2. **IOC arrays** (`ioc_full`, defined, unwired)
3. **STIX** (`stix_bundle`, `stix_export_full`, defined, unwired; also
   reconcile the two independent TAXII gates in §3b)
4. **TAXII** (enterprise-endpoints.js's `taxii_access`-equivalent helper —
   needs reconciling with index.js's existing wired `taxii_access` resource
   rather than adding a duplicate)
5. **MISP** (confirm which of the two MISP export handlers is actually live
   before wiring either)
6. **Premium reports** — ✅ done in v185.5 (`report_full`,
   `/api/reports/premium`, shadow-mode; note premium-reports.js already has
   stronger protection than most: real per-customer ownership checks, not
   just a tier check)
7. **SIEM** (`siem`, defined, unwired — 3 routes in enterprise-endpoints.js)
8. **Webhooks** (`/api/alerts/dispatch` and related — `alerts` resource
   defined, unwired)
9. **SLA** — ✅ done in v185.4/PR #253 (`sla_report`, `sla_incidents`,
   `sla_certificate`, shadow-mode)
10. **Enterprise APIs** (`/api/scoring/*`, `/api/stream` — no matching
    `enforceTierGate` resource exists yet, needs new cases)
11. **MSSP resources** (`/api/mssp/tenants/{id}/feed` — see §5 first,
    tenant-identity verification is a prerequisite, not just a wiring task)
12. **Remaining paid endpoints** (`/api/search`, `/api/actors`, `/api/cves`,
    `/api/export/csv`, `/api/intel/correlate`, `/api/predict`,
    `/api/v1/campaigns/intel`, `/api/v1/anomalies`, `/api/v1/intel/graph`,
    `/api/v1/intel/relations`)

**`CANONICAL_ENTITLEMENT_COVERAGE` today: 15 of ~46 identified paid resources
wired (≈33%), 1 of 31 defined resources actually enforced (≈3%). Not 100%.**
(v185.5: `report_full` added, `/api/reports/premium`, shadow mode, priority-6
item from the backlog below.)
Reaching 100% is real, sequenced, multi-PR work — not something to wildcard
in one pass per the mission's own Phase 8 instruction ("Do not enable all via
wildcard until each class is validated").

---

## 5. Findings surfaced by this inventory (not fixed this pass unless noted)

- **MSSP tenant feed (`/api/mssp/tenants/{tenant_id}/feed`) does not verify
  the caller owns `tenant_id`.** It checks `requireEnterprise(tier)` only;
  `tenant_id` comes straight from the URL path and is used purely as a
  response label / filter context, not as an authorization check. In
  practice this is lower severity than a classic BOLA because the underlying
  `items` are the same shared global feed for every tenant — there is no
  per-tenant *private* data in this codebase today for it to leak. But the
  endpoint's own `_mssp_note` ("Tenant-scoped feed") and its doc comment
  ("Tenant-scoped threat feed for MSSP multi-customer deployments") oversell
  what it does: any Enterprise/MSSP key can query any `tenant_id` string and
  get the identical filtered feed. This is a truth-in-product-behavior gap
  the same way the trial-contract issue (PR #251) and stale pricing (PR
  #252) were — not a data-leak vulnerability given current architecture, but
  a real misrepresentation. Flagged for Phase 11 (tenant isolation); not
  fixed here because a real fix means either (a) correcting the product
  copy to state the feed is shared, not isolated, or (b) building actual
  per-tenant data storage — both are product/architecture decisions beyond
  this pass's scope.
- **No `revoked`/`suspended`/`cancelled` state exists anywhere in the key
  record or `resolveAuth()`.** See `docs/SUBSCRIPTION_STATE_MODEL_V185.md`.
- **17 of 31 `enforceTierGate()` resources have zero callers** — dead policy
  logic. Not a security risk (nothing depends on them), but worth noting so
  a future pass doesn't assume "defined in the switch" means "protecting a
  real route" without checking.
- **Two independent TAXII gates exist** (index.js's `taxii_access` resource
  vs. enterprise-endpoints.js's own tier helper) — should be reconciled to
  one canonical check during the TAXII migration step (§4.4), not two
  parallel policies that could drift from each other.

---
*CYBERDUDEBIVASH SENTINEL APEX — Mission v185.0 Phase 3 deliverable*
