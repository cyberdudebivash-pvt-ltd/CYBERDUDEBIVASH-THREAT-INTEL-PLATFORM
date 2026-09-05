#!/usr/bin/env python3
"""
tests/test_r2_lifecycle_manager.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- P0 FinOps: R2 native lifecycle policy
manager regression + drift-gate tests. See docs/P0_R2_COST_CONTAINMENT.md
Section 8 and scripts/r2_lifecycle_manager.py's own module docstring for
the full evidence trail.

Like tests/test_r2_reports_purge_safety.py, this file never exercises a
real R2 call (--verify/--apply's aws s3api calls need live credentials and
are intentionally out of scope here). It proves: the checked-in policy file
itself is valid and matches the mandated shape (the CI drift gate), that
sentinel-apex-data can never carry an age-based Expiration rule even if a
future edit tries to add one, and that --apply's CLI-level safety gate
cannot be bypassed -- the two things that matter for a tool whose job is to
mutate a production bucket's lifecycle configuration.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "r2_lifecycle_manager.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_lifecycle_manager as lm  # noqa: E402


def _valid_policy(**overrides) -> dict:
    base = {
        "max_expiration_days_allowed": 7,
        "rules": [
            {
                "rule_id": "reports-html-7d-backstop",
                "bucket": "sentinel-apex-reports",
                "prefix": "reports/",
                "expiration_days": 7,
                "purpose": "test rule",
            }
        ],
        "incomplete_multipart_abort_days": {
            "sentinel-apex-data": 7,
            "sentinel-apex-reports": 7,
        },
    }
    base.update(overrides)
    return base


class TestCheckedInPolicyIsValid(unittest.TestCase):
    """The CI drift gate: the actual checked-in config/r2_lifecycle_policy.json
    must always pass schema validation and honor the 7-day ephemeral mandate.
    Static file check only -- never touches live R2."""

    def test_policy_file_exists_and_parses(self):
        self.assertTrue(lm.POLICY_PATH.exists(), f"{lm.POLICY_PATH} must exist")
        policy = lm.load_policy()
        self.assertIsInstance(policy, dict)

    def test_checked_in_policy_passes_schema_validation(self):
        policy = lm.load_policy()
        errors = lm.validate_policy(policy)
        self.assertEqual(errors, [], f"config/r2_lifecycle_policy.json failed validation: {errors}")

    def test_every_rule_expiration_is_at_most_7_days(self):
        policy = lm.load_policy()
        for rule in policy["rules"]:
            self.assertLessEqual(
                rule["expiration_days"], 7,
                f"rule {rule['rule_id']!r} exceeds the mandated 7-day ephemeral retention ceiling",
            )

    def test_no_rule_targets_sentinel_apex_data(self):
        """Locks in this policy's central safety finding: sentinel-apex-data
        holds single overwrite-in-place current-state keys, not date-
        partitioned generations -- an age-based rule there risks deleting
        the only live copy of production data during a pipeline stall."""
        policy = lm.load_policy()
        buckets = {rule["bucket"] for rule in policy["rules"]}
        self.assertNotIn(lm.BUCKET_DATA, buckets)

    def test_multipart_abort_covers_both_production_buckets(self):
        policy = lm.load_policy()
        multipart = policy.get("incomplete_multipart_abort_days", {})
        for bucket in (lm.BUCKET_DATA, lm.BUCKET_REPORTS):
            self.assertIn(bucket, multipart)
            self.assertLessEqual(multipart[bucket], 7)


class TestValidatePolicySchema(unittest.TestCase):
    """Direct unit coverage of validate_policy()'s individual checks,
    independent of whatever the checked-in file currently says."""

    def test_valid_policy_has_no_errors(self):
        self.assertEqual(lm.validate_policy(_valid_policy()), [])

    def test_missing_rules_is_an_error(self):
        errors = lm.validate_policy(_valid_policy(rules=[]))
        self.assertTrue(any("at least one rule" in e for e in errors))

    def test_sentinel_apex_data_rule_is_always_rejected(self):
        policy = _valid_policy(rules=[{
            "rule_id": "bad-rule",
            "bucket": lm.BUCKET_DATA,
            "prefix": "intel/",
            "expiration_days": 7,
            "purpose": "should never be allowed",
        }])
        errors = lm.validate_policy(policy)
        self.assertTrue(any("sentinel-apex-data" in e for e in errors))

    def test_expiration_days_over_max_is_rejected(self):
        policy = _valid_policy(max_expiration_days_allowed=7, rules=[{
            "rule_id": "too-long",
            "bucket": lm.BUCKET_REPORTS,
            "prefix": "reports/",
            "expiration_days": 30,
            "purpose": "test",
        }])
        errors = lm.validate_policy(policy)
        self.assertTrue(any("exceeds max_expiration_days_allowed" in e for e in errors))

    def test_zero_or_negative_expiration_days_is_rejected(self):
        for bad_value in (0, -1):
            policy = _valid_policy(rules=[{
                "rule_id": "zero-days",
                "bucket": lm.BUCKET_REPORTS,
                "prefix": "reports/",
                "expiration_days": bad_value,
                "purpose": "test",
            }])
            errors = lm.validate_policy(policy)
            self.assertTrue(any("expiration_days must be a positive integer" in e for e in errors))

    def test_missing_purpose_is_rejected(self):
        policy = _valid_policy(rules=[{
            "rule_id": "no-purpose",
            "bucket": lm.BUCKET_REPORTS,
            "prefix": "reports/",
            "expiration_days": 7,
        }])
        errors = lm.validate_policy(policy)
        self.assertTrue(any("purpose missing" in e for e in errors))

    def test_duplicate_rule_ids_are_rejected(self):
        rule = {
            "rule_id": "dup",
            "bucket": lm.BUCKET_REPORTS,
            "prefix": "reports/",
            "expiration_days": 7,
            "purpose": "test",
        }
        policy = _valid_policy(rules=[rule, dict(rule)])
        errors = lm.validate_policy(policy)
        self.assertTrue(any("duplicate" in e for e in errors))

    def test_unknown_bucket_is_rejected(self):
        policy = _valid_policy(rules=[{
            "rule_id": "unknown-bucket",
            "bucket": "some-other-bucket",
            "prefix": "x/",
            "expiration_days": 7,
            "purpose": "test",
        }])
        errors = lm.validate_policy(policy)
        self.assertTrue(any("not one of" in e for e in errors))


class TestBuildLifecycleConfiguration(unittest.TestCase):
    def test_reports_bucket_gets_expiration_and_multipart_rules(self):
        policy = _valid_policy()
        config = lm.build_lifecycle_configuration(policy, lm.BUCKET_REPORTS)
        rule_ids = {r["ID"] for r in config["Rules"]}
        self.assertIn("reports-html-7d-backstop", rule_ids)
        self.assertIn(f"{lm.BUCKET_REPORTS}-abort-incomplete-multipart", rule_ids)

    def test_data_bucket_gets_only_multipart_rule_never_expiration(self):
        policy = _valid_policy()
        config = lm.build_lifecycle_configuration(policy, lm.BUCKET_DATA)
        for rule in config["Rules"]:
            self.assertNotIn("Expiration", rule)
        rule_ids = {r["ID"] for r in config["Rules"]}
        self.assertEqual(rule_ids, {f"{lm.BUCKET_DATA}-abort-incomplete-multipart"})

    def test_bucket_with_no_rules_at_all_returns_empty_rules_list_not_omitted(self):
        """An explicit {"Rules": []} actively clears any stale rule already
        on the live bucket -- never silently skip the call for a bucket the
        policy doesn't mention."""
        policy = {"rules": [], "incomplete_multipart_abort_days": {}}
        config = lm.build_lifecycle_configuration(policy, lm.BUCKET_DATA)
        self.assertEqual(config, {"Rules": []})


class TestCliSafetyGates(unittest.TestCase):
    """End-to-end CLI invocations (subprocess) -- proves refusals fire from
    the actual entry point without requiring any R2 credentials."""

    def test_show_is_the_default_and_needs_no_credentials(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("SCHEMA VALIDATION: PASS", result.stdout)

    def test_apply_without_execute_is_a_dry_run(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--apply"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        # Dry-run path never reaches get_credentials()'s hard FATAL exit for
        # a mismatched/absent CF_ACCOUNT_ID in this sandbox would also
        # return non-zero -- assert on the dry-run message specifically so
        # this test distinguishes "safely dry-ran" from "crashed for an
        # unrelated reason".
        self.assertIn("[DRY-RUN]", result.stdout + result.stderr)

    def test_apply_execute_without_confirm_bucket_never_calls_aws_put(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--apply", "--execute"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        combined = result.stdout + result.stderr
        # Either credential validation fails first (no CF_ACCOUNT_ID in this
        # sandbox) or the per-bucket confirm-bucket mismatch fires -- both
        # are acceptable "did not proceed to mutate anything" outcomes; the
        # one unacceptable outcome is a successful PUT, which cannot happen
        # here since neither gate is satisfied.
        self.assertNotIn("Applied lifecycle configuration", combined)


if __name__ == "__main__":
    unittest.main()
