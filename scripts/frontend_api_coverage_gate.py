#!/usr/bin/env python3
"""
scripts/frontend_api_coverage_gate.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Frontend API Coverage Gate

Evidence: a manual page-by-page audit this session (see cves.html and
ransomware.html fixes) found that a large share of this platform's
top-level HTML pages ship zero client-side calls to workers/intel-gateway's
30+ live API routes -- pages whose entire purpose is to show live
intelligence data (cves.html, ransomware.html at time of writing) were
rendering hardcoded placeholder text instead, regardless of what the
backend actually exposes. That manual audit's own page count ("246") did
not match a direct, repeatable count taken later in the same session
(144, confirmed by both `ls *.html` and `git ls-files` at the repo root) --
a concrete demonstration that a one-time manual sweep drifts and cannot be
trusted as a durable source of truth. This script exists so the platform
never again has to re-derive that count by hand, and so a *new* static-only
product page cannot silently ship without at least being recorded.

SCOPE: top-level *.html files only (repo root), matching the manual audit's
own scope -- excludes reports/, blog/, docs/, dashboard/, components/,
landing/, and other subdirectories, which are a separate, much larger
population (25,000+ files, mostly generated report artifacts) with
different rules.

CLASSIFICATION (deliberately simple and auditable -- a page is "dynamic" if
it contains ANY evidence of a client-side call into this platform's own
API surface):
  - a `fetch(` call whose literal argument contains "/api/", or
  - a <script src="..."> reference to one of this codebase's known
    live-data client scripts (js/sentinel-live-feeds.js, js/api_adapter.js,
    js/card_renderer.js) -- these are the shared scripts that themselves
    call the API on the page's behalf, so a page that includes one is
    "dynamic" even if it has no inline fetch() of its own.
This mirrors the exact method used in this session's own manual audit
(grep for fetch(/<script API references) -- not a new, unverified heuristic.

DELIBERATELY NOT A HARD-FAIL GATE YET (RX-PUB-A0 bake-in rollout pattern):
this script has no allowlist of legitimately-static pages (privacy,
terms, pricing, legal/marketing content -- confirmed to be the majority of
the static pages, but "confirmed" requires a human or a follow-up pass to
actually curate that list page by page, which this script does not invent
on its own -- see "NEVER ... Invent" in this repo's CLAUDE.md). Until that
allowlist exists and has a run history, this script only classifies and
reports (exit 0 always) -- it never fails CI. Once an allowlist is added
(see ALLOWLIST_PATH below) a future change can add a real gate: any
non-allowlisted static page blocks deployment.

Writes data/quality/frontend_api_coverage_report.json (Phase/Observable
Everything requirement -- CLAUDE.md "Minimum observability requirements").
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "quality" / "frontend_api_coverage_report.json"
ALLOWLIST_PATH = REPO_ROOT / "data" / "quality" / "frontend_static_page_allowlist.json"

# Known shared client scripts that themselves call the platform's API on a
# page's behalf -- a page that includes one of these is "dynamic" even with
# no inline fetch() of its own. Reuse Before Build / Single Source of Truth:
# these are exactly the scripts already established elsewhere this session
# (js/sentinel-live-feeds.js -- ransomware.html's fix; js/api_adapter.js,
# js/card_renderer.js -- referenced in scripts/frontend_integrity.py's own
# TIER 3 protected-file list).
KNOWN_LIVE_DATA_SCRIPTS = (
    "sentinel-live-feeds.js",
    "api_adapter.js",
    "card_renderer.js",
    "card_renderer_integration.js",
)


# Deliberately loose: a strict "fetch( immediately followed by a quote then
# /api/" pattern missed both real pages this script exists to catch --
# cves.html and ransomware.html's own live-wiring fixes this session both
# build the URL via variable concatenation (`fetch(API_BASE + "/api/...")`),
# not a literal string starting with /api/. Matching "/api/ appears
# somewhere within the fetch(...) call's argument list" instead catches
# concatenation, template literals, and a URL variable assigned from an
# /api/ literal a few lines earlier -- at the cost of a rare, harmless
# false positive (a fetch() call with an unrelated /api/-containing string
# nearby). A false positive here under-reports gaps rather than
# over-reporting them, which is the safer failure direction for a
# find-real-gaps tool. [^)] already spans newlines (unlike `.` without
# re.DOTALL), so a multi-line fetch(...) call is still matched correctly.
_FETCH_API_RE = re.compile(r"fetch\s*\([^)]{0,200}?/api/", re.IGNORECASE)
_SCRIPT_SRC_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def _is_dynamic(content: str) -> tuple[bool, str]:
    """Returns (is_dynamic, reason). reason is empty for a static page."""
    if _FETCH_API_RE.search(content):
        return True, "inline fetch() of /api/*"
    for m in _SCRIPT_SRC_RE.finditer(content):
        src = m.group(1)
        for known in KNOWN_LIVE_DATA_SCRIPTS:
            if known in src:
                return True, f"includes {known}"
    return False, ""


def _load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.exists():
        return set()
    try:
        data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
        return set(data.get("static_pages", []))
    except Exception:
        return set()


def main() -> int:
    pages = sorted(REPO_ROOT.glob("*.html"))
    allowlist = _load_allowlist()

    dynamic_pages: list[dict] = []
    static_pages: list[dict] = []

    for page in pages:
        try:
            content = page.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"[WARN] could not read {page.name}: {e}")
            continue
        is_dynamic, reason = _is_dynamic(content)
        entry = {"file": page.name, "reason": reason}
        if is_dynamic:
            dynamic_pages.append(entry)
        else:
            entry["allowlisted"] = page.name in allowlist
            static_pages.append(entry)

    unclassified_static = [p for p in static_pages if not p["allowlisted"]]

    report = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "top-level *.html (repo root only)",
        "total_pages": len(pages),
        "dynamic_count": len(dynamic_pages),
        "static_count": len(static_pages),
        "static_allowlisted_count": len(static_pages) - len(unclassified_static),
        "static_unclassified_count": len(unclassified_static),
        "allowlist_source": str(ALLOWLIST_PATH.relative_to(REPO_ROOT)),
        "allowlist_present": ALLOWLIST_PATH.exists(),
        "dynamic_pages": dynamic_pages,
        "static_pages": static_pages,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)

    print("=" * 70)
    print("FRONTEND API COVERAGE GATE (observability-only -- see script docstring)")
    print(f"Scope: {report['scope']}")
    print(f"Total pages:              {report['total_pages']}")
    print(f"Dynamic (calls the API):  {report['dynamic_count']}")
    print(f"Static, allowlisted:      {report['static_allowlisted_count']}")
    print(f"Static, UNCLASSIFIED:     {report['static_unclassified_count']}")
    if not report["allowlist_present"]:
        print(f"[WARN] no allowlist at {ALLOWLIST_PATH.relative_to(REPO_ROOT)} -- "
              f"every static page currently reports as unclassified")
    if unclassified_static:
        names = ", ".join(p["file"] for p in unclassified_static[:15])
        more = f" (+{len(unclassified_static) - 15} more)" if len(unclassified_static) > 15 else ""
        print(f"[NOTICE] unclassified static pages: {names}{more}")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
