#!/usr/bin/env python3
"""
scripts/validate_intelligence_plane_output.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- P0 RUNTIME INTELLIGENCE STATE RECOVERY

Fail-closed gate for NEXUS/CORTEX/QUANTUM/SOVEREIGN/GENESIS's aggregate
output files, run BEFORE the R2 upload step in genesis-powerhouse.yml and
sovereign-platform.yml.

Root cause this closes: each engine step now runs with `continue-on-error:
true` (an engine crashing must not cascade and skip its siblings -- see
ai-predictions.yml's already-approved precedent for this exact pattern).
That alone would make a genuinely-broken engine's stale, hours-old
aggregate file look identical to a fresh one to the next step -- silently
uploading old data to R2 under a "the job succeeded" banner is the exact
defect class this mission exists to eliminate ("green workflow != persisted
state" generalizes to "engine step failed != no output was produced").

This gate is deliberately generic across all 5 engines rather than five
per-engine schema validators: every one of them unconditionally stamps
`generated_at` at the top of execute_full_cycle(), before any of that
engine's own internal try/except sub-blocks run (confirmed by reading each
orchestrator directly) -- so "generated_at is fresh, within this job's own
runtime window" is a precise, reusable proxy for "the orchestrator actually
executed this run," without needing to hand-encode each engine's very
different internal aggregate shape here as a second, competing schema
authority (same reasoning r2_state_sync.py's _is_recognized_state_shape()
already documents for why it stays shape-agnostic).

Usage:
  python3 scripts/validate_intelligence_plane_output.py \\
      --file data/nexus/nexus_output.json --engine NEXUS

Exit 0: PASS. Exit 1: FAIL (missing, malformed, or stale beyond
--max-age-seconds) -- the workflow step calling this must NOT be
continue-on-error, matching the mission's fail-closed requirement.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

DEFAULT_MAX_AGE_SECONDS = 1200  # 20 min -- generous vs. any single engine's
                                  # realistic runtime, tight enough to catch
                                  # a genuinely stale/untouched leftover file.


def _parse_iso8601(value: str) -> datetime:
    # Python's fromisoformat() predates "Z" support in 3.10; every engine
    # here emits Z via datetime.now(timezone.utc).isoformat(), which is
    # actually "+00:00" already (isoformat() never emits "Z" itself) -- kept
    # as a defensive normalization in case a future engine change emits "Z"
    # literally, matching the same .replace("Z", "+00:00") idiom already
    # used throughout the v40/v41 engines themselves.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate(file_path: str, engine: str, max_age_seconds: int) -> tuple[bool, str]:
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return False, f"{engine}: MISSING -- {file_path} does not exist. Engine step produced no output this run."
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, f"{engine}: MALFORMED -- {file_path} is not valid JSON ({exc})."

    if not isinstance(data, dict):
        return False, f"{engine}: WRONG SHAPE -- {file_path} top-level value is a {type(data).__name__}, not an object."

    generated_at = data.get("generated_at")
    if not generated_at:
        return False, f"{engine}: NO TIMESTAMP -- {file_path} has no 'generated_at' field."

    try:
        ts = _parse_iso8601(generated_at)
    except (ValueError, AttributeError) as exc:
        return False, f"{engine}: BAD TIMESTAMP -- {file_path}'s generated_at={generated_at!r} does not parse ({exc})."

    now = datetime.now(timezone.utc)
    age_seconds = (now - ts).total_seconds()
    if age_seconds < 0:
        # A future timestamp is exactly as suspicious as a stale one -- never
        # silently accept it as "fresh enough."
        return False, f"{engine}: FUTURE TIMESTAMP -- {file_path}'s generated_at={generated_at!r} is {-age_seconds:.0f}s in the future."
    if age_seconds > max_age_seconds:
        return False, (
            f"{engine}: STALE -- {file_path}'s generated_at={generated_at!r} is "
            f"{age_seconds:.0f}s old (limit {max_age_seconds}s). The engine step "
            f"likely crashed before writing output this run; this is a leftover "
            f"from a previous run and must not be re-persisted as if it were fresh."
        )

    return True, f"{engine}: OK -- {file_path} generated {age_seconds:.0f}s ago."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Path to the engine's aggregate output JSON file.")
    parser.add_argument("--engine", required=True, help="Engine name, for log messages only (e.g. NEXUS).")
    parser.add_argument(
        "--max-age-seconds", type=int, default=DEFAULT_MAX_AGE_SECONDS,
        help=f"Maximum acceptable age of generated_at (default: {DEFAULT_MAX_AGE_SECONDS}s).",
    )
    args = parser.parse_args()

    ok, message = validate(args.file, args.engine, args.max_age_seconds)
    print(("[OK] " if ok else "[FAIL] ") + message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
