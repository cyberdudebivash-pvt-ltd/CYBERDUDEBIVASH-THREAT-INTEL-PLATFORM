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
    allowed = {"PERSISTED_REVIEW_PENDING", "PERSISTED_REVIEW_BLOCKED"}
    if state.get("state") not in allowed or state.get("remote_verified") is not True:
        raise RuntimeError("Generated commit was not remotely verified on its protected review branch")
    payload = {
        "state": state["state"],
        "branch": state["branch"],
        "commit_sha": state["commit_sha"],
        "main_updated": False,
        "remote_verified": True,
        "review_required": True,
    }
    if state.get("pr_number") is not None:
        payload["pr_number"] = state["pr_number"]
    if state.get("reason"):
        payload["reason"] = state["reason"]
    print(json.dumps(payload, sort_keys=True))
    return state


if __name__ == "__main__":
    publish()

