#!/usr/bin/env bash
# sdk/publish.sh — build and publish sentinel-apex-sdk to PyPI.
#
# This script BUILDS and VERIFIES unconditionally, but will not upload
# without an explicit --upload flag and a live confirmation prompt --
# publishing to PyPI is effectively permanent (a version number can be
# yanked but never reused) and requires real PyPI credentials this
# script does not (and should not) embed or assume.
#
# Usage:
#   cd sdk/
#   ./publish.sh              # build + verify only (safe, repeatable)
#   ./publish.sh --upload     # build + verify, then prompt before uploading
#   ./publish.sh --test-upload  # same, but uploads to TestPyPI instead
#
# Requires: python3 -m pip install --upgrade build twine
# For --upload you'll need a PyPI API token (https://pypi.org/manage/account/token/)
# configured via ~/.pypirc or the TWINE_USERNAME=__token__ / TWINE_PASSWORD env vars.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

MODE="${1:-}"

echo "== Cleaning previous build artifacts =="
rm -rf build/ dist/ sentinel_sdk.egg-info/ sentinel_apex_sdk.egg-info/

echo "== Building sdist + wheel =="
python3 -m build

echo "== Verifying the built distributions =="
python3 -m twine check dist/*

echo ""
echo "Built artifacts:"
ls -la dist/

if [ "$MODE" != "--upload" ] && [ "$MODE" != "--test-upload" ]; then
  echo ""
  echo "Build + verification complete. Re-run with --upload (PyPI) or"
  echo "--test-upload (TestPyPI) to actually publish."
  exit 0
fi

if [ "$MODE" = "--test-upload" ]; then
  REPO_FLAG="--repository testpypi"
  TARGET="TestPyPI (https://test.pypi.org/project/sentinel-apex-sdk/)"
else
  REPO_FLAG=""
  TARGET="PyPI (https://pypi.org/project/sentinel-apex-sdk/) -- this is PUBLIC and effectively PERMANENT"
fi

echo ""
echo "About to upload to: $TARGET"
read -r -p "Type 'yes' to continue: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "Aborted -- nothing uploaded."
  exit 1
fi

# shellcheck disable=SC2086
python3 -m twine upload $REPO_FLAG dist/*

echo "Done. Verify at: https://pypi.org/project/sentinel-apex-sdk/"
