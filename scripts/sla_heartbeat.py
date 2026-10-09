#!/usr/bin/env python3
"""
scripts/sla_heartbeat.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- external uptime heartbeat for /api/sla/*
=========================================================================
/api/sla/status, /api/sla/report and /api/sla/certificate compute uptime from
heartbeats sent to POST /api/sla/ping. Until 2026-09-26 nothing sent any, so
every one of them reported insufficient_data.

This prober runs outside the Worker (.github/workflows/sla-heartbeat.yml,
every 10 minutes), so it can observe the Worker being down:

  1. GET <target>/api/health. Up = HTTP 200 with a JSON body. One retry after
     a short pause, so a single dropped connection on the runner is not
     recorded as an outage.
  2. Append the result (observed_at, probe_id, latency) to a pending buffer.
  3. POST every pending result to /api/sla/ping in batches. Results that
     could not be delivered (typically: the Worker was the thing that was
     down) stay in the buffer and are replayed on the next run with their
     original observed_at; probe_id makes a replay idempotent.

Exit codes: 0 up, 1 down (the workflow run goes red, which notifies the
owner), 2 misconfigured (WORKER_ADMIN_SECRET missing or rejected).

Env:
  WORKER_ADMIN_SECRET   required; sent as X-Admin-Secret (same secret the
                        Worker's other admin routes use)
  SLA_TARGET            default https://intel.cyberdudebivash.com
  SLA_PENDING_FILE      default .sla-heartbeat/pending.json
  GITHUB_RUN_ID         used in probe_id when present

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_TARGET = "https://intel.cyberdudebivash.com"
DEFAULT_PENDING = ".sla-heartbeat/pending.json"
PROBE_TIMEOUT_S = 15
RETRY_PAUSE_S = 10
BATCH = 500             # the Worker's per-request cap (SLA_MAX_BATCH)
PENDING_CAP = 5000      # ~35 days at one probe per 10 minutes
USER_AGENT = "cdb-sla-heartbeat/1.0 (+https://intel.cyberdudebivash.com/status.html)"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def probe_once(target: str, timeout: float = PROBE_TIMEOUT_S) -> tuple[bool, int, str]:
    """Returns (up, latency_ms, note)."""
    req = urllib.request.Request(f"{target}/api/health", headers={"User-Agent": USER_AGENT,
                                                                   "Accept": "application/json",
                                                                   "Cache-Control": "no-cache"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(65536)
            ms = int((time.monotonic() - t0) * 1000)
            if r.status != 200:
                return False, ms, f"HTTP {r.status}"
            try:
                data = json.loads(body)
            except ValueError:
                return False, ms, "HTTP 200, body is not JSON"
            if not isinstance(data, dict) or data.get("status") != "ok":
                state = data.get("status", "invalid") if isinstance(data, dict) else "not_object"
                return False, ms, f"HTTP 200 but health={state}"
            return True, ms, "health=ok"
    except urllib.error.HTTPError as e:
        return False, int((time.monotonic() - t0) * 1000), f"HTTP {e.code}"
    except Exception as e:  # timeout, DNS, TLS, connection reset
        return False, int((time.monotonic() - t0) * 1000), f"{type(e).__name__}: {str(e)[:120]}"



def probe_worker_liveness(target: str, timeout: float = PROBE_TIMEOUT_S) -> str:
    """Diagnostics only: never override the SLA readiness failure.

    Called once only when /api/health fails with HTTP 503 twice. The worker
    can be alive while customer intelligence is stale. This GET does not
    change the recorded availability result or incur any R2/KV operation.
    """
    req = urllib.request.Request(
        f"{target}/api/health/live",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            if res.status != 200:
                return f"worker_liveness=HTTP_{res.status}"
            body = json.loads(res.read(4096))
            if isinstance(body, dict) and body.get("status") == "alive" and body.get("service") == "sentinel-apex":
                return "worker_liveness=alive"
            return "worker_liveness=invalid_response"
    except urllib.error.HTTPError as exc:
        return f"worker_liveness=HTTP_{exc.code}"
    except Exception as exc:
        return f"worker_liveness={type(exc).__name__}"



def probe(target: str, retry_pause: float | None = None, probe_fn=None, liveness_fn=None) -> dict:
    injected_probe = probe_fn is not None
    probe_fn = probe_fn or probe_once
    retry_pause = RETRY_PAUSE_S if retry_pause is None else retry_pause
    observed_at = _now_iso()
    up, ms, note = probe_fn(target)
    if not up:
        time.sleep(retry_pause)
        up, ms, retry_note = probe_fn(target)
        note = f"{note}; retry: {retry_note}"
        # Diagnose, but DO NOT recategorize HTTP 503 as a successful SLA
        # sample: customer intelligence readiness is unavailable. Avoid
        # extra requests when readiness is healthy or a test injects a probe.
        if "HTTP 503" in note:
            diagnostic = liveness_fn if liveness_fn is not None else (
                None if injected_probe else probe_worker_liveness
            )
            if diagnostic is not None:
                note = f"{note}; {diagnostic(target)}"
    run = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    return {
        "ok": up,
        "latency_ms": ms,
        "component": "intel-gateway",
        "region": "github-actions",
        "note": note[:200],
        "observed_at": observed_at,
        "probe_id": f"gh-{run}-{attempt}"[:64],
    }


def load_pending(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_pending(path: Path, pending: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pending[-PENDING_CAP:]), encoding="utf-8")


def deliver(target: str, secret: str, pending: list, post=None) -> list:
    """POSTs pending results oldest-first; returns the ones not delivered."""
    post = post or _post
    remaining = list(pending)
    while remaining:
        chunk = remaining[:BATCH]
        if not post(f"{target}/api/sla/ping", secret, {"pings": chunk}):
            break
        remaining = remaining[BATCH:]
    return remaining


def _post(url: str, secret: str, payload: dict) -> bool:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "X-Admin-Secret": secret,
                                          "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_S) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise PermissionError("/api/sla/ping rejected the admin secret (403)") from e
        return False
    except Exception:
        return False


def main() -> int:
    secret = os.environ.get("WORKER_ADMIN_SECRET", "")
    if not secret:
        print("::error::WORKER_ADMIN_SECRET is not set; cannot record heartbeats")
        return 2
    target = os.environ.get("SLA_TARGET", DEFAULT_TARGET).rstrip("/")
    pending_path = Path(os.environ.get("SLA_PENDING_FILE", DEFAULT_PENDING))

    result = probe(target)
    pending = load_pending(pending_path) + [result]
    try:
        remaining = deliver(target, secret, pending)
    except PermissionError as e:
        save_pending(pending_path, pending)
        print(f"::error::{e} -- check the WORKER_ADMIN_SECRET repository secret")
        return 2
    save_pending(pending_path, remaining)

    worker_alive_but_unready = not result["ok"] and "worker_liveness=alive" in result["note"]
    state = "UP" if result["ok"] else ("INTELLIGENCE_DEGRADED" if worker_alive_but_unready else "DOWN")
    print(f"{target}/api/health: {state} in {result['latency_ms']}ms ({result['note']}); "
          f"delivered {len(pending) - len(remaining)}/{len(pending)}, {len(remaining)} buffered for replay")
    if not result["ok"]:
        reason = "intelligence readiness is degraded (Worker is alive)" if worker_alive_but_unready else "readiness is DOWN"
        print(f"::error::{target} {reason}: {result['note']}")
        return 1
    if remaining:
        print(f"::warning::{len(remaining)} heartbeat(s) not delivered; will replay next run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
