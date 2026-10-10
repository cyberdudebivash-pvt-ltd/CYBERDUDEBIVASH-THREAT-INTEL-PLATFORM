"""P0 R40: dashboard cache-bust version must match shipped JS bytes."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_eicc_snapshot_query_version_matches_actual_source_hash():
    blob = (ROOT / "js/apex-dashboard-snapshot.js").read_bytes()
    digest = hashlib.sha256(blob).hexdigest()[:12]
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    expected = f'<script src="/js/apex-dashboard-snapshot.js?v={digest}"></script>'
    assert expected in index, "Dashboard snapshot script must use the exact current SHA-256 content version"
    assert index.count('/js/apex-dashboard-snapshot.js?v=') == 1


def test_frontend_publisher_includes_index_html_in_push_and_merge_triggers():
    wf = (ROOT / ".github/workflows/pages-fast-publish.yml").read_text(encoding="utf-8")
    assert wf.count("      - '*.html'") >= 2, "Root HTML updates must trigger Pages republish"
