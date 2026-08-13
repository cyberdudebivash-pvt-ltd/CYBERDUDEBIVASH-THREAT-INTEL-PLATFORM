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
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html", skip_public=True)

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
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html", skip_public=True)

        self.assertEqual(result["publication_state"], "STALE_OR_DIVERGENT")
        self.assertEqual(result["artifact_sha256"], _sha256(local_data))
        self.assertEqual(result["remote_sha256"], _sha256(remote_data))
        self.assertNotEqual(result["artifact_sha256"], result["remote_sha256"])
        self.assertIn("diverge", result["error"])

    def test_missing_remote_object_is_failed(self):
        self._write("<!DOCTYPE html><html>content</html>")

        with patch.object(rrv._verifier, "_s3api_head_object", return_value={"status": 404, "content_length": 0, "etag": ""}), \
             patch.object(rrv._verifier, "_boto3_head_object", return_value=None):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html", skip_public=True)

        self.assertEqual(result["publication_state"], "FAILED")
        self.assertIsNone(result["remote_sha256"])
        self.assertIn("does not exist", result["error"])

    def test_head_object_totally_unreachable_is_unknown(self):
        self._write("<!DOCTYPE html><html>content</html>")

        with patch.object(rrv._verifier, "_s3api_head_object", return_value=None), \
             patch.object(rrv._verifier, "_boto3_head_object", return_value=None):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html", skip_public=True)

        self.assertEqual(result["publication_state"], "UNKNOWN")

    def test_get_object_failure_after_successful_head_is_unknown_not_verified(self):
        """A HEAD success with a failed GET must never be silently treated as
        verified -- that would be exactly the "successful aws s3 sync ==
        content-identity proof" fallacy the mission's Section 3 prohibits,
        just at a different layer."""
        self._write("<!DOCTYPE html><html>content</html>")

        with patch.object(rrv._verifier, "_s3api_head_object", return_value={"status": 200, "content_length": 10, "etag": "z"}), \
             patch.object(rrv, "_get_object_bytes", return_value=None):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--testverify0000.html", skip_public=True)

        self.assertEqual(result["publication_state"], "UNKNOWN")
        self.assertIsNone(result["remote_sha256"])


class TestManifestSchema(unittest.TestCase):
    """Static check that the Phase 9 required JSON manifest fields are all
    present in verify_one()'s output shape, matching the mission's schema."""

    def test_result_shape_matches_phase9_schema_fields(self):
        REQUIRED_FIELDS = {
            "r2_key", "size_bytes", "generator", "artifact_sha256",
            "remote_sha256", "remote_verified_at", "publication_state",
            "public_sha256", "public_verified_at", "live_state",
            "public_response_headers",
        }
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="rrv_schema_"))
        try:
            p = tmp / "intel--schematest00000.html"
            data = p.write_bytes(b"<!DOCTYPE html><html>x</html>") and None
            with patch.object(rrv._verifier, "_s3api_head_object", return_value={"status": 404, "content_length": 0, "etag": ""}), \
                 patch.object(rrv._verifier, "_boto3_head_object", return_value=None):
                result = rrv.verify_one(p, "reports/2026/08/intel--schematest00000.html", skip_public=True)
            missing = REQUIRED_FIELDS - set(result.keys())
            self.assertEqual(missing, set(), f"verify_one() result is missing required schema fields: {missing}")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestPublicHttpLayer(unittest.TestCase):
    """RX-PUB-A0.4 Phase 2: the public HTTP layer must run and classify
    independently of the R2 layer (it needs no R2 credentials at all), and
    must never treat a failed/missing fetch as verified -- the same
    "successful check != content-identity proof" principle already proven
    for the R2 layer, enforced here too."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="rrv_public_test_"))
        self.report_path = self.tmp / "intel--publictest00000.html"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, content: str) -> bytes:
        data = content.encode("utf-8")
        self.report_path.write_bytes(data)
        return data

    def _no_r2(self):
        return patch.object(rrv._verifier, "_s3api_head_object", return_value=None), \
               patch.object(rrv._verifier, "_boto3_head_object", return_value=None)

    def test_matching_public_bytes_is_live_verified(self):
        data = self._write("<!DOCTYPE html><html>correct content</html>")
        p1, p2 = self._no_r2()
        with p1, p2, patch.object(rrv, "_fetch_public", return_value={"bytes": data, "status": 200, "headers": {"cf-ray": "abc"}, "error": None}):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--publictest00000.html")

        self.assertEqual(result["live_state"], "LIVE_VERIFIED")
        self.assertEqual(result["public_sha256"], _sha256(data))
        self.assertIsNotNone(result["public_verified_at"])
        self.assertEqual(result["public_response_headers"], {"cf-ray": "abc"})

    def test_divergent_public_bytes_is_live_stale_or_divergent(self):
        local_data = self._write("<!DOCTYPE html><html>LOCAL fixed content</html>")
        remote_data = b"<!DOCTYPE html><html>STALE customer-served content</html>"
        p1, p2 = self._no_r2()
        with p1, p2, patch.object(rrv, "_fetch_public", return_value={"bytes": remote_data, "status": 200, "headers": {}, "error": None}):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--publictest00000.html")

        self.assertEqual(result["live_state"], "LIVE_STALE_OR_DIVERGENT")
        self.assertEqual(result["public_sha256"], _sha256(remote_data))
        self.assertNotEqual(result["artifact_sha256"], result["public_sha256"])
        self.assertIn("diverge", result["public_error"])

    def test_public_404_is_live_missing(self):
        self._write("<!DOCTYPE html><html>content</html>")
        p1, p2 = self._no_r2()
        with p1, p2, patch.object(rrv, "_fetch_public", return_value={"bytes": None, "status": 404, "headers": {}, "error": "HTTP 404"}):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--publictest00000.html")

        self.assertEqual(result["live_state"], "LIVE_MISSING")
        self.assertIsNone(result["public_sha256"])

    def test_public_fetch_failure_is_live_fetch_failed_not_verified(self):
        """A network timeout or 5xx must never be silently treated as
        LIVE_VERIFIED -- the exact same "successful transfer != content
        identity" fallacy the R2 layer already guards against, at this
        layer too."""
        self._write("<!DOCTYPE html><html>content</html>")
        p1, p2 = self._no_r2()
        with p1, p2, patch.object(rrv, "_fetch_public", return_value={"bytes": None, "status": 503, "headers": {}, "error": "HTTP 503"}):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--publictest00000.html")

        self.assertEqual(result["live_state"], "LIVE_FETCH_FAILED")
        self.assertIsNone(result["public_sha256"])

    def test_skip_public_does_not_call_fetch_at_all(self):
        """--skip-public (cost-governance escape hatch) must genuinely skip
        the fetch, not just discard its result after paying for it."""
        self._write("<!DOCTYPE html><html>content</html>")
        p1, p2 = self._no_r2()
        with p1, p2, patch.object(rrv, "_fetch_public") as mock_fetch:
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--publictest00000.html", skip_public=True)

        mock_fetch.assert_not_called()
        self.assertEqual(result["live_state"], "PENDING")

    def test_public_layer_runs_without_any_r2_credentials(self):
        """The public HTTP layer needs no R2 credentials -- proven by
        running it with the R2 helpers forced to their credential-absent
        return value (None), matching exactly what happens in this sandbox
        (no CF_ACCOUNT_ID) and confirming the two layers are independent."""
        data = self._write("<!DOCTYPE html><html>content</html>")
        p1, p2 = self._no_r2()
        with p1, p2, patch.object(rrv, "_fetch_public", return_value={"bytes": data, "status": 200, "headers": {}, "error": None}):
            result = rrv.verify_one(self.report_path, "reports/2026/08/intel--publictest00000.html")

        self.assertEqual(result["publication_state"], "UNKNOWN")  # R2 layer: no credentials
        self.assertEqual(result["live_state"], "LIVE_VERIFIED")   # Public layer: independent, still works


if __name__ == "__main__":
    unittest.main()
