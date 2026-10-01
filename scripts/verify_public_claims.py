#!/usr/bin/env python3
"""
scripts/verify_public_claims.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Unsupported Social-Proof Gate
==================================================================================
Rebuilt 2026-09-19 after the original implementation was silently dropped by a
`.gitignore` rule (`verify*.py`) that pre-dated this file and was never scoped to
exclude it -- it was written, run green, and never actually committed. See
scripts/verify_commercial_contract.py for the sibling gate with the same history.

config/evidence-register.json's "withdrawn" array is the ground truth: every
listed claim and variant failed an evidence check and must not reappear,
unnegated, on any buyer-facing page. This gate is data-driven from that file
rather than hardcoding the claim list a second time.

NEGATION SCOPE -- the one hole found and fixed during this rebuild's own
negative-testing: a withdrawn claim is only treated as an honest, negated
mention (e.g. "Evidence, not testimonials") when the negation cue word and the
claim text share the SAME HTML text node. A prior draft of this idea scanned a
fixed character window (~120 chars) *before* the match regardless of tag
boundaries, so an unrelated disclaimer sentence earlier in the page could mask
a genuinely reintroduced bare claim a few tags later. Splitting on tag
boundaries first, then windowing only inside one resulting text node, closes
that hole -- confirmed by the negative tests in this file's own test run (see
the verification section of PR #435).

Exit codes:
  0 = ALL PASS (no unevidenced claim found unnegated)
  1 = ONE OR MORE FAIL

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [public-claims] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.verify_public_claims")

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_REGISTER_PATH = REPO_ROOT / "config" / "evidence-register.json"
CLAIM_MATRIX_PATH = REPO_ROOT / "p0-revenue-os" / "config" / "claim_matrix.json"
EXCLUDED_DIRS = {"blog", "threat", "reports", "node_modules", ".git", "dist", "data"}

# How far back inside the SAME text node we look for a negation cue.
# Deliberately small and node-scoped -- see module docstring.
NEGATION_WINDOW_CHARS = 60
NEGATION_CUES = (
    "not ", "no longer", "never ", "removed", "withdrawn", "cannot claim",
    "does not", "doesn't", "isn't", "is not", "was not", "were not",
    "no review", "no rating", "unevidenced", "un-evidenced",
)

TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)

CHECK_COUNT = 0
FAILURES: list[str] = []


def check(condition: bool, description: str) -> None:
    global CHECK_COUNT
    CHECK_COUNT += 1
    if condition:
        log.info("PASS P%03d: %s", CHECK_COUNT, description)
    else:
        FAILURES.append(f"P{CHECK_COUNT:03d}: {description}")
        log.error("FAIL P%03d: %s", CHECK_COUNT, description)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_buyer_html_files():
    for path in sorted(REPO_ROOT.rglob("*.html")):
        rel = path.relative_to(REPO_ROOT)
        if any(part in EXCLUDED_DIRS for part in rel.parts[:-1]):
            continue
        yield rel, path


def text_nodes(html: str) -> list[str]:
    """Split raw HTML into its text-node segments, dropping script/style bodies
    (code, not prose) so a variable name or comment can't trip a claim match."""
    stripped = SCRIPT_STYLE_RE.sub(" ", html)
    return TAG_RE.split(stripped)


def is_negated_in_node(node: str, match_start: int, match_end: int) -> bool:
    # Symmetric: a disclaimer can lead ("no longer claim X") or trail
    # ("X -- that figure was withdrawn"). Both windows stay strictly inside
    # this one text node; the caller never passes text from another node.
    before = node[max(0, match_start - NEGATION_WINDOW_CHARS):match_start].lower()
    after = node[match_end:match_end + NEGATION_WINDOW_CHARS].lower()
    return any(cue in before for cue in NEGATION_CUES) or any(cue in after for cue in NEGATION_CUES)


def cross_node_match(nodes: list[str], pattern: re.Pattern) -> str | None:
    """A claim split across elements, e.g. a stat widget rendering
    <div>80+</div><div>Countries</div>, never appears inside one text node,
    so the per-node scan cannot see it (2026-09-30: demo.html published
    "1,200+ SOC Teams / 80+ Countries" that way while "80+ countries" was
    already withdrawn). Join the visible nodes with single spaces and return
    any match that spans a node boundary. Such a match gets no negation
    allowance: an honest disclaimer is written as prose inside one node,
    which the per-node pass already handles."""
    parts = [re.sub(r"\s+", " ", n).strip() for n in nodes]
    parts = [p for p in parts if p]
    spans, pos = [], 0
    for p in parts:
        spans.append((pos, pos + len(p)))
        pos += len(p) + 1
    joined = " ".join(parts)
    for m in pattern.finditer(joined):
        if not any(start <= m.start() and m.end() <= end for start, end in spans):
            return m.group(0)
    return None


def build_forbidden_patterns(withdrawn: list[dict]) -> list[tuple[str, re.Pattern]]:
    patterns: list[tuple[str, re.Pattern]] = []
    for entry in withdrawn:
        variants = entry.get("variants") or [entry["claim"]]
        for variant in variants:
            escaped = re.escape(variant)
            # Loosen internal whitespace so "500+  teams" / line-wrapped text still matches.
            escaped = re.sub(r"\\ ", r"\\s+", escaped)
            patterns.append((variant, re.compile(escaped, re.IGNORECASE)))
    return patterns


CLAIM_MATRIX_VARIANTS = {
    "ISO27001": ["ISO/IEC 27001 certified", "ISO 27001 certified"],
    "SOC2": ["SOC 2 Type II certified"],
    "DARKWEB_LIVE": ["Live dark web monitoring"],
    # "plug-and-play" is the unsafe packaging claim regardless of whether
    # vendor names are separated by HTML tags or punctuation.
    "SIEM_PLUG_PLAY": ["Splunk / Sentinel / QRadar plug-and-play", "plug-and-play"],
    "COUNTRIES_PROTECTED": ["50+ countries protected"],
    "FASTER_TRIAGE_PCT": ["72% faster threat triage", "72% faster"],
    "NAMED_CUSTOMERS": ["Named enterprise customer logos"],
}


def build_claim_matrix_patterns(matrix: dict) -> list[tuple[str, re.Pattern]]:
    patterns: list[tuple[str, re.Pattern]] = []
    for entry in matrix.get("claims", []):
        status = str(entry.get("status", "")).lower()
        if not status.startswith("forbidden"):
            continue
        variants = CLAIM_MATRIX_VARIANTS.get(entry.get("id"), [entry.get("text", "")])
        for variant in variants:
            if not variant:
                continue
            escaped = re.escape(variant)
            escaped = re.sub(r"\\ ", r"\\s+", escaped)
            patterns.append((f"{entry.get('id')}:{variant}", re.compile(escaped, re.IGNORECASE)))
    return patterns


def main() -> int:
    if not EVIDENCE_REGISTER_PATH.exists():
        log.error("Evidence register missing: %s", EVIDENCE_REGISTER_PATH)
        return 1
    register = load_json(EVIDENCE_REGISTER_PATH)
    withdrawn = register.get("withdrawn", [])
    check(len(withdrawn) > 0, "evidence-register.json lists at least one withdrawn claim")

    forbidden_patterns = build_forbidden_patterns(withdrawn)
    log.info("Loaded %d forbidden claim variant(s) from evidence-register.json.", len(forbidden_patterns))

    if not CLAIM_MATRIX_PATH.exists():
        log.error("Claim matrix missing: %s", CLAIM_MATRIX_PATH)
        return 1
    claim_matrix = load_json(CLAIM_MATRIX_PATH)
    matrix_patterns = build_claim_matrix_patterns(claim_matrix)
    check(len(matrix_patterns) > 0, "claim_matrix.json yields forbidden customer-claim patterns")
    log.info("Loaded %d forbidden claim-matrix pattern(s).", len(matrix_patterns))

    scanned = 0
    for rel, path in iter_buyer_html_files():
        scanned += 1
        html = path.read_text(encoding="utf-8", errors="ignore")
        nodes = text_nodes(html)
        for variant, pattern in forbidden_patterns:
            violation_found = False
            for node in nodes:
                for m in pattern.finditer(node):
                    if not is_negated_in_node(node, m.start(), m.end()):
                        violation_found = True
                        break
                if violation_found:
                    break
            check(not violation_found, f"{rel} does not publish withdrawn claim '{variant}' unnegated")
            split = cross_node_match(nodes, pattern)
            check(split is None, f"{rel} does not publish withdrawn claim '{variant}' split across elements"
                  + (f" (found '{split}')" if split else ""))

        for label, pattern in matrix_patterns:
            violation_found = False
            for node in nodes:
                for m in pattern.finditer(node):
                    if not is_negated_in_node(node, m.start(), m.end()):
                        violation_found = True
                        break
                if violation_found:
                    break
            check(not violation_found, f"{rel} does not publish claim-matrix prohibition '{label}' unnegated")
    log.info(
        "Swept %d buyer-facing HTML page(s) for withdrawn and claim-matrix-prohibited customer claims.",
        scanned,
    )

    # --- Sanity checks: retained/labelled claims must still carry their
    # required framing, so this gate cannot be satisfied by over-purging. ---
    sla_path = REPO_ROOT / "sla.html"
    if sla_path.exists():
        sla_text = sla_path.read_text(encoding="utf-8", errors="ignore").lower()
        check("outage credit" in sla_text, "sla.html retains the P0 outage-credit commitment")
        check("99.9%" in sla_text or "99.5%" in sla_text, "sla.html retains a tier uptime commitment")

    roi_path = REPO_ROOT / "roi-calculator.html"
    if roi_path.exists():
        roi_text = roi_path.read_text(encoding="utf-8", errors="ignore").lower()
        check(
            "projection" in roi_text or "estimate" in roi_text,
            "roi-calculator.html labels its output as a projection/estimate, not an achieved result",
        )

    print()
    print(f"verify_public_claims.py: {CHECK_COUNT} checks, {len(FAILURES)} failed.")
    if FAILURES:
        print("\nFAILURES:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("ALL PUBLIC CLAIMS CHECKS PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
