"""
tests/test_observability_status_truth.py

observability.html is the public status page (2026-09-26). A render against
the live API showed it reporting things nothing measured:
  - "API Uptime (30d) 99.9%" and "30-Day Uptime 99.9%" were fixed HTML, and
    a 30-day uptime bar was drawn with a made-up incident on day 22, while
    GET /api/sla/status reported status=insufficient_data (zero heartbeats);
  - it read every pipeline value from data.pipeline, which /api/health does
    not return, so the advisory count fell back to "156+" (live: 38) and
    last sync / freshness showed "--";
  - its API diagnostics probed /api/v1/intel/preview.json and
    /api/v1/intel/feed.json, routes the Worker does not have (404), so two
    rows were permanently WARN.

The page now shows uptime only as /api/sla/status measures it, reads the
/api/health top-level fields, and probes routes the Worker serves.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGE = (REPO / "observability.html").read_text(encoding="utf-8")
WORKER = (REPO / "workers" / "intel-gateway" / "src" / "index.js").read_text(encoding="utf-8")


def _probe_paths():
    block = re.search(r"const probeList = \[(.*?)\];", PAGE, re.S)
    assert block, "renderApiDiag() probeList not found"
    rows = re.findall(r"\[\s*'([^']+)',\s*'([^']+)',\s*(\d+),\s*'([A-Z]+)'\s*\]", block.group(1))
    assert len(rows) >= 4
    return [path for _label, path, _code, _tier in rows]


def test_no_fixed_uptime_figure():
    assert not re.search(r'class="card-value[^"]*"[^>]*>\s*\d{2}(\.\d+)?%\s*<', PAGE), \
        "uptime must come from /api/sla/status, not fixed markup"
    assert "uptime-seg" not in PAGE and "renderUptimeBar" not in PAGE, \
        "no per-day uptime data exists; the bar was fabricated"


def test_uptime_comes_from_sla_status():
    assert "/api/sla/status" in PAGE
    assert "uptime_pct_30d" in PAGE
    assert "Not yet measured" in PAGE, "an unmeasured window must say so"
    assert re.search(r'"/api/sla/status"', WORKER), "the Worker must still serve /api/sla/status"


def test_no_invented_advisory_count():
    assert "156+" not in PAGE


def test_reads_health_top_level_fields():
    """/api/health has advisory_count/last_sync at the top level, no .pipeline."""
    assert "data.pipeline || data" in PAGE
    assert "health?.pipeline || health" in PAGE


def _worker_serves(path):
    if f'"{path}"' in WORKER:
        return True
    # /api/ai/<file> is served from the AI_STATIC_PROXY_FILES allowlist.
    allow = re.search(r"AI_STATIC_PROXY_FILES = new Set\(\[([^\]]*)\]\)", WORKER)
    return bool(allow) and path.startswith("/api/ai/") and \
        f'"{path[len("/api/ai/"):]}"' in allow.group(1)


def test_every_probe_targets_a_worker_route():
    missing = [p for p in _probe_paths() if not _worker_serves(p)]
    assert missing == [], f"status page probes routes the Worker does not serve: {missing}"


def test_retired_probe_paths_stay_gone():
    for dead in ("/api/v1/intel/preview.json", "/api/v1/intel/feed.json"):
        assert dead not in PAGE
