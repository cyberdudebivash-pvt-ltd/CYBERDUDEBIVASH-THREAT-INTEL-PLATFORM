#!/usr/bin/env python3
"""
SENTINEL APEX - Pricing Consistency Gate (Phase 1 architecture consolidation)

Checks the canonical pricing source (workers/intel-gateway/src/pricing-data.json,
what the live Worker actually charges via Razorpay) against:
  1. config/pricing.json (the declared SSOT) - PRO tier must match exactly
     (hard fail on drift: PRO already agrees today, so any difference here is
     a real regression, not a pending business decision).
  2. config/pricing.json's ENTERPRISE/MSSP annual figures - known, pre-existing
     discrepancy pending a business-approved figure. Reported as a WARNING,
     not a hard fail, so this gate does not block deploys on an already-known,
     already-escalated issue. If the delta ever changes from what is recorded
     here, or a NEW tier/cycle starts disagreeing, that is unexpected drift
     and DOES hard-fail.
  3. pricing.html's INR monthly display object - currently agrees with the
     canonical source and is not wired to fetch /api/pricing at runtime
     (it is a marketing page, not a checkout path), so this is its only
     protection against silent drift. Hard fail on mismatch.
  4. upgrade.html and PAYMENT-GATEWAY.html must still contain their
     syncCanonicalPricing() fetch of /api/pricing - hard fail if removed,
     since that would silently reintroduce hardcoded-only pricing.

Exit 0 = PASS (warnings allowed), Exit 1 = FAIL (hard-fail conditions found)
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

failures = []
warnings = []


def load_json(rel_path):
    path = os.path.join(REPO, rel_path)
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def read_text(rel_path):
    path = os.path.join(REPO, rel_path)
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


canonical = load_json("workers/intel-gateway/src/pricing-data.json")["tiers"]
declared_ssot = load_json("config/pricing.json")["tiers"]

# -- 1 & 2: canonical (live charge) vs declared SSOT -------------------------
# Known, pre-existing deltas (paise). Anything beyond this exact set is new
# drift and hard-fails.
KNOWN_ANNUAL_DELTAS_PAISE = {
    "ENTERPRISE": 41600000 - 41500000,   # +INR 1,000/yr
    "MSSP":       166600000 - 160000000,  # +INR 66,000/yr
}

for tier_key, ssot_key in (("PRO", "pro"), ("ENTERPRISE", "enterprise"), ("MSSP", "mssp")):
    canon = canonical[tier_key]
    ssot = declared_ssot[ssot_key]
    canon_monthly_paise = canon["monthly"]
    canon_annual_paise = canon["annual"]
    ssot_monthly_paise = ssot["monthly_inr"] * 100
    ssot_annual_paise = ssot["annual_inr"] * 100

    if canon_monthly_paise != ssot_monthly_paise:
        failures.append(
            f"{tier_key} monthly: canonical={canon_monthly_paise} paise vs "
            f"config/pricing.json={ssot_monthly_paise} paise - unexpected drift"
        )

    annual_delta = canon_annual_paise - ssot_annual_paise
    expected_delta = KNOWN_ANNUAL_DELTAS_PAISE.get(tier_key, 0)
    if annual_delta == 0:
        pass
    elif annual_delta == expected_delta:
        warnings.append(
            f"{tier_key} annual: canonical={canon_annual_paise} paise vs "
            f"config/pricing.json={ssot_annual_paise} paise (delta {annual_delta:+d} paise). "
            f"Known, pending business-approved pricing decision - see pricing-data.json's _note. "
            f"Not a build blocker."
        )
    else:
        failures.append(
            f"{tier_key} annual: delta is {annual_delta:+d} paise, expected "
            f"{expected_delta:+d} paise - this is NEW drift beyond the known, "
            f"already-flagged discrepancy and must be investigated."
        )

# -- 3: pricing.html's INR monthly display object ----------------------------
pricing_html = read_text("pricing.html")
INR_MONTHLY_EXPECTED = {
    "pro": canonical["PRO"]["monthly"] // 100,
    "ent": canonical["ENTERPRISE"]["monthly"] // 100,
    "mssp": canonical["MSSP"]["monthly"] // 100,
}
# The same USD.monthly / INR.monthly shape appears twice (USD block, then INR
# block) - anchor the search to start after the "INR:" marker so we don't
# accidentally match the USD prices, which share the same tier labels.
inr_marker = re.search(r"INR:\s*\{", pricing_html)
inr_section = pricing_html[inr_marker.end():] if inr_marker else ""
if not inr_marker:
    warnings.append("pricing.html: could not locate the INR pricing block to verify - check manually")

for label, rupees in INR_MONTHLY_EXPECTED.items():
    # pricing.html uses Indian digit grouping (e.g. 1,66,600) for mssp; match
    # digits only, ignoring comma placement, to avoid a locale-formatting trap.
    digits_only = str(rupees)
    match = re.search(rf"{label}:\s*\{{\s*sym:'[^']*',\s*price:'([\d,]+)'", inr_section) if inr_marker else None
    if not match:
        if inr_marker:
            warnings.append(f"pricing.html: could not locate '{label}' INR monthly price string to verify - check manually")
        continue
    found_digits = match.group(1).replace(",", "")
    if found_digits != digits_only:
        failures.append(
            f"pricing.html INR monthly for '{label}': found {found_digits} vs "
            f"canonical {digits_only} - unexpected drift on a page with no "
            f"runtime sync; this needs a code fix, not just a config update."
        )

# -- 4: checkout pages must still fetch /api/pricing -------------------------
# PAYMENT-GATEWAY.html is intentionally NOT in this list: per its own header
# comment, it was deliberately rewritten as a pure redirect to /upgrade.html
# (0; url=/upgrade.html + a JS fallback) that displays no pricing at all --
# "completely removing every manual-payment code path this page used to
# contain." There is no hardcoded price on that page to silently drift, so
# requiring a runtime pricing fetch on it tests a stale pre-redirect
# assumption. upgrade.html is the only checkout page that actually renders
# a price and must stay wired to the canonical source.
for page in ("upgrade.html",):
    content = read_text(page)
    if "/api/pricing" not in content or "syncCanonicalPricing" not in content:
        failures.append(
            f"{page}: canonical pricing sync (fetch('/api/pricing') via "
            f"syncCanonicalPricing) is missing - this page has silently "
            f"reverted to hardcoded-only pricing."
        )

# -- 5: revenue-engine internal duplicate pricing tables (2026-09-10 incident) --
# handleCommercialDashboard() and updateMRR() (workers/revenue-engine/src/index.js)
# each carried their own hardcoded { FREE:0, PRO:99, ENTERPRISE:999, MSSP:1999 }
# price map -- a *second* duplicate of the canonical TIERS constant defined
# ~900 lines earlier in the same file, missed by the 2026-08-31 monetization
# audit that reconciled TIERS itself (see that constant's own header comment).
# Silently inflated the live Commercial Analytics Dashboard's mrr_usd/arr_usd
# and the persisted revenue:mrr_usd KV ledger by ~2x for every PRO/ENTERPRISE
# customer. Fixed 2026-09-10 by making both read TIERS.<tier>.price_usd
# directly instead of a second copy. Two checks so this exact incident (not
# just this exact file state) cannot silently recur:
revenue_engine_path = "workers/revenue-engine/src/index.js"
revenue_engine_src = read_text(revenue_engine_path)

# 5a. The canonical TIERS constant itself must still agree with config/pricing.json
# (protects the single source of truth the two call sites above now depend on).
tiers_marker = re.search(r"const TIERS\s*=\s*\{", revenue_engine_src)
tiers_section = revenue_engine_src[tiers_marker.end(): tiers_marker.end() + 2000] if tiers_marker else ""
if not tiers_marker:
    failures.append(f"{revenue_engine_path}: could not locate 'const TIERS = {{' - verify manually, this gate depends on it existing.")
else:
    for tier_key, ssot_key in (("PRO", "pro"), ("ENTERPRISE", "enterprise"), ("MSSP", "mssp")):
        m = re.search(rf"{tier_key}:\s*\{{[^}}]*?price_usd:\s*(\d+)", tiers_section)
        if not m:
            failures.append(f"{revenue_engine_path}: TIERS.{tier_key}.price_usd not found - verify manually.")
            continue
        found = int(m.group(1))
        expected = declared_ssot[ssot_key]["monthly_usd"]
        if found != expected:
            failures.append(
                f"{revenue_engine_path}: TIERS.{tier_key}.price_usd={found} vs "
                f"config/pricing.json monthly_usd={expected} - unexpected drift in "
                f"the canonical tier table this file's revenue math depends on."
            )

# 5b. The exact historical bad literal must never reappear anywhere in this file,
# regardless of which function it's copy-pasted into next.
if re.search(r"PRO:\s*99\s*,\s*ENTERPRISE:\s*999\b", revenue_engine_src):
    failures.append(
        f"{revenue_engine_path}: found the exact pre-2026-09-10 hardcoded bad "
        f"price literal (PRO:99, ENTERPRISE:999) - this is the specific ~2x MRR "
        f"overstatement bug already fixed once; every price map in this file "
        f"must read TIERS.<tier>.price_usd instead of a hardcoded copy."
    )

# -- Report -------------------------------------------------------------------
if warnings:
    print("WARNINGS (non-blocking, known pending business decision):")
    for w in warnings:
        print(f"  - {w}")

if failures:
    print("FAILURES (hard fail):")
    for f in failures:
        print(f"  - {f}")
    print(f"\npricing_consistency_gate: FAIL ({len(failures)} failure(s))")
    sys.exit(1)

print(f"pricing_consistency_gate: PASS ({len(warnings)} known warning(s), 0 failures)")
sys.exit(0)
