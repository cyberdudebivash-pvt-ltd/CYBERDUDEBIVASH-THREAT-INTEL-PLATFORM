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


# The v157.0 dashboard route validator still listed revenue_acceleration.html,
# so the prune above failed STAGE 5.4.6 and skipped the Pages deploy and every
# post-deploy gate (sentinel-blogger run 36833320633, 2026-10-01T08:53Z).

def test_build_sequence_copy_prune_validate_passes(tmp_path):
    """The production order: copy dashboard/, prune, then validate routes."""
    dst = tmp_path / "dashboard"
    bda.copy_item(REPO / "dashboard", dst)
    bda.prune_include_dir_excludes("dashboard", dst)
    assert not (dst / "revenue_acceleration.html").exists()
    assert bda.missing_dashboard_routes(REPO, tmp_path) == []


def test_negative_control_validator_still_fails_a_missing_nav_route(tmp_path):
    dst = tmp_path / "dashboard"
    bda.copy_item(REPO / "dashboard", dst)
    bda.prune_include_dir_excludes("dashboard", dst)
    (dst / "revenue_dashboard.html").unlink()
    assert bda.missing_dashboard_routes(REPO, tmp_path) == ["dashboard/revenue_dashboard.html"]


def test_excluded_by_design_matches_only_the_exclusion_list():
    for dirname, names in bda.INCLUDE_DIR_FILE_EXCLUDES.items():
        for name in names:
            assert bda.is_excluded_by_design(f"{dirname}/{name}")
    for route in bda.NAV_DASHBOARD_ROUTES:
        if route != "dashboard/revenue_acceleration.html":
            assert not bda.is_excluded_by_design(route), route


def test_no_shipped_page_links_to_a_quarantined_page():
    """A link to a page that no longer ships is a production 404."""
    names = [Path(rel).name for rel in QUARANTINED]
    link = re.compile(r"""(?:href|src)\s*=\s*["'][^"']*?(%s)""" % "|".join(map(re.escape, names)), re.I)
    hits = {str(p.relative_to(REPO)): link.findall(p.read_text(encoding="utf-8", errors="ignore"))
            for p in shipped_pages()}
    assert not {k: v for k, v in hits.items() if v}, hits
    assert link.search('<a href="/dashboard/revenue_acceleration.html">'), "link pattern went blind"
