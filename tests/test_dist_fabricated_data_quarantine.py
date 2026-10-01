"""No shipped page renders invented business records (Phase 7, 2026-10-01).

Three live, unlinked internal revenue tools presented invented data as fact,
none labelled as sample data:

- dashboard/revenue_acceleration.html: a table of invented subscriber emails
  with MRR, hard-coded per-plan subscriber counts, a "Pro Subscribers 71" goal;
- conversion-analytics.html: fixed MRR figures, "21 active customers",
  renewal and expansion rates;
- demo-conversion-center.html: a "LIVE" pipeline of invented named contacts
  with ARR up to $180,000.

scripts/build_dist_artifact.py now keeps them out of dist/ (both Pages
deploys use clean: true, so they leave the live site on the next deploy),
the same treatment v200.1/v200.2 gave other internal tools. This file pins
the exclusions and guards every page that still ships against the record
patterns those pages used. Local files only.
"""
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_dist_artifact_under_test", REPO / "scripts" / "build_dist_artifact.py")
bda = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bda)

QUARANTINED = ("conversion-analytics.html", "demo-conversion-center.html", "dashboard/revenue_acceleration.html")

RECORD_PATTERNS = {
    "email field in a data literal": re.compile(r"\bemail\s*:\s*['\"][^'\"\s]+@[^'\"\s]+['\"]", re.I),
    "hard-coded subscriber count": re.compile(r"\bsubscribers\s*:\s*[1-9]\d*", re.I),
    "hard-coded MRR/ARR money": re.compile(r"\b(mrr|arr)\s*:\s*['\"]?\$?[1-9][\d,]*", re.I),
    "named contact in a data literal": re.compile(r"\bcontact\s*:\s*['\"][A-Z][a-z]+ [A-Z][a-z]+['\"]"),
}


def shipped_pages():
    pages = [p for p in sorted(REPO.glob("*.html")) if not bda.is_excluded_html(p.name)]
    for d in ("dashboard", "customer"):
        excluded = set(bda.INCLUDE_DIR_FILE_EXCLUDES.get(d, ()))
        pages += [p for p in sorted((REPO / d).glob("*.html")) if p.name not in excluded]
    return pages


def record_hits(path):
    text = re.sub(r"<!--.*?-->", " ", path.read_text(encoding="utf-8", errors="ignore"), flags=re.S)
    return {label: rx.findall(text) for label, rx in RECORD_PATTERNS.items() if rx.search(text)}


def test_quarantined_root_pages_are_excluded_and_neighbours_are_not():
    assert bda.is_excluded_html("conversion-analytics.html")
    assert bda.is_excluded_html("demo-conversion-center.html")
    for page in ("demo.html", "pricing.html", "index.html", "enterprise-demo.html"):
        assert not bda.is_excluded_html(page), f"{page} must keep shipping"


def test_dashboard_prune_removes_only_the_listed_file(tmp_path):
    for name in ("revenue_acceleration.html", "revenue_dashboard.html", "index.html"):
        (tmp_path / name).write_text("<html></html>", encoding="utf-8")
    assert bda.prune_include_dir_excludes("dashboard", tmp_path) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["index.html", "revenue_dashboard.html"]
    assert bda.prune_include_dir_excludes("customer", tmp_path) == 0


def test_build_loop_prunes_after_copying_include_dirs():
    src = (REPO / "scripts" / "build_dist_artifact.py").read_text(encoding="utf-8")
    assert "n -= prune_include_dir_excludes(dirname, dst)" in src


def test_no_shipped_page_renders_invented_records():
    hits = {str(p.relative_to(REPO)): h for p in shipped_pages() for h in [record_hits(p)] if h}
    assert not hits, hits


def test_negative_control_each_quarantined_page_trips_the_guard():
    for rel in QUARANTINED:
        assert record_hits(REPO / rel), f"{rel} no longer matches the guard; the guard may have gone blind"
