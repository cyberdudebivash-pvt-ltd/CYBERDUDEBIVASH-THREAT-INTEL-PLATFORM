#!/usr/bin/env python3
"""
scripts/certification_feed_guard.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Stale-Feed Recurrence Guard (Phase 2 P0)
==============================================================================
Phase 1 (PR #219) found scripts/p33_production_certification.py silently
measuring a 3-month-stale data/feed.json instead of the live api/feed.json.
Phase 2 found scripts/p25_enterprise_trust_gate.py had the identical defect
against the root feed.json snapshot -- and that script's name doesn't even
match the "certification"/"validator"/"quality" naming convention used to
scope this guard, which is why EXTRA_SCAN below exists: name-pattern
matching alone is not a reliable way to find every release/trust gate.

This is a repository-level, AST-based static guard over production
certification/quality/validator scripts: it flags any statically-resolvable
Path()/open() call whose path resolves to the known-stale root feed.json or
data/feed.json -- never free text, log messages, or docstrings -- so CI
fails if a script reintroduces a direct dependency on that dataset instead
of going through scripts/p38_shared_validators.get_certification_feed().

Deliberately AST-based and call-scoped, not grep/regex over the whole file:
an early version of this guard that flagged any string constant containing
"feed.json" produced 260 false positives across log messages like "Loaded
%d items from api/feed.json" -- this version only inspects the literal
argument of an actual Path(...)/open(...) construction.

Usage:
    python3 scripts/certification_feed_guard.py           # scan, exit 1 on hit
    python3 scripts/certification_feed_guard.py --list     # show scanned files
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Same search patterns as the Phase 2 mandate's own certification inventory
# sweep (*_production_certification.py, *certification*.py, *validator*.py,
# *quality*.py) -- scoped, not repo-wide, to keep this a high-signal gate
# rather than one contributors learn to ignore.
NAME_GLOBS = (
    "*_production_certification.py",
    "*certification*.py",
    "*validator*.py",
    "*quality*.py",
)

# Confirmed release/trust-gate scripts that do NOT match the name patterns
# above (p25's defect, found in Phase 2, is exactly why this list exists --
# a naming-convention-only scope would have missed it). Extend this list
# whenever a new release gate is confirmed, regardless of its filename.
EXTRA_SCAN = (
    "p25_enterprise_trust_gate.py",
    "manifest_integrity_system.py",
    "confidence_calibrator.py",
    "source_diversity_checker.py",
)

# Files intentionally exempt from this guard:
#   - p38_shared_validators.py: the canonical FEED_REGISTRY itself must name
#     the stale path once, to classify it as non-production input.
#   - this guard script: its own docstring/logic legitimately names the path.
#
# Verified (Phase 2 certification inventory + independent spot-check reading
# of each file, not just the naming convention) as NOT the stale-feed bug,
# despite this guard's static reconstruction flagging a literal reference:
#   - p37_production_certification.py: PRIMARY_FEEDS tries api/feed.json
#     FIRST, with data/feed.json and root feed.json only as documented
#     last-resort fallbacks that are never reached in practice.
#   - commercial_quality_orchestrator.py: _FEED_PATH = _API/"feed.json"
#     where _API = _ROOT/"api" -- this guard's static reconstruction can't
#     trace that assignment, so it misreads the segment as unqualified.
#   - feed_quality_engine.py, attribution_validator.py, timestamp_validator.py,
#     deployment_convergence_validator.py: each deliberately processes
#     live/root/research as separate, transparently-labelled entries (a
#     diagnostic/repair tool over multiple files), never silently
#     substituting one for another as a single certification verdict.
#   - apex_feed_quality_v2.py: a write/upgrade utility, not wired into any
#     CI certification gate.
#   - cti_validator.py: primary verdict (mitre_attck.api_feed_*) is driven
#     entirely by api/feed.json (LIVE); data/feed.json (RESEARCH) only
#     populates a separately-labelled, non-gating comparison stat
#     (data_feed_mapped/data_feed_total), never mixed into the verdict.
# p36_production_certification.py was investigated in Phase 2: despite an
# ADR comment elsewhere suggesting it was deliberately frozen, it was
# reading data/feed.json directly with no fallback -- a genuine instance of
# the same bug, now fixed (see its own v161.3 P0 FIX comment) and is
# therefore NOT in this list -- it is protected by this guard like every
# other fixed script.
EXEMPT_FILES = {
    "p38_shared_validators.py",
    "certification_feed_guard.py",
    "p37_production_certification.py",
    "commercial_quality_orchestrator.py",
    "feed_quality_engine.py",
    "attribution_validator.py",
    "timestamp_validator.py",
    "deployment_convergence_validator.py",
    "apex_feed_quality_v2.py",
    "cti_validator.py",
}

_STALE_EXACT = {"feed.json", "data/feed.json", "./feed.json", "./data/feed.json"}
_PATH_CALL_NAMES = {"Path", "open"}
_PATH_CALL_ATTRS = {"Path"}  # e.g. pathlib.Path(...)


def _literal_segments(node: ast.AST) -> Optional[List[str]]:
    """Reconstruct string literal segments in a static `/` (pathlib) chain,
    or a single string constant. Returns None if not statically analyzable.
    Opaque (non-literal) operands contribute no segment -- this guard errs
    toward flagging an opaque prefix like `_DATA / "feed.json"`, exactly
    the shape both real defects (p33, p25) had."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _literal_segments(node.left) or []
        right = _literal_segments(node.right) or []
        if not left and not right:
            return None
        return left + right
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return None


def _is_stale_feed_chain(segments: List[str]) -> bool:
    """True if reconstructed path segments resolve to the stale root
    feed.json / data/feed.json, and not the live api/feed.json."""
    if not segments:
        return False
    flat: List[str] = []
    for s in segments:
        flat.extend(p for p in s.split("/") if p)
    if not flat or flat[-1] != "feed.json":
        return False
    return "api" not in flat


def _call_target_name(call: ast.Call) -> Optional[str]:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def scan_file(path: Path) -> List[str]:
    """Return human-readable findings for stale-feed Path()/open() calls in
    this file. Empty list = clean. Only inspects actual path-construction
    call arguments and pathlib `/` chains -- never free text."""
    try:
        tree = ast.parse(path.read_bytes(), filename=str(path))
    except (SyntaxError, ValueError):
        return []  # syntax errors are T02's job, not this guard's

    findings: List[str] = []

    for node in ast.walk(tree):
        # Case 1: a `/` chain anywhere, e.g. _ROOT / "data" / "feed.json"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            segs = _literal_segments(node)
            if segs and _is_stale_feed_chain(segs):
                findings.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                    f"static path resolves to stale feed ({'/'.join(segs)})"
                )
            continue
        # Case 2: an exact stale string passed straight to Path()/open()
        if isinstance(node, ast.Call):
            name = _call_target_name(node)
            if name not in _PATH_CALL_NAMES and name not in _PATH_CALL_ATTRS:
                continue
            for arg in node.args[:1]:  # path/filename is always the first positional arg
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value.strip() in _STALE_EXACT:
                        findings.append(
                            f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                            f"{name}({arg.value!r}) references the stale feed"
                        )

    return findings


def _candidates() -> List[Path]:
    found: dict[str, Path] = {}
    for pattern in NAME_GLOBS:
        for p in SCRIPTS_DIR.glob(pattern):
            found[p.name] = p
    for name in EXTRA_SCAN:
        p = SCRIPTS_DIR / name
        if p.exists():
            found[p.name] = p
    return sorted(found.values())


def main() -> int:
    candidates = _candidates()

    if "--list" in sys.argv[1:]:
        for p in candidates:
            print(p.relative_to(REPO_ROOT))
        return 0

    all_findings: List[str] = []
    scanned = 0
    for path in candidates:
        if path.name in EXEMPT_FILES:
            continue
        scanned += 1
        all_findings.extend(scan_file(path))

    print("=" * 70)
    print("SENTINEL APEX -- Stale-Feed Recurrence Guard")
    print("=" * 70)
    print(f"Scanned {scanned} production certification/quality/validator script(s)")

    if all_findings:
        print(f"\nFAIL: {len(all_findings)} stale-feed reference(s) found:\n")
        for f in all_findings:
            print(f"  !! {f}")
        print(
            "\nA production certification/quality script must resolve its feed via "
            "scripts/p38_shared_validators.get_certification_feed('live'), never a "
            "direct path to the stale root feed.json or data/feed.json snapshot."
        )
        return 1

    print("\nPASS: no scanned script has a direct dependency on the stale feed snapshot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
