"""
tests/test_r2_reports_verifier.py

RX-PUB-A0 Phase 9: scripts/r2_reports_verifier.py cannot be exercised against
real R2 in this environment (no CF_ACCOUNT_ID / aws CLI available -- see
docs/RX_PUB_A0_EXECUTION_PATH.md Section 5). These tests instead verify its
decision logic directly by mocking the R2 head/get primitives it reuses from
scripts/r2_upload_verifier.py, proving the classification behavior
(REMOTE_VERIFIED / STALE_OR_DIVERGENT / FAILED / UNKNOWN) is correct for
each case the mission's Section 12 case table requires.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_reports_verifier as rrv  # noqa: E402


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestVerifyOne(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="rrv_test_"))
        self.report_path = self.tmp / "intel--testverify0000.html"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, content: str) -> bytes:
        data = content.encode("utf-8")
        self.report_path.write_bytes(data)
        return data

    def test_matching_content_is_remote_verified(self):
        data = self._write("<!DOCTYPE html><html>correct content</html>")

        with patch.object(rrv._verifier, "_s3api_head_object", return_value={"status": 200, "content_length": len(data), "etag": "x"}), \
             patch.object(rrv, "_get_object_bytes", return_value=data):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html")

        self.assertEqual(result["publication_state"], "REMOTE_VERIFIED")
        self.assertEqual(result["artifact_sha256"], _sha256(data))
        self.assertEqual(result["remote_sha256"], _sha256(data))
        self.assertIsNotNone(result["remote_verified_at"])
        self.assertNotIn("error", result)

    def test_divergent_content_is_stale_or_divergent(self):
        local_data = self._write("<!DOCTYPE html><html>LOCAL fixed content</html>")
        remote_data = b"<!DOCTYPE html><html>REMOTE stale content, different bytes</html>"

        with patch.object(rrv._verifier, "_s3api_head_object", return_value={"status": 200, "content_length": len(remote_data), "etag": "y"}), \
             patch.object(rrv, "_get_object_bytes", return_value=remote_data):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html")

        self.assertEqual(result["publication_state"], "STALE_OR_DIVERGENT")
        self.assertEqual(result["artifact_sha256"], _sha256(local_data))
        self.assertEqual(result["remote_sha256"], _sha256(remote_data))
        self.assertNotEqual(result["artifact_sha256"], result["remote_sha256"])
        self.assertIn("diverge", result["error"])

    def test_missing_remote_object_is_failed(self):
        self._write("<!DOCTYPE html><html>content</html>")

        with patch.object(rrv._verifier, "_s3api_head_object", return_value={"status": 404, "content_length": 0, "etag": ""}), \
             patch.object(rrv._verifier, "_boto3_head_object", return_value=None):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html")

        self.assertEqual(result["publication_state"], "FAILED")
        self.assertIsNone(result["remote_sha256"])
        self.assertIn("does not exist", result["error"])

    def test_head_object_totally_unreachable_is_unknown(self):
        self._write("<!DOCTYPE html><html>content</html>")

        with patch.object(rrv._verifier, "_s3api_head_object", return_value=None), \
             patch.object(rrv._verifier, "_boto3_head_object", return_value=None):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html")

        self.assertEqual(result["publication_state"], "UNKNOWN")

    def test_get_object_failure_after_successful_head_is_unknown_not_verified(self):
        """A HEAD success with a failed GET must never be silently treated as
        verified -- that would be exactly the "successful aws s3 sync ==
        content-identity proof" fallacy the mission's Section 3 prohibits,
        just at a different layer."""
        self._write("<!DOCTYPE html><html>content</html>")

        with patch.object(rrv._verifier, "_s3api_head_object", return_value={"status": 200, "content_length": 10, "etag": "z"}), \
             patch.object(rrv, "_get_object_bytes", return_value=None):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html")

        self.assertEqual(result["publication_state"], "UNKNOWN")
        self.assertIsNone(result["remote_sha256"])


class TestManifestSchema(unittest.TestCase):
    """Static check that the Phase 9 required JSON manifest fields are all
    present in verify_one()'s output shape, matching the mission's schema."""

    def test_result_shape_matches_phase9_schema_fields(self):
        REQUIRED_FIELDS = {
            "r2_key", "size_bytes", "generator", "artifact_sha256",
            "remote_sha256", "remote_verified_at", "publication_state",
        }
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="rrv_schema_"))
        try:
            p = tmp / "intel--schematest00000.html"
            data = p.write_bytes(b"<!DOCTYPE html><html>x</html>") and None
            with patch.object(rrv._verifier, "_s3api_head_object", return_value={"status": 404, "content_length": 0, "etag": ""}), \
                 patch.object(rrv._verifier, "_boto3_head_object", return_value=None):
                result = rrv.verify_one(p, "reports/2026/08/intel--schematest00000.html")
            missing = REQUIRED_FIELDS - set(result.keys())
            self.assertEqual(missing, set(), f"verify_one() result is missing required schema fields: {missing}")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
