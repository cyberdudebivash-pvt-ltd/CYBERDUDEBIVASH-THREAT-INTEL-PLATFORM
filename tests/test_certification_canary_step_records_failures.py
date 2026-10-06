"""F28 (2026-10-02): the certification's canary step records why a canary failed.

commercial-customer-ops-certification.yml (Phases 8-15) runs its step under
`bash -e`. Its canary() helper captured the canary's exit code with
`out=$(node ...); rc=$?`. Under -e, a non-zero exit aborts the script at that
assignment, so the FAIL / OPERATOR_WEBHOOK_SINK_REQUIRED record and the
summary never ran. Runs 37006162439 and 37006645392 ended with exit code 1
and no reason; the PRO canary had refused a STALE feed.

These tests run the step's own record() and canary() functions under
`bash -e` with a stub `node` that answers like the canary.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "commercial-customer-ops-certification.yml"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="the step under test uses jq")


def _helpers() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    runs = [
        step["run"]
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "canary() {" in str(step.get("run", ""))
    ]
    assert len(runs) == 1, "exactly one step defines canary()"
    run = runs[0]
    start = run.index("record() {")
    end = run.index("PRO=$(mk pro PRO)")
    return run[start:end]


def _run(tmp_path: Path, stub_rc: int, stub_json: str) -> subprocess.CompletedProcess:
    stub = tmp_path / "node"
    stub.write_text(f"#!/usr/bin/env bash\necho '{stub_json}'\nexit {stub_rc}\n", encoding="utf-8")
    stub.chmod(0o755)
    script = tmp_path / "harness.sh"
    script.write_text(
        "RESULTS=(); FAIL=0; BLOCKED=0\n"
        + _helpers()
        + '\ncanary "PRO canary" pro\n'
        + 'echo "CONTINUED FAIL=$FAIL BLOCKED=$BLOCKED"\n',
        encoding="utf-8",
    )
    env = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    return subprocess.run(["bash", "-e", str(script)], capture_output=True, text=True, env=env, timeout=60)


def test_a_failing_canary_is_recorded_with_its_reason_and_the_step_continues(tmp_path):
    proc = _run(tmp_path, 1, '{"result":"NO_GO_FEED_NOT_FRESH","status":200,"freshness_status":"STALE"}')
    assert "PRO canary: FAIL (NO_GO_FEED_NOT_FRESH" in proc.stdout, proc.stdout + proc.stderr
    assert "CONTINUED FAIL=1 BLOCKED=0" in proc.stdout, proc.stdout + proc.stderr


def test_a_blocked_canary_is_recorded_as_blocked(tmp_path):
    proc = _run(tmp_path, 11, '{"result":"OPERATOR_WEBHOOK_SINK_REQUIRED"}')
    assert "PRO canary: OPERATOR_WEBHOOK_SINK_REQUIRED" in proc.stdout, proc.stdout + proc.stderr
    assert "CONTINUED FAIL=0 BLOCKED=1" in proc.stdout, proc.stdout + proc.stderr


def test_a_passing_canary_is_recorded_as_pass(tmp_path):
    proc = _run(tmp_path, 0, '{"result":"PASS","evidence":{"mode":"PRO","result":"PASS","checks":13}}')
    assert "PRO canary: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "CONTINUED FAIL=0 BLOCKED=0" in proc.stdout, proc.stdout + proc.stderr
