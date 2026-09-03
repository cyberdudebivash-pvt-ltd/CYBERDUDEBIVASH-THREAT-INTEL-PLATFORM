#!/usr/bin/env python3
"""
scripts/capability_live_probe.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Capability Live Probe (Tier 1/2)

WHY THIS EXISTS
----------------
scripts/capability_runtime_auditor.py is 100% static/offline evidence --
its DYNAMIC_VERIFIED verdict means "the code is internally self-consistent"
(genuine fetch()+/api/ evidence, declared API paths resolve to a route
found somewhere in this repo's own source), not "confirmed live in
production." This script is the separate, EXPLICITLY-INVOKED live-HTTP
tier the mission text requires kept apart from ordinary PR CI (network
calls to production are exactly the kind of flakiness risk this repo's own
STAGE 3.6a incident history warns against baking into every PR).

TWO TIERS
---------
  Tier 1 -- every CUSTOMER_UI frontend_route: GET, record HTTP status +
            whether the response looks like real HTML (existence/render
            sanity, not a full headless render -- see the separate,
            smaller Tier 3 headless pass this session ran directly via
            Playwright against capability-directory.html and a
            representative sample, documented in the PR/report rather than
            as a committed script, matching this repo's own precedent of
            not running 130+ heavyweight browser sessions for a mostly-
            mechanical existence check).
  Tier 2 -- every unique api_dependency extracted by capability_runtime_
            auditor.py (deduplicated once per literal path, not once per
            page): GET, record HTTP status. 200/401/403/404/405/429 are
            all "the route exists and answered" in different postures
            (401/403 = exists, auth required; 405 = exists, wrong method --
            several dependencies here, e.g. /api/checkout/session, are
            documented POST-only endpoints, so a live 405 on a GET probe
            CONFIRMS existence rather than refuting it); only a 404 (or a
            connection-level failure) is treated as "does not exist."

READ-ONLY, NON-DESTRUCTIVE (mission Section 35): every request is a plain
GET against production, no state-changing verb, no authentication token
used or required. Modest concurrency + per-request timeout so this cannot
hammer production or hang indefinitely.

Writes data/quality/capability_live_probe_report.json. Requires network
access to PRODUCTION_BASE -- not run in ordinary offline PR CI.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_REPORT_PATH = REPO_ROOT / "data" / "quality" / "capability_runtime_report.json"
OUTPUT_PATH = REPO_ROOT / "data" / "quality" / "capability_live_probe_report.json"
PRODUCTION_BASE = "https://intel.cyberdudebivash.com"
TIMEOUT_S = 10
MAX_WORKERS = 8


def _probe(url: str) -> dict:
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": "SentinelApex-CapabilityLiveProbe/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = resp.read(2048)
            elapsed_ms = round((time.monotonic() - t0) * 1000)
            return {"status": resp.status, "elapsed_ms": elapsed_ms, "error": None,
                     "looks_like_html": body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))}
    except urllib.error.HTTPError as e:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        return {"status": e.code, "elapsed_ms": elapsed_ms, "error": None, "looks_like_html": False}
    except Exception as e:
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        return {"status": None, "elapsed_ms": elapsed_ms, "error": str(e), "looks_like_html": False}


def main() -> int:
    if not RUNTIME_REPORT_PATH.exists():
        print("[FATAL] capability_runtime_report.json missing -- run capability_runtime_auditor.py first.")
        return 1
    runtime = json.loads(RUNTIME_REPORT_PATH.read_text(encoding="utf-8"))
    capabilities = runtime["capabilities"]

    routes = [(c["capability_id"], PRODUCTION_BASE + c["frontend_route"]) for c in capabilities]
    dep_set = sorted({d for c in capabilities for d in c["api_dependencies"]})
    deps = [(d, PRODUCTION_BASE + d) for d in dep_set]

    print(f"Tier 1: probing {len(routes)} CUSTOMER_UI routes against {PRODUCTION_BASE} ...")
    route_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_probe, url): cid for cid, url in routes}
        for fut in as_completed(futures):
            cid = futures[fut]
            route_results[cid] = fut.result()

    print(f"Tier 2: probing {len(deps)} unique API dependencies ...")
    dep_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_probe, url): dep for dep, url in deps}
        for fut in as_completed(futures):
            dep = futures[fut]
            dep_results[dep] = fut.result()

    route_unreachable = {cid: r for cid, r in route_results.items()
                          if r["status"] is None or r["status"] >= 500 or r["status"] == 404}
    dep_confirmed_missing = {dep: r for dep, r in dep_results.items()
                              if r["status"] == 404 or (r["status"] is None)}

    report = {
        "schema_version": "1",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "production_base": PRODUCTION_BASE,
        "routes_probed": len(routes),
        "routes_unreachable": len(route_unreachable),
        "api_dependencies_probed": len(deps),
        "api_dependencies_confirmed_missing": len(dep_confirmed_missing),
        "route_results": route_results,
        "dependency_results": dep_results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"Routes probed: {len(routes)} -- unreachable (404/5xx/error): {len(route_unreachable)}")
    for cid, r in route_unreachable.items():
        print(f"  [UNREACHABLE] {cid}: status={r['status']} error={r['error']}")
    print(f"API dependencies probed: {len(deps)} -- confirmed missing (404/error): {len(dep_confirmed_missing)}")
    for dep, r in dep_confirmed_missing.items():
        print(f"  [MISSING] {dep}: status={r['status']} error={r['error']}")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
