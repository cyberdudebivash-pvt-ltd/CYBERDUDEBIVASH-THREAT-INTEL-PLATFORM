#!/usr/bin/env python3
"""
scripts/report_engine_consistency_gate.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Report Engine Consistency Gate v1.0
========================================================================
Observability gate for the multi-generator report pipeline. Three
independent components can write report HTML for the same report_id:
  - generate_intel_reports.py  (runs first, subprocess of run_pipeline.py)
  - report_generator.py        (runs second, Stage 3.2 -- usually a no-op
                                 due to its own skip_existing/God-Mode gate)
  - generateIntelReport()       (Cloudflare Worker, fires on R2 cache-miss)

Each now stamps a one-line HTML comment identifying itself:
  <!-- CDB-REPORT-ENGINE: <engine-name> v<version> -->

This gate does NOT decide which engine should win -- that is a pending
architectural decision (see the Report Pipeline Architecture Audit).
It only makes the current, previously-invisible behaviour observable:
  1. What engine distribution exists across all reports right now.
  2. Whether any report_id's owning engine CHANGED since the last run --
     the concrete, measurable signature of two generators fighting over
     the same key.

ADDITIVE ONLY -- reads existing manifests and report files, writes only
its own ledger (data/quality/report_engine_ledger.json). Modifies no
existing report, script, or workflow behaviour.

Exit 0 always, unless --enforce is passed (opt-in; not used in CI yet --
this is a Day-1 observability check pending a bake-in period before it
is trusted to block a release).

Usage:
  python3 scripts/report_engine_consistency_gate.py
  python3 scripts/report_engine_consistency_gate.py --manifest api/feed.json
  python3 scripts/report_engine_consistency_gate.py --enforce
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

REPO_ROOT     = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_FEEDS = [
    "data/stix/feed_manifest.json",
    "api/feed.json",
]
LEDGER_PATH   = REPO_ROOT / "data" / "quality" / "report_engine_ledger.json"

_MARKER_RE = re.compile(rb"CDB-REPORT-ENGINE:\s*([^\s]+)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_items(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, list):
        return raw
    for key in ("advisories", "reports", "items"):
        if key in raw and isinstance(raw[key], list):
            return raw[key]
    return []


def _engine_name(marker: str) -> str:
    """Strip a trailing version token (e.g. 'v184.0') so version bumps of
    the SAME engine are not misread as an ownership change."""
    return re.sub(r"v[\d.]+x?$", "", marker).rstrip("-")


def _extract_marker(local_path: pathlib.Path) -> str | None:
    try:
        with open(local_path, "rb") as fh:
            head = fh.read(512)
    except Exception:
        return None
    m = _MARKER_RE.search(head)
    return m.group(1).decode("utf-8", errors="replace") if m else None


def _load_ledger() -> dict:
    if LEDGER_PATH.exists():
        try:
            return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")


def run(feed_paths: list[pathlib.Path]) -> dict:
    ledger = _load_ledger()
    new_ledger: dict = {}
    engine_counts: dict[str, int] = {}
    unmarked = 0
    ownership_changes: list[str] = []
    checked = 0

    seen_ids: set[str] = set()
    for feed in feed_paths:
        for item in _load_items(feed):
            report_id = item.get("id") or item.get("stix_id") or ""
            ru = item.get("report_url", "")
            if not report_id or not ru or ru.startswith("http") or not ru.startswith("/reports/"):
                continue
            if report_id in seen_ids:
                continue  # same item present in more than one feed -- count once
            seen_ids.add(report_id)

            local = REPO_ROOT / ru.lstrip("/")
            if not local.exists():
                continue  # existence is report_existence_validator.py's job, not ours
            checked += 1

            marker = _extract_marker(local)
            if marker is None:
                unmarked += 1
                continue

            engine = _engine_name(marker)
            engine_counts[engine] = engine_counts.get(engine, 0) + 1
            new_ledger[report_id] = {"engine": engine, "marker": marker, "last_seen": _now()}

            prev = ledger.get(report_id)
            if prev and prev.get("engine") and prev["engine"] != engine:
                ownership_changes.append(
                    f"[OWNERSHIP_CHANGE] id={report_id[:40]} url={ru} "
                    f"{prev['engine']!r} -> {engine!r}"
                )

    _save_ledger(new_ledger)
    return {
        "checked": checked,
        "unmarked": unmarked,
        "engine_counts": engine_counts,
        "ownership_changes": ownership_changes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="Feed JSON path (default: auto-detect both known feeds)")
    parser.add_argument("--enforce", action="store_true",
                         help="Exit 1 on any detected ownership change (opt-in; not used in CI yet)")
    args = parser.parse_args()

    print("=" * 70)
    print("SENTINEL APEX -- Report Engine Consistency Gate v1.0 (observability)")
    print("=" * 70)

    feeds = [pathlib.Path(args.manifest)] if args.manifest else [REPO_ROOT / f for f in DEFAULT_FEEDS]
    feeds = [f for f in feeds if f.exists()]
    if not feeds:
        print("WARN: No feed manifest files found -- skipping")
        return 0

    result = run(feeds)

    print(f"\nReports checked: {result['checked']}")
    print(f"Unmarked (pre-dates engine markers): {result['unmarked']}")
    print("\nEngine distribution:")
    for engine, count in sorted(result["engine_counts"].items(), key=lambda kv: -kv[1]):
        print(f"  {engine:40s} {count}")

    changes = result["ownership_changes"]
    if changes:
        print(f"\n{len(changes)} ownership change(s) since last recorded run:")
        for c in changes[:20]:
            print(f"  {c}")
        if len(changes) > 20:
            print(f"  ... and {len(changes) - 20} more")
    else:
        print("\nNo ownership changes since last recorded run.")

    print()
    if changes and args.enforce:
        print(f"RESULT: FAIL -- {len(changes)} report(s) changed owning engine (--enforce active)")
        return 1
    print("RESULT: OK (observability only -- pass --enforce to block on ownership changes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
