"""
tests/test_r2_state_sync.py

Regression tests for scripts/r2_state_sync.py, the P0 fix that moves
data/cache/feed_state.json, data/processed_intel.json and
data/stix/feed_manifest.json from a direct `git push origin main` (rejected
on every run since main started requiring PRs -- see
tests/test_git_publish_no_silent_push_failure.py) onto Cloudflare R2 as the
cross-run, cross-workflow authority, matching the pattern already reviewed
and approved for issue #274 / PR #293.

These tests mock subprocess.run (the underlying `aws s3 cp` invocation) so
they exercise the real download()/upload()/s3_get() code paths without any
network access or real R2 credentials. time.sleep is also mocked -- the
retry-exhaustion tests would otherwise take 90-150 real seconds each.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_state_sync as rs  # noqa: E402
import r2_upload  # noqa: E402


def _proc(returncode=0, stdout="", stderr=""):
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def _parse_cp_cmd(cmd):
    """Both s3_get (download) and s3_cp (upload) build an
    ["aws", "s3", "cp", <src>, <dst>, ...] command -- the only way to tell
    them apart is which of <src>/<dst> (cmd[3]/cmd[4]) starts with "s3://".
    Returns (is_download, local_path, r2_key)."""
    if cmd[3].startswith("s3://"):
        s3_url, local_path = cmd[3], cmd[4]
        is_download = True
    else:
        local_path, s3_url = cmd[3], cmd[4]
        is_download = False
    r2_key = s3_url.split("/", 3)[-1]  # strip "s3://<bucket>/"
    return is_download, local_path, r2_key


class TestS3GetOutcomeClassification(unittest.TestCase):
    """s3_get() must distinguish OK / NOT_FOUND / ERROR -- callers rely on
    this three-way split to know when it's safe to bootstrap vs. when it
    must hard-fail."""

    def test_success_returns_ok(self):
        with patch.object(r2_upload.subprocess, "run", return_value=_proc(0)):
            self.assertEqual(r2_upload.s3_get("/tmp/x.json", "b", "k", "https://e"), "OK")

    def test_404_in_stderr_returns_not_found(self):
        with patch.object(r2_upload.subprocess, "run",
                           return_value=_proc(1, stderr="fatal error: An error occurred (404) when calling the HeadObject operation: Not Found")):
            self.assertEqual(r2_upload.s3_get("/tmp/x.json", "b", "k", "https://e"), "NOT_FOUND")

    def test_nosuchkey_returns_not_found(self):
        with patch.object(r2_upload.subprocess, "run",
                           return_value=_proc(1, stderr="An error occurred (NoSuchKey) when calling the GetObject operation")):
            self.assertEqual(r2_upload.s3_get("/tmp/x.json", "b", "k", "https://e"), "NOT_FOUND")

    def test_auth_failure_returns_error_not_not_found(self):
        with patch.object(r2_upload.subprocess, "run",
                           return_value=_proc(1, stderr="An error occurred (InvalidAccessKeyId) when calling the HeadObject operation")):
            self.assertEqual(r2_upload.s3_get("/tmp/x.json", "b", "k", "https://e"), "ERROR")

    def test_network_timeout_returns_error(self):
        with patch.object(r2_upload.subprocess, "run",
                           return_value=_proc(1, stderr="Connection timed out")):
            self.assertEqual(r2_upload.s3_get("/tmp/x.json", "b", "k", "https://e"), "ERROR")


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_dl_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mock_run_for(self, outcomes: dict):
        """outcomes: {r2_key: 'OK'|'NOT_FOUND'|'ERROR'} -- fakes `aws s3 cp` per key."""
        def _fake_run(cmd, **kwargs):
            _is_download, local_path, r2_key = _parse_cp_cmd(cmd)
            outcome = outcomes.get(r2_key, "ERROR")
            if outcome == "OK":
                pathlib.Path(local_path).write_text(json.dumps({"ok": True}), encoding="utf-8")
                return _proc(0)
            if outcome == "NOT_FOUND":
                return _proc(1, stderr="An error occurred (404) when calling the HeadObject operation: Not Found")
            return _proc(1, stderr="Connection timed out")
        return _fake_run

    def test_all_ok_populates_every_local_file(self):
        with patch.object(r2_upload.subprocess, "run",
                           side_effect=self._mock_run_for({k: "OK" for _, k in rs.STATE_FILES})):
            rc = rs.download(self.tmp, "https://e")
        self.assertEqual(rc, 0)
        for local_rel, _ in rs.STATE_FILES:
            self.assertTrue((self.tmp / local_rel).exists())

    def test_not_found_keeps_existing_local_bootstrap_copy(self):
        local_rel, r2_key = rs.STATE_FILES[0]
        local_path = self.tmp / local_rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text('{"bootstrap": true}', encoding="utf-8")

        outcomes = {k: "NOT_FOUND" for _, k in rs.STATE_FILES}
        with patch.object(r2_upload.subprocess, "run", side_effect=self._mock_run_for(outcomes)):
            rc = rs.download(self.tmp, "https://e")

        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(local_path.read_text()), {"bootstrap": True})

    def test_not_found_with_no_local_copy_is_not_an_error(self):
        outcomes = {k: "NOT_FOUND" for _, k in rs.STATE_FILES}
        with patch.object(r2_upload.subprocess, "run", side_effect=self._mock_run_for(outcomes)):
            rc = rs.download(self.tmp, "https://e")
        self.assertEqual(rc, 0)
        for local_rel, _ in rs.STATE_FILES:
            self.assertFalse((self.tmp / local_rel).exists())

    def test_error_hard_fails_even_with_existing_local_copy(self):
        """The dangerous case: a transient R2 outage must NOT be silently
        treated the same as 'this object has never existed'."""
        local_rel, r2_key = rs.STATE_FILES[0]
        local_path = self.tmp / local_rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text('{"real_history": "must_not_be_discarded"}', encoding="utf-8")

        outcomes = {k: "ERROR" for _, k in rs.STATE_FILES}
        with patch.object(r2_upload.subprocess, "run", side_effect=self._mock_run_for(outcomes)):
            rc = rs.download(self.tmp, "https://e")

        self.assertEqual(rc, 1)
        # And the existing (real) local copy must be left untouched, not wiped.
        self.assertEqual(json.loads(local_path.read_text()), {"real_history": "must_not_be_discarded"})

    def test_one_file_error_does_not_abort_processing_the_others(self):
        keys = [k for _, k in rs.STATE_FILES]
        outcomes = {keys[0]: "ERROR", keys[1]: "OK", keys[2]: "OK"}
        with patch.object(r2_upload.subprocess, "run", side_effect=self._mock_run_for(outcomes)):
            rc = rs.download(self.tmp, "https://e")
        self.assertEqual(rc, 1)  # overall failure reported...
        # ...but the other two files were still downloaded.
        self.assertTrue((self.tmp / rs.STATE_FILES[1][0]).exists())
        self.assertTrue((self.tmp / rs.STATE_FILES[2][0]).exists())

    def test_malformed_json_after_successful_download_is_fatal(self):
        def _fake_run(cmd, **kwargs):
            _is_download, local_path, _r2_key = _parse_cp_cmd(cmd)
            pathlib.Path(local_path).write_text("{not valid json", encoding="utf-8")
            return _proc(0)

        with patch.object(r2_upload.subprocess, "run", side_effect=_fake_run):
            rc = rs.download(self.tmp, "https://e")
        self.assertEqual(rc, 1)


class TestUpload(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_ul_"))
        for local_rel, _ in rs.STATE_FILES:
            p = self.tmp / local_rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"file": local_rel}), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_success_on_first_attempt(self):
        with patch.object(r2_upload.subprocess, "run", return_value=_proc(0)) as m:
            with patch.object(rs.time, "sleep") as sleep_mock:
                rc = rs.upload(self.tmp, "https://e")
        self.assertEqual(rc, 0)
        sleep_mock.assert_not_called()
        self.assertEqual(m.call_count, len(rs.STATE_FILES))

    def test_succeeds_after_retries(self):
        attempts_for_first_file = {"n": 0}

        def _fake_run(cmd, **kwargs):
            _is_download, local_path, _r2_key = _parse_cp_cmd(cmd)
            if "feed_state.json" in local_path:
                attempts_for_first_file["n"] += 1
                if attempts_for_first_file["n"] <= 2:
                    return _proc(1, stderr="503 Slow Down")
            return _proc(0)

        with patch.object(r2_upload.subprocess, "run", side_effect=_fake_run):
            with patch.object(rs.time, "sleep") as sleep_mock:
                rc = rs.upload(self.tmp, "https://e")
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(sleep_mock.call_count, 2)

    def test_exhausted_retries_is_fatal(self):
        with patch.object(r2_upload.subprocess, "run", return_value=_proc(1, stderr="500 Internal Error")):
            with patch.object(rs.time, "sleep"):
                rc = rs.upload(self.tmp, "https://e")
        self.assertEqual(rc, 1)

    def test_missing_local_file_is_skipped_not_an_error(self):
        empty_dir = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_ul_empty_"))
        try:
            with patch.object(r2_upload.subprocess, "run") as m:
                rc = rs.upload(empty_dir, "https://e")
            self.assertEqual(rc, 0)
            m.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_one_file_exhaustion_does_not_abort_the_others(self):
        keys = [k for _, k in rs.STATE_FILES]
        uploaded_keys = []

        def _fake_run(cmd, **kwargs):
            _is_download, _local_path, r2_key = _parse_cp_cmd(cmd)
            if r2_key == keys[0]:
                return _proc(1, stderr="500 Internal Error")
            uploaded_keys.append(r2_key)
            return _proc(0)

        with patch.object(r2_upload.subprocess, "run", side_effect=_fake_run):
            with patch.object(rs.time, "sleep"):
                rc = rs.upload(self.tmp, "https://e")
        self.assertEqual(rc, 1)
        self.assertIn(keys[1], uploaded_keys)
        self.assertIn(keys[2], uploaded_keys)


class TestRoundTripFidelity(unittest.TestCase):
    """The script must be a byte-transparent pass-through: whatever gets
    uploaded is exactly what a later download returns -- no silent mutation
    of dedup fingerprints or manifest content."""

    def test_upload_then_download_round_trips_exact_content(self):
        src_dir = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_rt_src_"))
        dst_dir = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_rt_dst_"))
        fake_bucket: dict[str, bytes] = {}
        try:
            local_rel, r2_key = rs.STATE_FILES[2]  # feed_manifest.json
            payload = {"items": [{"id": "intel--abc123", "title": "Real advisory"}]}
            src_path = src_dir / local_rel
            src_path.parent.mkdir(parents=True, exist_ok=True)
            src_path.write_text(json.dumps(payload), encoding="utf-8")

            def _fake_run(cmd, **kwargs):
                is_download, local_path, key = _parse_cp_cmd(cmd)
                if not is_download:
                    fake_bucket[key] = pathlib.Path(local_path).read_bytes()
                    return _proc(0)
                if key not in fake_bucket:
                    return _proc(1, stderr="An error occurred (404) Not Found")
                pathlib.Path(local_path).write_bytes(fake_bucket[key])
                return _proc(0)

            (dst_dir / local_rel).parent.mkdir(parents=True, exist_ok=True)
            with patch.object(r2_upload.subprocess, "run", side_effect=_fake_run):
                self.assertEqual(r2_upload.s3_cp(str(src_path), r2_upload.BUCKET_DATA, r2_key, "https://e"), True)
                outcome = r2_upload.s3_get(str(dst_dir / local_rel), r2_upload.BUCKET_DATA, r2_key, "https://e")

            self.assertEqual(outcome, "OK")
            self.assertEqual(json.loads((dst_dir / local_rel).read_text()), payload)
        finally:
            import shutil
            shutil.rmtree(src_dir, ignore_errors=True)
            shutil.rmtree(dst_dir, ignore_errors=True)


class TestCli(unittest.TestCase):
    def test_download_and_upload_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            with patch.object(sys, "argv", ["r2_state_sync.py", "--download", "--upload"]):
                rs.main()

    def test_one_mode_is_required(self):
        with self.assertRaises(SystemExit):
            with patch.object(sys, "argv", ["r2_state_sync.py"]):
                rs.main()


if __name__ == "__main__":
    unittest.main()
