"""
tests/test_p0_r2_stix_manifest_diagnostic_read_only.py

P0-MP.1A Section 2 requirement: a static/structural proof that
scripts/p0_r2_stix_manifest_diagnostic.py contains no remote-mutating R2/S3
operation. This diagnostic exists specifically because it runs against
production R2 credentials in CI -- the mission's read-only guarantee is not
credible without an automated check, not just a promise in a docstring.

Approach: scan the script's own source text (not execute it) for every
forbidden token, and separately assert that every "aws s3api <verb>" /
"aws s3 <verb>" invocation the script constructs uses only an allowlisted
read-only verb. A pure source-text check has no R2 credentials, no network
access, and cannot itself mutate anything -- it proves the property by
construction, independent of whether CI credentials happen to be present
when this test runs.
"""
import re
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "p0_r2_stix_manifest_diagnostic.py"

# Any of these substrings appearing in the script source is an automatic
# failure -- these are the mutating operations the mission's Section 2
# explicitly prohibits (aws CLI subcommand form, boto3 method form, and
# generic verbs), independent of context.
FORBIDDEN_SUBSTRINGS = [
    "put-object", "put_object",
    "delete-object", "delete_object",
    "copy-object", "copy_object",
    "restore-object", "restore_object",
    "\"s3\", \"cp\"",   # aws s3 cp (uploading TO remote)
    "\"s3\", \"sync\"", # aws s3 sync (uploading TO remote)
    "\"s3\", \"mv\"",
    "\"s3\", \"rm\"",
    "abort-multipart-upload",
    "complete-multipart-upload",
    "create-multipart-upload",
    "put_bucket", "delete_bucket",
]

# Every "aws" invocation in the script must use one of these s3api verbs
# (list-object-versions and list-objects-v2 are the only two-word verbs used
# here; head-object and get-object are the others).
ALLOWED_S3API_VERBS = {
    "head-object",
    "get-object",
    "list-objects-v2",
    "list-object-versions",
}


class TestP0R2DiagnosticReadOnly(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT_PATH.exists(), f"diagnostic script not found at {SCRIPT_PATH}")
        self.source = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_no_forbidden_mutating_substrings(self):
        hits = [tok for tok in FORBIDDEN_SUBSTRINGS if tok in self.source]
        self.assertEqual(
            hits, [],
            f"Found forbidden remote-mutating token(s) in {SCRIPT_PATH.name}: {hits}. "
            "This diagnostic must be strictly read-only (P0-MP.1A Section 2).",
        )

    def test_every_s3api_call_uses_an_allowed_read_only_verb(self):
        verbs_found = set(re.findall(r'"aws",\s*"s3api",\s*"([a-z0-9-]+)"', self.source))
        self.assertTrue(verbs_found, "Expected at least one 'aws s3api <verb>' call in the diagnostic script")
        disallowed = verbs_found - ALLOWED_S3API_VERBS
        self.assertEqual(
            disallowed, set(),
            f"Disallowed s3api verb(s) found: {disallowed}. Only {ALLOWED_S3API_VERBS} are permitted.",
        )

    def test_no_bare_s3_subcommand_other_than_s3api(self):
        # Every `"aws", "s3...", ...` invocation must be "s3api" (read-only
        # verb family checked above), never the bare "s3" subcommand family
        # (cp/sync/mv/rm), which this script has no legitimate use for.
        s3_family_calls = re.findall(r'"aws",\s*"(s3[a-z0-9]*)"', self.source)
        non_s3api = [c for c in s3_family_calls if c != "s3api"]
        self.assertEqual(
            non_s3api, [],
            f"Found 'aws {non_s3api}' invocation(s) -- only 'aws s3api <read-only-verb>' is permitted "
            "in this diagnostic, never the bare 's3' subcommand family (cp/sync/mv/rm).",
        )

    def test_never_writes_to_the_local_stix_manifest_path(self):
        self.assertNotIn(
            'MANIFEST_PATH.write', self.source,
            "Diagnostic must never write to the local data/stix/feed_manifest.json path.",
        )
        self.assertNotIn(
            '"data" / "stix" / "feed_manifest.json", "w"', self.source,
        )


if __name__ == "__main__":
    unittest.main()
