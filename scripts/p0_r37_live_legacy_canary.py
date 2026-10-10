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
_RESPONSE_METADATA = {}


def _response_summary(url: str, status: int, raw: bytes) -> dict:
    """Public routing diagnostics without dumping advisory or customer bodies."""
    out = {"url": url, "status": status, "headers": _RESPONSE_METADATA.get(url, {})}
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        out["shape"] = "non_json"
        return out
    out["shape"] = type(data).__name__
    if isinstance(data, dict):
        out.update({k: data.get(k) for k in ("error", "generated_at", "count", "freshness_status")})
        out["item_count"] = len(data["items"]) if isinstance(data.get("items"), list) else None
    elif isinstance(data, list):
        out["item_count"] = len(data)
    return out


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


def assert_matches_fresh_authority(
    alias_status: int, alias_body: bytes, api_status: int,
    api_body: bytes, alias: str, now: float
) -> None:
    """Only allow a Worker-served LIVE alias if exact source identity is verified.

    During degraded API health the legacy path must NEVER emit any records.
    A legitimate freshly published live Worker alias is allowed, so this
    gate cannot accidentally block healthy recovery forever.
    """
    if alias_status != 200 or api_status != 200:
        raise AssertionError(f"{alias}: live alias not backed by healthy API")
    try:
        alias_data = json.loads(alias_body)
        api_data = json.loads(api_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AssertionError(f"{alias}: unparseable live authoritative response") from exc
    if not isinstance(alias_data, dict) or not isinstance(api_data, dict):
        raise AssertionError(f"{alias}: unexpected live response shape")
    stamp = api_data.get("generated_at")
    if not isinstance(stamp, str) or not stamp.endswith("Z"):
        raise AssertionError(f"{alias}: missing authoritative generation clock")
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError as exc:
        raise AssertionError(f"{alias}: invalid authoritative generation clock") from exc
    if t > now or now - t >= 6 * 3600:
        raise AssertionError(f"{alias}: authoritative feed is expired or future dated")
    ids = lambda d: [item.get("id") for item in d.get("items", []) if isinstance(item, dict)]
    canonical_ids = ids(api_data)
    alias_ids = ids(alias_data)
    if not canonical_ids or any(not i for i in canonical_ids):
        raise AssertionError(f"{alias}: authoritative feed lacks validated IDs")
    if alias_data.get("generated_at") != stamp or alias_ids != canonical_ids:
        raise AssertionError(f"{alias}: static/cached payload does not match live authoritative feed")


def _request(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            body = response.read(MAX_BYTES + 1)
            headers = response.headers
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read(MAX_BYTES + 1)
        headers = exc.headers
    _RESPONSE_METADATA[url] = {k: headers.get(k) for k in (
        "Server", "Cache-Control", "Age", "CF-Cache-Status", "CF-Ray",
        "X-Sentinel-Version", "X-Sentinel-Freshness", "X-Request-ID",
    ) if headers is not None and headers.get(k) is not None}
    if len(body) > MAX_BYTES:
        raise AssertionError(f"Unexpected large response: {url}")
    return status, body


def run(base: str = BASE) -> None:
    base = base.rstrip("/")
    for alias in ALIASES:
        token = str(time.time_ns())
        canonical = "/api/feed" if alias == "/feed.json" else "/api/v1/intel/latest.json"
        # The bare customer URL is mandatory: checking only a unique query
        # would hide an expired Cloudflare/browser cache entry.
        for suffix in ("", "?" + urllib.parse.urlencode({"cdb_r37": token})):
            url = base + alias + suffix
            status, body = _request(url)
            try:
                assert_unavailable(status, body, alias)
                print(f"[P0 R37] PASS {url}: status={status}, no stale intelligence")
            except AssertionError:
                api_url = base + canonical + "?" + urllib.parse.urlencode({"cdb_r37": token})
                api_status, api_body = _request(api_url)
                try:
                    assert_matches_fresh_authority(status, body, api_status, api_body, alias, time.time())
                except AssertionError as exc:
                    raise AssertionError(f"{exc}; responses=" + json.dumps([
                        _response_summary(url, status, body), _response_summary(api_url, api_status, api_body),
                    ], sort_keys=True)) from exc
                print(f"[P0 R37] PASS {url}: matches verified fresh live Worker API")

if __name__ == "__main__":
    try:
        run(sys.argv[1] if len(sys.argv) > 1 else BASE)
    except Exception as exc:
        print(f"[P0 R37] FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
