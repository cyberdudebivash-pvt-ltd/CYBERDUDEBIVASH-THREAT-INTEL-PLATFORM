"""
tests/test_r2_state_migration_wiring.py

Structural regression tests for the R2 state migration (see
scripts/r2_state_sync.py and tests/test_r2_state_sync.py for the sync logic
itself). These tests assert the *wiring* around that logic is correct:
workflow step ordering, .gitignore, obsolete git-staging removal, and the
existing concurrency safeguard staying intact -- the class of thing a unit
test of r2_state_sync.py alone cannot catch.
"""
import pathlib
import subprocess
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MULTI_SOURCE_YML = REPO_ROOT / ".github" / "workflows" / "multi-source-intel.yml"
SENTINEL_BLOGGER_YML = REPO_ROOT / ".github" / "workflows" / "sentinel-blogger.yml"
GITIGNORE = REPO_ROOT / ".gitignore"

MIGRATED_FILES = [
    "data/cache/feed_state.json",
    "data/processed_intel.json",
    "data/stix/feed_manifest.json",
    "data/feed_manifest.json",
]

# CodeRabbit review finding on this migration (verified, not taken on
# faith): these 5 registry files + the advisories/ chunk directory were
# still on multi-source-intel.yml's doomed-to-fail git push after the 4
# files above were pulled off it -- same root cause, same fix, tracked
# separately here since they were a later, second round of the migration.
MIGRATED_REGISTRY_FILES = [
    "data/intelligence_repository/intelligence_index.json",
    "data/intelligence_repository/advisory_registry.json",
    "data/intelligence_repository/intel_retention_registry.json",
    "data/intelligence_repository/intel_lifecycle_registry.json",
    "data/intelligence_repository/historical_feed_registry.json",
]
MIGRATED_REGISTRY_DIR = "data/intelligence_repository/advisories/"


def _step_names(doc: dict, job_key: str | None = None) -> list[str]:
    jobs = doc["jobs"]
    job = jobs[job_key] if job_key else next(iter(jobs.values()))
    return [s.get("name") for s in job["steps"]]


class TestGitignoreCompletesTheMigration(unittest.TestCase):
    """The gitignore comments for these files already declared the intent
    ("Committed to GitHub = auth bypass. Do not un-ignore these lines" /
    "MUST be committed so all downstream workflows find them on checkout")
    -- these tests confirm the intent is now actually enforced, not just
    documented."""

    def test_all_four_files_are_gitignored(self):
        for f in MIGRATED_FILES:
            result = subprocess.run(
                ["git", "check-ignore", f], cwd=REPO_ROOT, capture_output=True,
            )
            self.assertEqual(
                result.returncode, 0,
                f"{f} is not gitignored -- the R2 migration is incomplete "
                f"(a fresh `git add .` would re-track it).",
            )

    def test_none_of_the_four_files_are_git_tracked(self):
        result = subprocess.run(
            ["git", "ls-files"] + MIGRATED_FILES,
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(
            result.stdout.strip(), "",
            f"these files are still git-tracked despite being gitignored "
            f"(git rm --cached was needed, not just a .gitignore entry): "
            f"{result.stdout.strip()}",
        )

    def test_registry_files_and_advisories_dir_are_gitignored(self):
        for f in MIGRATED_REGISTRY_FILES + [MIGRATED_REGISTRY_DIR]:
            result = subprocess.run(
                ["git", "check-ignore", f], cwd=REPO_ROOT, capture_output=True,
            )
            self.assertEqual(
                result.returncode, 0,
                f"{f} is not gitignored -- the R2 migration is incomplete "
                f"(a fresh `git add .` would re-track it).",
            )

    def test_registry_files_and_advisories_dir_are_not_git_tracked(self):
        result = subprocess.run(
            ["git", "ls-files"] + MIGRATED_REGISTRY_FILES + [MIGRATED_REGISTRY_DIR],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(
            result.stdout.strip(), "",
            f"these are still git-tracked despite being gitignored "
            f"(git rm --cached was needed, not just a .gitignore entry): "
            f"{result.stdout.strip()}",
        )

    def test_unrelated_cache_file_is_unaffected(self):
        """data/cache/intel_index.json is explicitly out of scope for this
        migration -- must still be tracked."""
        result = subprocess.run(
            ["git", "check-ignore", "data/cache/intel_index.json"],
            cwd=REPO_ROOT, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0, "intel_index.json must NOT be gitignored")

        result = subprocess.run(
            ["git", "ls-files", "data/cache/intel_index.json"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.stdout.strip(), "data/cache/intel_index.json")


class TestMultiSourceIntelWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(MULTI_SOURCE_YML, encoding="utf-8") as f:
            cls.doc = yaml.safe_load(f)
        cls.names = _step_names(cls.doc)
        cls.text = MULTI_SOURCE_YML.read_text(encoding="utf-8")

    def test_download_step_runs_before_ingestion(self):
        self.assertLess(
            self.names.index("Download Intel State from R2"),
            self.names.index("True Incremental Intel Ingestion"),
        )

    def test_upload_step_runs_after_ingestion_and_before_commit(self):
        ingest = self.names.index("True Incremental Intel Ingestion")
        upload = self.names.index("Upload Intel State to R2")
        commit = self.names.index("Commit Intel State & Manifest")
        self.assertLess(ingest, upload)
        self.assertLess(upload, commit)

    def test_r2_credentials_present_on_both_new_steps(self):
        for name in ("Download Intel State from R2", "Upload Intel State to R2"):
            step = next(s for s in self.doc["jobs"]["multi-source-enrichment"]["steps"] if s.get("name") == name)
            env = step.get("env", {})
            for key in ("CF_ACCOUNT_ID", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
                self.assertIn(key, env, f"{name} is missing {key}")

    def test_migrated_files_no_longer_staged_in_commit_step(self):
        """CodeRabbit review finding on this migration (verified and fixed):
        this step's git push was guaranteed to fail on every run regardless
        of which files it carried -- main's branch ruleset rejects ANY
        direct push, not just pushes of specific paths -- so the fix is a
        complete no-op, not just removing the 3 originally-migrated files
        while leaving the 5 registry files + advisories/ still staged."""
        commit_step = next(
            s for s in self.doc["jobs"]["multi-source-enrichment"]["steps"]
            if s.get("name") == "Commit Intel State & Manifest"
        )
        run_block = commit_step["run"]
        self.assertNotIn("git add -f", run_block)
        self.assertNotIn("git push", run_block)

    def test_persistence_engine_runs_before_upload_not_after(self):
        """CodeRabbit review finding on this migration (verified and fixed):
        intel_persistence_engine.py -- which writes the 5 registry files +
        advisories/ -- used to run inside the old "Commit Intel State &
        Manifest" step, which was AFTER "Upload Intel State to R2". That
        meant the upload always published the PREVIOUS run's registry
        content, never the current run's. Now a dedicated step runs it
        before the upload."""
        persistence = self.names.index("Run Intelligence Persistence Engine")
        upload = self.names.index("Upload Intel State to R2")
        self.assertLess(persistence, upload)

    def test_existing_concurrency_safeguard_is_untouched(self):
        """multi-source-intel.yml and sentinel-blogger.yml's staggered cron
        schedules (see r2_state_sync.py's own docstring) are the ONLY
        protection against a concurrent write race on the shared R2 state --
        this migration must not accidentally remove or weaken it."""
        concurrency = self.doc["jobs"]["multi-source-enrichment"].get("concurrency") \
            or self.doc.get("concurrency")
        self.assertIsNotNone(concurrency, "concurrency group was removed")
        self.assertEqual(concurrency.get("group"), "sentinel-data-writer")
        self.assertFalse(concurrency.get("cancel-in-progress", True))

    def test_workflow_is_valid_yaml(self):
        self.assertIn("multi-source-enrichment", self.doc["jobs"])


class TestSentinelBloggerWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SENTINEL_BLOGGER_YML, encoding="utf-8") as f:
            cls.doc = yaml.safe_load(f)
        cls.job_key = next(iter(cls.doc["jobs"]))
        cls.steps = cls.doc["jobs"][cls.job_key]["steps"]
        cls.names = [s.get("name") for s in cls.steps]

    def test_download_step_runs_before_master_orchestrator(self):
        self.assertLess(
            self.names.index("Download Intel State from R2"),
            self.names.index("STAGE 1-3 - Master Pipeline Orchestrator"),
        )

    def test_download_step_runs_after_required_directories_exist(self):
        """data/stix/ must exist before the download step tries to write
        data/stix/feed_manifest.json into it."""
        self.assertLess(
            self.names.index("Ensure required directories"),
            self.names.index("Download Intel State from R2"),
        )

    def test_upload_step_runs_after_stage_3_5_and_final_r2_sync(self):
        stage_35 = self.names.index("STAGE 3.5 - Upload Intel to Cloudflare R2 (MANDATORY)")
        stage_41 = self.names.index("STAGE 4.1 - Final R2 Full Sync (v184.0 -- post-git-push complete feed)")
        upload = self.names.index("Upload Intel State to R2 (final, post-enrichment)")
        self.assertLess(stage_35, upload)
        self.assertLess(stage_41, upload)

    def test_upload_step_is_non_fatal(self):
        """Unlike multi-source-intel.yml (where this is the last step), this
        step sits mid-pipeline -- a hard sys.exit(1)-style failure here must
        not be allowed to cascade-skip the dozens of steps after it (Pages
        deploy, regression gates) the way STAGE 0.0's encoding_guard.py bug
        used to. Must follow the same if:always() + captured-exit-code
        pattern as the existing STAGE 4.1 step right before it."""
        step = next(s for s in self.steps if s.get("name") == "Upload Intel State to R2 (final, post-enrichment)")
        self.assertEqual(step.get("if"), "always()")
        self.assertIn("if ! python3 scripts/r2_state_sync.py --upload", step["run"])
        self.assertNotIn("exit 1", step["run"])

    def test_download_step_r2_credentials_present(self):
        step = next(s for s in self.steps if s.get("name") == "Download Intel State from R2")
        env = step.get("env", {})
        for key in ("CF_ACCOUNT_ID", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            self.assertIn(key, env)

    def test_workflow_is_valid_yaml(self):
        self.assertTrue(len(self.steps) > 100)

    def test_every_feed_manifest_writer_runs_between_download_and_upload(self):
        """data/feed_manifest.json (the EII-enriched manifest) has no
        dedicated download-before/upload-after step of its own -- it rides
        the same two steps as the other three STATE_FILES entries. That is
        only correct if every script that patches this file in place runs
        strictly between those two steps; otherwise the upload would ship a
        stale pre-enrichment copy, or a script would read a copy older than
        what this run's download just fetched. Confirmed by reading each
        script's own read/patch logic, not assumed from naming."""
        download = self.names.index("Download Intel State from R2")
        upload = self.names.index("Upload Intel State to R2 (final, post-enrichment)")
        writer_step_name_fragments = [
            "STAGE 1-3 - Master Pipeline Orchestrator",  # run_pipeline.py
            "apex_quality_field_backfill.py",
            "cve_id_backfill.py",
            "actor_attribution_enricher.py",
            "generate_advisory_pdfs.py",
            "threat_graph_engine.py",
        ]
        for fragment in writer_step_name_fragments:
            matches = [
                i for i, s in enumerate(self.steps)
                if fragment in (s.get("name") or "") or fragment in (s.get("run") or "")
            ]
            self.assertTrue(matches, f"no step found invoking/matching {fragment!r}")
            for i in matches:
                self.assertGreater(
                    i, download,
                    f"step {i} ({self.names[i]!r}, matched {fragment!r}) runs "
                    f"before the R2 download -- it would read stale/missing state.",
                )
                self.assertLess(
                    i, upload,
                    f"step {i} ({self.names[i]!r}, matched {fragment!r}) runs "
                    f"after the R2 upload -- its writes would never be persisted.",
                )


if __name__ == "__main__":
    unittest.main()
