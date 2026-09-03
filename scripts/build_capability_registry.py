#!/usr/bin/env python3
"""Generates data/quality/frontend_capability_registry.json.

Build script for data/quality/frontend_capability_registry.json, the
canonical frontend capability registry (CLAUDE.md Section 3 / mission item 3
of the sentinel-apex-transformation-8x3y26 session).

Not a CI-invoked script -- scripts/capability_registry_gate.py (added
alongside this file) is what CI runs against the JSON this writes; this
generator is kept in the repo so a future classification pass can
regenerate the mechanical baseline (dynamic vs. allowlisted-static, pulled
fresh from frontend_api_coverage_report.json) instead of hand-editing JSON,
then extend the CLASSIFICATIONS dict below for any newly-added page before
re-running.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COVERAGE_REPORT = REPO_ROOT / "data/quality/frontend_api_coverage_report.json"
OUTPUT = REPO_ROOT / "data/quality/frontend_capability_registry.json"

# Evidence-based classification for the 47 pages the mechanical dynamic/static
# heuristic cannot resolve on its own (data/quality/frontend_static_page_allowlist.json
# only covers the zero-<form>/zero-fetch( subset). Derived from a full-file read
# of every page below during the sentinel-apex-transformation-8x3y26 session
# (2026-09-03), independently spot-verified (see session notes / final report),
# not name-guessed.
#
# category: CUSTOMER_UI | API_ONLY | ADMIN | INTERNAL | DEPRECATED
# status (CUSTOMER_UI only): live | orphan | form_only | static_content | interactive_docs
CLASSIFICATIONS = {
    # -- Fixed this session --
    "sentinel-onboarding.html": ("CUSTOMER_UI", "form_only",
        "Fixed this session: removed fabricated org/tenant/API-key credentials and the false "
        "'account activated' / 'credentials emailed' claims from step 5. Now honestly states "
        "activation is manual. No route wires a real self-serve paid-tier provisioning flow yet "
        "(payment step is decorative -- simulatePaypal() just opens paypal.com); building one is "
        "explicitly out of scope here (CLAUDE.md: payment/billing logic is frozen)."),
    "support-center.html": ("CUSTOMER_UI", "orphan",
        "Fixed this session: a real JS syntax error (unescaped raw HTML in a return statement, "
        "not wrapped in a template literal) was breaking the entire inline <script>, so nothing on "
        "the page worked. Syntax now valid. Still shows a hardcoded ticket list -- no live route "
        "for a per-tenant support-ticket API exists yet; tracked as a residual orphan."),
    # -- Genuine CUSTOMER_UI orphans: real customer surfaces showing hardcoded/placeholder data,
    #    not yet wired this session. best-fit route(s) noted for the next pass. --
    "ai-runtime-defense.html": ("CUSTOMER_UI", "orphan", "Hardcoded/animated stat counters, zero fetch. No dedicated backend route found; partial fit /api/v1/ai-ops/analytics."),
    "ai-security-ops-hub.html": ("CUSTOMER_UI", "orphan", "Hardcoded inference/prompt-firewall counters, zero fetch. Partial fit /api/v1/ai-ops/analytics."),
    "api-management-center.html": ("CUSTOMER_UI", "orphan", "Hardcoded API usage/success-rate stats, zero fetch. No key/webhook CRUD route exists (see api-key-manager.html for the one page with a real fetch() pattern)."),
    "api-reference-card.html": ("CUSTOMER_UI", "orphan", "Hardcoded 'live' advisory badge with pulsing indicator, no fetch. Best fit: /api/health."),
    "billing-center.html": ("CUSTOMER_UI", "orphan", "Hardcoded usage-meter numbers, zero fetch. Partial fit /api/payment/status."),
    "customer-dashboard.html": ("CUSTOMER_UI", "orphan", "Single-tenant demo dashboard, fully hardcoded. Fits /api/v1/intel/apt, /api/v1/intel/feed, /api/health."),
    "customer-portal.html": ("CUSTOMER_UI", "orphan", "Hardcoded threat/IOC counts and a fake masked API key. Fits /api/v1/intel/feed, /api/v1/detections, /api/health."),
    "daily-operations-center.html": ("CUSTOMER_UI", "orphan", "Multi-tab ops tool, hardcoded across every tab. Fits /api/v1/intel/latest.json, /api/v1/incidents, /api/v1/detections, /api/sla/incidents."),
    "dashboard.html": ("CUSTOMER_UI", "orphan",
        "Investigated this session, deliberately NOT fixed: its fetch() calls target /auth/login "
        "and /auth/keys (missing /api/ prefix AND /api/auth/keys does not exist as a route at all -- "
        "only /api/admin/keys [admin-scoped] and /api/keys/free [free-tier signup] exist). This is an "
        "auth-model mismatch, not a URL typo -- see login.html note. Also references stale element IDs "
        "('login-screen'/'dashboard-screen') that don't match its own DOM ('auth-gate'/'dashboard'). "
        "Needs an auth-model decision before any fix, not a frontend-only patch."),
    "dependency-platform.html": ("CUSTOMER_UI", "orphan", "Hardcoded 'sticky score' and API-call stats. No obvious existing backend route."),
    "evidence-threat-map.html": ("CUSTOMER_UI", "orphan", "Hardcoded map stats with fake Math.random()-driven 'live counters'. Fits /api/v1/intel/graph, /api/v1/geo/cybermap, /api/v1/intel/relations."),
    "executive-reporting-center.html": ("CUSTOMER_UI", "orphan", "Hardcoded board-report figures ('$9.7M Annualized ROI'). Fits /api/v1/executive/command-center, /api/v1/reports/."),
    "malware-intel-hub.html": ("CUSTOMER_UI", "orphan", "Hardcoded sample counters, fake sandbox hash stream via Math.random(). Partial fit /api/yara, /api/sigma."),
    "mssp-console.html": ("CUSTOMER_UI", "orphan", "1785-line MSSP console, fully hardcoded, zero fetch. Fits /api/mssp, /api/mssp/feed, /api/mssp/tenants/{id}/feed."),
    "mssp-customer-center.html": ("CUSTOMER_UI", "orphan", "Hardcoded partner/customer arrays. Fits /api/mssp, /api/mssp/feed."),
    "mssp-partner-portal.html": ("CUSTOMER_UI", "orphan", "Hardcoded tenant list. Fits /api/mssp/tenants/{id}/feed, /api/mssp/feed."),
    "my-exposure-center.html": ("CUSTOMER_UI", "orphan", "Hardcoded CVEs/campaigns/recommendations presented as personalized. Fits /api/v1/cve/live, /api/v1/intel/campaigns, /api/v1/assets/intelligence."),
    "payment-confirmation.html": ("CUSTOMER_UI", "orphan", "Activation timeline derived only from URL query params, never calls the real payment-status API. Fits /api/payment/status."),
    "soc-operations-center.html": ("CUSTOMER_UI", "orphan", "Hardcoded INTEL_ITEMS array despite an in-code comment claiming 'No fake data -- Real manifest-driven'. Fits /api/v1/incidents, /api/v1/intel/graph, /api/v1/geo/cybermap."),
    "soc-workspace.html": ("CUSTOMER_UI", "orphan", "Hardcoded incidents/hunts/timeline; updateStats() fakes live numbers via Math.random(). Fits /api/v1/incidents, /api/v1/detections."),
    "subscription-billing-center.html": ("CUSTOMER_UI", "orphan", "Hardcoded MRR/usage figures; every action button alert()s a nonexistent route. Partial fit /api/payment/status."),
    "telemetry-embedding.html": ("CUSTOMER_UI", "orphan", "Hardcoded/rotated telemetry counters via setInterval + Math.random(). No obvious existing route."),
    "telemetry-visibility-ops.html": ("CUSTOMER_UI", "orphan", "Hardcoded event-rate counters and tickets. Fits /api/v1/detections, /api/v1/incidents, /api/v1/intel/graph."),
    "unified-ops-hub.html": ("CUSTOMER_UI", "orphan", "Hardcoded alert/IOC/score tiles across all tabs. Fits /api/v1/incidents, /api/v1/intel/graph, /api/v1/detections."),
    "value-center.html": ("CUSTOMER_UI", "orphan", "Hardcoded ROI/threat figures with a fake 'LIVE' badge; period selector re-displays the same static numbers. Fits /api/v1/incidents, /api/v1/detections, /api/v1/stats."),
    "login.html": ("CUSTOMER_UI", "orphan",
        "Investigated this session, deliberately NOT fixed: fetch() calls are missing the /api/ "
        "prefix (/auth/login, /auth/signup), but the deeper issue is an auth-MODEL mismatch, not a "
        "URL typo -- POST /api/auth/login expects {api_key}, not {email,password} (this platform has "
        "no password-based account system), and POST /api/auth/register unconditionally returns 422 "
        "'Email registration is not available.' A shallow /api/ prefix fix would still be broken and "
        "would look fixed when it isn't; CLAUDE.md freezes auth-logic changes outright. Needs a product "
        "decision (build real email/password auth, or redesign this page around API-key issuance via "
        "the already-working /api/keys/free flow that get-api-key.html correctly uses) before any code "
        "changes here."),
    # -- ADMIN: internal ops tools, not customer-facing --
    "admin.html": ("ADMIN", None, "Password-gated internal admin control panel."),
    "conversion-analytics.html": ("ADMIN", None, "CDB-internal sales-funnel analytics."),
    "customer-health-platform.html": ("ADMIN", None, "CDB-internal customer health/churn scoring tool."),
    "customer-intelligence.html": ("ADMIN", None, "CDB-internal customer health-scoring engine."),
    "customer-ops-center.html": ("ADMIN", None, "CDB-internal 'Global Ops' command center."),
    "customer-success-center.html": ("ADMIN", None, "CDB-internal CS team tool."),
    "demo-conversion-center.html": ("ADMIN", None, "CDB-internal demo-to-customer sales pipeline tracker."),
    "lead-intelligence.html": ("ADMIN", None, "CDB-internal lead-scoring engine."),
    "monetization-ops.html": ("ADMIN", None, "CDB-internal revenue/monetization ops dashboard."),
    "revenue-intelligence.html": ("ADMIN", None, "CDB-internal revenue-ops engine; own code comment says data is 'seeded...in production fetched from revenue registry API'."),
    "sentinel-master-ops-center.html": ("ADMIN", None, "CDB-internal master operations command center."),
    # -- CUSTOMER_UI form-only: real customer surface, only function is a form/CTA --
    "contact-enterprise.html": ("CUSTOMER_UI", "form_only", "Enterprise sales contact form."),
    "demo.html": ("CUSTOMER_UI", "form_only", "'Book a Demo' page; explicitly self-labeled sandbox/demo mode."),
    "enterprise-demo.html": ("CUSTOMER_UI", "form_only", "Enterprise-tier 'Book a Demo' page."),
    "executive-briefing.html": ("CUSTOMER_UI", "form_only", "CISO/board briefing-pack marketing page; ROI cites a real external IBM breach-cost report."),
    "lead-capture.html": ("CUSTOMER_UI", "form_only", "Paywall-unlock lead-gen form."),
    "partner.html": ("CUSTOMER_UI", "form_only", "Partner/reseller program marketing page."),
    # -- INTERNAL: one-off report artifact, not a live product surface --
    "GODMODE-REVENUE-AUDIT-REPORT.html": ("INTERNAL", None, "One-off internal audit report artifact (added to the static allowlist -- zero real form/fetch; its 'fetch(' matches are prose describing suggested code, not executable JS)."),
    # -- CUSTOMER_UI, correctly excluded from the strict static allowlist --
    "api-docs.html": ("CUSTOMER_UI", "interactive_docs", "Has real interactive 'try it' fetch() calls (an embedded API console), not a placeholder-data page -- intentionally not in the zero-fetch static allowlist."),
    "intelligence-archive.html": ("CUSTOMER_UI", "live_non_gateway", "Genuinely fetches live JSON from /data/intelligence_repository/*.json -- a real data source outside the /api/ gateway, so the coverage gate's /api/-only regex permanently misses it (by design, not a bug in that gate -- see its own docstring's scope note). Deliberately NOT status='live': that status feeds capability_registry_gate.py's placeholder-regression check against frontend_api_coverage_report.json's dynamic_pages list, which this page can never appear in. Not a defect; not added to the static allowlist because it IS dynamic."),
}

STATUS_NOTE = {
    "orphan": "Static/placeholder data on a real customer surface -- tracked defect, needs live API wiring.",
    "form_only": "Customer-facing; its only function is a form/CTA, no live-data surface required.",
    "static_content": "Legitimately static marketing/legal/informational content.",
    "interactive_docs": "Static reference content with a live interactive example widget.",
    "live": "Wired to a live backend API.",
    "live_non_gateway": "Wired to genuinely live data from a source outside the /api/ gateway (e.g. static archived JSON); excluded from status='live' so it is never checked against the /api/-only coverage heuristic.",
}


def main():
    if not COVERAGE_REPORT.exists():
        raise SystemExit(
            f"[FATAL] {COVERAGE_REPORT.relative_to(REPO_ROOT)} does not exist. "
            f"Run scripts/frontend_api_coverage_gate.py first (STAGE 3.92b runs "
            f"before this step in sentinel-blogger.yml)."
        )
    try:
        report = json.loads(COVERAGE_REPORT.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"[FATAL] {COVERAGE_REPORT.relative_to(REPO_ROOT)} is not valid JSON ({e}). "
            f"Re-run scripts/frontend_api_coverage_gate.py to regenerate it."
        )
    entries = []

    for p in report["dynamic_pages"]:
        entries.append({
            "id": p["file"], "frontend_route": "/" + p["file"],
            "category": "CUSTOMER_UI", "status": "live",
            "notes": STATUS_NOTE["live"] + " (" + p["reason"] + ")",
        })

    for p in report["static_pages"]:
        fname = p["file"]
        if fname in CLASSIFICATIONS:
            category, status, notes = CLASSIFICATIONS[fname]
            entry = {"id": fname, "frontend_route": "/" + fname, "category": category, "notes": notes}
            if status:
                entry["status"] = status
            entries.append(entry)
        elif p.get("allowlisted"):
            entries.append({
                "id": fname, "frontend_route": "/" + fname,
                "category": "CUSTOMER_UI", "status": "static_content",
                "notes": STATUS_NOTE["static_content"],
            })
        else:
            raise SystemExit(f"UNCLASSIFIED page with no registry entry: {fname} -- add it to CLASSIFICATIONS before regenerating")

    entries.sort(key=lambda e: e["id"])

    by_category = {}
    for e in entries:
        by_category[e["category"]] = by_category.get(e["category"], 0) + 1
    orphan_count = sum(1 for e in entries if e.get("status") == "orphan")

    registry = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/build_capability_registry.py (one-time build; hand-maintained CLASSIFICATIONS dict thereafter)",
        "scope": "top-level *.html (repo root) -- see CLAUDE.md's P-layer table and scripts/capability_coverage_audit.py for the /api/v1/pXX/* backend route -> handler registry (a distinct, complementary artifact; this file classifies FRONTEND pages, not backend routes)",
        "taxonomy": ["CUSTOMER_UI", "API_ONLY", "ADMIN", "INTERNAL", "DEPRECATED"],
        "total_pages": len(entries),
        "by_category": by_category,
        "customer_ui_orphan_count": orphan_count,
        "unclassified_count": 0,
        "note": (
            "unclassified_count is the mission-tracked metric (target: 0). A page's presence in "
            "this file's `entries` array with a category from `taxonomy` IS its classification -- "
            "there is no separate UNCLASSIFIED bucket by construction (see scripts/capability_registry_gate.py, "
            "which fails CI if a top-level *.html page exists with no entry here). customer_ui_orphan_count "
            "tracks a SEPARATE, non-blocking metric: CUSTOMER_UI pages that are correctly classified but "
            "still show static/placeholder data pending a live-API wiring fix -- see each entry's `notes`."
        ),
        "access_navigation_audit_status": (
            "NOT YET DONE for most entries. The mission's requested `access` (public/api_key_required/admin) "
            "and `navigation` (which nav menus link to this page) fields were audited and are accurate ONLY "
            "for the 9 pages this session touched directly (see the P21-P40 dashboard family and the git log "
            "for claude/sentinel-apex-transformation-8x3y26). Populating them accurately for the other 140 "
            "pages requires reading each page's own auth-wall markup and cross-referencing every nav/header "
            "partial across the site -- exactly the 'Unified Application Shell' audit (mission item 4) this "
            "session did not have room for. Recommended as the next P0: a dedicated navigation-shell audit "
            "pass, not a guess encoded into this file."
        ),
        "entries": entries,
    }

    OUTPUT.write_text(json.dumps(registry, indent=2) + "\n")
    print(f"Wrote {OUTPUT} -- {len(entries)} pages classified, by_category={by_category}, orphans={orphan_count}")


if __name__ == "__main__":
    main()
