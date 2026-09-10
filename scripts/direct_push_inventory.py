#!/usr/bin/env python3
"""
scripts/direct_push_inventory.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- P0 RUNTIME INTELLIGENCE STATE RECOVERY

Repository-wide OBSERVABILITY inventory (not a fix, not a blocking gate) of
every .github/workflows/*.yml still containing `git push origin main` for
its own runtime data, per this mission's explicit Section 17/18 requirement:
"add/extend a repository-wide observability test inventorying remaining
direct-runtime-pushes after this fix, without silently claiming the
repo-wide class is solved."

Context (issue #274): ~34 workflows were identified with this historical
direct-push pattern. This mission fixed exactly 2 of them
(genesis-powerhouse.yml, sovereign-platform.yml) -- scoped deliberately, per
the mission's own explicit "DO NOT EXPAND TO ALL 34 WORKFLOWS" /
"one production failure class per PR" instruction. Every other workflow
using this pattern is unchanged by this mission and remains exactly as
fragile to main's branch ruleset as before -- this script's only job is
making that remaining count visible and trackable, not closing it.

Usage:
  python3 scripts/direct_push_inventory.py

Always exits 0 (observability, not a gate) and writes
data/quality/direct_push_inventory.json.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import datetime, timezone

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
REPORT_PATH = REPO_ROOT / "data" / "quality" / "direct_push_inventory.json"

# Workflows this mission migrated off direct git push onto R2. Kept as an
# explicit list (not inferred) so the report is honest about exactly what
# changed, rather than a diff against a prior report this script doesn't
# have access to.
MIGRATED_BY_THIS_MISSION = frozenset({
    "genesis-powerhouse.yml",
    "sovereign-platform.yml",
})

_PUSH_RE = re.compile(r"git push origin (?:main|HEAD)\b")


def _all_run_bodies(doc: dict) -> str:
    """Every step's `run:` value across every job, concatenated. Scans only
    actual executable step bodies -- not YAML comments (stripped away by
    yaml.safe_load), which several already-migrated workflows deliberately
    quote the old, removed `git push origin main` pattern in for historical
    context (e.g. ai-predictions.yml's own header comment). A raw-text
    search over the file would false-positive on those comments and
    undercount how many workflows have actually been fixed."""
    parts = []
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            run = step.get("run")
            if run:
                parts.append(run)
    return "\n".join(parts)


def scan() -> dict:
    findings = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        run_bodies = _all_run_bodies(doc)
        matches = _PUSH_RE.findall(run_bodies)
        if matches:
            findings.append({
                "workflow": path.name,
                "push_call_count": len(matches),
                "migrated_by_p0_runtime_intelligence_mission": path.name in MIGRATED_BY_THIS_MISSION,
            })

    return {
        "script": "direct_push_inventory",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_workflows_scanned": len(list(WORKFLOWS_DIR.glob("*.yml"))),
        "workflows_with_direct_runtime_push": len(findings),
        "migrated_by_this_mission": sorted(MIGRATED_BY_THIS_MISSION),
        "findings": findings,
        "note": (
            "This is an OBSERVABILITY inventory, not a completeness gate. "
            "A nonzero workflows_with_direct_runtime_push count is EXPECTED "
            "and does not indicate a regression -- this mission (P0 RUNTIME "
            "INTELLIGENCE STATE RECOVERY) deliberately scoped its fix to "
            "exactly the 2 workflows listed in migrated_by_this_mission. "
            "The remaining count is tracked here for a future, separately "
            "scoped migration (see issue #274's ~34-workflow historical "
            "count) -- not claimed as solved by this report."
        ),
    }


def main() -> int:
    report = scan()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REPORT_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    tmp.replace(REPORT_PATH)

    print(f"Scanned {report['total_workflows_scanned']} workflows.")
    print(f"{report['workflows_with_direct_runtime_push']} still use direct git push for runtime state.")
    print(f"Migrated by this mission: {', '.join(report['migrated_by_this_mission'])}")
    print(f"Report: {REPORT_PATH}")
    return 0  # observability only -- never blocks CI


if __name__ == "__main__":
    sys.exit(main())
