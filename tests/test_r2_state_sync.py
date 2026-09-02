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

    def test_nosuchbucket_returns_error_not_not_found(self):
        """CodeRabbit review finding (verified, not taken on faith): AWS's
        actual NoSuchBucket message is "An error occurred (NoSuchBucket)
        when calling the HeadObject operation: The specified bucket does
        not exist" -- which contains "does not exist", one of the generic
        NOT_FOUND substrings this function already matched on. A wrong or
        misconfigured bucket name would have been silently misclassified as
        "this object simply hasn't been created yet" and treated as a safe
        bootstrap case instead of the configuration error it actually is."""
        with patch.object(r2_upload.subprocess, "run",
                           return_value=_proc(1, stderr="An error occurred (NoSuchBucket) when calling the HeadObject operation: The specified bucket does not exist")):
            self.assertEqual(r2_upload.s3_get("/tmp/x.json", "b", "k", "https://e"), "ERROR")


class TestStateFilesManifest(unittest.TestCase):
    """STATE_FILES is the single source of truth other tests (download/
    upload/wiring) drive off of via len()/iteration -- these tests pin its
    actual expected contents directly, so a future accidental removal of an
    entry doesn't silently pass just because the generic tests adapted to
    the shorter list."""

    def test_exactly_nine_files_migrated(self):
        self.assertEqual(len(rs.STATE_FILES), 9)

    def test_all_five_intelligence_repository_registry_files_present(self):
        """CodeRabbit review finding on this migration (verified, not taken
        on faith): these 5 files were still on multi-source-intel.yml's
        doomed-to-fail git push after the 4 files above were pulled off it."""
        local_paths = [local for local, _ in rs.STATE_FILES]
        for f in (
            "data/intelligence_repository/intelligence_index.json",
            "data/intelligence_repository/advisory_registry.json",
            "data/intelligence_repository/intel_retention_registry.json",
            "data/intelligence_repository/intel_lifecycle_registry.json",
            "data/intelligence_repository/historical_feed_registry.json",
        ):
            self.assertIn(f, local_paths)

    def test_top_level_feed_manifest_is_present_with_path_mirrored_key(self):
        self.assertIn(
            ("data/feed_manifest.json", "data/feed_manifest.json"),
            rs.STATE_FILES,
        )

    def test_top_level_and_stix_feed_manifest_are_distinct_entries(self):
        """These are two different files (the EII-enriched manifest vs. the
        raw STIX ingestion bundle) -- must never collapse onto the same
        local path or the same R2 key."""
        local_paths = [local for local, _ in rs.STATE_FILES]
        r2_keys = [key for _, key in rs.STATE_FILES]
        self.assertIn("data/feed_manifest.json", local_paths)
        self.assertIn("data/stix/feed_manifest.json", local_paths)
        self.assertEqual(len(local_paths), len(set(local_paths)))
        self.assertEqual(len(r2_keys), len(set(r2_keys)))


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_dl_"))
        # STATE_DIRS uses a different (sync, not cp) subprocess command shape
        # than the STATE_FILES tests below fake -- these tests are about
        # STATE_FILES semantics specifically, so STATE_DIRS is neutralized
        # to a trivial success here. TestStateDirs below covers its own
        # behavior directly.
        patcher = patch.object(rs, "s3_sync_download", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_malformed_json_after_download_preserves_existing_local_copy(self):
        """PRODUCTION-VERIFICATION HARDENING (2026-09-02): s3_get() used to
        write straight to local_path, so a malformed download had already
        overwritten a good local copy by the time this function's own
        validation ran -- correctly reported as fatal (rc=1), but the file
        on disk was left corrupt, not restored. download() now stages into
        a .tmp sibling first and only promotes it on successful validation,
        so a real pre-existing local copy must survive a malformed download
        completely unchanged, not just get an accurate error code."""
        local_rel, r2_key = rs.STATE_FILES[0]
        local_path = self.tmp / local_rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text('{"real_history": "must_not_be_discarded"}', encoding="utf-8")

        def _fake_run(cmd, **kwargs):
            _is_download, dst, key = _parse_cp_cmd(cmd)
            if key == r2_key:
                pathlib.Path(dst).write_text("{not valid json", encoding="utf-8")
            else:
                pathlib.Path(dst).write_text(json.dumps({"ok": True}), encoding="utf-8")
            return _proc(0)

        with patch.object(r2_upload.subprocess, "run", side_effect=_fake_run):
            rc = rs.download(self.tmp, "https://e")

        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(local_path.read_text()), {"real_history": "must_not_be_discarded"})
        # No leftover .tmp sibling, success or rejection.
        self.assertFalse((self.tmp / (local_rel + ".r2sync.tmp")).exists())

    def test_wrong_shape_json_is_rejected_and_preserves_existing_local_copy(self):
        """Section 19 Case C of the P0 R2 hardening mandate: valid JSON that
        is not the expected shape (here, a bare string instead of a list/
        object) must be rejected the same as malformed JSON, not silently
        accepted just because json.loads() succeeds."""
        local_rel, r2_key = rs.STATE_FILES[0]
        local_path = self.tmp / local_rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text('{"real_history": "must_not_be_discarded"}', encoding="utf-8")

        def _fake_run(cmd, **kwargs):
            _is_download, dst, key = _parse_cp_cmd(cmd)
            if key == r2_key:
                pathlib.Path(dst).write_text(json.dumps("just a string, not a list or object"), encoding="utf-8")
            else:
                pathlib.Path(dst).write_text(json.dumps({"ok": True}), encoding="utf-8")
            return _proc(0)

        with patch.object(r2_upload.subprocess, "run", side_effect=_fake_run):
            rc = rs.download(self.tmp, "https://e")

        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(local_path.read_text()), {"real_history": "must_not_be_discarded"})

    def test_valid_correctly_shaped_download_replaces_existing_local_copy(self):
        """Sanity counterpart to the two rejection tests above: a valid,
        correctly-shaped download must still replace an existing local file
        (the hardening must reject bad content, not everything)."""
        local_rel, r2_key = rs.STATE_FILES[0]
        local_path = self.tmp / local_rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text('{"stale": true}', encoding="utf-8")

        outcomes = {k: "OK" for _, k in rs.STATE_FILES}
        with patch.object(r2_upload.subprocess, "run", side_effect=self._mock_run_for(outcomes)):
            rc = rs.download(self.tmp, "https://e")

        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(local_path.read_text()), {"ok": True})


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


class TestStateDirs(unittest.TestCase):
    """STATE_DIRS (data/intelligence_repository/advisories/) uses sync, not
    cp, semantics -- these tests exercise that path directly rather than
    relying on TestDownload/TestUpload's STATE_FILES-shaped mocking."""

    def test_exactly_one_dir_migrated(self):
        self.assertEqual(len(rs.STATE_DIRS), 1)
        self.assertIn(
            ("data/intelligence_repository/advisories", "data/intelligence_repository/advisories"),
            rs.STATE_DIRS,
        )

    def test_download_calls_sync_for_each_configured_dir(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_dirs_dl_"))
        try:
            with patch.object(rs, "s3_sync_download", return_value=True) as m:
                with patch.object(rs, "s3_get", return_value="NOT_FOUND"):
                    rc = rs.download(tmp, "https://e")
            self.assertEqual(rc, 0)
            self.assertEqual(m.call_count, len(rs.STATE_DIRS))
            for local_rel, r2_prefix in rs.STATE_DIRS:
                m.assert_any_call(str(tmp / local_rel), rs.BUCKET_DATA, r2_prefix, "https://e")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_download_sync_failure_is_an_error_not_silently_ignored(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_dirs_dl_"))
        try:
            with patch.object(rs, "s3_sync_download", return_value=False):
                with patch.object(rs, "s3_get", return_value="NOT_FOUND"):
                    rc = rs.download(tmp, "https://e")
            self.assertEqual(rc, 1)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_upload_skips_missing_or_empty_dir_not_an_error(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_dirs_ul_empty_"))
        try:
            with patch.object(r2_upload.subprocess, "run") as m:
                rc = rs.upload(tmp, "https://e")
            self.assertEqual(rc, 0)
            m.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_upload_syncs_dir_with_content(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_dirs_ul_"))
        try:
            local_rel, _ = rs.STATE_DIRS[0]
            adv_dir = tmp / local_rel
            adv_dir.mkdir(parents=True, exist_ok=True)
            (adv_dir / "registry_202609.json").write_text('{"items": []}', encoding="utf-8")

            with patch.object(rs, "s3_sync", return_value=True) as m:
                rc = rs.upload(tmp, "https://e")
            self.assertEqual(rc, 0)
            m.assert_called_once()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_upload_sync_exhaustion_is_fatal_and_reported_as_mixed_state_when_partial(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_dirs_ul_"))
        try:
            local_rel, _ = rs.STATE_DIRS[0]
            adv_dir = tmp / local_rel
            adv_dir.mkdir(parents=True, exist_ok=True)
            (adv_dir / "registry_202609.json").write_text('{"items": []}', encoding="utf-8")
            for f, _ in rs.STATE_FILES:
                p = tmp / f
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("{}", encoding="utf-8")

            with patch.object(rs, "s3_sync", return_value=False):
                with patch.object(rs, "s3_cp", return_value=True):
                    with patch.object(rs.time, "sleep"):
                        with self.assertLogs("r2-state-sync", level="ERROR") as cm:
                            rc = rs.upload(tmp, "https://e")
            self.assertEqual(rc, 1)
            self.assertTrue([line for line in cm.output if "MIXED STATE" in line])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestMixedStateVisibility(unittest.TestCase):
    """CodeRabbit review finding on PR #332: R2 has no cross-object
    transactions, so a run where some of the 4 STATE_FILES upload
    successfully and others exhaust their retries leaves R2 in a genuinely
    inconsistent mix -- and the original per-file-only error message
    ('this run's state was NOT persisted') was misleading in exactly that
    case, since some of it *had* been. These tests assert the partial
    failure is loudly, distinctly diagnosable rather than indistinguishable
    from a total failure."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_mixed_"))
        for local_rel, _ in rs.STATE_FILES:
            p = self.tmp / local_rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"file": local_rel}), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_partial_failure_logs_mixed_state_warning(self):
        keys = [k for _, k in rs.STATE_FILES]

        def _fake_run(cmd, **kwargs):
            _is_download, _local_path, r2_key = _parse_cp_cmd(cmd)
            if r2_key == keys[0]:
                return _proc(1, stderr="500 Internal Error")
            return _proc(0)

        with patch.object(r2_upload.subprocess, "run", side_effect=_fake_run):
            with patch.object(rs.time, "sleep"):
                with self.assertLogs("r2-state-sync", level="ERROR") as cm:
                    rc = rs.upload(self.tmp, "https://e")

        self.assertEqual(rc, 1)
        mixed_state_lines = [line for line in cm.output if "MIXED STATE" in line]
        self.assertTrue(mixed_state_lines, "expected a MIXED STATE warning when some files "
                                            "succeeded and others failed")
        # Names both the stale (failed) and fresh (succeeded) files, not just a count.
        self.assertIn(keys[0], mixed_state_lines[0])
        for k in keys[1:]:
            self.assertIn(k, mixed_state_lines[0])

    def test_total_failure_does_not_log_mixed_state_warning(self):
        """All 4 files failing is not 'mixed' -- it's uniformly stale, same
        as before this fix. The MIXED STATE signal must be reserved for the
        genuinely partial case so it isn't cried wolf on every outage."""
        with patch.object(r2_upload.subprocess, "run", return_value=_proc(1, stderr="500 Internal Error")):
            with patch.object(rs.time, "sleep"):
                with self.assertLogs("r2-state-sync", level="ERROR") as cm:
                    rc = rs.upload(self.tmp, "https://e")

        self.assertEqual(rc, 1)
        self.assertFalse([line for line in cm.output if "MIXED STATE" in line])

    def test_total_success_does_not_log_mixed_state_warning(self):
        with patch.object(r2_upload.subprocess, "run", return_value=_proc(0)):
            rc = rs.upload(self.tmp, "https://e")
        self.assertEqual(rc, 0)

    def test_single_file_failure_message_does_not_overclaim_whole_run_lost(self):
        """The original wording implied the entire run's state was lost even
        when only one of several files failed -- must now scope the claim to
        the file it actually describes."""
        keys = [k for _, k in rs.STATE_FILES]

        def _fake_run(cmd, **kwargs):
            _is_download, _local_path, r2_key = _parse_cp_cmd(cmd)
            if r2_key == keys[0]:
                return _proc(1, stderr="500 Internal Error")
            return _proc(0)

        with patch.object(r2_upload.subprocess, "run", side_effect=_fake_run):
            with patch.object(rs.time, "sleep"):
                with self.assertLogs("r2-state-sync", level="ERROR") as cm:
                    rs.upload(self.tmp, "https://e")

        per_file_failure = [line for line in cm.output if keys[0] in line and "MIXED STATE" not in line]
        self.assertTrue(per_file_failure)
        self.assertNotIn("this run's state was NOT persisted", per_file_failure[0])


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


class TestTopLevelFeedManifestRoundTrip(unittest.TestCase):
    """Same round-trip guarantee as TestRoundTripFidelity above, specifically
    for data/feed_manifest.json (STATE_FILES[3]) -- the EII-enriched
    manifest, not the STIX one already covered by that test. Written by
    apex_quality_field_backfill.py / cve_id_backfill.py / etc. in place, so
    an upload that silently truncated or reordered its content would corrupt
    accumulated enrichment history, not just fail to add new items."""

    def test_upload_then_download_round_trips_exact_content(self):
        src_dir = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_rt2_src_"))
        dst_dir = pathlib.Path(tempfile.mkdtemp(prefix="r2sync_rt2_dst_"))
        fake_bucket: dict[str, bytes] = {}
        try:
            local_rel, r2_key = next(
                (local, key) for local, key in rs.STATE_FILES if local == "data/feed_manifest.json"
            )
            payload = {
                "version": "70.0",
                "advisories": [{"id": "intel--abc123", "cve_id": "CVE-2026-4075", "apex_risk": 91.2}],
            }
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
