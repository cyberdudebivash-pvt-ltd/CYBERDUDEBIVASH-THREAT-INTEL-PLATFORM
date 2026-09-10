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

Both checks are read-only, mechanical, and evidence-based against the
actual `.github/workflows/*.yml` files -- not a hand-maintained list that
itself could drift out of sync with what's real.
"""
import pathlib
import re
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

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


if __name__ == "__main__":
    unittest.main()
