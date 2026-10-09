#!/usr/bin/env python3
"""P0 R28: read-only forensic census of public-feed provenance.

Never creates source evidence, changes feeds, alters TLP, or grants release.
Exit 1 when any candidate fails the existing M3/M4/M8 publication mandates.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sentinel_apex_mandate_enforcer import (
    REQUIRED_PROVENANCE_FIELDS, INTERNAL_SOURCES,
    check_mandate_3, check_mandate_4, check_mandate_8,
)

def diagnose(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "INVALID_INPUT", "error": type(exc).__name__, "records": 0}
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        return {"status": "INVALID_INPUT", "error": "feed_must_be_list_of_objects", "records": 0}
    missing = collections.Counter()
    internal = []
    bad_quality = []
    samples = collections.defaultdict(list)
    for index, row in enumerate(data):
        identifier = str(row.get("id") or f"row-{index}")[:120]
        for key in REQUIRED_PROVENANCE_FIELDS:
            if row.get(key) is None or row.get(key) == "" or row.get(key) == 0:
                missing[key] += 1
                if len(samples[key]) < 5:
                    samples[key].append(identifier)
        origin = str(row.get("source") or row.get("feed_source") or row.get("source_name") or "").strip()
        if origin.upper() in {s.upper() for s in INTERNAL_SOURCES}:
            internal.append(identifier)
    m3 = check_mandate_3(data)
    m4 = check_mandate_4(data)
    m8 = check_mandate_8(data)
    bad_quality = [v.item_id for v in m8]
    return {
        "status": "BLOCKED" if (m3 or m4 or m8 or not data) else "PRECHECK_PASS_NOT_RELEASE_GO",
        "records": len(data),
        "missing_fields": dict(sorted(missing.items())),
        "sample_ids_by_missing_field": dict(sorted(samples.items())),
        "violations": {"M3": len(m3), "M4": len(m4), "M8": len(m8)},
        "internal_source_sample_ids": internal[:10],
        "quality_failure_sample_ids": bad_quality[:10],
        "limitations": "Read-only precheck. Does not prove authenticity of present fields, report deliverability, TLP authorization, or live readiness.",
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, default=Path("api/feed.json"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = diagnose(args.feed)
    payload = json.dumps(result, indent=2, sort_keys=True)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if result["status"] == "PRECHECK_PASS_NOT_RELEASE_GO" else 1

if __name__ == "__main__":
    raise SystemExit(main())
