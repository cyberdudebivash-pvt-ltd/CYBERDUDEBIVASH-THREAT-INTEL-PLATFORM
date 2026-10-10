#!/usr/bin/env python3
"""P0 R37 live canary: static legacy aliases must NEVER expose intelligence."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://intel.cyberdudebivash.com"
ALIASES = ("/feed.json", "/latest.json")
MAX_BYTES = 2_000_000


def assert_unavailable(status: int, raw: bytes, alias: str) -> None:
    # A Worker 503 is a valid fail-closed response, and 404 means that an
    # unauthorised legacy alias was removed instead of publishing a snapshot.
    if status == 404:
        return
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AssertionError(f"{alias}: unparseable response status={status}") from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"{alias}: legacy snapshot array exposed")
    if payload.get("items") not in (None, []):
        raise AssertionError(f"{alias}: stale items exposed")
    if payload.get("data") not in (None, []):
        raise AssertionError(f"{alias}: stale data exposed")
    if payload.get("count") not in (None, 0):
        raise AssertionError(f"{alias}: stale count exposed")
    if status == 503 and payload.get("live_data_available") is False:
        return
    if status == 200 and payload.get("error") == "legacy_static_feed_disabled" and payload.get("live_data_available") is False:
        return
    raise AssertionError(f"{alias}: unapproved legacy response status={status}")


def run(base: str = BASE) -> None:
    base = base.rstrip("/")
    for alias in ALIASES:
        # Force a distinct cache key so old edge snapshot caches cannot
        # accidentally be treated as evidence of successful deployment.
        url = base + alias + "?" + urllib.parse.urlencode({"cdb_r37": str(time.time_ns())})
        request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.status
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise AssertionError(f"{alias}: unexpected large legacy response")
        assert_unavailable(status, body, alias)
        print(f"[P0 R37] PASS {alias}: status={status}, no stale intelligence")


if __name__ == "__main__":
    try:
        run(sys.argv[1] if len(sys.argv) > 1 else BASE)
    except Exception as exc:
        print(f"[P0 R37] FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
