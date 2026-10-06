# Phase 3 — Entitlement Engine (Shadow Mode)

**Date:** 2026-08-03
**Scope:** Entitlement/policy engine consolidation + shadow-mode comparison logging. No enforcement switch (that's Phase 4, Gateway Enforcement), no pricing changes, no trial/provisioning changes.
**Builds on:** Phases 0–2, already in `main`.

---

## 1. Discovery (Stage 1/2) — what already existed

Before writing anything, searched for every existing tier/feature-gating implementation, matching the discipline used in Phase 0/2.

**Found: a real, already-built policy engine — `enforceTierGate()` in `workers/intel-gateway/src/revenue-enforcement.js` (806 lines).** 17 resource cases (`ioc_full`, `stix_bundle`, `ai_full`, `report_full`, `siem`, `alerts`, `api_keys`, `ioc_confidence_detail`, `stix_export_full`, `ai_predict`, `ai_campaigns`, `ai_anomalies`, `intel_graph`, `intel_graph_full`, `intel_relations`, `detection_rules`, `actor_attribution`), each returning `{allowed, reason, message, upgrade}` with genuinely good, human-readable copy and upgrade CTAs. This is exactly what "policy engine + feature mapping" asks for — largely already built.

**Found: it was never actually callable with a real tier.** `enforceTierGate`'s own tier vocabulary (`TIERS: {FREE:"free", PRO:"premium", ENTERPRISE:"enterprise"}`, no MSSP) does not match the live `TIERS` constant in `index.js` (`{FREE:"FREE", PRO:"PRO", ENTERPRISE:"ENTERPRISE", MSSP:"MSSP"}`). `enforceTierGate(resource, tier)` did `(tier||"free").toLowerCase()` then compared against `"premium"` — a real `auth.tier` of `"PRO"` lowercases to `"pro"`, which matches neither `"premium"` nor anything else, so every real PRO/ENTERPRISE/MSSP caller was silently treated as free. The only two live call sites (`index.js`'s `campaigns_paywall`/`anomalies_paywall`) sidestepped this by hardcoding the literal `"free"` — correct for what they do (building the free-tier-masked view unconditionally), not a workaround for the bug, but it meant the bug never surfaced.

**Found: 11 real feature gates with zero shared policy**, hand-rolled inline across `index.js`'s newer modules (brand protection, vendor risk, geopolitical, NLQ, incident response, TAXII, feed manifest, CVE detail) — each duplicating the same "if free tier, reject" pattern `enforceTierGate` already exists to centralize, apparently added without whoever wrote them knowing the engine was there.

**Found (out of scope, flagged): a third, dead trial-issuance path.** `revenue-enforcement.js` also contains `handleTrialIssuance`/`handleLeadCapture` (same `/api/leads/trial` route pattern already implemented, live and working, in `revenue-engine` — see Phase 0). Confirmed via grep: neither function is imported or called anywhere in `index.js` — fully dead code, unreachable, zero live impact. Worth noting for whoever picks up the Trial Engine phase: even if wired up, it stores the issued key under `key:${sha256(apiKey)}` in `API_KEYS_KV`, while `resolveAuth()` looks up `API_KEYS_KV.get(rawKey)` directly — the exact same class of bug a prior session's comment (found in Phase 0) already described fixing once in a *different* file. Not touched here — Trial Engine is explicitly deferred, and this code has zero production exposure today.

**Found (out of scope, flagged): a fifth pricing figure.** `REVENUE_CONFIG.PRICING` in this same file (`PRO: ₹2,499/$29`, `ENTERPRISE: ₹14,999/$199`) is yet another value, independent of the four already flagged in Phase 0/2 (`config/pricing.json`, `pricing-data.json`, `revenue-engine`'s own `TIERS`). Not touched — `PRICING` is out of scope for the entitlement domain, same "needs a business decision" treatment as the others.

## 2. What this phase actually did

1. **Fixed `enforceTierGate`'s tier vocabulary** to match the live `TIERS` constant exactly (`FREE`/`PRO`/`ENTERPRISE`/`MSSP`, uppercase), added the missing `MSSP` tier (evidenced as ≥ `ENTERPRISE` everywhere else in this codebase — every existing ad-hoc check pairs `ENTERPRISE`/`MSSP` identically). Fixed the same vocabulary in `trackUsageAndEnforce`, `buildUpgradeTrigger`, `applyTierGateV2` (the masking function, already live at 8 call sites — verified the fix doesn't change its behavior, since those call sites already pass the literal `"free"`, which normalizes identically either way), and `computeApexAIGated`. Left `PRICING`, `UPGRADE_URLS`, and the internal `targetTier`/`getUpgradeFeatures` display vocabulary alone (self-contained, don't compare against real tier values, out of scope).
2. **Added 11 new resource cases** to `enforceTierGate`, one per discovered ad-hoc gate, each matching the exact threshold and message the inline check already enforces (evidence-based, not invented): `taxii_access`, `taxii_kev`, `brand_protection`, `vendor_risk`, `vendor_risk_bulk`, `geopolitical_risk`, `nlq`, `incident_response`, `incident_delete`, `intel_manifest_full`, `cve_detail_full`.
3. **Added `shadowCheckEntitlement()`** (`index.js`) — computes what `enforceTierGate` would decide, compares against the ad-hoc decision already being made at that call site, logs a mismatch via the existing `auditLog`/`SECURITY_HUB_KV` mechanism if they differ. Never changes what's returned — the original ad-hoc `if` condition remains the sole thing determining the response at every site.
4. **Wired it into all 11 gates** (12 call sites — `taxii_kev` has two). Three handlers (`handleBrandProtection`, `handleVendorRisk`, `handleGeopolitical`) needed `ctx` threaded through as a new parameter (it was already available at their one call site each, just not passed down) — small, mechanical, safe.

## 3. Dependency graph

```
index.js (live request handling)
  │
  ├── TIERS = {FREE,PRO,ENTERPRISE,MSSP}  (single source of truth for tier identity)
  │
  ├── resolveAuth() ──reads──▶ API_KEYS_KV ──▶ { tier, key, sub }
  │
  ├── 11 ad-hoc gate sites (taxii ×2, brand, vendor-risk ×2, geo, nlq,
  │   incidents ×2, manifest, cve-detail)
  │     │
  │     ├──still solely determines the response── (unchanged)
  │     │
  │     └──shadowCheckEntitlement(ctx, env, resource, auth, currentDecision)
  │              │
  │              ├──▶ enforceTierGate(resource, auth.tier)  [revenue-enforcement.js]
  │              │        └──▶ REVENUE_CONFIG.{TIERS,LIMITS}  (fixed, Phase 3)
  │              │
  │              └──if mismatch──▶ auditLog(ctx, env, {...}) ──▶ SECURITY_HUB_KV
  │
  └── applyTierGateV2(item, tier, usageState)  [revenue-enforcement.js]
        (8 existing call sites, all pass "free" literally -- unaffected by this phase,
         verified behavior-identical before/after the vocabulary fix)
```

`revenue-enforcement.js` has zero imports — a leaf module. No circular-import risk from this phase's changes (unlike Phase 2, which had to work around a real one between three interdependent files).

## 4. Files changed

| File | Change |
|---|---|
| `workers/intel-gateway/src/revenue-enforcement.js` | Tier vocabulary fixed throughout (`TIERS`, `LIMITS` + MSSP added, `trackUsageAndEnforce`, `buildUpgradeTrigger`, `applyTierGateV2`, `computeApexAIGated`, dead `handleTrialIssuance`'s `TRIAL.tier`); 11 new resource cases added to `enforceTierGate` |
| `workers/intel-gateway/src/index.js` | New `shadowCheckEntitlement()` helper; `ctx` threaded through 3 handler signatures + their call sites; shadow-check calls added at 11 resources / 12 call sites |
| `docs/PHASE3_ENTITLEMENT_ENGINE.md` | New — this document |

## 5. Duplicate logic removed / consolidated

- 11 previously-independent inline tier checks now delegate their *decision logic* (via shadow comparison, not yet enforcement) to one shared policy function instead of each re-deriving "is this tier allowed" from scratch.
- No duplicate engines introduced. `enforceTierGate` remains the one policy function; it was extended, not replaced or shadowed by a second implementation.

## 6. Schema / storage changes

None. Shadow-mismatch events reuse the existing `SECURITY_HUB_KV` `audit:{ts}:{rand}` key pattern `auditLog` already writes, same TTL, same namespace.

## 7. Feature flags

None needed for this phase — same reasoning as Phase 2: every change is either a bug fix (tier vocabulary, which had zero real effect before since the engine was never callable with real data) or purely additive observability (shadow-mode logging that never changes a response). There is no new enforcement to gate.

## 8. Migration strategy / Rollback

None needed (no data shape changes). `git revert` — every change is additive or a same-file consistency fix.

## 9. Security review

- No auth logic touched. `resolveAuth()` unmodified.
- No response any caller receives is different before/after this PR — verified by construction (every shadow-check call sits alongside, not in place of, the original condition) and by re-reading every diff hunk against the original.
- `shadowCheckEntitlement` fails safe: wrapped in try/catch, a bug in the comparison itself can never affect the real (already-executed) decision, and never throws into the caller.
- The MSSP-as-≥-ENTERPRISE assumption is evidenced (every existing ad-hoc check already treats them identically) not invented, so it doesn't create a new privilege level.
- Known, deliberately out-of-scope item found during discovery: the dead `handleTrialIssuance` key-storage bug (§1). Zero production exposure (unreachable), flagged for whoever picks up Trial Engine rather than fixed here (fixing it would mean touching provisioning logic, explicitly out of this phase's lock).

## 10. Performance impact

Negligible. `shadowCheckEntitlement` is one function call (no I/O) plus, only on a mismatch, one `ctx.waitUntil`-deferred KV write (same non-blocking pattern `auditLog` already uses elsewhere) — never on the request's critical path, never adds latency to the response.

## 11. Test evidence

- [x] `node --check` on both files.
- [x] Full module graph load verified (worked around Node's JSON-import-assertion requirement in a scratch copy only — a Node-tooling quirk unrelated to this change and pre-existing on `pricing.js`'s import of `pricing-data.json`; Cloudflare's actual bundler doesn't require it). Zero load errors.
- [x] `python3 scripts/regression_tests.py` — 21/21 PASS.
- [x] No conflict markers.
- [x] Manual re-trace of all 11 gates confirming the original ad-hoc condition is untouched and remains the sole determinant of the response; `shadowCheckEntitlement` is additive-only at every site.
- [x] Confirmed `applyTierGateV2`'s 8 existing call sites (all pass literal `"free"`) are behavior-identical before/after the vocabulary fix, since `"free"` normalizes to `"FREE"` either way.
- [ ] **Not done, flagged rather than hidden**: no real production traffic has hit these paths yet post-deploy, so no actual `entitlement_shadow_mismatch` events have been observed. That's the entire point of shipping this in shadow mode — watch for mismatches over real traffic before Phase 4 considers switching enforcement.

## 12. Production validation checklist

- [x] Regression suite green
- [x] Full module graph loads without error
- [x] Zero response-shape change verified by construction at all 11 sites
- [x] MSSP support added evidence-based, not invented
- [ ] Owner/team: watch `entitlement_shadow_mismatch` audit events (`SECURITY_HUB_KV`, `audit:*` keys, `action: "entitlement_shadow_mismatch"`) for the first days of real traffic before Phase 4 considers enforcement

## 13. Deferred work (explicitly out of scope per the lock)

- Gateway Enforcement (Phase 4) — actually switching any of these 11 gates over to `enforceTierGate`'s decision. This phase only observes; nothing is enforced by the new engine yet.
- Pricing consolidation (now a confirmed 5-way conflict across Sentinel APEX + AI Hub) — needs a business decision, not code.
- Trial Engine — the dead `handleTrialIssuance` bug found in §1, and reconciling it with `revenue-engine`'s already-working trial system.
- The "quantity-based" tier differentiations found during discovery but not formalized as entitlement decisions (brand-scan variant limit: 100 vs 200; NLQ result limit: 25 vs 100; incident list scope: own-only vs all) — these are response-shaping/limits, not access control, and don't fit `enforceTierGate`'s allow/deny model. Left as-is; a future Usage/Limits service (Phase 6-adjacent) is the right place for these, not invented here.
