#!/usr/bin/env python3
"""
SENTINEL APEX — Homepage Metadata Patcher
==========================================
Replaces the static <title>/description/OpenGraph/Twitter metadata block in
index.html with versionless, enterprise-positioned copy, and repoints
og:image/twitter:image at a correctly-dimensioned banner asset.

ROOT CAUSE: index.html's static <title>/og:title/twitter:title carry a
version number, an emoji, and live-looking counts baked in at generation
time (e.g. "v184.0 | 77+ Live Advisories"). Social crawlers (LinkedIn,
Slack, Facebook, WhatsApp, Discord) never execute sentinel-live-feeds.js's
client-side document.title rewrite, so they serve this static string
verbatim — confirmed directly against a LinkedIn link-preview screenshot.
Separately, the existing og:image already declares width=1200/height=630,
but the referenced file (assets/sentinel-apex-thumbnail.jpg) is actually
784x1168 (portrait) — a real dimension mismatch, independent of the text
issue, that this patch also corrects by repointing to a verified
1200x630 asset (assets/sentinel-apex-og-banner.jpg).

SAFE: Idempotent (detects prior patch via a marker string). Creates a
timestamped backup before any write. Validates HTML/EMBEDDED_INTEL
integrity after patching, matching this repository's existing
scripts/patch_sync_display.py / patch_top_threats.py convention. Aborts
on any check it cannot confirm rather than writing a partial result.

Usage:
    python3 scripts/patch_homepage_metadata.py --dry-run   # inspect only
    python3 scripts/patch_homepage_metadata.py --apply     # write changes

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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = REPO_ROOT / "index.html"

# Marker unique to the patched state — presence means this script has
# already run successfully against the current file.
ALREADY_PATCHED_MARKER = "Correlated in Real Time"

NEW_TITLE = "CYBERDUDEBIVASH&reg; SENTINEL APEX &mdash; Global Threat Intelligence Platform"
NEW_DESCRIPTION = (
    "CyberDudeBivash SENTINEL APEX &mdash; AI-Powered Threat Intelligence Platform. "
    "Real-time intel feeds, STIX 2.1 exports, AI campaign clustering, zero-day anomaly "
    "detection, MITRE ATT&CK mapping, EPSS enrichment, MISP export. API from $49/mo."
)
NEW_OG_TITLE = (
    "CYBERDUDEBIVASH® SENTINEL APEX — Global Threat Intelligence, "
    "Correlated in Real Time"
)
NEW_OG_DESCRIPTION = (
    "AI-native correlation engine for enterprise SOC teams. Global feed coverage, "
    "MITRE ATT&CK mapping, STIX 2.1 export, API-first integration."
)
NEW_OG_IMAGE_URL = "https://intel.cyberdudebivash.com/assets/sentinel-apex-og-banner.jpg"
NEW_OG_IMAGE_ALT = "CYBERDUDEBIVASH® SENTINEL APEX — Global Threat Intelligence Platform"
NEW_TWITTER_TITLE = NEW_OG_TITLE
NEW_TWITTER_DESCRIPTION = NEW_OG_DESCRIPTION

# --------------------------------------------------------------------------
# Patterns. Each is anchored on structure (an exact known attribute plus a
# generic content group) rather than today's full string, so a future,
# still-unwanted edit to the live file (e.g. a stat number changing) does
# not silently defeat the match — but each pattern is still specific enough
# that it cannot accidentally match an unrelated tag.
# --------------------------------------------------------------------------
TITLE_RE = re.compile(r"<title>[^<]*CYBERDUDEBIVASH[^<]*SENTINEL APEX[^<]*</title>", re.IGNORECASE)
DESCRIPTION_RE = re.compile(r'<meta\s+name="description"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
OG_TITLE_RE = re.compile(r'<meta\s+property="og:title"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
OG_DESCRIPTION_RE = re.compile(r'<meta\s+property="og:description"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
OG_IMAGE_RE = re.compile(r'<meta\s+property="og:image"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
OG_IMAGE_ALT_RE = re.compile(r'<meta\s+property="og:image:alt"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
TWITTER_TITLE_RE = re.compile(r'<meta\s+name="twitter:title"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
TWITTER_DESCRIPTION_RE = re.compile(r'<meta\s+name="twitter:description"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
TWITTER_IMAGE_RE = re.compile(r'<meta\s+name="twitter:image"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
TWITTER_CARD_RE = re.compile(r'<meta\s+name="twitter:card"\s+content="[^"]*"\s*/?>', re.IGNORECASE)


@dataclass
class FieldPatch:
    name: str
    pattern: re.Pattern
    replacement: str
    required: bool  # if True and not found, this is an ERROR, not a WARN


FIELD_PATCHES = [
    FieldPatch("title", TITLE_RE, f"<title>{NEW_TITLE}</title>", required=True),
    FieldPatch("meta description", DESCRIPTION_RE, f'<meta name="description" content="{NEW_DESCRIPTION}">', required=True),
    FieldPatch("og:title", OG_TITLE_RE, f'<meta property="og:title" content="{NEW_OG_TITLE}">', required=True),
    FieldPatch("og:description", OG_DESCRIPTION_RE, f'<meta property="og:description" content="{NEW_OG_DESCRIPTION}">', required=True),
    FieldPatch("og:image", OG_IMAGE_RE, f'<meta property="og:image" content="{NEW_OG_IMAGE_URL}">', required=True),
    FieldPatch("og:image:alt", OG_IMAGE_ALT_RE, f'<meta property="og:image:alt" content="{NEW_OG_IMAGE_ALT}">', required=False),
    FieldPatch("twitter:title", TWITTER_TITLE_RE, f'<meta name="twitter:title" content="{NEW_TWITTER_TITLE}">', required=True),
    FieldPatch("twitter:description", TWITTER_DESCRIPTION_RE, f'<meta name="twitter:description" content="{NEW_TWITTER_DESCRIPTION}">', required=True),
    FieldPatch("twitter:image", TWITTER_IMAGE_RE, f'<meta name="twitter:image" content="{NEW_OG_IMAGE_URL}">', required=False),
]


class PatchError(Exception):
    """Raised when a required check fails. Caller aborts with exit code 1."""


def load_index_html(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"{path} not found")
    return path.read_text(encoding="utf-8")


def apply_patches(content: str) -> tuple[str, list[str], list[str]]:
    """Returns (new_content, applied_field_names, warnings). Raises PatchError
    if a required field's pattern is not found."""
    new_content = content
    applied: list[str] = []
    warnings: list[str] = []

    for fp in FIELD_PATCHES:
        matches = fp.pattern.findall(new_content)
        if len(matches) == 0:
            if fp.required:
                raise PatchError(
                    f"required field '{fp.name}' not found — refusing to patch blind. "
                    f"Inspect index.html's current head block and update this script's "
                    f"pattern before re-running."
                )
            warnings.append(f"optional field '{fp.name}' not found — skipped (not added)")
            continue
        if len(matches) > 1:
            raise PatchError(
                f"field '{fp.name}' matched {len(matches)} times — expected exactly one. "
                f"Aborting rather than guessing which to replace."
            )
        new_content = fp.pattern.sub(fp.replacement, new_content, count=1)
        applied.append(fp.name)

    return new_content, applied, warnings


def verify_exactly_one(content: str, label: str, pattern: re.Pattern) -> None:
    count = len(pattern.findall(content))
    if count != 1:
        raise PatchError(f"post-patch check failed: expected exactly one {label}, found {count}")


def run_integrity_checks(before: str, after: str) -> None:
    """Mirrors this repo's existing patch_*.py convention: confirm nothing
    outside the intended metadata fields moved."""
    if before.count("<html") != after.count("<html"):
        raise PatchError("HTML structure count changed (<html> tag count differs) — aborting")
    if before.count("<body") != after.count("<body"):
        raise PatchError("HTML structure count changed (<body> tag count differs) — aborting")
    if "EMBEDDED_INTEL" in before and "EMBEDDED_INTEL" not in after:
        raise PatchError("EMBEDDED_INTEL lost during patch — aborting")
    if before.count("<script") != after.count("<script"):
        raise PatchError("script tag count changed — this patch must not touch scripts — aborting")

    # Exactly-one checks on the fields we control.
    verify_exactly_one(after, "<title>", re.compile(r"<title>", re.IGNORECASE))
    verify_exactly_one(after, 'meta name="description"', re.compile(r'<meta\s+name="description"', re.IGNORECASE))
    verify_exactly_one(after, 'og:title', re.compile(r'property="og:title"', re.IGNORECASE))
    verify_exactly_one(after, 'og:description', re.compile(r'property="og:description"', re.IGNORECASE))
    verify_exactly_one(after, 'twitter:title', re.compile(r'name="twitter:title"', re.IGNORECASE))
    verify_exactly_one(after, 'twitter:description', re.compile(r'name="twitter:description"', re.IGNORECASE))

    if ALREADY_PATCHED_MARKER not in after:
        raise PatchError("post-patch marker not present after supposedly successful patch — aborting")

    # Byte-size sanity: a metadata-only change should not move the file by
    # more than a few KB. A larger delta suggests something else changed.
    delta = len(after) - len(before)
    if abs(delta) > 4096:
        raise PatchError(
            f"unexpectedly large size delta ({delta:+d} bytes) for a metadata-only patch — aborting"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing.")
    mode.add_argument("--apply", action="store_true", help="Apply the patch and write index.html.")
    args = parser.parse_args()

    print("=" * 64)
    print("SENTINEL APEX — Homepage Metadata Patcher" + (" [DRY RUN]" if args.dry_run else " [APPLY]"))
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
        new_content, applied, warnings = apply_patches(content)
        run_integrity_checks(content, new_content)
    except PatchError as exc:
        print(f"[PATCH] ERROR: {exc}")
        print("[PATCH] Nothing written. Repository unchanged.")
        return 1

    for w in warnings:
        print(f"[PATCH] WARN: {w}")

    print(f"[PATCH] Fields updated: {', '.join(applied)}")
    print(f"[PATCH] New size: {len(new_content):,} bytes (delta {len(new_content) - original_size:+d})")
    print("[PATCH] All integrity checks passed:")
    print("        - <html>/<body>/<script> tag counts unchanged")
    print("        - EMBEDDED_INTEL preserved")
    print("        - exactly one instance of each metadata field")
    print("        - size delta within expected bounds for a metadata-only change")

    if args.dry_run:
        print("[PATCH] Dry run complete — no file written. Re-run with --apply to write.")
        return 0

    backup_path = INDEX_HTML.with_name(INDEX_HTML.name + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(INDEX_HTML, backup_path)
    print(f"[PATCH] Backup written: {backup_path.name}")

    INDEX_HTML.write_text(new_content, encoding="utf-8")
    print(f"[PATCH] SUCCESS — index.html updated ({len(new_content):,} bytes).")
    print("[PATCH] NEXT STEP: re-scrape via LinkedIn Post Inspector and Facebook Sharing Debugger —")
    print("        both cache previews and will keep serving the old one until re-scraped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
