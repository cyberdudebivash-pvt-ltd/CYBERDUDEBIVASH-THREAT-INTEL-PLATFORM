# Phase 4 — Gateway Enforcement (feature-flagged, per-resource, gradual)

**Date:** 2026-08-03
**Scope:** Give the 11 resources Phase 3 wired into shadow mode a real, feature-flagged path to actual enforcement — switched on gradually, one resource at a time, fully reversible. No new resources, no pricing changes, no schema changes.
**Builds on:** Phases 0–3, already in `main` (Phase 3 = PR #96, merged).

---

## 1. Discovery — what already existed

Phase 3 shipped `shadowCheckEntitlement()` (`index.js`) wired into 11 resources / 12 call sites (`taxii_access`, `taxii_kev` ×2, `brand_protection`, `vendor_risk`, `vendor_risk_bulk`, `geopolitical_risk`, `nlq`, `incident_response`, `incident_delete`, `intel_manifest_full`, `cve_detail_full`). It computes what `enforceTierGate()` (`revenue-enforcement.js`) would decide, compares it to the ad-hoc decision the call site already makes, and logs a mismatch — but never changes the response. That function is unmodified in this phase.

Re-read every one of the 12 call sites in full before writing any code (not just the Phase 3 doc's summary). Finding: **all 12 reduce to the same shape** — a single boolean (`adHocAllowed` under various local names) computed directly from an `auth.tier` comparison, then used either to short-circuit into a hard-rejection response (9 sites: `taxii_access`, `taxii_kev`-objects, `brand_protection`, `vendor_risk`, `vendor_risk_bulk`, `geopolitical_risk`, `nlq`, `incident_response`, `incident_delete`) or to pick between two response shapes / mask a field (3 sites: `taxii_kev`-collections-list sets `can_read`, `intel_manifest_full` picks which R2 object to serve, `cve_detail_full` picks summary vs. full). Both categories reduce to "one boolean drives the outcome," so one mechanism covers all 12 without a special case.

Also confirmed by reading `enforceTierGate`'s 11 Phase 3 resource cases directly (`revenue-enforcement.js:287-406`): every threshold (`isFree` / `isEnt`) is an exact mirror of the corresponding ad-hoc `auth.tier === TIERS.FREE` / `auth.tier === TIERS.ENTERPRISE || auth.tier === TIERS.MSSP` check. Since Phase 3 already fixed the tier vocabulary, there is currently **zero expected divergence** between the ad-hoc decision and the engine's decision for any of the 11 resources — which is exactly what makes turning enforcement on safe to attempt: if a mismatch ever fires post-enforcement, it is a real, actionable finding, not noise.

**Confirmed out of scope (no ad-hoc call site exists to "switch over"):** the original 17 pre-Phase-3 `enforceTierGate` resource cases (`ioc_full`, `stix_bundle`, `ai_full`, `report_full`, `siem`, `alerts`, `api_keys`, `ioc_confidence_detail`, `stix_export_full`, `ai_predict`, `ai_campaigns`, `ai_anomalies`, `intel_graph`, `intel_graph_full`, `intel_relations`, `detection_rules`, `actor_attribution`). Their only two live callers (`campaigns_paywall`/`anomalies_paywall`) hardcode the literal `"free"` to build a masked view unconditionally — they are not gates on the requester's own tier, so there is no existing ad-hoc decision to consolidate. Wiring those 17 up to real request-time gates would be *new* access control on previously ungated paths, a fundamentally different (and much larger) risk profile than "Gateway Enforcement" as scoped by the roadmap. Not touched.

## 2. What this phase actually did

1. **Added two feature flags** (`workers/intel-gateway/wrangler.toml`, both `[vars]` and `[env.production.vars]`, same pattern as Phase 1's `SUBSCRIPTION_EXPIRY_ENABLED`):
   - `ENTITLEMENT_ENFORCEMENT_ENABLED` (default `"false"`) — master kill switch.
   - `ENTITLEMENT_ENFORCEMENT_RESOURCES` (default `""`) — comma-separated allowlist of resource names actually enforced when the master switch is `"true"`. Empty list = nothing enforced regardless of the master switch. This is the per-resource dial that makes rollout gradual, as the roadmap specified.
2. **Added `isEntitlementEnforced(env, resource)` and `resolveEntitlement(ctx, env, resource, auth, adHocAllowed)`** (`index.js`, immediately after `shadowCheckEntitlement`). `resolveEntitlement` calls the unmodified `shadowCheckEntitlement` (so the Phase 3 shadow-mismatch log keeps firing exactly as before, unconditionally), then:
   - If enforcement is off for that resource (the default): returns `{ allowed: adHocAllowed, enforced: false }` — i.e., the original ad-hoc value, verbatim.
   - If enforcement is on for that resource: returns `{ allowed: decision.allowed, enforced: true }` — the engine's decision — and, only if it actually differs from the ad-hoc value, logs a new, distinct `entitlement_enforced_override` audit event (separate from Phase 3's passive `entitlement_shadow_mismatch`, so an operator watching a rollout sees an unambiguous, high-signal event only when live behavior actually changed).
3. **Rewired all 12 call sites** to gate on `resolveEntitlement(...).allowed` instead of the raw ad-hoc boolean, computed exactly as before and passed straight through as the fallback. Every rejection response's status code, body, and shape is untouched — verified byte-for-byte in the diff (§9).
4. **No changes to `revenue-enforcement.js`.** Everything Phase 4 needed (correct tier vocabulary, all 11 resource cases) was already built and shipped in Phase 3 — pure reuse.

## 3. Feature flags — rollout runbook

| Flag | Default | Effect |
|---|---|---|
| `ENTITLEMENT_ENFORCEMENT_ENABLED` | `"false"` | Master switch. `"false"` = every one of the 12 call sites behaves exactly as before Phase 4, unconditionally (verified in `resolveEntitlement`: the enforcement branch is never reached). |
| `ENTITLEMENT_ENFORCEMENT_RESOURCES` | `""` | Comma-separated resource allowlist, e.g. `"cve_detail_full"` or `"cve_detail_full,nlq"`. Only listed resources are enforced; everything else stays ad-hoc even with the master switch on. |

**To turn on enforcement for one resource** (recommended: start with `cve_detail_full` or `intel_manifest_full` — read-only, highest traffic, easiest to observe):
1. Set `ENTITLEMENT_ENFORCEMENT_ENABLED = "true"`.
2. Set `ENTITLEMENT_ENFORCEMENT_RESOURCES = "cve_detail_full"`.
3. Deploy.
4. Watch `SECURITY_HUB_KV` `audit:*` events for `action: "entitlement_enforced_override"` with `resource: "cve_detail_full"`. Zero events after a day of real traffic = the engine and the ad-hoc check never disagreed for real requests — safe to add the next resource to the list. Any event = a real divergence just changed a live response; inspect `ad_hoc_allowed` vs. `engine_allowed` and `engine_reason` before proceeding further.
5. Repeat, adding one resource at a time, until all 11 are enforced (or a decision is made to leave some permanently ad-hoc).

**To roll back:** set `ENTITLEMENT_ENFORCEMENT_ENABLED` back to `"false"` (or remove the resource from the list). No code change, no redeploy of logic — same reversibility guarantee as every prior phase's flags.

## 4. Dependency graph

```
index.js (live request handling)
  │
  ├── 12 call sites (unchanged ad-hoc boolean computed exactly as before)
  │     │
  │     └── resolveEntitlement(ctx, env, resource, auth, adHocAllowed)   [Phase 4, new]
  │            │
  │            ├── shadowCheckEntitlement(...)  [Phase 3, UNMODIFIED]
  │            │      ├──▶ enforceTierGate(resource, auth.tier)  [revenue-enforcement.js, UNMODIFIED]
  │            │      └──if mismatch──▶ auditLog(...) ──▶ SECURITY_HUB_KV  "entitlement_shadow_mismatch"
  │            │
  │            ├── isEntitlementEnforced(env, resource)  [Phase 4, new]
  │            │      reads ENTITLEMENT_ENFORCEMENT_ENABLED + ENTITLEMENT_ENFORCEMENT_RESOURCES
  │            │
  │            ├── if NOT enforced (default): returns adHocAllowed unchanged
  │            │
  │            └── if enforced AND decision differs: returns engine's decision,
  │                   logs "entitlement_enforced_override" ──▶ SECURITY_HUB_KV
  │
  └── every rejection response body/shape/status code: byte-identical to pre-Phase-4
```

## 5. Files changed

| File | Change |
|---|---|
| `workers/intel-gateway/wrangler.toml` | Two new flags added to `[vars]` and `[env.production.vars]`: `ENTITLEMENT_ENFORCEMENT_ENABLED="false"`, `ENTITLEMENT_ENFORCEMENT_RESOURCES=""` |
| `workers/intel-gateway/src/index.js` | New `isEntitlementEnforced()` + `resolveEntitlement()`; all 12 `shadowCheckEntitlement(...)` call sites replaced with `resolveEntitlement(...).allowed`, ad-hoc boolean computation preserved verbatim as the fallback value |
| `docs/PHASE4_GATEWAY_ENFORCEMENT.md` | New — this document |

`revenue-enforcement.js` — **not modified**. Everything this phase needed was already correct after Phase 3.

## 6. Duplicate logic removed / consolidated

None removed (nothing was duplicated to begin with — Phase 3 already consolidated the *decision logic* into `enforceTierGate`; Phase 4 only adds the *switch* that lets that decision reach the response). No duplicate engines or routes introduced.

## 7. Schema / storage changes

None. One new audit `action` value (`entitlement_enforced_override`) reuses the exact same `SECURITY_HUB_KV` `audit:{ts}:{rand}` key pattern, TTL, and `auditLog()` mechanism as every other audit event in this codebase.

## 8. Feature flags

Both described in full in §3. This is the entire enforcement mechanism for this phase — there is no enforcement without both flags explicitly set.

## 9. Migration strategy / Rollback

No data shape changes, no migration needed. Rollback is `git revert` for code, or simply resetting either flag to its default for behavior — both are equally safe and instant.

## 10. Security review

- No auth logic touched. `resolveAuth()` unmodified, `enforceTierGate()` unmodified, `shadowCheckEntitlement()` unmodified.
- **Default state is provably a no-op.** `isEntitlementEnforced()` returns `false` unconditionally when `ENTITLEMENT_ENFORCEMENT_ENABLED !== "true"` (the shipped default) — confirmed by direct reading of the function, not just the flag value, so there is no code path in the default configuration that can return anything other than the original ad-hoc decision.
- Every one of the 12 rejection response bodies (error text, `upgrade_url`, status code) is untouched — confirmed via direct diff inspection (§4 of the diff shown to the reviewer), not merely by construction.
- `resolveEntitlement` never throws: `shadowCheckEntitlement` already fails safe internally (try/catch around `enforceTierGate`, defaults to `adHocAllowed` on error), and `resolveEntitlement`'s own logic is a pure comparison with no I/O beyond the pre-existing `auditLog` call.
- Enforcement, when turned on, can only make a decision *more* aligned with `enforceTierGate`'s evidence-based rules — since those rules were built by tracing these exact 12 call sites in Phase 3, turning enforcement on is expected to be behavior-neutral in the steady state, and any exception is now individually observable per resource before affecting the next one.
- No new secrets, no new external calls, no new KV namespace, no D1/R2/schema changes.

## 11. Performance impact

Negligible and unchanged from Phase 3 — `resolveEntitlement` adds one string comparison and, at most, one env-var read (`isEntitlementEnforced`) on top of the existing `shadowCheckEntitlement` call already present at every site. No new I/O on the request's critical path; the only KV write (`entitlement_enforced_override`) is `ctx.waitUntil`-deferred via the existing `auditLog`, same as `entitlement_shadow_mismatch`, and only fires when enforcement is on for that resource *and* a real divergence occurs.

## 12. Test evidence

- [x] `node --check` on `index.js`.
- [x] Full module graph load (`node --input-type=module -e "await import('./index.js')"`) via a scratch-only copy (same pre-existing, unrelated Node JSON-import-assertion workaround as Phase 3 — Cloudflare's real bundler doesn't require it). Zero load errors.
- [x] `wrangler.toml` parsed with Python's `tomllib` — valid TOML, both `[vars]` and `[env.production.vars]` carry both new flags at their documented default values.
- [x] `python3 scripts/regression_tests.py` — 21/21 PASS.
- [x] No conflict markers; clean rebase onto latest `main`.
- [x] Full diff re-trace confirming: (a) every rejection response body/status code is byte-identical to pre-Phase-4, (b) every ad-hoc boolean expression is computed exactly as before and passed as the fallback, (c) `shadowCheckEntitlement`'s only caller is now `resolveEntitlement`, its own body untouched.
- [ ] **Not done, flagged rather than hidden:** no resource has actually been enforced in production yet (both flags remain at their safe defaults after this PR). Turning on the first resource, and confirming zero `entitlement_enforced_override` events over real traffic, is deliberately left as a post-merge operational step (§3 runbook) — not part of this PR.

## 13. Production validation checklist

- [x] Regression suite green
- [x] Full module graph loads without error
- [x] Default configuration verified to be a behavioral no-op (both flags at documented defaults; `isEntitlementEnforced` traced to confirm it cannot return `true` in that configuration)
- [x] Zero response-shape change verified by construction and by direct diff review at all 12 sites
- [ ] Owner/team: follow the §3 runbook to enable enforcement one resource at a time, watching `entitlement_enforced_override` audit events (`SECURITY_HUB_KV`, `audit:*` keys) before adding the next resource

## 14. Deferred work (explicitly out of scope per the roadmap)

- Actually flipping the flags in production and working through the 11-resource rollout — an operational task following §3's runbook, not a code change, and deliberately not done as part of this PR (see §12).
- Wiring the 17 pre-Phase-3 `enforceTierGate` resource cases (`ioc_full`, `stix_bundle`, etc.) to real request-time gates — no ad-hoc call site exists for them today, so this would be net-new access control, not enforcement of an existing decision. A different, future task.
- Pricing consolidation (5-way conflict, unchanged since Phase 3) — needs a business decision, not code.
- Trial Engine reconciliation — unchanged since Phase 3.
- Per Phase 5+ of the roadmap: Subscription Automation, Commercial Platform, Platform Hardening, Enterprise Scale.
