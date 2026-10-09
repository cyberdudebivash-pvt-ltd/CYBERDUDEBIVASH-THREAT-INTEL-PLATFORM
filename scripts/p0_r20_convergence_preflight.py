#!/usr/bin/env python3
"""R20 read-only release-state accounting when mandatory publisher stages fail.

Executed only in the blocked branch of the GitHub Actions convergence step.
Produces a truthful 0-probe diagnostic, never a deployment certification.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import tempfile


def build_blocked_verdict(pipeline: str, apex: str, regression: str) -> dict:
    stages = {
        "pipeline_orchestrator": pipeline,
        "public_feed_enrichment": apex,
        "mandatory_regression_suite": regression,
    }
    if all(status == "success" for status in stages.values()):
        raise ValueError("All mandatory stages passed; no blocked verdict can be fabricated")
    return {
        "schema_version": "p0-r20-upstream-release-hold-v1",
        "classification": "UPSTREAM_BLOCKED",
        "confidence_score": 0,
        "convergence_achieved": False,
        "release_go": False,
        "network_probes_attempted": 0,
        "verification_performed": False,
        "reason": "MANDATORY_UPSTREAM_RELEASE_GATES_NOT_SUCCESSFUL",
        "mandatory_stage_outcomes": stages,
        "signals": {},
    }


def write_verdict(output: pathlib.Path, verdict: dict) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".r20-blocked-", suffix=".json", dir=str(output.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(verdict, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--apex", required=True)
    parser.add_argument("--regression", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        verdict = build_blocked_verdict(args.pipeline, args.apex, args.regression)
    except ValueError as exc:
        parser.error(str(exc))
    write_verdict(args.output, verdict)
    print("[P0 R20] UPSTREAM_BLOCKED: 0 deployment network requests; release NO-GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
