"""Required-check readiness for main (2026-10-02).

Ruleset 21556637 protects main with a pull-request rule but no required
status checks, so a pull request can merge while a check is red (#641 did).
The owner asked for two stable required checks: the SAST gate and the gateway
regression gate. A repository admin adds them to the ruleset; these tests keep
both workflows fit to be required:

  * each check reports on every pull request to main (a path filter that
    skips a required check leaves the pull request waiting forever);
  * the check names a ruleset pins stay stable;
  * no job-level `if:` can skip a required job (a skipped check satisfies a
    requirement without running anything), except the SAST gate's
    `always()`, which makes it report even when a scanner fails.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"

REGRESSION_CHECKS = {
    "gateway-tests": "workers/intel-gateway -- full unit suite (1121 tests)",
    "python-tests": "scripts/ + tests/ -- Python unit and regression suites",
}
SAST_CHECK = ("sast-gate", "SAST Gate (required)")


def _load(name):
    workflow = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return workflow, workflow.get("on") or workflow.get(True)


def test_regression_gate_reports_on_every_pull_request_to_main():
    _, on = _load("intel-gateway-regression-gate.yml")
    pull_request = on["pull_request"]
    assert pull_request.get("branches") == ["main"]
    assert "paths" not in pull_request and "paths-ignore" not in pull_request
    assert "types" not in pull_request, "default activity types: opened, synchronize, reopened"


def test_regression_gate_check_names_are_stable_and_never_skipped():
    workflow, _ = _load("intel-gateway-regression-gate.yml")
    for job_id, check_name in REGRESSION_CHECKS.items():
        job = workflow["jobs"][job_id]
        assert job["name"] == check_name
        assert "if" not in job, f"{job_id} must not be skippable"


def test_sast_gate_reports_on_every_pull_request_to_main():
    workflow, on = _load("sast-security-scan.yml")
    pull_request = on["pull_request"]
    assert "main" in pull_request.get("branches", [])
    assert "paths" not in pull_request and "paths-ignore" not in pull_request
    job_id, check_name = SAST_CHECK
    job = workflow["jobs"][job_id]
    assert job["name"] == check_name
    assert job.get("if") == "always()", "the gate reports even when a scanner job fails"
