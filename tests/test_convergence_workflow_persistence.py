"""Regression tests for convergence workflow generated-artifact persistence."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
