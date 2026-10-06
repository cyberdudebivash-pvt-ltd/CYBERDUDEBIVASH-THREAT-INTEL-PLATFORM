#!/usr/bin/env python3
"""
scripts/final_feed_dedup_guard.py
SENTINEL APEX v185.2 -- STAGE 4.06 Final Feed Dedup Guard

ROOT CAUSE (Fortune-500 audit, Phase 1): run_pipeline.py's own dedup gates
(Phase 4 and the v185.2 final-pre-write gate added in PR #249) both call
enforce_manifest_uniqueness() correctly, but they run INSIDE the single
"Stage 1-3 - Master Pipeline Orchestrator" CI step. Per STAGE 4.1's own
documented root cause (this same workflow file), dozens of separate CI
steps between Stage 1-3 and STAGE 4 (Git Sync) independently read-modify-
write api/feed.json -- e.g. STAGE 3.1.13 Multi-Source Intelligence
Collector, which can re-ingest an already-present article under a fresh
item ID. None of those intervening steps re-run the dedup gate. Confirmed
live: commit 955cf6e86 (a normal, non-conflict pipeline run, produced
entirely by this workflow) already contained 2 source_url duplicates that
regression_tests.py's T22 correctly flagged -- but STAGE 5.6 (Regression
Test Suite) runs AFTER STAGE 4 (Git Sync) already committed and pushed,
so the failure was purely informational and never blocked the bad commit.

FIX: run the same idempotent enforce_manifest_uniqueness() one more time,
in a dedicated stage positioned immediately before STAGE 4 -- the latest
possible point before the commit that actually reaches origin/main -- so
regardless of which of the ~40 intervening stages reintroduced a
duplicate, it is caught before the commit, not just reported after.

Exit code is always 0 (non-blocking monitor + guard, matches STAGE 4.05's
convention) -- this stage FIXES the file in place; it does not gate the
pipeline. A future hard-fail gate could be layered on top of this if the
correctness bar needs to be raised further, but that's a separate change.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from intel_dedup_engine import enforce_manifest_uniqueness  # noqa: E402

TARGET_PATHS = ["api/feed.json", "feed.json"]


def _dedup_one(rel_path: str) -> None:
    path = REPO_ROOT / rel_path
    if not path.exists():
        print(f"[STAGE 4.06] {rel_path}: not found, skipping")
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8").rstrip("\x00"))
    except Exception as exc:
        print(f"[STAGE 4.06] {rel_path}: could not parse ({exc}), skipping")
        return

    items = raw if isinstance(raw, list) else raw.get("items", raw.get("advisories", []))
    unique, removed = enforce_manifest_uniqueness(items)

    if not removed:
        print(f"[STAGE 4.06] {rel_path}: {len(items)} items, no duplicates -- clean")
        return

    if isinstance(raw, list):
        out = unique
    else:
        if "advisories" in raw:
            raw["advisories"] = unique
        elif "items" in raw:
            raw["items"] = unique
        out = raw

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)
    print(
        f"[STAGE 4.06] {rel_path}: {len(items)} -> {len(unique)} items, "
        f"{removed} duplicate(s) reintroduced by an earlier CI stage -- removed before commit"
    )


def main() -> int:
    for rel in TARGET_PATHS:
        try:
            _dedup_one(rel)
        except Exception as exc:
            print(f"[STAGE 4.06] {rel}: guard failed (non-fatal): {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
