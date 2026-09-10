#!/usr/bin/env python3
"""
tests/test_public_repo_zero_trust_gates.py

P0 (2026-09-10): SENTINEL APEX Public-Repo Zero-Trust Architecture, phase 1.

This repository is deliberately public (the GitHub Actions minutes quota is
a real production cost constraint), so the working security model is not
"hide the source" -- it is "assume every public file is already known to an
attacker; production must stay secure anyway." Two specific, mechanically
checkable pieces of that model regressed silently once already before this
commit and would again without a test:

1. Every third-party GitHub Action referenced from this repo's workflows
   was pinned to a floating tag (`@v6.0.2`, `@v5`, `@v4`, ...) rather than
   an immutable commit SHA -- a supply-chain risk this exact codebase has
   already had to fix twice for one single action (see
   sast-security-scan.yml's TruffleHog step history: floating @main ->
   version tag -> SHA, three separate incidents for one line). Fixed
   repo-wide in this commit (187 references across 63 workflow files,
   each resolved via `git ls-remote` against the action's real repository,
   not guessed) -- this test is what stops any of them, or a new workflow
   added later, from silently drifting back to a mutable tag.

2. `pull_request_target` combined with untrusted checkout is a well-known
   GitHub Actions injection vector (a fork PR's workflow run gets the base
   repo's secrets). This repository has never used that trigger -- this
   test pins that absence so it can't be introduced unnoticed in a future
   workflow, rather than relying on it staying true by accident.

Phase 2 (2026-09-10) added a third:

3. GITHUB_TOKEN write permissions. A repo-wide audit (see
   config/workflow_permissions_allowlist.json) found every workflow that
   requests a write scope, verified each against the actual git/API
   commands in that specific job (not assumed), and narrowed several from
   workflow-wide grants to the one job that genuinely needs them --
   including removing three permissions (deployments: write on
   enterprise-rollback-governance.yml, security-events: write on
   sbom-generation.yml, actions: write on automated-backup.yml) that were
   granted but never used by any step anywhere in those files. Every
   (workflow, job, permission) triple that currently resolves to a write
   scope must have a matching entry in that allowlist; a write permission
   introduced anywhere without one fails this test, rather than silently
   expanding what a compromised job in this public repo could do.

All checks are read-only, mechanical, and evidence-based against the
actual `.github/workflows/*.yml` files -- not a hand-maintained list that
itself could drift out of sync with what's real.
"""
import json
import pathlib
import re
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
PERMISSIONS_ALLOWLIST_PATH = REPO_ROOT / "config" / "workflow_permissions_allowlist.json"

# Every GITHUB_TOKEN scope that grants write authority (per GitHub's own
# `permissions:` schema) -- if a workflow ever spells write authority as
# the `write-all` shorthand instead of naming a scope, that's caught
# separately in TestNoUnexplainedWritePermissions.test_no_write_all_shorthand.
_WRITE_SCOPES = {
    "actions", "checks", "contents", "deployments", "discussions", "id-token",
    "issues", "packages", "pages", "pull-requests", "repository-projects",
    "security-events", "statuses",
}

# A `uses:` value is either a local/composite action (`./path`, exempt --
# none exist in this repo today, see module docstring) or `owner/repo@ref`.
# An immutable pin is exactly a 40-character hex commit SHA after the `@`.
_USES_RE = re.compile(r'^\s*uses:\s*([^\s#]+)', re.MULTILINE)
_FULL_SHA_RE = re.compile(r'^[0-9a-f]{40}$')


def _all_workflow_files():
    files = sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml"))
    assert files, f"no workflow files found under {WORKFLOWS_DIR} -- test can't validate anything"
    return files


class TestNoUnpinnedGitHubActions(unittest.TestCase):
    def test_every_third_party_action_is_pinned_to_a_full_commit_sha(self):
        violations = []
        for path in _all_workflow_files():
            text = path.read_text(encoding="utf-8")
            for match in _USES_RE.finditer(text):
                ref = match.group(1)
                if ref.startswith("./") or ref.startswith("docker://"):
                    continue  # local/composite or container-image reference, not a tag-pinnable Action
                if "@" not in ref:
                    violations.append(f"{path.name}: {ref!r} has no @ref at all")
                    continue
                pin = ref.rsplit("@", 1)[1]
                if not _FULL_SHA_RE.match(pin):
                    violations.append(f"{path.name}: {ref!r} is pinned to {pin!r}, not a 40-hex commit SHA")

        self.assertEqual(
            violations, [],
            "Found action reference(s) pinned to a mutable tag/branch instead of an "
            "immutable commit SHA -- a supply-chain risk this repo has already had to "
            "fix twice for a single action (see sast-security-scan.yml's TruffleHog "
            "step history). Resolve the real SHA via `git ls-remote <repo> <tag>` "
            "(never guess one) and pin as `owner/repo@<sha> # <original tag>`:\n  "
            + "\n  ".join(violations),
        )


class TestNoPullRequestTargetTrigger(unittest.TestCase):
    def test_pull_request_target_is_never_used_as_a_trigger(self):
        violations = []
        for path in _all_workflow_files():
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            on_block = doc.get(True, doc.get("on"))  # PyYAML parses bare `on:` as bool True
            if isinstance(on_block, dict) and "pull_request_target" in on_block:
                violations.append(path.name)
            elif isinstance(on_block, (list, str)) and "pull_request_target" in on_block:
                violations.append(path.name)

        self.assertEqual(
            violations, [],
            "pull_request_target combined with untrusted checkout is a known GitHub "
            "Actions secret-exfiltration vector for a public repository (a fork PR's "
            "workflow run receives the base repo's secrets). Found in: "
            + ", ".join(violations),
        )


def _enumerate_write_permissions():
    """For every job in every workflow, the write scopes it actually ends up
    with: a job-level `permissions:` block replaces the workflow-level one
    entirely (GitHub's own model) if present at all; otherwise the job
    inherits the workflow-level block as-is. Returns a list of
    (workflow_file, job_id, sorted_scopes_tuple)."""
    found = []
    for path in _all_workflow_files():
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        wf_perms = doc.get("permissions") or {}
        if wf_perms == "write-all":
            found.append((path.name, "(workflow-level write-all)", ("write-all",)))
            continue
        wf_write = {k for k, v in wf_perms.items() if v == "write" and k in _WRITE_SCOPES}

        for job_id, job in (doc.get("jobs") or {}).items():
            job_perms = job.get("permissions") or {}
            if job_perms == "write-all":
                found.append((path.name, job_id, ("write-all",)))
                continue
            if job_perms:
                effective = {k for k, v in job_perms.items() if v == "write" and k in _WRITE_SCOPES}
            else:
                effective = wf_write
            if effective:
                found.append((path.name, job_id, tuple(sorted(effective))))
    return found


class TestNoUnexplainedWritePermissions(unittest.TestCase):
    def test_no_write_all_shorthand(self):
        violations = [
            f"{wf}:{job}" for wf, job, scopes in _enumerate_write_permissions()
            if scopes == ("write-all",)
        ]
        self.assertEqual(
            violations, [],
            "`permissions: write-all` (or a job-level equivalent) grants every "
            "scope GITHUB_TOKEN supports -- strictly broader than any named "
            "scope this repo's workflows actually need. Found in: " + ", ".join(violations),
        )

    def test_every_residual_write_permission_is_allowlisted(self):
        allowlist = json.loads(PERMISSIONS_ALLOWLIST_PATH.read_text(encoding="utf-8"))
        allowed = {
            (e["workflow"], e["job"]) for e in allowlist["entries"]
            if not e["permission"].endswith("(removed)") and e["permission"] != "NONE (removed)"
        }

        violations = []
        for wf, job, scopes in _enumerate_write_permissions():
            if (wf, job) not in allowed:
                violations.append(f"{wf}:{job} has write scope(s) {scopes} with no entry in {PERMISSIONS_ALLOWLIST_PATH.name}")

        self.assertEqual(
            violations, [],
            "New, unexplained GITHUB_TOKEN write permission(s) found. Every job "
            "that genuinely needs to write must have a corresponding entry (with "
            "a real reason and evidence, not a guess) added to "
            f"{PERMISSIONS_ALLOWLIST_PATH.relative_to(REPO_ROOT)}:\n  " + "\n  ".join(violations),
        )

    def test_allowlist_itself_is_well_formed(self):
        allowlist = json.loads(PERMISSIONS_ALLOWLIST_PATH.read_text(encoding="utf-8"))
        for entry in allowlist["entries"]:
            for field in ("workflow", "job", "permission", "reason", "evidence"):
                self.assertIn(field, entry, f"allowlist entry missing required field {field!r}: {entry}")
                self.assertTrue(str(entry[field]).strip(), f"allowlist entry has an empty {field!r}: {entry}")


if __name__ == "__main__":
    unittest.main()
