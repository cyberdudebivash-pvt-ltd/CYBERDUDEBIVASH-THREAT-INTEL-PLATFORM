#!/usr/bin/env python3
"""
SENTINEL APEX — Landing Page Hero Patcher (PR-3)
==================================================
Inserts the new marketing hero section (headline, primary/secondary CTA,
enterprise trust grid, statistics strip, integrations list) into
index.html immediately after </header>, and links css/tokens.css +
css/hero.css in <head> if not already present.

WHY A PATCH SCRIPT INSTEAD OF A DIRECT EDIT: index.html is governed by
a deliberate "v184.0 IMMUTABLE API-FIRST" architecture enforced by
dedicated CI guard scripts (embedded_intel_gate.py, apex_stability_lock.py,
regression_immunity.py, platform_integrity_guard.py, etc.) following
documented past corruption incidents. Every legitimate change to this
file goes through a narrow, single-purpose, backup-then-write patch
script — this follows the same convention as
scripts/patch_homepage_metadata.py (PR-1) and the pre-existing
scripts/patch_sync_display.py / patch_top_threats.py.

WHAT THIS DOES NOT TOUCH: the existing <header> (brand mark, 30+ item
nav, trust bar, live threat map canvas) and everything below the
status strip (dashboard metrics, risk trend chart, search/filter bar,
threat card grid) are untouched. This inserts one new <section> between
</header> and the status-strip comment, and two new <link> tags in
<head> — nothing else moves.

SAFE: Idempotent (detects prior patch via an HTML comment marker).
Creates a timestamped backup before any write. Anchors on two strings
confirmed unique in the real file (`</head>`, `</header>`) and aborts
if either is missing or matched more than once, rather than guessing.
Post-write integrity checks mirror patch_homepage_metadata.py's
convention: <html>/<body>/<script> tag counts unchanged (this patch
adds zero <script> tags), EMBEDDED_INTEL preserved, and a byte-size
delta bound sized for a content insertion (not a metadata-only edit).

Usage:
    python3 scripts/patch_landing_hero.py --dry-run   # inspect only
    python3 scripts/patch_landing_hero.py --apply     # write changes

Exit codes:
    0  success (or already patched, or clean dry-run)
    1  fatal error — nothing written, or a validation check failed
    2  usage error (neither --dry-run nor --apply supplied)
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"

ALREADY_PATCHED_MARKER = "SAPX-HERO-V1"

HEAD_ANCHOR = "</head>"
HEADER_ANCHOR = "</header>"

NEW_HEAD_LINKS = (
    '<link rel="stylesheet" href="/css/tokens.css">\n'
    '<link rel="stylesheet" href="/css/hero.css">\n'
    "</head>"
)

HERO_FRAGMENT = """<!-- SAPX-HERO-V1 -->
        <section class="sapx-hero" id="sapx-hero" aria-labelledby="sapx-hero-heading">
            <div class="sapx-hero-content">
                <p class="sapx-hero-eyebrow">AI-Powered Threat Intelligence &middot; Built for Enterprise SOC</p>
                <h2 class="sapx-hero-heading" id="sapx-hero-heading">
                    Global threat intelligence,<br>
                    <span class="sapx-hero-heading-accent">correlated in real time.</span>
                </h2>
                <p class="sapx-hero-sub">
                    An AI-native correlation engine for enterprise SOC teams &mdash; real-time
                    feed correlation, STIX 2.1 export, MITRE ATT&amp;CK mapping, and
                    API-first integration into the tools you already run.
                </p>
                <div class="sapx-hero-ctas">
                    <a class="sapx-btn sapx-btn-primary" href="/upgrade.html?plan=free&amp;utm_source=hero&amp;utm_medium=cta&amp;utm_campaign=landing_hero">Start Free Trial</a>
                    <a class="sapx-btn sapx-btn-secondary" href="/demo.html?utm_source=hero&amp;utm_medium=cta&amp;utm_campaign=landing_hero">Book a Live Demo</a>
                </div>
                <ul class="sapx-hero-capabilities" aria-label="Platform capabilities">
                    <li><span class="sapx-hero-cap-icon" aria-hidden="true">&#9889;</span>Real-Time Feed Correlation</li>
                    <li><span class="sapx-hero-cap-icon" aria-hidden="true">&#129516;</span>STIX 2.1 Export</li>
                    <li><span class="sapx-hero-cap-icon" aria-hidden="true">&#127919;</span>MITRE ATT&amp;CK Mapping</li>
                    <li><span class="sapx-hero-cap-icon" aria-hidden="true">&#128268;</span>API-First Architecture</li>
                </ul>
            </div>

            <div class="sapx-hero-trust" aria-labelledby="sapx-hero-trust-heading">
                <h3 class="sapx-hero-section-kicker" id="sapx-hero-trust-heading">Enterprise-Grade Foundations</h3>
                <div class="sapx-hero-trust-grid">
                    <div class="sapx-trust-item">
                        <span class="sapx-trust-icon" aria-hidden="true">&#128737;</span>
                        <span class="sapx-trust-text">STIX 2.1 &amp; TAXII 2.1 Compliant</span>
                    </div>
                    <div class="sapx-trust-item">
                        <span class="sapx-trust-icon" aria-hidden="true">&#128274;</span>
                        <span class="sapx-trust-text">JWT Auth &middot; PBKDF2-SHA256 Key Storage</span>
                    </div>
                    <div class="sapx-trust-item">
                        <span class="sapx-trust-icon" aria-hidden="true">&#127470;&#127475;</span>
                        <span class="sapx-trust-text">Sovereign India-Operated Platform</span>
                    </div>
                    <div class="sapx-trust-item">
                        <span class="sapx-trust-icon" aria-hidden="true">&#9201;</span>
                        <span class="sapx-trust-text">99.9% Enterprise Uptime SLA</span>
                    </div>
                </div>
            </div>

            <div class="sapx-hero-stats" aria-labelledby="sapx-hero-stats-heading">
                <h3 class="sapx-hero-section-kicker" id="sapx-hero-stats-heading">Platform at a Glance</h3>
                <div class="sapx-hero-stats-grid">
                    <div class="sapx-stat-item">
                        <div class="sapx-stat-value">&lt;2h</div>
                        <div class="sapx-stat-label">Feed Freshness SLA</div>
                    </div>
                    <div class="sapx-stat-item">
                        <div class="sapx-stat-value">99.9%</div>
                        <div class="sapx-stat-label">Enterprise Uptime SLA</div>
                    </div>
                    <div class="sapx-stat-item">
                        <div class="sapx-stat-value">STIX 2.1</div>
                        <div class="sapx-stat-label">Native Export Format</div>
                    </div>
                    <div class="sapx-stat-item">
                        <div class="sapx-stat-value">ATT&amp;CK v15</div>
                        <div class="sapx-stat-label">MITRE Technique Mapping</div>
                    </div>
                </div>
            </div>

            <div class="sapx-hero-integrations" aria-labelledby="sapx-hero-integrations-heading">
                <h3 class="sapx-hero-section-kicker" id="sapx-hero-integrations-heading">Works With Your Stack</h3>
                <ul class="sapx-hero-integrations-list">
                    <li>Splunk</li>
                    <li>Microsoft Sentinel</li>
                    <li>IBM QRadar</li>
                    <li>Elastic SIEM</li>
                    <li>MISP</li>
                    <li>TAXII 2.1</li>
                </ul>
            </div>
        </section>
"""

# Byte-size sanity bound. This patch INSERTS new content (unlike
# patch_homepage_metadata.py's metadata-only edit), so the expected
# delta is the hero fragment (~5KB) plus two <link> lines (~150B) --
# bounded generously at 10KB to still catch a genuinely wrong/runaway
# result rather than silently accepting anything.
MAX_EXPECTED_DELTA = 10240


class PatchError(Exception):
    """Raised when a required check fails. Caller aborts with exit code 1."""


def load_index_html(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"{path} not found")
    return path.read_text(encoding="utf-8")


def apply_patch(content: str) -> str:
    """Returns the patched content. Raises PatchError if either anchor
    is missing or matched more than once."""
    head_count = content.count(HEAD_ANCHOR)
    if head_count != 1:
        raise PatchError(
            f"expected exactly one '{HEAD_ANCHOR}', found {head_count} — "
            f"aborting rather than guessing which to patch."
        )
    header_count = content.count(HEADER_ANCHOR)
    if header_count != 1:
        raise PatchError(
            f"expected exactly one '{HEADER_ANCHOR}', found {header_count} — "
            f"aborting rather than guessing which to patch."
        )

    new_content = content.replace(HEAD_ANCHOR, NEW_HEAD_LINKS, 1)
    new_content = new_content.replace(
        HEADER_ANCHOR, HEADER_ANCHOR + "\n\n" + HERO_FRAGMENT, 1
    )
    return new_content


def run_integrity_checks(before: str, after: str) -> None:
    """Mirrors patch_homepage_metadata.py's convention: confirm nothing
    outside the intended insertion points moved."""
    if before.count("<html") != after.count("<html"):
        raise PatchError("HTML structure count changed (<html> tag count differs) — aborting")
    if before.count("<body") != after.count("<body"):
        raise PatchError("HTML structure count changed (<body> tag count differs) — aborting")
    if before.count("<script") != after.count("<script"):
        raise PatchError(
            "script tag count changed — this patch adds zero <script> tags — aborting"
        )
    if "EMBEDDED_INTEL" in before and "EMBEDDED_INTEL" not in after:
        raise PatchError("EMBEDDED_INTEL lost during patch — aborting")

    if after.count('<link rel="stylesheet" href="/css/tokens.css">') != 1:
        raise PatchError("post-patch check failed: expected exactly one tokens.css link")
    if after.count('<link rel="stylesheet" href="/css/hero.css">') != 1:
        raise PatchError("post-patch check failed: expected exactly one hero.css link")
    if after.count('id="sapx-hero"') != 1:
        raise PatchError("post-patch check failed: expected exactly one #sapx-hero section")
    if after.count("</header>") != 1 or after.count("</head>") != 1:
        raise PatchError("post-patch check failed: header/head structure duplicated")

    if ALREADY_PATCHED_MARKER not in after:
        raise PatchError("post-patch marker not present after supposedly successful patch — aborting")

    delta = len(after) - len(before)
    if delta <= 0 or delta > MAX_EXPECTED_DELTA:
        raise PatchError(
            f"unexpected size delta ({delta:+d} bytes) for a hero-insertion patch — aborting"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing.")
    mode.add_argument("--apply", action="store_true", help="Apply the patch and write index.html.")
    args = parser.parse_args()

    print("=" * 64)
    print("SENTINEL APEX — Landing Page Hero Patcher" + (" [DRY RUN]" if args.dry_run else " [APPLY]"))
    print("=" * 64)

    try:
        content = load_index_html(INDEX_HTML)
    except PatchError as exc:
        print(f"[PATCH] FATAL: {exc}")
        return 1

    original_size = len(content)
    print(f"[PATCH] Loaded index.html: {original_size:,} bytes")

    if ALREADY_PATCHED_MARKER in content:
        print("[PATCH] ALREADY PATCHED — marker found, no changes needed.")
        return 0

    try:
        new_content = apply_patch(content)
        run_integrity_checks(content, new_content)
    except PatchError as exc:
        print(f"[PATCH] ERROR: {exc}")
        print("[PATCH] Nothing written. Repository unchanged.")
        return 1

    print("[PATCH] New size: {:,} bytes (delta {:+d})".format(len(new_content), len(new_content) - original_size))
    print("[PATCH] All integrity checks passed:")
    print("        - <html>/<body>/<script> tag counts unchanged (zero new <script> tags)")
    print("        - EMBEDDED_INTEL preserved")
    print("        - exactly one tokens.css link, one hero.css link, one #sapx-hero section")
    print("        - size delta within expected bounds for a hero-insertion patch")
    print("[PATCH] NOTE: css/tokens.css and css/hero.css must already exist in the repo")
    print("        (added in PR-2 and this PR respectively) for the new hero to render")
    print("        correctly — this script only edits index.html.")

    if args.dry_run:
        print("[PATCH] Dry run complete — no file written. Re-run with --apply to write.")
        return 0

    backup_path = INDEX_HTML.with_name(INDEX_HTML.name + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(INDEX_HTML, backup_path)
    print(f"[PATCH] Backup written: {backup_path.name}")

    INDEX_HTML.write_text(new_content, encoding="utf-8")
    print(f"[PATCH] SUCCESS — index.html updated ({len(new_content):,} bytes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
