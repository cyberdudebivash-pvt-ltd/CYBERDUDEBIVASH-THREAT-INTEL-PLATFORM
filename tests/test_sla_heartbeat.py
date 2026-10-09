"""
tests/test_sla_heartbeat.py

External uptime heartbeat (2026-09-26). /api/sla/* computed uptime from
POST /api/sla/ping heartbeats that nothing ever sent, so every SLA surface
reported insufficient_data. scripts/sla_heartbeat.py (run every 10 minutes
by .github/workflows/sla-heartbeat.yml) probes /api/health from outside the
Worker and replays results it could not deliver while the Worker was down.
No network: probe and POST are injected.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

from scripts import sla_heartbeat as hb

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "sla-heartbeat.yml"


def _seq(*results):
    it = iter(results)
    return lambda target: next(it)


def test_up_on_first_probe():
    r = hb.probe("https://t", retry_pause=0, probe_fn=_seq((True, 120, "health=ok")))
    assert r["ok"] is True and r["latency_ms"] == 120
    assert r["component"] == "intel-gateway"
    assert re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", r["probe_id"])
    assert r["observed_at"].endswith("Z")


def test_one_dropped_connection_is_not_an_outage():
    r = hb.probe("https://t", retry_pause=0,
                 probe_fn=_seq((False, 15000, "TimeoutError"), (True, 90, "health=ok")))
    assert r["ok"] is True
    assert "retry" in r["note"]


def test_two_failures_are_down():
    r = hb.probe("https://t", retry_pause=0,
                 probe_fn=_seq((False, 10, "HTTP 503"), (False, 12, "HTTP 503")))
    assert r["ok"] is False
    assert "HTTP 503" in r["note"]



def test_worker_alive_does_not_mask_customer_readiness_503():
    calls = []
    def liveness(target):
        calls.append(target)
        return "worker_liveness=alive"
    result = hb.probe(
        "https://example.invalid", retry_pause=0,
        probe_fn=_seq((False, 5, "HTTP 503"), (False, 4, "HTTP 503")),
        liveness_fn=liveness,
    )
    assert result["ok"] is False, "SLA readiness incident must remain a failed heartbeat"
    assert result["component"] == "intel-gateway"
    assert "HTTP 503" in result["note"]
    assert "worker_liveness=alive" in result["note"]
    assert calls == ["https://example.invalid"]


def test_healthy_probe_never_spends_extra_worker_liveness_read():
    calls = []
    def liveness(target):
        calls.append(target)
        return "worker_liveness=alive"
    result = hb.probe(
        "https://example.invalid", retry_pause=0,
        probe_fn=_seq((True, 3, "health=ok")), liveness_fn=liveness,
    )
    assert result["ok"] is True
    assert calls == []


def test_http_200_with_degraded_status_is_not_counted_healthy(monkeypatch):
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, cap):
            return b'{"status":"degraded","reason":"intelligence_stale"}'
    monkeypatch.setattr(hb.urllib.request, "urlopen", lambda req, timeout: Response())
    up, ms, note = hb.probe_once("https://example.invalid")
    assert up is False and ms >= 0
    assert "health=degraded" in note


def test_worker_live_fallback_validates_json_and_exact_service(monkeypatch):
    class Response:
        status = 200
        def __init__(self, body):
            self.body = body
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, cap):
            assert cap <= 4096
            return self.body
    bodies = (
        b'{"status":"alive","service":"sentinel-apex"}',
        b'{"status":"alive","service":"untrusted"}',
        b'{"status":"down","service":"sentinel-apex"}',
    )
    for body, expected in zip(bodies, ("worker_liveness=alive", "worker_liveness=invalid_response", "worker_liveness=invalid_response")):
        monkeypatch.setattr(hb.urllib.request, "urlopen", lambda req, timeout, body=body: Response(body))
        assert hb.probe_worker_liveness("https://example.invalid") == expected


def test_degraded_readiness_still_exits_nonzero_and_reports_precise_scope(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("WORKER_ADMIN_SECRET", "test-secret")
    monkeypatch.setenv("SLA_PENDING_FILE", str(tmp_path / "pending.json"))
    monkeypatch.setattr(hb, "probe", lambda target: {
        "ok": False, "latency_ms": 50,
        "note": "HTTP 503; retry: HTTP 503; worker_liveness=alive",
        "component": "intel-gateway", "region": "github-actions",
        "observed_at": "2026-10-09T04:20:00Z", "probe_id": "local-1",
    })
    monkeypatch.setattr(hb, "_post", lambda u, secret, payload: True)
    assert hb.main() == 1
    out = capsys.readouterr().out
    assert "INTELLIGENCE_DEGRADED" in out
    assert "Worker is alive" in out
    assert "readiness is DOWN" not in out



def test_deliver_batches_oldest_first_and_keeps_the_rest_on_failure():
    pending = [{"probe_id": f"p{i}"} for i in range(1200)]
    sent = []

    def post(url, secret, payload):
        if len(sent) == 2:
            return False
        sent.append([p["probe_id"] for p in payload["pings"]])
        return True

    remaining = hb.deliver("https://t", "s", pending, post=post)
    assert [len(b) for b in sent] == [500, 500]
    assert sent[0][0] == "p0"
    assert [p["probe_id"] for p in remaining] == [f"p{i}" for i in range(1000, 1200)]


def test_pending_buffer_is_capped(tmp_path):
    f = tmp_path / "pending.json"
    hb.save_pending(f, [{"i": i} for i in range(hb.PENDING_CAP + 50)])
    kept = hb.load_pending(f)
    assert len(kept) == hb.PENDING_CAP and kept[0] == {"i": 50}


def test_corrupt_buffer_is_ignored(tmp_path):
    f = tmp_path / "pending.json"
    f.write_text("{not json")
    assert hb.load_pending(f) == []


def _run_main(monkeypatch, tmp_path, probe_results, post):
    monkeypatch.setenv("WORKER_ADMIN_SECRET", "s")
    monkeypatch.setenv("SLA_PENDING_FILE", str(tmp_path / "pending.json"))
    monkeypatch.setattr(hb, "RETRY_PAUSE_S", 0)
    monkeypatch.setattr(hb, "probe_once", _seq(*probe_results))
    monkeypatch.setattr(hb, "_post", post)
    monkeypatch.setattr(hb.time, "sleep", lambda s: None)
    return hb.main()


def test_outage_is_buffered_then_replayed(monkeypatch, tmp_path):
    delivered = []
    # Run 1: Worker down -> probe fails, POST fails, result is buffered.
    code = _run_main(monkeypatch, tmp_path, [(False, 1, "ConnectionError"), (False, 1, "ConnectionError")],
                     lambda u, s, p: False)
    assert code == 1
    buffered = json.loads((tmp_path / "pending.json").read_text())
    assert len(buffered) == 1 and buffered[0]["ok"] is False

    # Run 2: back up -> both results delivered, the old one with its original time.
    def post(u, s, p):
        delivered.extend(p["pings"])
        return True
    code = _run_main(monkeypatch, tmp_path, [(True, 80, "health=ok")], post)
    assert code == 0
    assert [p["ok"] for p in delivered] == [False, True]
    assert delivered[0]["observed_at"] == buffered[0]["observed_at"]
    assert json.loads((tmp_path / "pending.json").read_text()) == []


def test_missing_secret_exits_2(monkeypatch):
    monkeypatch.delenv("WORKER_ADMIN_SECRET", raising=False)
    assert hb.main() == 2


def test_rejected_secret_exits_2_and_keeps_the_result(monkeypatch, tmp_path):
    def post(u, s, p):
        raise PermissionError("/api/sla/ping rejected the admin secret (403)")
    assert _run_main(monkeypatch, tmp_path, [(True, 50, "health=ok")], post) == 2
    assert len(json.loads((tmp_path / "pending.json").read_text())) == 1


# -- The workflow ---------------------------------------------------------------
@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_schedule_and_least_privilege(wf):
    on = wf.get("on") or wf.get(True)
    assert on["schedule"] == [{"cron": "*/10 * * * *"}]
    assert "workflow_dispatch" in on
    assert "pull_request_target" not in on
    assert wf["permissions"] == {"contents": "read"}
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_workflow_actions_are_sha_pinned_and_secret_is_scoped(wf):
    steps = wf["jobs"]["heartbeat"]["steps"]
    for s in steps:
        if "uses" in s:
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", s["uses"]), s["uses"]
    probe = next(s for s in steps if s.get("run", "").startswith("python3 scripts/sla_heartbeat.py"))
    assert probe["env"] == {"WORKER_ADMIN_SECRET": "${{ secrets.WORKER_ADMIN_SECRET }}"}
    save = next(s for s in steps if "cache/save" in s.get("uses", ""))
    assert save["if"] == "always()", "undelivered heartbeats must survive a red (DOWN) run"


def test_batch_size_matches_the_worker_cap():
    js = (REPO / "workers" / "intel-gateway" / "src" / "sla-monitor.js").read_text(encoding="utf-8")
    assert re.search(r"const SLA_MAX_BATCH\s*=\s*%d;" % hb.BATCH, js)


# -- Pages that render /api/sla/status ------------------------------------------
def _sla_pages():
    pages = [p for p in list(REPO.glob("*.html")) + list((REPO / "dashboard").glob("*.html"))
             if "/api/sla/status" in p.read_text(encoding="utf-8", errors="ignore")]
    assert len(pages) >= 3
    return pages


def test_no_page_defaults_missing_uptime_to_100():
    """Heartbeat data now exists, but until it does (and for unmonitored
    components) uptime is null: pages must not render that as 100%."""
    pat = re.compile(r"uptime(_pct_30d)?\s*\|\|\s*100\b")
    offenders = [p.name for p in _sla_pages() if pat.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_null_sla_met_is_not_rendered_as_breached():
    html = (REPO / "dashboard" / "enterprise_dashboard.html").read_text(encoding="utf-8")
    assert "d.sla_met_enterprise?'MET ✓':'BREACHED ✗'" not in html
    assert "d.sla_met_enterprise===false?'BREACHED ✗'" in html


def test_pages_render_monitoring_delayed_as_no_data_not_outage():
    """GitHub's scheduler is best-effort; a late heartbeat is reported as
    monitoring_delayed, and pages must not render that as an outage."""
    status = (REPO / "status.html").read_text(encoding="utf-8")
    assert "comp.status === 'monitoring_delayed'" in status and "'Monitoring Delayed'" in status
    assert "comp.status === 'degraded'" in status
    dash = (REPO / "dashboard" / "enterprise_dashboard.html").read_text(encoding="utf-8")
    assert "d.status==='monitoring_delayed'?'Monitoring delayed'" in dash
    js = (REPO / "workers" / "intel-gateway" / "src" / "sla-monitor.js").read_text(encoding="utf-8")
    assert '"monitoring_delayed"' in js
