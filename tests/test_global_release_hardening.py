from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "commercial-customer-ops-certification.yml"
TRACKER = ROOT / "ai-threat-tracker.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_customer_certification_runs_automatically_on_release_surfaces():
    text = _read(WORKFLOW)
    assert "push:" in text
    assert "branches: [main]" in text
    assert 'cron: "17 2 * * *"' in text
    for required_path in (
        "workers/intel-gateway/src/**",
        "workers/revenue-engine/src/**",
        "deploy/cyber-watchdog/**",
        "ai-threat-tracker.html",
        "config/**",
    ):
        assert required_path in text


def test_watchdog_sink_is_mandatory_for_global_customer_certification():
    text = _read(WORKFLOW)
    assert "watchdog_sink_present:" in text
    assert "WATCHDOG_SINK_PRESENT" in text
    assert 'BLOCKED_BY_SINK' in text
    assert '[ "${3:-}" = "blocked" ] && BLOCKED=1' in text
    assert '[ "$BLOCKED" -ne 0 ]' in text
    assert "every mandatory canary completed successfully" in text


def test_ai_tracker_has_no_hardcoded_trust_metrics_or_unlimited_quota():
    text = _read(TRACKER)
    compact = "".join(text.split())
    assert "99.99% UPTIME" not in text
    assert "18 anomalies, 22 campaigns, 12 sector forecasts" not in text
    assert "Enterprise unlimited" not in text
    assert "overall||89" not in compact
    assert "pipeline_version||'148.0.0'" not in compact
    assert "feed_freshness_hours||'<1'" not in compact


def test_ai_tracker_publishes_canonical_runtime_quota_copy():
    text = _read(TRACKER)
    assert (
        "FREE 30 req/min (50/day) · PRO 120 req/min (5,000/day) · "
        "ENTERPRISE 600 req/min (50,000/day) · MSSP 1,200 req/min (50,000/day)"
    ) in text
    assert 'id="es-system"' in text
    assert "HEALTH UNVERIFIED" in text
