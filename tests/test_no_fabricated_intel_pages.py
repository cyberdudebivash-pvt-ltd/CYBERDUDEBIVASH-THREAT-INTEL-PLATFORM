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
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# page -> the live API the page must read
CLEANED_PAGES = {
    "malware-intel-hub.html": "/api/feed.json",
}

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
    html = _text(page)
    assert f"fetch('{CLEANED_PAGES[page]}'" in html


def test_malware_hub_claims_removed():
    html = _text("malware-intel-hub.html")
    for claim in ("4.28M", "Sandbox Detonation", "18,441", "C2 Infrastructure Registry", "setInterval"):
        assert claim not in html, claim


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
