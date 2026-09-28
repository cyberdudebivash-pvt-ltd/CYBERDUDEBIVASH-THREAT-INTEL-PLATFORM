"""
tests/test_no_fabricated_intel_pages.py

Customer pages that used to present invented intelligence as live data
(2026-09-27). malware-intel-hub.html, linked from the homepage and five other
pages, streamed a Math.random() "sandbox detonation" feed with made-up hashes
and "C2" addresses (185.220.101.47 is a real public IP), showed fixed
"4.28M samples" / "18,441 YARA rules" counts, and a "C2 infrastructure
registry" attributing invented malware clusters to real ASNs (AS8075 is
Microsoft, AS16509 Amazon, AS20473 Vultr).

Each page listed here has been rebuilt on the live feed. The test keeps
fabrication from coming back: no random or fixed "live" numbers, no invented
network indicators, and the page must read the live feed.
ai-runtime-defense.html (2026-09-27) showed Math.random() "prompts screened"
counters and a blocked-attack log for a hosted runtime-guardrail service that
does not exist; it now says so and lists AI-security advisories from the feed.
soc-operations-center.html (2026-09-28) was an in-browser simulation: an
"ILLUSTRATIVE EVENT STREAM (SIMULATED DATA)", random 24h heatmap and source
counts, fixed IOC / sensor / replay / coverage figures and an invented
adversary graph, AI gauges, malware cards and honeynet mesh. It is rebuilt on
the live feed (js/soc-ops-model.js); panels with no data source were removed.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# page -> the live API the page must read
CLEANED_PAGES = {
    "malware-intel-hub.html": "/api/feed.json",
    "ai-runtime-defense.html": "/api/feed.json",
    "soc-operations-center.html": "/api/v1/intel/latest.json",
    "support-center.html": "/api/watchdog/health",
}

SHARED_VIEW = REPO / "js" / "feed-topic-view.js"

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
ASN = re.compile(r"\bAS\d{3,6}\b")


def _text(page):
    return (REPO / page).read_text(encoding="utf-8")


@pytest.mark.parametrize("page", sorted(CLEANED_PAGES))
def test_no_randomly_generated_values(page):
    assert "Math.random" not in _text(page)


@pytest.mark.parametrize("page", sorted(CLEANED_PAGES))
def test_no_invented_network_indicators(page):
    html = _text(page)
    ips = [ip for ip in IPV4.findall(html) if not ip.startswith(("0.", "127."))]
    assert ips == [], f"hardcoded IP addresses: {ips}"
    assert ASN.findall(html) == [], "hardcoded ASN attributions"


@pytest.mark.parametrize("page", sorted(CLEANED_PAGES))
def test_reads_the_live_feed(page):
    """Either fetches the API inline, or renders through the shared
    js/feed-topic-view.js, which fetches /api/feed.json."""
    html = _text(page)
    api = CLEANED_PAGES[page]
    if 'src="/js/feed-topic-view.js"' in html:
        assert "FeedTopicView.render(" in html
        assert f"fetch(opts.feedUrl || '{api}'" in SHARED_VIEW.read_text(encoding="utf-8")
    else:
        assert f"fetch('{api}'" in html


def test_shared_view_has_no_fabrication_and_escapes_feed_text():
    js = SHARED_VIEW.read_text(encoding="utf-8")
    assert "Math.random" not in js and "setInterval" not in js
    assert "esc(i.title)" in js and "safeUrl(i.source_url)" in js


def test_malware_hub_claims_removed():
    html = _text("malware-intel-hub.html")
    for claim in ("4.28M", "Sandbox Detonation", "18,441", "C2 Infrastructure Registry", "setInterval"):
        assert claim not in html, claim


def test_ai_runtime_defense_claims_removed():
    html = _text("ai-runtime-defense.html")
    for claim in ("2.84M", "tenant=ent", "setInterval"):
        assert claim not in html, claim
    # The hosted runtime product does not exist; the page must say so.
    assert "not offered as a hosted service today" in html


def test_malware_hub_detection_links_are_real_worker_routes():
    html = _text("malware-intel-hub.html")
    worker = (REPO / "workers" / "intel-gateway" / "src").glob("*.js")
    src = "\n".join(p.read_text(encoding="utf-8") for p in worker)
    links = re.findall(r'href="(/api/v1/export/[^"]+)"', html)
    assert links, "detection export links missing"
    missing = [l for l in links if l.rsplit("/", 1)[-1] not in src]
    assert missing == [], f"export files the Worker does not serve: {missing}"


def test_registry_marks_cleaned_pages_live():
    reg = (REPO / "scripts" / "build_capability_registry.py").read_text(encoding="utf-8")
    for page in CLEANED_PAGES:
        m = re.search(r'"' + re.escape(page) + r'":\s*\("CUSTOMER_UI",\s*"(\w+)"', reg)
        assert m and m.group(1) == "live", page


# Mockup pages with invented "live" data and no API call, replaced by a
# redirect to the nearest real page (2026-09-27): page -> redirect target.
REDIRECTED_PAGES = {
    "ai-security-ops-hub.html": "ai-runtime-defense.html",
    "evidence-threat-map.html": "enterprise-knowledge-graph.html",
    "soc-workspace.html": "enterprise-cyber-intelligence-os.html",
    "unified-ops-hub.html": "enterprise-cyber-intelligence-os.html",
    "telemetry-embedding.html": "observability.html",
    "telemetry-visibility-ops.html": "observability.html",
}


@pytest.mark.parametrize("page", sorted(REDIRECTED_PAGES))
def test_mockup_page_redirects_to_a_live_page(page):
    html = _text(page)
    target = REDIRECTED_PAGES[page]
    assert f'content="0; url=/{target}"' in html
    assert f"window.location.replace('/{target}'" in html
    assert 'name="robots" content="noindex' in html
    assert "Math.random" not in html and "setInterval" not in html
    cov = json.loads((REPO / "data" / "quality" / "frontend_api_coverage_report.json").read_text(encoding="utf-8"))
    assert target in {p["file"] for p in cov["dynamic_pages"]}, f"{target} is not a live (API-backed) page"


def test_redirected_pages_are_not_in_sitemaps():
    maps = "\n".join(p.read_text(encoding="utf-8") for p in REPO.glob("sitemap*.xml"))
    listed = [p for p in REDIRECTED_PAGES if "/" + p + "<" in maps]
    assert listed == []


def _visible(page):
    """Page text minus HTML comments (the rebuild note quotes the old labels)."""
    return re.sub(r"<!--.*?-->", "", _text(page), flags=re.S)


def test_soc_operations_center_ships_no_simulation():
    html = _visible("soc-operations-center.html")
    for claim in ("ILLUSTRATIVE", "SIMULATED DATA", "INTEL_ITEMS", "STREAM_DESCS", "Honeynet", "honeynet",
                  "Sensors", "YARA", "Adversary Graph", "graph-svg", "AI Runtime", "Replay", "104</div>", "100%</div>"):
        assert claim not in html, claim
    assert "innerHTML" not in html, "feed text is set with textContent only"
    # Only the platform's own live endpoints are read.
    fetched = set(re.findall(r"(?:fetch|getJson)\('([^']+)'", html))
    assert fetched == {"/api/watchdog/health", "/api/watchdog/brief", "/api/v1/intel/latest.json"}, fetched
    # Freshness authority gates every figure; KPI containers ship no numbers.
    assert "M.publication(" in html and "withhold(" in html
    assert re.search(r'id="so-kpis"[^>]*></div>', html)
    assert '<script src="/js/soc-ops-model.js"></script>' in html


def test_soc_ops_model_has_no_fabrication():
    js = (REPO / "js" / "soc-ops-model.js").read_text(encoding="utf-8")
    for banned in ("Math.random", "setInterval", "innerHTML", "fetch("):
        assert banned not in js, banned


# 2026-09-28 pre-release sweep: hardcoded mockups replaced by redirects to
# their live equivalents (page -> target, query string preserved).
REDIRECTS = {
    "billing-center.html": "/subscription-management.html",
    "customer-dashboard.html": "/soc-operations-center.html",
    "daily-operations-center.html": "/soc-operations-center.html",
    "dependency-platform.html": "/api-key-manager.html",
    "executive-reporting-center.html": "/enterprise-cyber-intelligence-os.html",
    "mssp-customer-center.html": "/mssp-tenant-dashboard.html",
    "mssp-partner-portal.html": "/mssp-tenant-dashboard.html",
    "my-exposure-center.html": "/cyber-watchdog.html#watches",
    "payment-confirmation.html": "/payment-status-dashboard.html",
    "value-center.html": "/roi-calculator.html",
    "api-management-center.html": "/api-key-manager.html",
    "customer-portal.html": "/api-key-manager.html",
}


@pytest.mark.parametrize("page", sorted(REDIRECTS))
def test_mockup_is_a_redirect_to_a_live_page(page):
    html = _text(page)
    target = REDIRECTS[page]
    path, _, frag = target.partition("#")
    assert f'http-equiv="refresh" content="0; url={target}"' in html
    assert f"window.location.replace('{path}' + qs" in html
    if frag:
        assert f"+ '#{frag}')" in html
    assert "Math.random" not in html and len(html) < 4000, "a redirect page carries no mockup content"
    registry = json.loads((REPO / "data/quality/frontend_capability_registry.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in registry["entries"]}
    assert by_id[page]["category"] == "DEPRECATED"
    target_entry = by_id[path.lstrip("/")]
    # A redirect never lands on another mockup or redirect: the target is live
    # (or, for roi-calculator.html, legitimately static -- values the customer enters).
    assert target_entry["category"] == "CUSTOMER_UI", target_entry
    assert target_entry["status"] in ("live", "static_content"), target_entry


def test_support_center_invents_no_tickets_and_matches_the_contract():
    html = _visible("support-center.html")
    for banned in ("TKT-", "Math.random", "slaRemain", "Open ticket", "innerHTML"):
        assert banned not in html, banned
    contract = json.loads((REPO / "config/commercial-contract.json").read_text(encoding="utf-8"))
    for tier, spec in contract["tiers"].items():
        row = re.search(r'<tr data-tier="%s"><td>[^<]+</td><td>([^<]+)</td></tr>' % tier, html)
        assert row, tier
        assert row.group(1) == spec["support"], f"{tier}: page says {row.group(1)!r}, contract says {spec['support']!r}"
    assert "mailto:support@cyberdudebivash.com" in html


def test_api_reference_card_claims_are_live_or_removed():
    html = _text("api-reference-card.html")
    body = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
    for banned in ("77+", "200 Live", "&lt;80ms", "55+", "Production API v184.0"):
        assert banned not in body, banned
    assert "fetch('/api/watchdog/health'" in html
    assert 'id="arc-count"' in html and 'id="arc-version"' in html
    assert "Uptime commitment (Enterprise / MSSP; Pro 99.5%)" in html
