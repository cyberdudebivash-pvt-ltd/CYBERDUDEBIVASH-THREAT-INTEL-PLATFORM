from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "generate-and-sync.yml"


class AiTrackerRuntimeStabilityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(
            r'- name: "STAGE 6\.87[^\n]*"(?P<body>.*?)(?=\n\s*# [─-]{5,})',
            cls.workflow,
            flags=re.DOTALL,
        )
        if match is None:
            raise AssertionError("AI Tracker runtime-stability step is missing")
        cls.step = match.group("body")

    def test_hard_failure_is_not_marked_continue_on_error(self):
        self.assertNotIn("continue-on-error: true", self.step)

    def test_pipeline_preserves_runtime_engine_exit_status(self):
        self.assertIn("set -o pipefail", self.step)
        self.assertIn(
            "python3 scripts/runtime_stability_engine.py --check --profile ai-tracker 2>&1 | tail -20",
            self.step,
        )
        self.assertNotIn("|| true", self.step)


if __name__ == "__main__":
    unittest.main()
