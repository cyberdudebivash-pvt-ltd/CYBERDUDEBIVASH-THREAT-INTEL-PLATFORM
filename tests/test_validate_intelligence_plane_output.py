#!/usr/bin/env python3
"""
tests/test_validate_intelligence_plane_output.py

Regression + mutation coverage for scripts/validate_intelligence_plane_output.py,
the fail-closed gate P0 RUNTIME INTELLIGENCE STATE RECOVERY inserts before the
R2 upload step in genesis-powerhouse.yml / sovereign-platform.yml. Each test
here corresponds to one of the mission's required mutation-test scenarios:
a genuinely broken engine's output must fail this gate, not silently pass.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_intelligence_plane_output as v  # noqa: E402


class TestValidateIntelligencePlaneOutput(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmpdir.name)
        self.addCleanup(self._tmpdir.cleanup)

    def _write(self, name, data):
        path = self.tmp / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_fresh_valid_output_passes(self):
        path = self._write("ok.json", {"generated_at": datetime.now(timezone.utc).isoformat(), "stream": {}})
        ok, msg = v.validate(path, "CORTEX", 1200)
        self.assertTrue(ok, msg)

    def test_missing_file_fails(self):
        ok, msg = v.validate(str(self.tmp / "does_not_exist.json"), "NEXUS", 1200)
        self.assertFalse(ok)
        self.assertIn("MISSING", msg)

    def test_malformed_json_fails(self):
        path = self.tmp / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        ok, msg = v.validate(str(path), "QUANTUM", 1200)
        self.assertFalse(ok)
        self.assertIn("MALFORMED", msg)

    def test_non_dict_top_level_fails(self):
        # Reproduces the exact live CORTEX bug class this mission fixed at
        # the source (generate_stream()'s empty-entries early return used to
        # be a bare list) -- the gate must independently catch it too, as
        # defense in depth against a future regression of the same shape.
        path = self._write("list_shaped.json", [1, 2, 3])
        ok, msg = v.validate(path, "CORTEX", 1200)
        self.assertFalse(ok)
        self.assertIn("WRONG SHAPE", msg)

    def test_missing_generated_at_fails(self):
        path = self._write("no_ts.json", {"stream": {}})
        ok, msg = v.validate(path, "CORTEX", 1200)
        self.assertFalse(ok)
        self.assertIn("NO TIMESTAMP", msg)

    def test_unparseable_generated_at_fails(self):
        path = self._write("bad_ts.json", {"generated_at": "not-a-timestamp"})
        ok, msg = v.validate(path, "SOVEREIGN", 1200)
        self.assertFalse(ok)
        self.assertIn("BAD TIMESTAMP", msg)

    def test_stale_leftover_from_previous_run_fails(self):
        """The exact production defect: an engine step crashes silently
        (continue-on-error: true), the previous run's output file is still
        sitting on disk from hours ago, and nothing downstream would notice
        without this check -- it would get re-uploaded to R2 looking fresh."""
        old = datetime.now(timezone.utc) - timedelta(hours=6)
        path = self._write("stale.json", {"generated_at": old.isoformat()})
        ok, msg = v.validate(path, "GENESIS", 1200)
        self.assertFalse(ok)
        self.assertIn("STALE", msg)

    def test_future_timestamp_fails(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        path = self._write("future.json", {"generated_at": future.isoformat()})
        ok, msg = v.validate(path, "NEXUS", 1200)
        self.assertFalse(ok)
        self.assertIn("FUTURE TIMESTAMP", msg)

    def test_age_exactly_at_boundary_passes(self):
        just_inside = datetime.now(timezone.utc) - timedelta(seconds=1199)
        path = self._write("boundary.json", {"generated_at": just_inside.isoformat()})
        ok, msg = v.validate(path, "QUANTUM", 1200)
        self.assertTrue(ok, msg)

    def test_cli_exit_codes(self):
        import subprocess
        fresh = self._write("cli_ok.json", {"generated_at": datetime.now(timezone.utc).isoformat()})
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "validate_intelligence_plane_output.py"),
             "--file", fresh, "--engine", "NEXUS"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        missing = str(self.tmp / "nope.json")
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "validate_intelligence_plane_output.py"),
             "--file", missing, "--engine", "NEXUS"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
