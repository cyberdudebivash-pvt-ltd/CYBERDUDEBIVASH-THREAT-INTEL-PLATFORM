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


# Deliberately loose within a <script> block's own text, not "fetch(
# followed closely by /api/" -- a stricter windowed version of this check
# missed THREE real variants while this script was being built and verified
# against its own fixes: fetch(API_BASE + "/api/...") string concatenation
# (ransomware.html, cves.html), and fetch(API_BASE + path, ...) where the
# actual "/api/..." literal is a call-site argument to a small helper
# function defined elsewhere in the same script, sometimes 40+ lines away
# (threats.html's fetchJSON() helper). Requiring both signals to appear
# ANYWHERE in the same <script> block, rather than adjacent to each other,
# catches all of these without needing a real JS parser.
#
# CodeRabbit review finding on PR #336 (verified, not taken on faith):
# an earlier version of this checked the whole raw file, not just script
# content -- SENTINEL_APEX_ENTERPRISE_AUDIT_v145.html (a prose audit
# report that discusses this platform's own /api/ endpoints in plain
# English) was misclassified dynamic purely because the sentence "daily
# public JSON fetch (no API key needed)" happens to contain the substring
# "fetch (" outside any <script> tag, nowhere near real code. Scoping the
# co-occurrence check to concatenated <script>...</script> body content
# (JSON-LD structured-data blocks excluded -- they hold JSON text, not
# executable JS, and could coincidentally contain the same two substrings
# as unrelated data) closes that false positive while still catching all
# three real cases above, since every one of them is genuine inline JS.
_FETCH_RE = re.compile(r"fetch\s*\(", re.IGNORECASE)
_API_PATH_LITERAL_RE = re.compile(r"""["'`][^"'`]*?/api/[^"'`]*["'`]""")
_SCRIPT_SRC_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

# GitHub Advanced Security / CodeQL finding on PR #336 ("Bad HTML filtering
# regexp", verified against the CodeQL rule's own stated rationale, not
# taken on faith): the previous pattern's closing half, `</script\s*>`,
# only tolerated whitespace between "</script" and the final ">". A real
# browser's HTML tokenizer closes a <script> element on "</script" followed
# by ANY run of characters up to the next ">" -- e.g. `</script data-x="1">`
# or CodeQL's own example `</script\t\n bar>` -- not just whitespace. Since
# the capturing group here is non-greedy (`.*?`), a closing tag the old
# pattern couldn't recognize would make the match skip past it and either
# swallow unrelated trailing HTML into a script "body" or fail to find a
# close at all, silently dropping that block's text from
# _inline_script_text()'s classification input (a false-negative risk, not
# an XSS one -- this script only ever parses this repo's own first-party
# *.html files to build a coverage report, it never sanitizes untrusted
# HTML for serving). `[^>]*` mirrors real tokenizer behavior and is a
# strict superset of the old `\s*` -- every previously-matching well-formed
# `</script>` still matches identically (both accept zero extra chars).
_SCRIPT_BLOCK_RE = re.compile(r"<script\b([^>]*)>(.*?)</script[^>]*>", re.IGNORECASE | re.DOTALL)


def _inline_script_text(content: str) -> str:
    """Concatenated text of every <script>...</script> block's own body,
    skipping external (src=) scripts (no inline body to scan -- handled
    separately below) and JSON-LD structured-data blocks (JSON text, not
    JS -- see _is_dynamic's docstring)."""
    parts = []
    for attrs, body in _SCRIPT_BLOCK_RE.findall(content):
        if "src=" in attrs.lower():
            continue
        if "application/ld+json" in attrs.lower():
            continue
        parts.append(body)
    return "\n".join(parts)


def _is_dynamic(content: str) -> tuple[bool, str]:
    """Returns (is_dynamic, reason). reason is empty for a static page."""
    script_text = _inline_script_text(content)
    if _FETCH_RE.search(script_text) and _API_PATH_LITERAL_RE.search(script_text):
        return True, "fetch() call plus an /api/* path literal in the same <script> block"
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
