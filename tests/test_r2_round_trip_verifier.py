#!/usr/bin/env python3
"""
tests/test_r2_round_trip_verifier.py

Regression coverage for scripts/r2_round_trip_verifier.py, the P0 RUNTIME
INTELLIGENCE STATE RECOVERY mission's independent post-write verification
step. Mocks r2_state_sync.download() (network-free) to drive it through
each outcome: genuine match, content mismatch, download failure, and a
missing local source file.
"""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_round_trip_verifier as vrt  # noqa: E402
import r2_state_sync as rss  # noqa: E402


class TestVerifyR2RoundTrip(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.source_root = pathlib.Path(self._tmpdir.name)
        self.addCleanup(self._tmpdir.cleanup)
        self.target = "data/nexus/nexus_output.json"
        (self.source_root / "data" / "nexus").mkdir(parents=True)
        (self.source_root / self.target).write_text('{"generated_at": "now"}', encoding="utf-8")

    def _fake_download_matching(self, root, endpoint, only=None):
        # Simulates a real R2 round trip that returns byte-identical content.
        for local_rel in only:
            dest = root / local_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((self.source_root / local_rel).read_bytes())
        return 0

    def test_matching_round_trip_passes(self):
        with patch.object(rss, "download", side_effect=self._fake_download_matching), \
             patch.object(vrt, "get_credentials", return_value=("acct", "k", "s")), \
             patch.object(vrt, "install_awscli"), \
             patch.object(sys, "argv", ["r2_round_trip_verifier.py", "--source-root", str(self.source_root), "--only", self.target]):
            rc = vrt.main()
        self.assertEqual(rc, 0)

    def test_content_mismatch_fails(self):
        def fake_download_mismatch(root, endpoint, only=None):
            for local_rel in only:
                dest = root / local_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text('{"generated_at": "DIFFERENT-STALE-COPY"}', encoding="utf-8")
            return 0

        with patch.object(rss, "download", side_effect=fake_download_mismatch), \
             patch.object(vrt, "get_credentials", return_value=("acct", "k", "s")), \
             patch.object(vrt, "install_awscli"), \
             patch.object(sys, "argv", ["r2_round_trip_verifier.py", "--source-root", str(self.source_root), "--only", self.target]):
            rc = vrt.main()
        self.assertEqual(rc, 1)

    def test_download_failure_fails(self):
        with patch.object(rss, "download", return_value=1), \
             patch.object(vrt, "get_credentials", return_value=("acct", "k", "s")), \
             patch.object(vrt, "install_awscli"), \
             patch.object(sys, "argv", ["r2_round_trip_verifier.py", "--source-root", str(self.source_root), "--only", self.target]):
            rc = vrt.main()
        self.assertEqual(rc, 1)

    def test_missing_local_source_fails(self):
        def fake_download_noop(root, endpoint, only=None):
            return 0  # nothing to download for a target that was never produced locally either

        with patch.object(rss, "download", side_effect=fake_download_noop), \
             patch.object(vrt, "get_credentials", return_value=("acct", "k", "s")), \
             patch.object(vrt, "install_awscli"), \
             patch.object(sys, "argv", ["r2_round_trip_verifier.py", "--source-root", str(self.source_root), "--only", "data/genesis/genesis_output.json"]):
            rc = vrt.main()
        self.assertEqual(rc, 1)

    def test_unknown_only_path_is_rejected(self):
        with patch.object(vrt, "get_credentials", return_value=("acct", "k", "s")), \
             patch.object(vrt, "install_awscli"), \
             patch.object(sys, "argv", ["r2_round_trip_verifier.py", "--source-root", str(self.source_root), "--only", "data/typo/nope.json"]):
            with self.assertRaises(SystemExit):
                vrt.main()


if __name__ == "__main__":
    unittest.main()
