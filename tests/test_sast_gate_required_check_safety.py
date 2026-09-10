#!/usr/bin/env python3
"""
tests/test_sast_gate_required_check_safety.py

P0 (2026-09-10): sast-security-scan.yml's `SAST Gate (required)` job is
intended to become a required branch status check on main. GitHub's
documented behavior for a required check whose workflow is path-filtered is
that a PR touching none of the listed paths never triggers the workflow at
all -- the check stays "Expected"/pending forever and permanently blocks
merging that PR. The workflow's `pull_request:` trigger carried exactly
such a path filter before this commit.

Fixed by removing that filter (the workflow now runs on every PR to
main/develop) and adding a `changes` job that classifies what actually
changed, driving each expensive scanner's own `if:` condition -- so an
unrelated PR still doesn't pay for a full Bandit/pip-audit/Semgrep run, it
just always produces a real, deterministic SAST Gate result instead of
never running at all.

This file proves that design mechanically, from the actual workflow file
and the actual bash classification logic inside it -- not a hand-written
reimplementation that could quietly drift out of sync with the real thing.
"""
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SAST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "sast-security-scan.yml"

CONDITIONAL_JOBS = {
    "bandit": "python_relevant",
    "safety": "dependency_relevant",
    "semgrep": "semgrep_relevant",
}
MANDATORY_JOBS = {"changes", "trufflehog", "workflow-hygiene"}
GATE_JOB_ID = "sast-gate"
GATE_JOB_NAME = "SAST Gate (required)"


def _load_workflow() -> dict:
    return yaml.safe_load(SAST_WORKFLOW.read_text(encoding="utf-8"))


def _jobs() -> dict:
    return _load_workflow()["jobs"]


class TestRequiredCheckCannotDeadlock(unittest.TestCase):
    def test_pull_request_trigger_has_no_paths_filter(self):
        doc = _load_workflow()
        on_block = doc.get(True, doc.get("on"))  # PyYAML parses bare `on:` as bool True
        pr_trigger = on_block.get("pull_request")
        self.assertIsNotNone(pr_trigger, "sast-security-scan.yml must still trigger on pull_request")
        self.assertNotIn(
            "paths", pr_trigger or {},
            "pull_request trigger has a 'paths:' filter again -- this is exactly the "
            "condition that deadlocks a required check: a PR touching none of the "
            "listed paths never triggers this workflow, so 'SAST Gate (required)' "
            "stays pending forever and permanently blocks that PR's merge.",
        )

    def test_push_trigger_keeps_its_own_unrelated_paths_filter(self):
        """The push: filter is a separate, pre-existing cost optimization, not
        part of the required-check deadlock (direct pushes to main aren't
        gated by a PR-required-check) -- confirms this fix didn't touch it."""
        doc = _load_workflow()
        on_block = doc.get(True, doc.get("on"))
        push_trigger = on_block.get("push")
        self.assertIn("paths", push_trigger or {}, "push: trigger's pre-existing path filter should be untouched")


class TestGateJobIdentityIsStable(unittest.TestCase):
    def test_sast_gate_job_id_and_name_unchanged(self):
        jobs = _jobs()
        self.assertIn(GATE_JOB_ID, jobs, f"job id '{GATE_JOB_ID}' must exist -- this is what a branch ruleset binds to")
        self.assertEqual(
            jobs[GATE_JOB_ID].get("name"), GATE_JOB_NAME,
            f"the gate job's display name must stay exactly {GATE_JOB_NAME!r} -- "
            f"that literal string is what gets bound as the required status check",
        )

    def test_sast_gate_runs_unconditionally_via_always(self):
        jobs = _jobs()
        self.assertEqual(
            jobs[GATE_JOB_ID].get("if"), "always()",
            "sast-gate must run even when an upstream job fails/is skipped, or it "
            "could itself disappear instead of reporting a deterministic pass/fail",
        )


class TestMandatoryJobsAlwaysRunAndAreRequired(unittest.TestCase):
    def test_mandatory_jobs_have_no_suppressing_if_condition(self):
        jobs = _jobs()
        for job_id in MANDATORY_JOBS:
            self.assertIn(job_id, jobs, f"mandatory job '{job_id}' is missing entirely")
            self.assertNotIn(
                "if", jobs[job_id],
                f"'{job_id}' is supposed to be mandatory (runs on every trigger) but "
                f"has an `if:` condition that could skip it",
            )

    def test_mandatory_jobs_are_all_in_sast_gate_needs(self):
        needs = set(_jobs()[GATE_JOB_ID]["needs"])
        missing = MANDATORY_JOBS - needs
        self.assertEqual(missing, set(), f"sast-gate's needs: list is missing mandatory job(s): {missing}")


class TestConditionalScannersAreGovernedByChangeClassification(unittest.TestCase):
    def test_every_conditional_scanner_needs_changes_job(self):
        jobs = _jobs()
        for job_id in CONDITIONAL_JOBS:
            needs = jobs[job_id].get("needs")
            needs_set = {needs} if isinstance(needs, str) else set(needs or [])
            self.assertIn("changes", needs_set, f"'{job_id}' must declare needs: changes to consume its classification output")

    def test_every_conditional_scanner_if_references_its_own_output(self):
        """Proves the `if:` actually reads the matching classification output --
        not hardcoded true/false, not reading a different job's output, and
        not silently unconditional (which would defeat the whole point of
        classifying changes at all)."""
        jobs = _jobs()
        for job_id, output_name in CONDITIONAL_JOBS.items():
            if_cond = jobs[job_id].get("if", "")
            expected = f"needs.changes.outputs.{output_name}"
            self.assertIn(
                expected, if_cond,
                f"'{job_id}' job's if: condition ({if_cond!r}) does not reference "
                f"{expected} -- its execution is no longer actually governed by "
                f"whether its own surface changed",
            )

    def test_sast_gate_needs_includes_every_conditional_scanner(self):
        needs = set(_jobs()[GATE_JOB_ID]["needs"])
        missing = set(CONDITIONAL_JOBS) - needs
        self.assertEqual(missing, set(), f"sast-gate's needs: list is missing conditional scanner(s): {missing}")

    def test_sast_gate_check_step_treats_skip_as_valid_only_when_output_says_so(self):
        """Static proof that the gate's own bash doesn't just check for
        'failure' (the pre-fix behavior) -- it must reference each
        classification output to decide whether 'skipped' is acceptable."""
        jobs = _jobs()
        script = jobs[GATE_JOB_ID]["steps"][0]["run"]
        for output_name in CONDITIONAL_JOBS.values():
            env_var = output_name.upper()
            self.assertIn(
                env_var, script,
                f"SAST Gate's check script never references {env_var} -- it can't "
                f"be validating that a skipped conditional job was actually "
                f"classified non-applicable",
            )
        self.assertIn("skipped", script, "gate script must explicitly reason about the 'skipped' result")


class TestChangeClassificationLogicIsCorrect(unittest.TestCase):
    """Executes the REAL bash from the `changes` job's classification step
    against synthetic git history -- not a Python reimplementation that
    could drift from what actually runs in CI. Covers both scenarios named
    in the P0 spec: a docs-only PR and a source/workflow-relevant PR."""

    @classmethod
    def setUpClass(cls):
        jobs = _jobs()
        classify_step = next(s for s in jobs["changes"]["steps"] if s.get("id") == "classify")
        cls.script = classify_step["run"]

    def _run_classification(self, changed_files, event_name="pull_request"):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)

            for rel in ["README.md"]:
                (repo / rel).write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
            ).stdout.strip()

            if changed_files:
                for rel in changed_files:
                    path = repo / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("changed\n", encoding="utf-8")
                subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
                subprocess.run(["git", "commit", "-q", "-m", "head"], cwd=repo, check=True)
                head_sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
                ).stdout.strip()
            else:
                # Non-PR events (schedule/dispatch/push) never reach the git
                # diff at all -- the real script returns "everything relevant"
                # before looking at PR_BASE_SHA/PR_HEAD_SHA, so reusing the
                # base commit for both is fine here; there is no "head" to diff.
                head_sha = base_sha

            output_file = repo / "github_output.txt"
            env = {
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "EVENT_NAME": event_name,
                "PR_BASE_SHA": base_sha,
                "PR_HEAD_SHA": head_sha,
                "GITHUB_OUTPUT": str(output_file),
            }
            result = subprocess.run(
                ["bash", "-c", self.script], cwd=repo, env=env,
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, f"classify script exited non-zero: {result.stderr}")

            outputs = {}
            for line in output_file.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    outputs[k] = v
            return outputs

    def test_scenario_a_docs_only_pr_marks_nothing_relevant(self):
        """A PR touching only docs/README must not trigger any expensive
        scanner -- proves the classification narrows scope correctly."""
        outputs = self._run_classification(["docs/CHANGELOG.md"])
        self.assertEqual(outputs.get("python_relevant"), "false")
        self.assertEqual(outputs.get("dependency_relevant"), "false")
        self.assertEqual(outputs.get("semgrep_relevant"), "false")

    def test_scenario_b_source_change_pr_marks_the_right_scanners_relevant(self):
        """A PR touching agent/ source, a requirements file, and api/ must
        mark exactly the scanners actually governing those paths relevant."""
        outputs = self._run_classification([
            "agent/some_module.py",
            "requirements.txt",
            "api/some_data.json",
        ])
        self.assertEqual(outputs.get("python_relevant"), "true")
        self.assertEqual(outputs.get("dependency_relevant"), "true")
        self.assertEqual(outputs.get("semgrep_relevant"), "true")

    def test_api_json_alone_is_not_python_relevant_but_is_semgrep_relevant(self):
        """Confirms the deliberate asymmetry: Bandit only scans api/**.py
        (matches the old path filter's own restriction), Semgrep scans all
        of api/ -- a non-.py api/ change should reflect that difference."""
        outputs = self._run_classification(["api/some_data.json"])
        self.assertEqual(outputs.get("python_relevant"), "false")
        self.assertEqual(outputs.get("semgrep_relevant"), "true")

    def test_workflow_file_itself_changing_is_relevant_to_every_scanner(self):
        outputs = self._run_classification([".github/workflows/sast-security-scan.yml"])
        self.assertEqual(outputs.get("python_relevant"), "true")
        self.assertEqual(outputs.get("dependency_relevant"), "true")
        self.assertEqual(outputs.get("semgrep_relevant"), "true")

    def test_non_pull_request_event_marks_everything_relevant(self):
        """schedule/workflow_dispatch/push must keep scanning everything --
        this fix only narrows the pull_request case."""
        outputs = self._run_classification([], event_name="schedule")
        self.assertEqual(outputs.get("python_relevant"), "true")
        self.assertEqual(outputs.get("dependency_relevant"), "true")
        self.assertEqual(outputs.get("semgrep_relevant"), "true")


if __name__ == "__main__":
    unittest.main()
