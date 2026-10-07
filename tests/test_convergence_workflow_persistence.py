"""Regression tests for convergence workflow generated-artifact persistence."""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import publish_generated_commit as publisher  # noqa: E402


class PublishGeneratedCommitTests(unittest.TestCase):
    def test_delegates_to_protected_main_publisher(self):
        state = {
            "state": "PERSISTED_REVIEW_PENDING",
            "branch": "sentinel-generated/run-37566281335-1",
            "commit_sha": "a" * 40,
            "pr_number": 703,
            "main_updated": False,
        }
        environment = {
            "GH_TOKEN": "offline-token",
            "GITHUB_REPOSITORY": "owner/repo",
        }
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
            publisher, "publish_metadata_pr", return_value=state
        ) as publish:
            self.assertEqual(publisher.publish(), state)
        publish.assert_called_once_with("offline-token", "owner/repo")

    def test_missing_identity_fails_closed(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "requires GH_TOKEN"):
                publisher.publish()

    def test_non_reviewable_state_fails_closed(self):
        state = {
            "state": "PERSISTED_BRANCH_ONLY",
            "branch": "sentinel-generated/run-1-1",
            "commit_sha": "b" * 40,
            "main_updated": False,
        }
        environment = {
            "GH_TOKEN": "offline-token",
            "GITHUB_REPOSITORY": "owner/repo",
        }
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(
            publisher, "publish_metadata_pr", return_value=state
        ):
            with self.assertRaisesRegex(RuntimeError, "reviewable PR"):
                publisher.publish()


class ConvergenceWorkflowContractTests(unittest.TestCase):
    def test_workflow_never_pushes_directly_to_protected_main(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "convergence.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("git push origin main", workflow)
        self.assertNotIn("merge origin/main -X ours", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertIn("python scripts/publish_generated_commit.py", workflow)


WORKFLOWS = {
    "bughunter-resilient.yml": "data/bughunter/bughunter_output.json",
    "omnishield.yml": "data/omnishield/omnishield_report.json",
}


def _git(root, *args):
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _fixture(tmp_path, workflow, *, changed=True, branch_rejected=False):
    """Use real Git and the real publisher; replace only GitHub HTTP, offline."""
    root = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    root.mkdir()
    _git(tmp_path, "init", "--bare", str(remote))
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Offline fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    scripts = root / "scripts"
    scripts.mkdir()
    for name in ("publish_generated_commit.py", "safe_git_commit.py"):
        shutil.copyfile(REPO_ROOT / "scripts" / name, scripts / name)
    artifact = root / WORKFLOWS[workflow]
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"generation": 1}\n', encoding="utf-8")
    (root / "unrelated.txt").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "offline baseline")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "main")
    # The workflow keeps its real token URL; Git rewrites this exact offline
    # fixture URL to a local bare remote. No external Git request is possible.
    _git(root, "config", f"url.{remote}.insteadOf",
         "https://x-access-token:offline-token@github.com/offline/repo")
    hook = remote / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n" + ("exit 1\n" if branch_rejected else
        'while read old new ref; do\n'
        '  [ "$ref" != "refs/heads/main" ] || exit 1\n'
        'done\n'), encoding="utf-8"
    )
    hook.chmod(0o755)
    mock_dir = tmp_path / "offline_http"
    mock_dir.mkdir()
    (mock_dir / "sitecustomize.py").write_text('''
import io, json, os, urllib.error, urllib.request
from pathlib import Path

def offline_urlopen(req, **kwargs):
    assert req.full_url.startswith("https://api.github.com/repos/offline/repo/pulls")
    with open(os.environ["OFFLINE_API_CALLS"], "a") as log:
        log.write(json.dumps({"method": req.method,
            "payload": json.loads(req.data) if req.data else None}) + "\\n")
    if req.method == "GET":
        return io.BytesIO(b"[]")
    assert req.method == "POST"
    if os.environ.get("OFFLINE_PR_BLOCKED") == "1":
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {},
            io.BytesIO(b'{"message":"GitHub Actions is not permitted to create or approve pull requests."}'))
    return io.BytesIO(b'{"number":705}')

urllib.request.urlopen = offline_urlopen
''', encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Also bound the unchanged-main negative control's legacy retry sleeps.
    sleep = bin_dir / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sleep.chmod(0o755)
    env = dict(os.environ, GH_TOKEN="offline-token", GITHUB_REPOSITORY="offline/repo",
               GITHUB_RUN_ID="42", GITHUB_RUN_ATTEMPT="1",
               PYTHONPATH=str(mock_dir), OFFLINE_API_CALLS=str(tmp_path / "api.jsonl"),
               GITHUB_STEP_SUMMARY=str(tmp_path / "summary.md"),
               PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
    if changed:
        artifact.write_text('{"generation": 2}\n', encoding="utf-8")
        (root / "unrelated.txt").write_text("must remain uncommitted\n", encoding="utf-8")
        (root / "untracked.txt").write_text("must remain uncommitted\n", encoding="utf-8")
    return root, remote, env, base, artifact


def _run_step(root, workflow, env):
    definition = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    )
    job = next(iter(definition["jobs"].values()))
    steps = [s for s in job["steps"] if "GH_TOKEN" in s.get("env", {})]
    assert len(steps) == 1
    # Render the one legacy expression for the original-source negative control.
    body = steps[0]["run"].replace("${{ github.repository }}", "offline/repo")
    return subprocess.run(["bash", "-e", "-o", "pipefail", "-c", body], cwd=root,
                          env=env, capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_generated_workflow_preserves_exact_scoped_commit_for_review(tmp_path, workflow):
    root, remote, env, base, _ = _fixture(tmp_path, workflow)
    result = _run_step(root, workflow, env)
    assert result.returncode == 0, result.stderr
    state = json.loads((root / "data/health/git_sync_state.json").read_text())
    head = _git(root, "rev-parse", "HEAD")
    assert state["state"] == "PERSISTED_REVIEW_PENDING"
    assert state["commit_sha"] == head
    assert state["main_updated"] is False
    assert _git(remote, "rev-parse", "refs/heads/sentinel-generated/run-42-1") == head
    assert _git(remote, "rev-parse", "refs/heads/main") == base
    assert _git(root, "diff", "--name-only", base, head) == WORKFLOWS[workflow]
    calls = [json.loads(x) for x in Path(env["OFFLINE_API_CALLS"]).read_text().splitlines()]
    assert calls[-1]["payload"]["draft"] is True
    assert calls[-1]["payload"]["head"] == state["branch"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_generated_workflow_pr_policy_rejection_is_nonzero_and_recoverable(tmp_path, workflow):
    root, remote, env, base, _ = _fixture(tmp_path, workflow)
    env["OFFLINE_PR_BLOCKED"] = "1"
    result = _run_step(root, workflow, env)
    assert result.returncode != 0, result.stdout
    assert "ACTIONS_PR_CREATION_DISABLED" in result.stderr
    state = json.loads((root / "data/health/git_sync_state.json").read_text())
    assert state["state"] == "PERSISTED_PR_BLOCKED"
    assert state["main_updated"] is False
    assert state["commit_sha"] == _git(root, "rev-parse", "HEAD")
    assert _git(remote, "rev-parse", "refs/heads/sentinel-generated/run-42-1") == state["commit_sha"]
    assert _git(remote, "rev-parse", "refs/heads/main") == base


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_generated_workflow_branch_rejection_never_claims_persistence(tmp_path, workflow):
    root, remote, env, base, _ = _fixture(tmp_path, workflow, branch_rejected=True)
    result = _run_step(root, workflow, env)
    assert result.returncode != 0, result.stdout
    assert "branch push rejected" in result.stderr
    assert not (root / "data/health/git_sync_state.json").exists()
    assert not Path(env["OFFLINE_API_CALLS"]).exists()
    assert _git(remote, "rev-parse", "refs/heads/main") == base


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_generated_workflow_no_changes_is_success_without_publication(tmp_path, workflow):
    root, remote, env, base, _ = _fixture(tmp_path, workflow, changed=False)
    result = _run_step(root, workflow, env)
    assert result.returncode == 0, result.stderr
    assert _git(root, "rev-parse", "HEAD") == base
    assert _git(remote, "rev-parse", "refs/heads/main") == base
    assert not Path(env["OFFLINE_API_CALLS"]).exists()


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_generated_workflow_missing_output_never_publishes_deletion(tmp_path, workflow):
    root, remote, env, base, artifact = _fixture(tmp_path, workflow)
    artifact.unlink()
    result = _run_step(root, workflow, env)
    assert result.returncode != 0
    assert _git(root, "rev-parse", "HEAD") == base
    assert _git(remote, "rev-parse", "refs/heads/main") == base
    assert not Path(env["OFFLINE_API_CALLS"]).exists()


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_generated_workflow_commit_rejection_never_calls_publisher(tmp_path, workflow):
    root, remote, env, base, _ = _fixture(tmp_path, workflow)
    hook = root / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    result = _run_step(root, workflow, env)
    assert result.returncode != 0
    assert _git(root, "rev-parse", "HEAD") == base
    assert _git(remote, "rev-parse", "refs/heads/main") == base
    assert not Path(env["OFFLINE_API_CALLS"]).exists()


def test_generated_workflows_never_bypass_main_and_are_selected_by_ci():
    for workflow in WORKFLOWS:
        source = (REPO_ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
        assert "git push origin main" not in source
        assert "merge origin/main -X ours" not in source
        assert "git rebase" not in source
        assert "Push deferred" not in source
        assert "pull-requests: write" in source
        assert "python scripts/publish_generated_commit.py" in source
    gate = (REPO_ROOT / ".github/workflows/intel-gateway-regression-gate.yml").read_text(encoding="utf-8")
    assert "tests/test_convergence_workflow_persistence.py" in gate


if __name__ == "__main__":
    unittest.main()
