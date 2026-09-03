#!/usr/bin/env python3
"""
scripts/metric_integrity_contract_gate.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Metric Integrity + Public Nav Contract Gate

WHY THIS EXISTS
----------------
A concurrent session landed p0-revenue-os/config/metric_integrity_contract.json
and p0-revenue-os/config/public_nav.json on main the same day as this
platform's frontend_capability_registry.json (see this script's own commit
for the reconciliation). Both are real, machine-readable contracts --
metric_integrity_contract.json names eight exact marketing-number strings
("forbidden_hardcodes") that must never appear as hardcoded page copy, and
public_nav.json names which nav items an unauthenticated visitor may see
and which must stay hidden until login. Neither contract had an enforcement
mechanism: nothing actually checked the live HTML against them. This script
is that mechanism -- it validates the EXISTING contracts, it does not
invent a new one (this repo's own "do not create another manually
maintained source of truth" rule).

TWO CHECKS
----------
1. forbidden_hardcodes: scans every CUSTOMER_UI page (per
   data/quality/frontend_capability_registry.json -- reused, not
   re-classified) for each literal string in
   metric_integrity_contract.json's forbidden_hardcodes list. A hit means a
   page is showing a hardcoded marketing number instead of a value rendered
   from /api/metrics or metrics/canonical.json, exactly the P0 defect class
   metric_integrity_contract.json exists to name.

2. hide_until_auth nav leakage: scans every CUSTOMER_UI page for an
   unguarded, always-visible link whose text matches one of
   public_nav.json's hide_until_auth labels. js/p0-public-contract.js
   already hides these client-side for unauthenticated visitors on the one
   page that loads it (index.html) -- this check surfaces pages that ship
   the same restricted-looking nav item with no hide mechanism active at
   all (frontend hiding is not authorization; this is a discoverability/
   consistency check, not a security boundary -- the platform's real
   entitlement checks stay server-side, unchanged by this script).

BAKE-IN, NOT YET A HARD GATE -- same rollout pattern already established in
this repo (see scripts/frontend_api_coverage_gate.py's own header for the
precedent and its "why non-blocking at first" rationale, which applies
identically here): this is the FIRST run of this check against the live
site, so its own current findings are unverified page-by-page. Always
exits 0. A future change can promote it to a hard gate once an allowlist
of accepted/false-positive findings exists and has a run history, exactly
how frontend_api_coverage_gate.py's own allowlist graduated.

Writes data/quality/metric_integrity_contract_report.json every run.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
METRIC_CONTRACT_PATH = REPO_ROOT / "p0-revenue-os" / "config" / "metric_integrity_contract.json"
NAV_CONTRACT_PATH = REPO_ROOT / "p0-revenue-os" / "config" / "public_nav.json"
REGISTRY_PATH = REPO_ROOT / "data" / "quality" / "frontend_capability_registry.json"
OUTPUT_PATH = REPO_ROOT / "data" / "quality" / "metric_integrity_contract_report.json"

# Findings accepted as known-fine (not the same page rendering these as a
# live "current value" claim -- see each entry's own reason). Extend this,
# with a reason, the same way frontend_static_page_allowlist.json's own
# entries are individually justified -- never add an entry just to silence
# a finding without checking the actual page content first.
ALLOWLISTED_FINDINGS: dict[str, set[str]] = {
    # (empty: first run -- see module docstring)
}


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _customer_ui_pages() -> list[str]:
    registry = _load_json(REGISTRY_PATH)
    if not registry:
        return []
    return [e["id"] for e in registry.get("entries", []) if e.get("category") == "CUSTOMER_UI"]


def _forbidden_hardcode_pattern(literal: str) -> re.Pattern:
    # A bare substring match on a short numeric string like "508" false-
    # positives inside an unrelated longer number or a CSS hex color (e.g.
    # "#050810" contains "508") -- verified against this exact false
    # positive on services.html while building this script. Requiring a
    # non-digit on both sides of the literal's own leading/trailing digits
    # rules that out while still matching the literal wherever it genuinely
    # appears as its own token in page copy (its own +/%/K suffix already
    # acts as a right boundary for most entries; this adds the symmetric
    # left-side digit guard every entry needs).
    escaped = re.escape(literal)
    return re.compile(r"(?<!\d)" + escaped + r"(?!\d)")


def _scan_forbidden_hardcodes(pages: list[str], forbidden: list[str]) -> list[dict]:
    patterns = {s: _forbidden_hardcode_pattern(s) for s in forbidden}
    findings = []
    for page in pages:
        path = REPO_ROOT / page
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        allowlisted = ALLOWLISTED_FINDINGS.get(page, set())
        hits = [s for s in forbidden if s not in allowlisted and patterns[s].search(text)]
        if hits:
            findings.append({"page": page, "hardcoded_strings": hits})
    return findings


def _scan_nav_leakage(pages: list[str], hide_labels: list[str]) -> list[dict]:
    # Loose, intentionally conservative: a real anchor/button text exactly
    # matching a hide_until_auth label, present in the raw page source with
    # no evidence this page loads the hiding runtime (js/metric-normalize.js
    # or js/p0-public-contract.js directly). A page that loads either script
    # is exempt here even if hidden nav-hiding logic runs after this script's
    # static read -- this check cannot execute JS, only flag pages with no
    # hiding mechanism wired in at all.
    label_res = [re.compile(r">\s*" + re.escape(label) + r"\s*<", re.IGNORECASE) for label in hide_labels]
    findings = []
    for page in pages:
        path = REPO_ROOT / page
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        has_hiding_runtime = "metric-normalize.js" in text or "p0-public-contract.js" in text
        if has_hiding_runtime:
            continue
        hit_labels = [hide_labels[i] for i, r in enumerate(label_res) if r.search(text)]
        if hit_labels:
            findings.append({"page": page, "unguarded_nav_labels": hit_labels})
    return findings


def main() -> int:
    metric_contract = _load_json(METRIC_CONTRACT_PATH)
    nav_contract = _load_json(NAV_CONTRACT_PATH)
    pages = _customer_ui_pages()

    forbidden_findings = []
    nav_findings = []

    if metric_contract:
        # metric_integrity_contract.json's own shape: fields.forbidden_hardcodes
        # is a bare list of strings (unlike its sibling field entries, which are
        # {type, source, example} objects) -- read directly, no reshaping.
        forbidden = metric_contract.get("fields", {}).get("forbidden_hardcodes")
        if isinstance(forbidden, list) and forbidden:
            forbidden_findings = _scan_forbidden_hardcodes(pages, forbidden)

    if nav_contract:
        hide_labels = nav_contract.get("hide_until_auth", [])
        if hide_labels:
            nav_findings = _scan_nav_leakage(pages, hide_labels)

    report = {
        "schema_version": "1",
        "contracts_validated": {
            "metric_integrity_contract": bool(metric_contract),
            "public_nav_contract": bool(nav_contract),
        },
        "pages_scanned": len(pages),
        "forbidden_hardcode_findings": forbidden_findings,
        "nav_leakage_findings": nav_findings,
        "note": (
            "Non-blocking bake-in run (see module docstring) -- findings are a candidate list for "
            "human triage, not an automatic verdict. A page showing a forbidden-hardcode string may "
            "be intentional historical/report content rather than a live claim; verify before treating "
            "as a defect, same standard as this repo's other coverage gates."
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 70)
    print("METRIC INTEGRITY + PUBLIC NAV CONTRACT GATE (bake-in, observability-only)")
    print(f"Contracts loaded: metric_integrity={report['contracts_validated']['metric_integrity_contract']} "
          f"public_nav={report['contracts_validated']['public_nav_contract']}")
    print(f"CUSTOMER_UI pages scanned: {report['pages_scanned']}")
    print(f"Forbidden-hardcode findings: {len(forbidden_findings)} page(s)")
    for f in forbidden_findings[:15]:
        print(f"  [HARDCODE] {f['page']}: {f['hardcoded_strings']}")
    if len(forbidden_findings) > 15:
        print(f"  (+{len(forbidden_findings) - 15} more)")
    print(f"Unguarded restricted-nav-label findings: {len(nav_findings)} page(s)")
    for f in nav_findings[:15]:
        print(f"  [NAV] {f['page']}: {f['unguarded_nav_labels']}")
    if len(nav_findings) > 15:
        print(f"  (+{len(nav_findings) - 15} more)")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print("Non-blocking by design (see this script's own header). Always exits 0.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
