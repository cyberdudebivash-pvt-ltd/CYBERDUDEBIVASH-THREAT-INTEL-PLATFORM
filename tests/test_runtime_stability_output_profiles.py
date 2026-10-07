import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "runtime_stability_engine.py"
SPEC = importlib.util.spec_from_file_location("runtime_stability_engine", MODULE_PATH)
runtime_stability = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime_stability)


class RuntimeStabilityOutputProfileTests(unittest.TestCase):
    def _write(self, root, relative, size):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)

    def test_ai_tracker_profile_accepts_its_three_fresh_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for spec in runtime_stability.AI_TRACKER_REQUIRED_OUTPUTS:
                self._write(root, spec["path"], spec["min_bytes"])
            with mock.patch.object(runtime_stability, "REPO_ROOT", root):
                result = runtime_stability.OutputExistenceProof(
                    runtime_stability.AI_TRACKER_REQUIRED_OUTPUTS
                ).validate()
        self.assertEqual(result["status"], "OK")
        self.assertFalse(result["hard_fail"])
        self.assertEqual(result["message"], "3/3 outputs verified fresh and present")

    def test_ai_tracker_profile_fails_when_a_customer_output_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for spec in runtime_stability.AI_TRACKER_REQUIRED_OUTPUTS[:-1]:
                self._write(root, spec["path"], spec["min_bytes"])
            with mock.patch.object(runtime_stability, "REPO_ROOT", root):
                result = runtime_stability.OutputExistenceProof(
                    runtime_stability.AI_TRACKER_REQUIRED_OUTPUTS
                ).validate()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["hard_fail"])
        missing = [item for item in result["files"] if item["status"] == "FAIL"]
        self.assertEqual(
            [item["file"] for item in missing],
            ["api/ai/executive-brief.json"],
        )

    def test_default_profile_still_requires_feed_manifest(self):
        paths = [spec["path"] for spec in runtime_stability.OUTPUT_PROFILES["default"]]
        self.assertIn("data/feed_manifest.json", paths)
        self.assertNotIn("api/ai/tracker.json", paths)


if __name__ == "__main__":
    unittest.main()
