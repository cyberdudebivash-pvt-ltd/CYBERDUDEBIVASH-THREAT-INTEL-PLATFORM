"""
Regression tests for scripts/generate_ai_tracker.py's percent-formatted
epss_score parsing (issue #277).

_parse_json_feed() (nested inside main(), used when loading a JSON feed
like api/feed.json) previously called float() directly on
apex.get("epss_score", ...), which crashes on a percent-formatted string
like "5.58%" -- the format api/feed.json actually stores this field in
for many items. The already-existing _parse_float() helper (used by the
CSV loader, load_feed()) already handles this exact format; the fix
reuses it in _parse_json_feed() too, rather than adding a second
percent-string parser.

Run with: pytest tests/test_generate_ai_tracker_epss_parser.py -v
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_ai_tracker.py"
API_FEED = REPO_ROOT / "api" / "feed.json"


@pytest.fixture(scope="module")
def tracker_module():
    spec = importlib.util.spec_from_file_location("generate_ai_tracker", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_float_handles_percent_strings(tracker_module):
    assert tracker_module._parse_float("5.58%") == pytest.approx(0.0558)
    assert tracker_module._parse_float("100%") == pytest.approx(1.0)


def test_parse_float_handles_plain_numbers(tracker_module):
    assert tracker_module._parse_float(0.5) == pytest.approx(0.5)
    assert tracker_module._parse_float("0.5") == pytest.approx(0.5)


def test_parse_float_handles_falsy_values(tracker_module):
    assert tracker_module._parse_float(None) == 0.0
    assert tracker_module._parse_float(0) == 0.0
    assert tracker_module._parse_float("") == 0.0


def test_generate_ai_tracker_does_not_crash_on_real_api_feed():
    """Reproduces issue #277's exact failing command against the real
    repository data (not a synthetic fixture) -- api/feed.json is known to
    contain at least one item with a percent-formatted epss_score."""
    assert API_FEED.exists(), f"{API_FEED} not found"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "tracker.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--feed", str(API_FEED), "--out", str(out_path)],
            capture_output=True, text=True, timeout=60, cwd=tmpdir,
        )
        assert result.returncode == 0, (
            f"generate_ai_tracker.py crashed against api/feed.json:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert out_path.exists(), "expected tracker.json to be written"
