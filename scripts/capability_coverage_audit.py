#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/capability_coverage_audit.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Backend Capability <-> Frontend Consumer Coverage Audit

WHY THIS EXISTS
----------------
This platform's UI is 150+ standalone HTML files plus a Next.js dashboard,
and its backend is a Cloudflare Worker gateway with 20+ additive P-layers
(P16-P40+) exposing 200+ /api/v1/pXX/* routes. During the P0 investigation
that produced this script (2026-09-02), four entire P-layers (P34, P36,
P37, P38) were found to be fully built, routed, and live -- with zero HTML
page anywhere in the repository ever calling them -- purely by manual
grep. That is not a sustainable way to keep 200+ routes and 150+ pages in
sync as the platform keeps growing one additive layer at a time.

This script generalizes that manual technique into something that can be
re-run on every PR: it extracts every backend route registered in the
Worker gateway, extracts every API-path reference from every frontend
file (HTML across the whole repo, plus the Next.js dashboard source), and
reports routes with no frontend consumer found -- so a newly-added
backend capability that nobody wired into the UI shows up as a finding
here instead of being discovered by an owner months later staring at an
empty dashboard tile.

WHAT THIS DOES NOT DO
----------------------
- It does NOT decide that every backend-only route is a bug. Many are
  correctly API-only, admin-only, machine-to-machine, or internal-by-design
  (see CLASSIFICATION_OVERRIDES below and each P-layer's own module
  header, e.g. p39-handlers.js's explicit "deliberately NOT routed"
  architecture note). This script's default output is a candidate list
  for a human (or a future PR) to classify, not an automatic verdict.
- It CANNOT see server-side-rendered consumption. Some P-layers (e.g. P28,
  per its buildP28ActionCenterBlock() -- see CLAUDE.md's Core Engine
  Functions table) are designed to be composed directly into another
  page's HTML by index.js at request time, not fetched by client-side JS
  from their own dedicated /api/v1/p28/* routes. This script only detects
  the latter (a URL string literal appearing in a frontend file) -- a
  "fully dark layer" finding for a layer with a documented server-side
  block function is a signal to check whether ITS OWN sub-routes
  (certify/feedback/observability, say) are genuinely unused, not
  evidence the whole layer's output never reaches a customer.
- It does NOT execute anything or make network calls. Purely static
  text/regex analysis of files already in the checkout.
- It is NON-BLOCKING by design (always exits 0) -- see the CI-gate note
  at the bottom of this file for why, and what STAGE 3.6a's
  continue-on-error-less timeout taught this repository about turning a
  new observability check into an accidental hard gate.

USAGE
-----
    python3 scripts/capability_coverage_audit.py
    python3 scripts/capability_coverage_audit.py --json   # machine-readable only

Writes data/quality/capability_coverage_report.json on every run.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent
GATEWAY_SRC = REPO_ROOT / "workers" / "intel-gateway" / "src"
OUTPUT_PATH = REPO_ROOT / "data" / "quality" / "capability_coverage_report.json"

ROUTE_RE = re.compile(r'path\s*===\s*["\'](/api/v1/p\d+/[a-zA-Z0-9_-]+)["\']')
# Any string literal that looks like one of this platform's own API paths,
# wherever it appears (fetch(), template literals, hrefs, etc.) -- kept
# deliberately loose (no requirement that it's inside a fetch() call)
# because this codebase's dashboards build request URLs several different
# ways (API + path, template literals, a shared fetchJSON() helper).
CONSUMER_REF_RE = re.compile(r'/api/v1/p\d+/[a-zA-Z0-9_-]+')

# Directories whose *.html/*.js content should never count as a
# "frontend consumer" of a route -- these are backend source, generated
# report archives, or vendored/build output, not customer-facing UI.
EXCLUDED_DIR_PARTS = {
    "workers", "node_modules", "reports", ".git", "dist",
    "__tests__", "__pycache__",
}

# Layers/routes documented as intentionally not requiring a public UI
# consumer. Keyed by exact route path. Extend this as new intentionally
# API-only/internal/admin routes are added -- do NOT add an entry here
# just to silence a finding; add it because the route's own module header
# documents the intent (see p39-handlers.js for the canonical example of
# how to document that decision).
CLASSIFICATION_OVERRIDES: dict[str, str] = {
    # P39 is explicitly documented (p39-handlers.js header) as internal-only,
    # never routed to HTTP at all -- it will never appear in ROUTE_RE's
    # extraction in the first place, listed here only for self-documentation.

    # -- sentinel-apex-transformation-8x3y26 session (2026-09-03) --
    # Every route below was evaluated against its actual handler source
    # (workers/intel-gateway/src/pXX-handlers.js) before classifying, not
    # name-guessed. See data/quality/frontend_capability_registry.json for
    # the companion frontend-page classification and the session's final
    # report for the full evidence trail.

    # API_ONLY: single-item / id-required drill-down endpoints. Each needs a
    # specific item, entity, or source id the caller must already have (from
    # an already-wired list/search/graph endpoint) -- not aggregate data a
    # passive dashboard tile can show, so not wired into a new UI card this
    # session. Legitimate self-serve API capabilities, not orphans.
    "/api/v1/p22/validate": "API_ONLY",       # handleP22Validate: requires ?id= (or defaults to items[0])
    "/api/v1/p28/certify": "API_ONLY",        # handleP28Certify: GET ?id= or POST a single item body
    "/api/v1/p29/certify": "API_ONLY",        # handleP29Certify: requires ?id=
    "/api/v1/p31/entity": "API_ONLY",         # handleP31Entity: requires ?id=, tier-gated (paid only)
    "/api/v1/p31/relationships": "API_ONLY",  # handleP31Relationships: requires ?entity=, tier-gated
    "/api/v1/p40/source-detail": "API_ONLY",  # handleP40SourceDetail: requires ?id=, 400s without one

    # API_ONLY: navigation alias, not a data endpoint.
    "/api/v1/p21/dashboard": "API_ONLY",  # handleP21Dashboard is a bare 302 redirect to /threat-intel-certification-dashboard.html

    # CUSTOMER_UI (server-composed): reaches customers via HTML composed
    # server-side into another page (index.js:buildP28FeedbackBlock), not a
    # client-side fetch() from a dedicated page -- exactly the blind spot
    # this script's own docstring warns CONSUMER_REF_RE can't see. Verified
    # by reading buildP28FeedbackBlock's own output: it embeds a real
    # fetch(apiBase + "/api/v1/p28/feedback", {method:"POST",...}) call.
    "/api/v1/p28/feedback": "CUSTOMER_UI",

    # CUSTOMER_UI (served transitively): the route's own data is a strict
    # subset of, or is already computed by, an aggregate endpoint already
    # wired and rendered on this route's own dashboard -- adding a second
    # UI card would just redisplay the same numbers under a new tab, not
    # surface anything new to a customer. Verified by diffing each pair of
    # handler return shapes, not assumed from route naming.
    "/api/v1/p23/observability": "CUSTOMER_UI",  # subset of /p23/actionability's per-item data, already aggregated client-side on enterprise-action-dashboard.html
    "/api/v1/p34/status": "CUSTOMER_UI",         # subset of /p34/dashboard (platform_status/release_tier) + /p34/assurance (gate counts), both wired on enterprise-assurance-center.html
    "/api/v1/p35/metrics": "CUSTOMER_UI",        # identical kpis object to /p35/dashboard's own `kpis` field (same _computeKPIs() call, same args) -- wired there
    "/api/v1/p36/metrics": "CUSTOMER_UI",        # overlaps /p36/dashboard's scorecard/quality_targets/reliability; its two non-overlapping fields (avg_p20_quality/avg_p25_trust) are below the bar for a dedicated card
    "/api/v1/p36/quality": "CUSTOMER_UI",        # field_coverage + quality_targets is the same _evaluateTargets(coverage) output already rendered on the wired /p36/targets tab
    "/api/v1/p37/hardening": "CUSTOMER_UI",      # summary rollup of /p37/dashboard + /p37/debt + /p37/enrichment, all three already wired
    "/api/v1/p37/metrics": "CUSTOMER_UI",        # overlaps /p37/dashboard's iq_score/enrichment/confidence/reliability/cert_chain fields
}


def find_frontend_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ("*.html", "*.js"):
        for p in REPO_ROOT.rglob(pattern):
            rel_parts = set(p.relative_to(REPO_ROOT).parts)
            if rel_parts & EXCLUDED_DIR_PARTS:
                continue
            files.append(p)
    return files


def extract_backend_routes() -> dict[str, str]:
    """Return {route_path: source_file_relative_path}."""
    routes: dict[str, str] = {}
    if not GATEWAY_SRC.exists():
        return routes
    for js_file in GATEWAY_SRC.glob("*.js"):
        try:
            text = js_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in ROUTE_RE.finditer(text):
            routes.setdefault(m.group(1), str(js_file.relative_to(REPO_ROOT)))
    return routes


def extract_frontend_references(files: list[Path]) -> dict[str, set[str]]:
    """Return {route_path: {consumer_file_relative_paths}}."""
    refs: dict[str, set[str]] = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in CONSUMER_REF_RE.finditer(text):
            refs.setdefault(m.group(0), set()).add(str(f.relative_to(REPO_ROOT)))
    return refs


def layer_of(route: str) -> str:
    m = re.match(r"/api/v1/(p\d+)/", route)
    return m.group(1) if m else "unknown"


def main() -> int:
    json_only = "--json" in sys.argv

    backend_routes = extract_backend_routes()
    frontend_files = find_frontend_files()
    frontend_refs  = extract_frontend_references(frontend_files)

    wired: list[dict] = []
    backend_only: list[dict] = []

    for route, source_file in sorted(backend_routes.items()):
        consumers = sorted(frontend_refs.get(route, set()))
        entry = {
            "route": route,
            "layer": layer_of(route),
            "handler_file": source_file,
            "consumers": consumers,
        }
        if route in CLASSIFICATION_OVERRIDES:
            entry["classification"] = CLASSIFICATION_OVERRIDES[route]
            wired.append(entry)
        elif consumers:
            entry["classification"] = "DASHBOARD_CONSUMED"
            wired.append(entry)
        else:
            entry["classification"] = "BACKEND_ONLY_NO_UI_FOUND"
            backend_only.append(entry)

    # Group backend-only findings by layer for a compact summary --
    # a layer with 0 consumed routes and >0 routes is the strongest signal
    # (an entire layer with no linked dashboard, exactly the P34-P38 case
    # this script exists because of), vs. a layer with most routes wired
    # and one or two legitimately-internal stragglers.
    by_layer: dict[str, dict] = {}
    for route, source_file in backend_routes.items():
        layer = layer_of(route)
        by_layer.setdefault(layer, {"total": 0, "wired": 0})
        by_layer[layer]["total"] += 1
        if route in frontend_refs or route in CLASSIFICATION_OVERRIDES:
            by_layer[layer]["wired"] += 1

    fully_dark_layers = sorted(
        layer for layer, stats in by_layer.items()
        if stats["wired"] == 0 and stats["total"] > 0
    )

    report = {
        "schema_version": "1.0",
        "generator": "scripts/capability_coverage_audit.py",
        "total_routes_found": len(backend_routes),
        "total_frontend_files_scanned": len(frontend_files),
        "wired_count": len(wired),
        "backend_only_count": len(backend_only),
        "layers": by_layer,
        "fully_dark_layers": fully_dark_layers,
        "backend_only_routes": backend_only,
        "note": (
            "backend_only_routes is a candidate list for human triage, not an "
            "automatic defect list -- classify each as DASHBOARD_CONSUMED, "
            "API_PRODUCT, INTERNAL, ADMIN, MACHINE_TO_MACHINE, or DEPRECATED "
            "and add a durable entry to CLASSIFICATION_OVERRIDES in this "
            "script once a route's non-UI status is a deliberate, documented "
            "decision (not just 'nobody has built it yet')."
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if json_only:
        print(json.dumps(report, indent=2))
        return 0

    print("=" * 70)
    print("CAPABILITY COVERAGE AUDIT -- backend routes vs. frontend consumers")
    print("=" * 70)
    print(f"Backend routes found:     {report['total_routes_found']}")
    print(f"Frontend files scanned:   {report['total_frontend_files_scanned']}")
    print(f"Wired (consumer found):   {report['wired_count']}")
    print(f"Backend-only (no consumer found): {report['backend_only_count']}")
    if fully_dark_layers:
        print(f"\nFully dark layers (every route unwired): {', '.join(fully_dark_layers)}")
    if backend_only:
        print("\nBackend-only routes (candidates for triage):")
        for entry in backend_only:
            print(f"  [{entry['layer']}] {entry['route']}  <- {entry['handler_file']}")
    print(f"\nFull report: {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print("\nNon-blocking by design (see this script's own header). Always exits 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
