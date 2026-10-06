#!/usr/bin/env python3
"""
scripts/r2_round_trip_verifier.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- P0 RUNTIME INTELLIGENCE STATE RECOVERY

Independent post-write verification for scripts/r2_state_sync.py --upload,
run immediately after it in genesis-powerhouse.yml / sovereign-platform.yml.

Why this exists as a SEPARATE step rather than trusting --upload's own exit
code: r2_state_sync.py's upload() already performs a real network PUT with
retry and honest failure accounting (not "fire and forget") -- but the
mission's Definition of Done treats "required R2 persistence succeeded" and
"post-write verification succeeded" as two distinct checks, and a second,
independent read-back closes the (narrow but real) gap between "the CLI
reported success" and "what is actually now stored in R2 matches what we
just wrote."

Reuses r2_state_sync.download() unchanged (Principle 4: call the existing
function, don't reimplement it) -- downloads the exact same --only file set
into an isolated scratch root and byte-compares each file against the
just-uploaded local copy. This is a genuine round trip: a real second GET
against R2, not a re-inspection of the same local file the upload step
already had.

Usage:
  python3 scripts/r2_round_trip_verifier.py \\
      --source-root . --only data/nexus/nexus_output.json,data/cortex/cortex_output.json

Exit 0: every file round-trips byte-identical. Exit 1: any download failure
or content mismatch -- the calling workflow step must NOT be
continue-on-error.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import r2_state_sync as rss  # noqa: E402
from r2_upload import get_credentials, install_awscli  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=pathlib.Path, default=rss.REPO_ROOT, help="Root the just-uploaded files live under.")
    parser.add_argument("--only", required=True, help="Comma-separated STATE_FILES local paths to round-trip verify.")
    args = parser.parse_args()

    only = frozenset(p.strip() for p in args.only.split(",") if p.strip())
    unknown = only - rss.KNOWN_LOCAL_RELS
    if unknown:
        parser.error(f"--only references path(s) not in STATE_FILES/STATE_DIRS: {sorted(unknown)}")

    cf_account, _, _ = get_credentials()
    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"
    install_awscli()

    had_error = False
    with tempfile.TemporaryDirectory(prefix="r2-round-trip-") as scratch:
        scratch_root = pathlib.Path(scratch)
        rc = rss.download(scratch_root, endpoint, only=only)
        if rc != 0:
            print("[FAIL] round-trip download from R2 failed -- see r2_state_sync log lines above.")
            return 1

        for local_rel in sorted(only):
            source_path = args.source_root / local_rel
            downloaded_path = scratch_root / local_rel
            if not source_path.exists():
                print(f"[FAIL] {local_rel}: no local source copy to compare against (nothing was uploaded?).")
                had_error = True
                continue
            if not downloaded_path.exists():
                print(f"[FAIL] {local_rel}: round-trip download did not produce a file (object missing in R2?).")
                had_error = True
                continue
            source_bytes = source_path.read_bytes()
            downloaded_bytes = downloaded_path.read_bytes()
            if source_bytes != downloaded_bytes:
                print(f"[FAIL] {local_rel}: R2's content does not match what was just uploaded ({len(source_bytes)} vs {len(downloaded_bytes)} bytes).")
                had_error = True
                continue
            print(f"[OK] {local_rel}: round-trips byte-identical ({len(source_bytes)} bytes).")

    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
