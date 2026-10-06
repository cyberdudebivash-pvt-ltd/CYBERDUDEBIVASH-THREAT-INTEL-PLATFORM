"""
tests/test_bust_kv_cache_visibility.py — CyberDudeBivash SENTINEL APEX

Regression test for the "no false green" fix to scripts/bust_kv_cache.py.

Live production investigation (Phase-2 P0 live acceptance pass) found this
step failing 403 Forbidden on every single cache-bust call, every run
(WORKER_ADMIN_SECRET mismatch between the GitHub Actions secret and the
Worker's actual runtime secret) -- confirmed via job logs showing
"Cache bust complete: 0 succeeded, 0 skipped, 11 failed". Because the step
runs as `python3 scripts/bust_kv_cache.py || true` and the script itself
always sys.exit(0) by design (cache-bust failure must never block a
deploy -- a deliberate, correct choice this test does not change), that
100% failure rate was completely invisible in CI status: every run showed
green while production kept serving pre-deploy data past the ~60s TTL the
script's own comments promised.

This test only asserts the new visibility signal exists -- a GitHub
Actions ::warning:: annotation printed to stdout when every cache-bust
request fails -- not the exit code (which correctly stays 0).
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import bust_kv_cache  # noqa: E402


class TestAllBustsFailedEmitsVisibleWarning:
    def test_prints_github_actions_warning_annotation_on_total_failure(self, capsys):
        with patch.object(bust_kv_cache.os.environ, "get", side_effect=lambda k, d="": "fake-secret" if k == "WORKER_ADMIN_SECRET" else d), \
             patch.object(bust_kv_cache, "_make_request", return_value=403), \
             patch.object(bust_kv_cache.time, "sleep", return_value=None):
            try:
                bust_kv_cache.main()
            except SystemExit as exc:
                assert exc.code == 0, "cache-bust failure must never block the pipeline"

        out = capsys.readouterr().out
        assert "::warning::" in out, (
            "a 100% cache-bust failure must emit a GitHub Actions ::warning:: "
            "annotation so it is visible in the run summary, not just in full logs"
        )
        assert "WORKER_ADMIN_SECRET" in out

    def test_no_warning_annotation_when_busts_succeed(self, capsys):
        with patch.object(bust_kv_cache.os.environ, "get", side_effect=lambda k, d="": "fake-secret" if k == "WORKER_ADMIN_SECRET" else d), \
             patch.object(bust_kv_cache, "_make_request", return_value=200), \
             patch.object(bust_kv_cache.time, "sleep", return_value=None):
            try:
                bust_kv_cache.main()
            except SystemExit as exc:
                assert exc.code == 0

        out = capsys.readouterr().out
        assert "::warning::" not in out
