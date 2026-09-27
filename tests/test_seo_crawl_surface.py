"""Crawl surface: robots.txt groups, sitemap coverage, report discovery.

robots.txt's internal-page Disallows sat after "User-agent: Bingbot", so they
applied to Bing only; the static sitemaps listed 2 of the published reports
and none of several public trust/tool pages; sitemap.xml carried a copied
lastmod on every URL. These checks keep one crawler group with the
Disallows, the Worker-served report sitemap advertised, the reviewed pages
listed, and every lastmod a real date that is not in the future.
Local files only; no network.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = "https://intel.cyberdudebivash.com"
ROBOTS = (REPO / "robots.txt").read_text(encoding="utf-8")
INDEX = (REPO / "sitemap-index.xml").read_text(encoding="utf-8")
SITEMAP = (REPO / "sitemap.xml").read_text(encoding="utf-8")
WORKER = (REPO / "workers/intel-gateway/src/index.js").read_text(encoding="utf-8")


def _groups(robots: str):
    """[(user_agents, rules)] per robots.txt group (RFC 9309 grouping)."""
    groups, agents, rules, last_was_agent = [], [], [], False
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = (x.strip() for x in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if not last_was_agent and agents:
                groups.append((agents, rules)); agents, rules = [], []
            agents.append(value); last_was_agent = True
        elif field in ("allow", "disallow"):
            rules.append((field, value)); last_was_agent = False
    if agents:
        groups.append((agents, rules))
    return groups


def test_internal_pages_are_disallowed_for_every_crawler():
    groups = _groups(ROBOTS)
    star = [rules for agents, rules in groups if "*" in agents]
    assert len(star) == 1
    disallowed = {v for f, v in star[0] if f == "disallow"}
    for internal in ("/admin.html", "/revenue-dashboard.html", "/lead-pipeline.html",
                     "/monetization-ops.html", "/conversion-analytics.html", "/scripts/", "/.github/"):
        assert internal in disallowed, internal
    # A crawler-specific group would replace the * group for that crawler and
    # drop these Disallows (the original bug); any such group must repeat them.
    for agents, rules in groups:
        if "*" not in agents:
            assert disallowed <= {v for f, v in rules if f == "disallow"}, agents


def test_report_sitemap_is_advertised_and_served_by_the_worker():
    assert f"Sitemap: {SITE}/reports/sitemap.xml" in ROBOTS
    assert f"<loc>{SITE}/reports/sitemap.xml</loc>" in INDEX
    assert 'if (path === "/reports/sitemap.xml") {' in WORKER
    # It must be matched before the /reports/** handler.
    assert WORKER.index('if (path === "/reports/sitemap.xml") {') < WORKER.index('if (path.startsWith("/reports/")) {')
    for m in re.findall(r"^Sitemap:\s*(\S+)", ROBOTS, re.M):
        assert m.startswith(SITE + "/"), m


def test_reviewed_public_pages_are_in_the_sitemap():
    for page in ("about.html", "methodology.html", "lookup.html", "soc-integrations.html",
                 "integration-catalog.html", "platform-capabilities.html", "services.html",
                 "enterprise-use-cases.html", "reference-architecture.html", "roi-calculator.html",
                 "executive-briefing.html", "sla.html", "privacy.html", "terms.html", "eula.html",
                 "pricing.html", "enterprise.html", "get-api-key.html", "api-docs.html",
                 # Added once their claims were verified (tests/test_comparison_claims_truth.py).
                 "compare.html", "alternative-to-mandiant.html", "alternative-to-recorded-future.html"):
        assert f"<loc>{SITE}/{page}</loc>" in SITEMAP, page
        assert (REPO / page).exists(), page


def test_no_disallowed_page_is_in_a_sitemap():
    disallowed = {v for f, v in _groups(ROBOTS)[0][1] if f == "disallow"}
    for sm in REPO.glob("sitemap*.xml"):
        for loc in re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8")):
            path = loc.replace(SITE, "") or "/"
            assert not any(path.startswith(d) for d in disallowed if d), f"{sm.name}: {loc}"


def test_lastmod_values_are_real_dates_not_in_the_future():
    today = datetime.date.today()
    for sm in [REPO / "sitemap.xml", REPO / "sitemap-index.xml"]:
        dates = re.findall(r"<lastmod>([^<]+)</lastmod>", sm.read_text(encoding="utf-8"))
        assert dates, sm.name
        for d in dates:
            assert datetime.date.fromisoformat(d[:10]) <= today, f"{sm.name}: {d}"


def test_sales_pages_have_a_share_card():
    """A link to these pages shared on LinkedIn/X/Slack/email shows a preview."""
    img = f"{SITE}/assets/sentinel-apex-og-banner.jpg"
    assert (REPO / "assets/sentinel-apex-og-banner.jpg").exists()
    for page in ("pricing.html", "enterprise.html", "get-api-key.html", "contact-enterprise.html",
                 "mssp.html", "trust-center.html", "demo.html"):
        head = (REPO / page).read_text(encoding="utf-8").split("</head>", 1)[0]
        assert f'property="og:image" content="{img}"' in head, page
        assert 'name="twitter:card" content="summary_large_image"' in head, page
