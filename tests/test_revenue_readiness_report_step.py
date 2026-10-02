"""F24: the revenue engine deploy's "Commercial readiness report" step.

It printed "readiness endpoint not reachable yet" on every deploy (runs
36460344094 and 36914355894) while the route answered 401 without the
secret: `curl -sf` dropped the HTTP status, so a rejected secret, a network
error and an edge block all read the same, and a BLOCKED verdict never
reached the deploy log.

These tests run the REAL step script from deploy-revenue-engine.yml with a
stub `curl` first on PATH that replays scripted responses. The step must
stay informational (exit 0), name the cause, retry only 5xx / no response,
and never print the secret.
"""
import json
import os
import pathlib
import stat
import subprocess
import tempfile
import textwrap
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-revenue-engine.yml"
STEP_NAME = "Commercial readiness report"
SECRET = "rae-test-secret-value-7f3a"

STUB_CURL = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, sys
    args = sys.argv[1:]
    log = os.environ["STUB_LOG"]
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(args) + "\\n")
    calls = sum(1 for _ in open(log, encoding="utf-8"))
    responses = json.loads(os.environ["STUB_RESPONSES"])
    code, body, exit_code = responses[min(calls, len(responses)) - 1]
    out = args[args.index("-o") + 1]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(body)
    sys.stdout.write(code)
    sys.exit(exit_code)
''')


def _step():
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == STEP_NAME:
                return step
    raise AssertionError(f"step {STEP_NAME!r} not found in {WORKFLOW}")


class TestReadinessReportStep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.step = _step()
        cls.script = cls.step["run"]

    def _run(self, responses, secret=SECRET):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            curl = tmp / "curl"
            curl.write_text(STUB_CURL, encoding="utf-8")
            curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
            log = tmp / "calls.log"
            log.write_text("", encoding="utf-8")
            env = {
                "PATH": f"{tmp}:/usr/bin:/bin:/usr/local/bin",
                "STUB_LOG": str(log),
                "STUB_RESPONSES": json.dumps(responses),
                "READINESS_RETRY_SLEEP_SECONDS": "0",
                "REVENUE_ADMIN_SECRET": secret,
            }
            result = subprocess.run(["bash", "-e", "-c", self.script], env=env, capture_output=True, text=True)
            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
            return result, calls

    def _assert_safe(self, result):
        self.assertEqual(result.returncode, 0, "the report is informational and must never fail the deploy")
        self.assertNotIn(SECRET, result.stdout + result.stderr, "the secret must never be printed")

    def test_ready_verdict_is_reported(self):
        body = json.dumps({"verdict": "READY", "blockers": [], "warnings": ["gst_invoice_config"], "queue": {"attention": 0}})
        result, calls = self._run([["200", body, 0]])
        self._assert_safe(result)
        self.assertIn("verdict: READY", result.stdout)
        self.assertNotIn("::warning", result.stdout)
        self.assertEqual(len(calls), 1)

    def test_blocked_verdict_raises_a_warning_with_the_blockers(self):
        body = json.dumps({"verdict": "BLOCKED", "blockers": ["razorpay_plan_ids"], "warnings": [], "queue": None})
        result, _ = self._run([["200", body, 0]])
        self._assert_safe(result)
        self.assertIn("::warning title=Commercial readiness: BLOCKED::Blockers: razorpay_plan_ids", result.stdout)

    def test_rejected_secret_is_named_not_reported_as_unreachable(self):
        body = json.dumps({"error": "unauthorized", "message": "X-Admin-Secret required."})
        result, calls = self._run([["401", body, 0]])
        self._assert_safe(result)
        self.assertIn("HTTP 401", result.stdout)
        self.assertIn("rejected the REVENUE_ADMIN_SECRET repository secret", result.stdout)
        self.assertNotIn("not reachable", result.stdout)
        self.assertEqual(len(calls), 1, "a rejected secret is not retried")

    def test_edge_block_is_told_apart_from_a_rejected_secret(self):
        result, _ = self._run([["403", "<html>Attention Required</html>", 0]])
        self._assert_safe(result)
        self.assertIn("did not come from the revenue engine", result.stdout)

    def test_no_response_is_retried_then_reported(self):
        result, calls = self._run([["000", "", 7]])
        self._assert_safe(result)
        self.assertEqual(len(calls), 3)
        self.assertIn("No HTTP response", result.stdout)

    def test_transient_5xx_is_retried_until_the_verdict_arrives(self):
        body = json.dumps({"verdict": "READY", "blockers": [], "warnings": [], "queue": {"attention": 2}})
        result, calls = self._run([["503", "busy", 0], ["200", body, 0]])
        self._assert_safe(result)
        self.assertEqual(len(calls), 2)
        self.assertIn("verdict: READY", result.stdout)

    def test_missing_secret_skips_with_a_warning_and_no_request(self):
        result, calls = self._run([["200", "{}", 0]], secret="")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        self.assertIn("::warning title=Commercial readiness not reported::", result.stdout)

    def test_secret_goes_only_in_the_admin_header(self):
        _, calls = self._run([["200", json.dumps({"verdict": "READY"}), 0]])
        args = calls[0]
        self.assertIn(f"X-Admin-Secret: {SECRET}", args)
        self.assertEqual(sum(SECRET in a for a in args), 1)
        self.assertTrue(args[-1].startswith("https://revenue.intel.cyberdudebivash.com/"))

    def test_step_stays_informational(self):
        self.assertIs(self.step.get("continue-on-error"), True)
        self.assertNotIn("curl -sf", self.script, "-f hides the HTTP status this report exists to show")


if __name__ == "__main__":
    unittest.main()
