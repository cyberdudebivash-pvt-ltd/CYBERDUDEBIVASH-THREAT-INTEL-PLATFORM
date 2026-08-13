"""
tests/test_safe_git_commit_artifact_recovery.py

Regression test for a P0 customer-facing intelligence staleness bug found
during live post-deploy verification of a production pipeline run.

scripts/safe_git_commit.py's conflict-recovery path (git stash -> git reset
--hard origin/main -> git stash pop) discards the local commit made moments
earlier in the same run -- which includes freshly generated
api/v1/intel/latest.json, apex.json, etc. Those files are staged and
committed by this script BEFORE the push loop runs (JSON_GUARDED /
files_to_stage), so they have nothing to stash: git stash only protects
uncommitted working-tree changes, not already-committed content. Nothing
restored these specific paths from ORIG_HEAD afterward, so on every
concurrent-push conflict (this pipeline runs long enough to overlap with
other automation that also commits to main) the freshly generated
customer-facing intelligence silently reverted to whatever origin/main had
-- which a later stage then re-uploaded to the CDN, overwriting the correct
version an earlier stage had just published moments earlier. Live evidence:
api/v1/intel/latest.json and apex.json stuck at a generation from hours
earlier despite multiple successful pipeline runs.

This test builds two real git repositories (a bare "origin" and a working
clone simulating the CI runner), forces the exact same conflict/recovery
code path production hit (a delete/modify conflict, which -X ours cannot
auto-resolve -- the same failure class the production logs showed:
"Merge failed on attempt 1 -- stash recovery"), and asserts the freshly
generated api/v1/intel/latest.json survives with its NEW content instead of
reverting to the OLD origin/main content.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT_REAL = Path(__file__).resolve().parent.parent
REAL_SCRIPT = REPO_ROOT_REAL / "scripts" / "safe_git_commit.py"


def _git(cwd, *args):
    result = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}:\n{result.stdout}\n{result.stderr}")
    return result


def _init_repo_with_identity(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestGeneratedArtifactSurvivesConflictRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sgc_test_"))
        self.bare = self.tmp / "origin.git"
        self.runner = self.tmp / "runner"

        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.bare)], check=True)

        # Seed the common-ancestor commit via a throwaway clone.
        seed = self.tmp / "seed"
        _init_repo_with_identity(seed)
        _write_json(seed / "api" / "v1" / "intel" / "latest.json",
                    {"count": 3, "items": [{"id": "a"}, {"id": "b"}, {"id": "c"}]})
        _write_json(seed / "data" / "health" / "sla_status.json", {"status": "ancestor"})
        _write_json(seed / "data" / "governance" / "trigger.json", {"v": "ancestor"})
        # Ancestor also carries a stale api/reports/index.json (written by
        # build_reports_index.py, Stage 3.3.7) -- this file family was found
        # missing from _GENERATED_ARTIFACT_PATHS during live production
        # verification (2026-08-11, run 31458784542): total_reports=11805
        # was correctly computed on disk but silently reverted to this exact
        # kind of stale prior-origin/main snapshot after conflict recovery,
        # because nothing restored it. Seeded here the same way as
        # api/v1/intel/latest.json above, to prove the fix.
        _write_json(seed / "api" / "reports" / "index.json",
                    {"total_reports": 3, "reports_listed": 3, "reports": [{"id": "a"}, {"id": "b"}, {"id": "c"}]})
        (seed / "reports").mkdir(parents=True, exist_ok=True)
        (seed / "reports" / ".gitkeep").write_text("")
        _git(seed, "add", "-A")
        _git(seed, "commit", "-q", "-m", "ancestor")
        _git(seed, "remote", "add", "origin", str(self.bare))
        _git(seed, "push", "-q", "origin", "main")

        # "other-actor" clone: simulates the concurrent governance-bot commit
        # that lands on origin/main while the pipeline run is still working.
        other = self.tmp / "other-actor"
        _git(self.tmp, "clone", "-q", str(self.bare), str(other))
        _git(other, "config", "user.email", "bot@example.com")
        _git(other, "config", "user.name", "GovernanceBot")
        _write_json(other / "data" / "governance" / "trigger.json", {"v": "origin-concurrent"})
        _git(other, "add", "-A")
        _git(other, "commit", "-q", "-m", "concurrent governance commit")
        _git(other, "push", "-q", "origin", "main")

        # "runner" clone: simulates the CI runner. Cloned from the ancestor
        # commit -- has not seen the concurrent push above yet, matching how
        # the real pipeline checks out main once at the start of a long run.
        _git(self.tmp, "clone", "-q", str(self.bare), str(self.runner))
        _git(self.runner, "checkout", "-q", "main")
        _git(self.runner, "reset", "-q", "--hard", "HEAD~1")  # drop back before the concurrent push
        _git(self.runner, "config", "user.email", "sentinel@cyberdudebivash.com")
        _git(self.runner, "config", "user.name", "CDB-Sentinel-Bot")

        # Place the real script under test at <runner>/scripts/, so its own
        # `Path(__file__).resolve().parent.parent` resolves REPO_ROOT to this
        # temp repo -- exactly like running `python3 scripts/safe_git_commit.py`
        # from within the real repo, just pointed at an isolated sandbox.
        (self.runner / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL_SCRIPT, self.runner / "scripts" / "safe_git_commit.py")

        # Pipeline "generates" fresh customer-facing intelligence this run.
        _write_json(self.runner / "api" / "v1" / "intel" / "latest.json",
                    {"count": 5, "items": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}, {"id": "e"}]})

        # Pipeline also "generates" the fresh reports registry this run.
        _write_json(self.runner / "api" / "reports" / "index.json",
                    {"total_reports": 11805, "reports_listed": 500, "reports": [{"id": "x"}]})
        # Pipeline also writes fresh SLA data locally. Left UNSTAGED here
        # (matching production: an earlier pipeline stage writes this file
        # directly, safe_git_commit.py never explicitly `git add`s it) so it
        # exercises the PRE-EXISTING manifest-guard/stash path, not the new
        # artifact-guard -- proving that mechanism still works alongside the
        # new one. (Staging it here would accidentally commit it, which
        # would defeat the point: only uncommitted changes are protected by
        # `git stash`.)
        _write_json(self.runner / "data" / "health" / "sla_status.json", {"status": "runner-fresh"})
        # Delete the trigger file locally and stage only that deletion --
        # combined with the concurrent commit's edit to the same file, this
        # is a delete/modify conflict, a class `-X ours` cannot auto-resolve,
        # forcing the exact same "Merge failed -- stash recovery" path
        # production hit.
        (self.runner / "data" / "governance" / "trigger.json").unlink()
        _git(self.runner, "add", "-A", "--", "data/governance/trigger.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_script(self):
        env = dict(os.environ)
        env.pop("GH_TOKEN", None)
        env.pop("GITHUB_REPOSITORY", None)
        env["PIPELINE_VERSION"] = "test"
        proc = subprocess.run(
            [sys.executable, str(self.runner / "scripts" / "safe_git_commit.py")],
            cwd=self.runner,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return proc

    def test_conflict_is_actually_forced(self):
        """Sanity check: the scenario must actually reproduce a merge failure,
        otherwise the rest of this test proves nothing."""
        proc = self._run_script()
        self.assertIn("stash recovery", proc.stdout,
                       f"scenario did not force the conflict-recovery path -- test is not "
                       f"reproducing the production failure mode.\nstdout={proc.stdout}")

    def test_fresh_generated_artifact_survives_conflict_recovery(self):
        proc = self._run_script()
        self.assertEqual(proc.returncode, 0, f"script must always exit 0\nstdout={proc.stdout}\nstderr={proc.stderr}")

        latest_path = self.runner / "api" / "v1" / "intel" / "latest.json"
        latest = json.loads(latest_path.read_text())
        self.assertEqual(
            latest["count"], 5,
            f"freshly generated latest.json (5 items) must survive conflict recovery, "
            f"not revert to the stale origin/main version (3 items). Got: {latest}"
        )

        self.assertIn("[artifact-guard]", proc.stdout)
        self.assertIn(
            "REVERTED by reset --hard", proc.stdout,
            "the guard's own log must make a real revert-and-restore visible "
            "(silent rollback is unacceptable)"
        )

    def test_fix_actually_reaches_origin_main_not_just_local_disk(self):
        """`git push` publishes commits, not working-tree/staged state. Every
        restore guard (including the pre-existing reports-guard) only
        checks out files into the index/working tree -- if nothing commits
        that afterward, `git reset --hard origin/main` leaves local HEAD
        identical to origin/main, so the push that follows has nothing new
        to send and exits 0 trivially ("Everything up-to-date") while the
        restored content never leaves the runner's disk. This proves the
        recovery commit actually publishes the correction to the remote,
        not just the local worktree checked by the test above."""
        proc = self._run_script()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("[recovery-commit] Committed restored artifacts", proc.stdout)

        # Refresh the local remote-tracking ref explicitly rather than
        # relying on git's opportunistic post-push update (version-dependent
        # behavior) -- read directly from the bare "origin" repo the script
        # actually pushed to.
        _git(self.runner, "fetch", "-q", "origin", "main")
        show = subprocess.run(
            ["git", "show", "origin/main:api/v1/intel/latest.json"],
            cwd=self.runner, capture_output=True, text=True,
        )
        self.assertEqual(show.returncode, 0, f"could not read the file back from the pushed origin/main: {show.stderr}")
        published = json.loads(show.stdout)
        self.assertEqual(
            published["count"], 5,
            f"the restored content must actually be pushed to origin/main, not just "
            f"left on local disk. origin/main has: {published}"
        )

    def test_reports_registry_survives_conflict_recovery(self):
        """api/reports/index.json (Stage 3.3.7's build_reports_index.py
        output) must survive the same conflict-recovery path as
        api/v1/intel/latest.json -- this file family was the one actually
        found reverted live (total_reports=356 served instead of the
        11805 the pipeline run genuinely computed)."""
        proc = self._run_script()
        self.assertEqual(proc.returncode, 0, f"script must always exit 0\nstdout={proc.stdout}\nstderr={proc.stderr}")

        index_path = self.runner / "api" / "reports" / "index.json"
        index_data = json.loads(index_path.read_text())
        self.assertEqual(
            index_data["total_reports"], 11805,
            f"freshly generated api/reports/index.json (total_reports=11805) must "
            f"survive conflict recovery, not revert to the stale origin/main "
            f"version (total_reports=3). Got: {index_data}"
        )
        self.assertIn("api/reports/index.json", proc.stdout)

    def test_unrelated_governance_style_file_still_survives(self):
        """Proves the new artifact-guard doesn't regress the pre-existing
        manifest-guard mechanism for files it doesn't own."""
        proc = self._run_script()
        self.assertEqual(proc.returncode, 0)

        sla_path = self.runner / "data" / "health" / "sla_status.json"
        sla = json.loads(sla_path.read_text())
        self.assertEqual(
            sla["status"], "runner-fresh",
            "the runner's own locally-written sla_status.json must survive "
            "conflict recovery via the pre-existing manifest-guard snapshot"
        )


class TestHtmlReportContentReversionSurvivesConflictRecovery(unittest.TestCase):
    """RX-PUB-A0: the pre-existing reports-guard (P0-FIX v154.0.0) only
    detects HTML reports that VANISH after `git reset --hard origin/main`
    (a path-set difference). It is blind to a report whose PATH already
    exists on origin/main (any report from a prior run -- the common case,
    since reports/ retains recent history) getting its CONTENT silently
    reverted to the stale origin/main bytes while the path itself survives.
    Confirmed live: a real production report (intel--20282e88b1f49bf2) was
    found served with pre-fix content weeks after the generator was fixed
    and re-verified to regenerate correctly, with no missing-file signal
    anywhere in the pipeline. This test builds the same delete/modify
    concurrent-push conflict as the class above, but for an HTML report
    whose path exists in BOTH the ancestor commit (stale content) and the
    runner's fresh local commit (corrected content) -- exactly the case the
    old path-set-only check could not see -- and asserts the fresh content
    survives."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sgc_html_test_"))
        self.bare = self.tmp / "origin.git"
        self.runner = self.tmp / "runner"

        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.bare)], check=True)

        seed = self.tmp / "seed"
        _init_repo_with_identity(seed)
        report_rel = Path("reports") / "2026" / "08" / "intel--test0000000000.html"
        (seed / report_rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / report_rel).write_text(
            "<!DOCTYPE html><html><body>STALE pre-fix content "
            "PATCH WITHIN 14 DAYS</body></html>",
            encoding="utf-8",
        )
        _write_json(seed / "data" / "governance" / "trigger.json", {"v": "ancestor"})
        _git(seed, "add", "-A")
        _git(seed, "commit", "-q", "-m", "ancestor")
        _git(seed, "remote", "add", "origin", str(self.bare))
        _git(seed, "push", "-q", "origin", "main")

        other = self.tmp / "other-actor"
        _git(self.tmp, "clone", "-q", str(self.bare), str(other))
        _git(other, "config", "user.email", "bot@example.com")
        _git(other, "config", "user.name", "GovernanceBot")
        _write_json(other / "data" / "governance" / "trigger.json", {"v": "origin-concurrent"})
        _git(other, "add", "-A")
        _git(other, "commit", "-q", "-m", "concurrent governance commit")
        _git(other, "push", "-q", "origin", "main")

        _git(self.tmp, "clone", "-q", str(self.bare), str(self.runner))
        _git(self.runner, "checkout", "-q", "main")
        _git(self.runner, "reset", "-q", "--hard", "HEAD~1")
        _git(self.runner, "config", "user.email", "sentinel@cyberdudebivash.com")
        _git(self.runner, "config", "user.name", "CDB-Sentinel-Bot")

        (self.runner / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL_SCRIPT, self.runner / "scripts" / "safe_git_commit.py")

        # Pipeline regenerates this SAME report this run with corrected
        # content, then safe_git_commit.py's normal staging (files_to_stage
        # includes reports/) commits it locally BEFORE the push loop runs --
        # matching production exactly (Zero-skip regenerates every in-window
        # report every run, then it is git-added/committed same as any other
        # tracked file).
        self.report_path = self.runner / report_rel
        self.report_path.write_text(
            "<!DOCTYPE html><html><body>FRESH corrected content "
            "no unsupported patch-window claim</body></html>",
            encoding="utf-8",
        )
        _git(self.runner, "add", "-A", "--", str(report_rel))
        _git(self.runner, "commit", "-q", "-m", "runner: regenerated report this run")

        (self.runner / "data" / "governance" / "trigger.json").unlink()
        _git(self.runner, "add", "-A", "--", "data/governance/trigger.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_script(self):
        env = dict(os.environ)
        env.pop("GH_TOKEN", None)
        env.pop("GITHUB_REPOSITORY", None)
        env["PIPELINE_VERSION"] = "test"
        proc = subprocess.run(
            [sys.executable, str(self.runner / "scripts" / "safe_git_commit.py")],
            cwd=self.runner, env=env, capture_output=True, text=True, timeout=60,
        )
        return proc

    def test_regenerated_report_content_survives_conflict_recovery(self):
        proc = self._run_script()
        self.assertEqual(proc.returncode, 0, f"script must always exit 0\nstdout={proc.stdout}\nstderr={proc.stderr}")

        content = self.report_path.read_text(encoding="utf-8")
        self.assertIn(
            "FRESH corrected content", content,
            f"the regenerated report's content must survive conflict recovery, "
            f"not silently revert to the stale ancestor content -- this is the exact "
            f"live incident (intel--20282e88b1f49bf2 served pre-fix content weeks "
            f"after the generator fix). Got: {content!r}"
        )
        self.assertNotIn("PATCH WITHIN 14 DAYS", content)

        self.assertIn("[reports-guard]", proc.stdout)
        self.assertIn(
            "CONTENT-REVERTED", proc.stdout,
            "the guard must make a content-only revert visible in its own log -- "
            "the pre-fix guard produced zero output for this case because the "
            "path-set difference was empty (silent divergence)."
        )

    def test_fix_actually_reaches_origin_main(self):
        proc = self._run_script()
        self.assertEqual(proc.returncode, 0)

        _git(self.runner, "fetch", "-q", "origin", "main")
        report_rel_str = "reports/2026/08/intel--test0000000000.html"
        show = subprocess.run(
            ["git", "show", f"origin/main:{report_rel_str}"],
            cwd=self.runner, capture_output=True, text=True,
        )
        self.assertEqual(show.returncode, 0, f"could not read the file back from pushed origin/main: {show.stderr}")
        self.assertIn("FRESH corrected content", show.stdout)


class TestReportsRegistryInGeneratedArtifactGuard(unittest.TestCase):
    """Static guard: all three files build_reports_index.py (Stage 3.3.7)
    writes must be listed in safe_git_commit.py's _GENERATED_ARTIFACT_PATHS,
    or a future concurrent-push conflict silently reverts them again with
    no warning at all (exactly what happened live before this fix -- the
    revert produced zero log output because the file simply wasn't checked)."""

    def test_all_three_reports_registry_files_are_guarded(self):
        source = REAL_SCRIPT.read_text(encoding="utf-8")
        start = source.index("_GENERATED_ARTIFACT_PATHS = [")
        end = source.index("]", start)
        guard_list_src = source[start:end]
        for path in (
            "api/reports/index.json",
            "api/reports/latest.json",
            "api/reports/stats.json",
        ):
            self.assertIn(
                f'"{path}"', guard_list_src,
                f"{path} (written by build_reports_index.py, Stage 3.3.7) is missing "
                f"from _GENERATED_ARTIFACT_PATHS -- a concurrent-push conflict will "
                f"silently revert it with no restore and no warning."
            )


if __name__ == "__main__":
    unittest.main()
