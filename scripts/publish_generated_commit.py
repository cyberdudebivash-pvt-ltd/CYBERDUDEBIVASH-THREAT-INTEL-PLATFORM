#!/usr/bin/env python3
"""Preserve a workflow-generated commit on a review branch and open its PR."""

from __future__ import annotations

import json
import os

from safe_git_commit import publish_metadata_pr


def publish() -> dict:
    """Publish the current commit through the repository's protected-main path."""
    token = os.environ.get("GH_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repository:
        raise RuntimeError(
            "Generated commit publication requires GH_TOKEN and GITHUB_REPOSITORY"
        )

    state = publish_metadata_pr(token, repository)
    if state.get("state") != "PERSISTED_REVIEW_PENDING":
        raise RuntimeError("Generated commit was not preserved in a reviewable PR")
    print(
        json.dumps(
            {
                "state": state["state"],
                "branch": state["branch"],
                "commit_sha": state["commit_sha"],
                "pr_number": state["pr_number"],
                "main_updated": False,
            },
            sort_keys=True,
        )
    )
    return state


if __name__ == "__main__":
    publish()

