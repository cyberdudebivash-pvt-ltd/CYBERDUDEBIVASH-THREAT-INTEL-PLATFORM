#!/usr/bin/env python3
"""
scripts/capability_runtime_gate.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Capability Runtime CI Gate

WHY THIS EXISTS
----------------
scripts/capability_runtime_auditor.py computes a runtime disposition for
every CUSTOMER_UI capability but never fails a build on its own (documented
in its own header: "Always exits 0"). This is the (separately, narrowly)
blocking layer, following the EXACT two-script split this repo's own
scripts/capability_registry_gate.py already established over scripts/
build_capability_registry.py (mission Section 28/29's own required "CI --
CUSTOMER_UI Runtime Contract" and "CI -- Orphan Prevention" gates).

ONE GATE, BLOCKING (Section 28: "A new CUSTOMER_UI capability must not
enter production with no implementation decision"):

  GATE 1 -- Every CUSTOMER_UI capability has an explicit runtime
    disposition (one of the 7 mission-defined verdicts). Trivially true
    today -- capability_runtime_auditor.py's decision tree always resolves
    to a valid verdict for every entry -- but this gate exists so that
    guarantee is permanently, mechanically enforced rather than merely
    true by construction today. Safe to hard-block: it can only fail if a
    future change to the auditor or the registry schema introduces an
    unclassifiable entry, which is exactly the kind of silent gap this
    gate exists to catch immediately rather than let ship.

NOT YET A SECOND, REGRESSION-DETECTING BLOCKING GATE (deliberate, and
different from capability_registry_gate.py's own Gate 2 in one important
way worth being explicit about): a real "did a previously-working
capability regress" check needs a genuine PR-base-vs-head comparison
(`git show <base-sha>:data/quality/capability_runtime_certification.json`
vs the current run), not just "does this run's own live-vs-static
reconciliation disagree anywhere" -- the latter would re-fire identically
on the SAME 2 pre-existing findings this session already discovered and
documented (ENTERPRISE-CUSTOMER-RESPONSE-SYSTEM.html, SENTINEL-APEX-
PRODUCTION-BACKLOG.html -- both unreachable in production for reasons
unrelated to and predating this session's work) on every single future PR
forever, which is not a regression gate, it is a permanently-tripped
alarm. Implementing the real base-vs-head comparison correctly (handling
the "no prior commit has this file yet" first-run case, detached-HEAD CI
checkouts, etc.) is real work this session chose not to rush just to claim
a second blocking gate -- see this session's PR/report "Next P0
Recommendation." The reconciled findings (BROKEN/ORPHANED counts and the
full per-page evidence) ARE fully computed and written every run
(data/quality/capability_runtime_certification.json) -- observability
first, same rollout pattern frontend_api_coverage_gate.py and
metric_integrity_contract_gate.py's own docstrings already establish and
explicitly justify, applied honestly here rather than faked with a gate
that would either always pass (if scoped to do nothing) or always fail
(if scoped to this run's own findings alone).

Exits 1 only on GATE 1 failure. Requires data/quality/capability_runtime_
certification.json (run capability_runtime_auditor.py, then capability_
live_probe.py, then capability_runtime_reconcile.py first).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CERTIFICATION_PATH = REPO_ROOT / "data" / "quality" / "capability_runtime_certification.json"

VALID_VERDICTS = frozenset({
    "DYNAMIC_VERIFIED", "STATIC_VALID", "AUTH_GATED", "DEGRADED",
    "BROKEN", "ORPHANED", "MISCLASSIFIED",
})


def main() -> int:
    if not CERTIFICATION_PATH.exists():
        print(f"[FATAL] {CERTIFICATION_PATH.relative_to(REPO_ROOT)} does not exist. "
              f"Run scripts/capability_runtime_auditor.py, scripts/capability_live_probe.py, "
              f"then scripts/capability_runtime_reconcile.py first.")
        return 1
    try:
        cert = json.loads(CERTIFICATION_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[FATAL] {CERTIFICATION_PATH.relative_to(REPO_ROOT)} is not valid JSON ({e}).")
        return 1

    capabilities = cert.get("capabilities", [])

    # -- GATE 1: every capability has a valid disposition ---------------------
    unclassified = [c["capability_id"] for c in capabilities if c.get("final_verdict") not in VALID_VERDICTS]

    verdict_counts = cert.get("verdict_counts", {})
    broken_count = verdict_counts.get("BROKEN", 0)
    orphaned_count = verdict_counts.get("ORPHANED", 0)
    corrections = cert.get("corrections", [])

    print("=" * 70)
    print("CAPABILITY RUNTIME GATE -- disposition completeness (blocking) + findings (observability)")
    print("=" * 70)
    print(f"Total CUSTOMER_UI: {cert.get('total_customer_ui', len(capabilities))}")
    print(f"Verdict counts: {verdict_counts}")
    print(f"GATE 1 (every capability classified): {'PASS' if not unclassified else 'FAIL'}")
    print(f"[OBSERVABILITY ONLY, non-blocking -- see module docstring for why] "
          f"BROKEN: {broken_count}  ORPHANED: {orphaned_count}  "
          f"live/static disagreements this run: {len(corrections)}")
    for corr in corrections[:10]:
        print(f"  [LIVE-UNREACHABLE] {corr['capability_id']}: static={corr['static_verdict']} "
              f"live_status={corr['live_route_status']}")

    if unclassified:
        print()
        print("BLOCKING FAILURE:")
        print(f"  - GATE 1 FAIL: {len(unclassified)} CUSTOMER_UI capability(ies) with no valid runtime "
              f"disposition: {unclassified}")
        print("=" * 70)
        return 1

    print("PASS -- every CUSTOMER_UI capability has an explicit runtime disposition.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
