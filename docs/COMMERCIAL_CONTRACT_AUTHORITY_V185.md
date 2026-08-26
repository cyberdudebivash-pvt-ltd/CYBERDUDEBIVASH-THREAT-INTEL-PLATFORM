# SENTINEL APEX — Commercial Contract Authority (v185)

**Purpose:** one canonical reference for what each tier costs, what it's entitled to, and — for every figure — which source is authoritative, which sources previously conflicted, and which conflicts remain open pending a business decision.

**Method:** every figure below was traced to its actual enforcement or checkout code path, not inferred from whichever source appeared most often. See "Checkout source" and "Backend enforced source" columns for the trace.

**Status as of this document:** the real Razorpay checkout authority (`pricing-data.json` via `pricing.js` via `handleRazorpayCreateOrder`) is the canonical price source. It has been cross-checked against every other pricing surface in this pass; conflicts found against it were fixed in code (see "Conflict?" column), except where explicitly marked `BLOCKED_BUSINESS_DECISION`.

---

## 1. Price

| Field | FREE | PRO | ENTERPRISE | MSSP |
|---|---|---|---|---|
| **Monthly (USD)** | $0 | **$49** | **$499** | $1,999 |
| **Monthly (INR)** | ₹0 | **₹4,100** | **₹41,600** | ₹166,600 |
| **Annual (USD)** | — | $490 | $4,790 | $19,190 |
| **Annual (INR)** | — | ₹41,000 | ₹416,000 | ₹1,666,000 |
| Customer-visible source | `pricing.html`, `upgrade.html` | same | same | same |
| Checkout source (authoritative) | n/a | `pricing-data.json` via `handleRazorpayCreateOrder` | same | same |
| Backend enforced source | n/a | same as checkout | same as checkout | same as checkout |
| Conflict? | — | **Fixed this pass** — `revenue-enforcement.js` `PRICING.premium`/`prices.pro` said $29, corrected to $49 | **Fixed this pass** — `revenue-enforcement.js` `PRICING.enterprise`/`prices.enterprise` said $199, corrected to $499 | None found |
| Canonical authority | — | `pricing-data.json` | `pricing-data.json` | `pricing-data.json` |

### How the Enterprise conflict was resolved (Phase 2 method, not majority vote)

Traced the real production checkout path exactly as required: customer clicks Enterprise → frontend sends `{tier:"ENTERPRISE", email, billing}` (no price) → `handleRazorpayCreateOrder` (`workers/intel-gateway/src/index.js:2962`) looks up `RAZORPAY_TIER_PRICES["ENTERPRISE"]` (imported from `pricing.js`, which is `pricing-data.json.tiers`) → `amount = pricing.monthly` = `4160000` (paise) → this exact amount is sent to Razorpay's real Orders API (`https://api.razorpay.com/v1/orders`). The client never supplies or influences the amount. `4160000` paise = INR 41,600/mo = $499/mo at the rate the platform's own annual/GST math already uses elsewhere. `upgrade.html` and `pricing.html` already advertised $499/₹41,600 consistently before this pass — the only place still disagreeing was `revenue-enforcement.js`'s two informational-text objects (`REVENUE_CONFIG.PRICING.enterprise` and the local `prices` object inside `getUpgradeFeatures()`), which fed the live paywall JSON response (`upgrade.price`, `upgrade.cta_primary`) shown to customers hitting a 402/403. Both corrected to $499/₹41,600 in this pass — no business decision was needed because the checkout authority was unambiguous.

### Still open — annual Enterprise/MSSP figure (`pricing-data.json`'s own note)

`pricing-data.json` carries this note verbatim, unresolved:

> *"config/pricing.json and config/subscription_tiers.json currently state different ENTERPRISE and MSSP annual figures (ENTERPRISE annual: this file says 41600000 paise / INR 41,600 vs config/pricing.json's 41500000 paise / INR 41,500; MSSP annual: this file says 166600000 paise / INR 166,600 vs config/pricing.json's 160000000 paise / INR 160,000). Do not resolve that discrepancy by editing the numbers in this file based on inference — it must be resolved by a supplied, business-approved figure."*

**`ENTERPRISE_ANNUAL_PRICE_STATUS = BLOCKED_BUSINESS_DECISION`** — a ₹100/₹6,000 discrepancy between two config files, neither of which is the live checkout amount for the *annual* cadence specifically (the monthly amount is proven above; the annual figure was not independently re-traced through a real annual checkout in this pass since no annual test order was placed). Do not resolve without a supplied figure.

---

## 2. Rate limits and quotas

| Field | FREE | PRO | ENTERPRISE | MSSP |
|---|---|---|---|---|
| **Requests/minute (enforced)** | 30 | **120** | **600** | **1,200** |
| **Requests/day (enforced)** | 100 | **5,000** | Unlimited (-1) | Unlimited (-1) |
| Customer-visible source | `upgrade.html`, `trial-center.html` | same | same | same |
| Backend enforced source | `RATE_LIMITS` (`index.js:150`), sliding 60s window via `RATE_LIMIT_KV` | same | same | same |
| Conflict? | Fixed in PR #250/#251 | Fixed in PR #250 (was 500/min on 2 pages), PR #251 (was 1,000/day on `trial-center.html`) | Fixed in PR #250 (was 2,000/min; daily was variously 50,000/10,000 across pages, corrected to Unlimited) | Fixed in PR #250 (was marked unlimited/min in `revenue-enforcement.js`; corrected to 1,200/min, which matches `RATE_LIMITS.MSSP`) |
| Canonical authority | `index.js` `RATE_LIMITS` const + `revenue-enforcement.js` `LIMITS.*.api_calls_day` | same | same | same |

**Distinguishing the two controls (per this mission's Phase 12 instruction):** `RATE_LIMITS` in `index.js` is a **burst/per-minute** sliding-window limiter, keyed per-IP per-60s-bucket in `RATE_LIMIT_KV`. `LIMITS.*.api_calls_day` in `revenue-enforcement.js` is a **separate daily allowance**, tracked via `trackUsageAndEnforce()`. Both apply simultaneously; neither substitutes for the other. Live 429/Retry-After/header behavior under load was **not** independently load-tested in this pass (no `ADMIN_SECRET` — see the mission's blocked-phase list).

---

## 3. Feature entitlements

| Resource | FREE | PRO | ENTERPRISE | MSSP | Canonical gate |
|---|---|---|---|---|---|
| Live feed (metadata) | ✓ | ✓ | ✓ | ✓ | unauthenticated |
| Full IOC arrays | ✗ | ✓ | ✓ | ✓ | `enforceTierGate("ioc_full")` |
| STIX 2.1 bundle | ✗ | metadata only | full | full | `enforceTierGate("stix_bundle")` |
| TAXII 2.1 (main collection) | ✗ | ✓ | ✓ | ✓ | `enforceTierGate("taxii_access")` |
| TAXII CISA-KEV collection | ✗ | ✗ | ✓ | ✓ | `enforceTierGate("taxii_kev")` / `resolveEntitlement` (1 of the entitlement-enforced resources) |
| MISP JSON export | ✗ | ✗ | ✓ | ✓ | scope system, `SCOPE_DEFINITIONS["export:misp"]` |
| SIEM webhook push | ✗ | ✗ | ✓ | ✓ | `enforceTierGate("siem")` |
| SLA reports/incidents/certificate | ✗ | ✗ | ✓ | ✓ (fixed PR #249 — was wrongly excluding MSSP) | `sla-monitor.js` inline checks |
| CVE full detail | ✗ | ✓ | ✓ | ✓ | `resolveEntitlement("cve_detail_full")` — **the only resource on the canonical enforcement path today** |
| Enterprise scoring / MSSP routing | ✗ | ✗ | ✓ | ✓ | `enterprise-endpoints.js` `requireEnterprise`/`requireProOrEnterprise` |

Full per-route inventory (route, legacy check, canonical check, migration status) is in the entitlement-authority findings from this session's earlier Phase 4 audit — summarized in Section 4 below rather than duplicated here in full.

---

## 4. Entitlement architecture — current state (carried forward from this session's Phase 4 audit, not re-derived)

**There is no single canonical entitlement authority today.** At least 8 independently-coded gating mechanisms coexist in production simultaneously:

1. `resolveEntitlement()`/`shadowCheckEntitlement()` (`index.js:434-490`) — a shadow-mode wrapper around `enforceTierGate()`. 13 call sites, 11 resources, but `ENTITLEMENT_ENFORCEMENT_RESOURCES=cve_detail_full` means **only 1 resource is actually governed by it**; the other 10 are shadow-logging only.
2. `enforceTierGate()` (`revenue-enforcement.js:118`) — the fullest policy table (~19 resources), called directly (bypassing `resolveEntitlement`) from `p18-handlers.js`, `p31-handlers.js` (4 sites), and 2 hardcoded sites in `index.js`.
3. `applyTierGateV2()` — per-item feed masking, 9 call sites across `index.js`/`api-extensions.js`.
4. `requireEnterprise()`/`requireProOrEnterprise()` (`enterprise-endpoints.js`) — ~16 gates covering TAXII, MISP, Sigma/YARA bulk, scoring, webhooks, SIEM, SSE stream, MSSP routing. **Never calls `resolveEntitlement` or `enforceTierGate`.**
5. Scope-based system (`api-extensions.js`) — a fifth, structurally distinct mechanism (`SCOPE_DEFINITIONS`, `enforceScopeMiddleware`), with its own `normalizeTier()`. Several handlers redundantly layer this *and* an inline `tier === "free"` check for the same decision.
6. Plain inline `tier ===` checks scattered through `index.js` with no shared function.
7. Per-file re-implementations: `sla-monitor.js`, `alert-engine.js`, `premium-reports.js`, `credit-system.js`, `usage-meter.js` — each with its own tier-string normalization. At least 6 of these files independently carry a "ZERO-TRUST HARDENING FIX" comment for the *same* uppercase/lowercase tier-casing bug, found and fixed separately each time — direct evidence that the lack of one shared authority has already caused repeated real incidents.
8. `isCustomerReady()` (`publication-gate.js`) — a content-readiness gate, orthogonal to tier, composed with (not duplicating) the above.

**Quantified:** of ~50+ distinct access-decision points in the codebase, only ~13 touch `resolveEntitlement`, and only 1 resource is actually enforced by it in production.

**One confirmed live bug from this fragmentation, already fixed (PR #249):** `sla-monitor.js` excluded MSSP from Enterprise-tier gates — the platform's top-paying tier was denied SLA reports/incidents/certificates that ENTERPRISE got.

**Subscription expiry:** checked in exactly one place (`resolveAuth()`'s API-key-KV branch, `index.js:383`), currently inert because `SUBSCRIPTION_EXPIRY_ENABLED=false` means `expires_at` is hardcoded `null` for every new key. The JWT auth path never re-checks expiry after token issuance. `alert-engine.js` dispatch uses a KV-cached tier snapshot from subscribe-time, which would not see a later expiry even if the flag were enabled centrally.

**Conclusion for Phase 4/8 of this mission:** migrating "every paid resource" onto canonical enforcement in one pass is not a config flip — it requires reconciling 8 independent code paths, several of which (`enterprise-endpoints.js`, `sla-monitor.js`, `alert-engine.js`) have zero contact with `resolveEntitlement` today. This is real, multi-PR engineering work, not something safely completed as a rushed side effect of this pass. See PR #252's body for what specific migration slice (if any) was completed in this tranche versus deferred.

---

## 5. Trial contract

Fixed in PR #251. Only the **Community** tier is genuinely free/no-payment (`/api/apikeys/request-free`, real, wired, no card). PRO/Enterprise/MSSP "trial" buttons redirect to the real, full-price Razorpay/Gumroad checkout with no reduced charge, no distinct trial period, and no automatic suspension (since `SUBSCRIPTION_EXPIRY_ENABLED=false`). `trial-center.html` now describes this accurately. See PR #251 for the full list of contradictory claims removed.

---

## 6. Payment security finding (this pass)

**`handleRazorpayVerify`** (`index.js:3003`, the client-initiated payment-verify endpoint called immediately after Razorpay checkout) previously derived the tier to provision from a **client-supplied, unsigned** `tier` field in the request body. The Razorpay signature check only proves `order_id|payment_id` is authentic — it says nothing about which tier that specific payment was for. This endpoint normally wins the provisioning race against the signed server-to-server webhook (`handleWebhookRazorpay`, which already derived tier correctly from Razorpay's own signed `notes.tier`), since it fires synchronously right after checkout while the webhook arrives async — making it the **primary**, not an edge-case, provisioning path.

**Exploit scenario (pre-fix):** pay the real PRO order (₹4,100), then call `/api/payment/razorpay/verify` with `tier:"ENTERPRISE"` in the body → provisioned an Enterprise-tier key for PRO money.

**Fixed this pass:** the endpoint now fetches the payment record back from Razorpay's own API (authoritative, not client-suppliable), verifies it is `captured` and bound to the claimed `order_id` (closing a secondary payment/order-confusion vector), and derives tier exclusively from the payment's own `notes.tier` (set server-side at order-creation time). The client's `tier` field is no longer read at all.

This is the single most significant finding of this pass — see PR #252 for the full diff and rationale.

---

## 7. Blocked items (this pass)

| Item | Status | Reason |
|---|---|---|
| Enterprise annual price (₹41,600 vs ₹41,500) | `BLOCKED_BUSINESS_DECISION` | No live annual checkout was traced in this pass; `pricing-data.json` itself says not to resolve by inference |
| MSSP annual price (₹166,600 vs ₹160,000) | `BLOCKED_BUSINESS_DECISION` | Same reason |
| Full canonical entitlement migration (Phase 8) | Not completed this pass | Requires reconciling 8 independent gating mechanisms across many files — real multi-PR work, not a config flip |
| `SUBSCRIPTION_EXPIRY_ENABLED=true` cutover (Phase 7) | Not enabled | Mission's own rule: requires Phase 5's full lifecycle regression suite passing against live identities first, which requires `ADMIN_SECRET` (not available this session) |
| Live black-box customer journeys, tenant isolation, rate-limit load testing | `BLOCKED_BY_SECRET` | No `ADMIN_SECRET` available in this session's runtime — verified via presence-only check (`ADMIN_SECRET_PRESENT=false`), never printed |
