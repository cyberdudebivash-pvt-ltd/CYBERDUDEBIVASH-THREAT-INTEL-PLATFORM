#!/usr/bin/env python3
"""
scripts/capability_runtime_reconcile.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Capability Runtime Certification (final)

Merges capability_runtime_auditor.py's static verdict (data/quality/
capability_runtime_report.json) with capability_live_probe.py's live-HTTP
evidence (data/quality/capability_live_probe_report.json) into the single
authoritative per-capability disposition -- mission Section 44's
"PRODUCTION CERTIFICATION MODEL": CAPABILITY REGISTERED -> ROUTE VERIFIED
-> RUNTIME CLASSIFIED -> ... -> PRODUCTION VERIFIED.

Deliberately a THIRD, separate script rather than merging this logic into
either input script: capability_runtime_auditor.py must stay 100% offline
(safe for every PR); capability_live_probe.py must stay a thin, dumb HTTP
prober with no verdict logic (so its own output is trustworthy raw
evidence, not pre-interpreted). This script is the one place static and
live evidence combine, and only correction it currently applies is
evidence-based and narrow: a route static analysis called STATIC_VALID/
DYNAMIC_VERIFIED/DEGRADED that the live probe found genuinely unreachable
(404, 5xx, or a connection error) becomes ORPHANED -- "registered but
unreachable" is precisely that verdict's mission-given definition,
regardless of whether the underlying file exists in the git working tree
(verified live this session: multiple ALL-CAPS-named files exist in git
and pass the static ROUTE_EXISTS check, yet 404 in production -- a real,
systemic finding static analysis alone could never surface. See this
session's PR/report for the root-cause hypothesis).

Requires both input reports to already exist (run capability_runtime_
auditor.py then capability_live_probe.py first). Writes data/quality/
capability_runtime_certification.json.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_REPORT_PATH = REPO_ROOT / "data" / "quality" / "capability_runtime_report.json"
LIVE_PROBE_PATH = REPO_ROOT / "data" / "quality" / "capability_live_probe_report.json"
OUTPUT_PATH = REPO_ROOT / "data" / "quality" / "capability_runtime_certification.json"

VALID_VERDICTS = (
    "DYNAMIC_VERIFIED", "STATIC_VALID", "AUTH_GATED", "DEGRADED",
    "BROKEN", "ORPHANED", "MISCLASSIFIED",
)


def main() -> int:
    if not RUNTIME_REPORT_PATH.exists():
        print("[FATAL] capability_runtime_report.json missing -- run capability_runtime_auditor.py first.")
        return 1
    if not LIVE_PROBE_PATH.exists():
        print("[FATAL] capability_live_probe_report.json missing -- run capability_live_probe.py first.")
        return 1

    runtime = json.loads(RUNTIME_REPORT_PATH.read_text(encoding="utf-8"))
    live = json.loads(LIVE_PROBE_PATH.read_text(encoding="utf-8"))

    entries = []
    corrections = []
    for c in runtime["capabilities"]:
        cid = c["capability_id"]
        static_verdict = c["verdict"]
        final_verdict = static_verdict
        live_route = live["route_results"].get(cid, {})
        live_status = live_route.get("status")
        route_unreachable_live = live_status is None or live_status == 404 or (live_status or 0) >= 500

        if route_unreachable_live and static_verdict in ("STATIC_VALID", "DYNAMIC_VERIFIED", "DEGRADED"):
            final_verdict = "ORPHANED"
            corrections.append({
                "capability_id": cid,
                "static_verdict": static_verdict,
                "live_corrected_verdict": final_verdict,
                "live_route_status": live_status,
                "reason": "Static analysis found the file on disk; live HTTP probe confirms it is unreachable in production.",
            })

        missing_deps_live = [
            d for d in c["api_dependencies"]
            if (live["dependency_results"].get(d, {}).get("status") in (404, None))
        ]

        entries.append({
            "capability_id": cid,
            "frontend_route": c["frontend_route"],
            "static_verdict": static_verdict,
            "final_verdict": final_verdict,
            "verdict_reason": c["verdict_reason"],
            "live_route_status": live_status,
            "api_dependencies": c["api_dependencies"],
            "api_dependencies_confirmed_missing_live": missing_deps_live,
        })

    counts = Counter(e["final_verdict"] for e in entries)
    for v in VALID_VERDICTS:
        counts.setdefault(v, 0)

    report = {
        "schema_version": "1",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "total_customer_ui": len(entries),
        "verdict_counts": dict(counts),
        "live_corrections_applied": len(corrections),
        "corrections": corrections,
        "capabilities": entries,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 70)
    print("CAPABILITY RUNTIME CERTIFICATION (static + live, reconciled)")
    print(f"Total CUSTOMER_UI: {len(entries)}")
    for v in VALID_VERDICTS:
        print(f"  {v:18s} {counts[v]}")
    print(f"Live corrections applied: {len(corrections)}")
    for corr in corrections:
        print(f"  - {corr['capability_id']}: {corr['static_verdict']} -> {corr['live_corrected_verdict']} (live status={corr['live_route_status']})")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
