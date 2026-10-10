"""Pages that act on API keys, sessions or payments cannot be clickjacked.

The static site is served by GitHub Pages behind Cloudflare: _headers is never
applied and the live pages carry no X-Frame-Options / CSP frame-ancestors
(frame-ancestors in a <meta> CSP is ignored by spec). js/frame-guard.js hides
a page framed by another origin; cloudflare/security_headers_transform_rule.json
is the header-level fix for the account owner to apply. Local files + node.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "js/frame-guard.js"
TAG = '<script src="/js/frame-guard.js"></script>'
SENSITIVE = [
    "login.html", "landing/auth.html", "get-api-key.html", "api-key-manager.html",
    "customer/api-keys.html", "upgrade.html", "billing.html", "subscription-management.html",
    "payment-submission.html", "PAYMENT-GATEWAY.html", "store.html", "onboarding.html",
    "developer-portal.html", "dashboard.html", "admin.html", "mssp-tenant-dashboard.html",
    "contact-enterprise.html", "index.html",
]


@pytest.mark.parametrize("page", SENSITIVE)
def test_guard_is_the_first_script_in_head(page):
    src = (REPO / page).read_text(encoding="utf-8")
    head = src[:src.lower().index("</head>")]
    assert TAG in head, page
    first_script = re.search(r"<script\b[^>]*>", head, re.I)
    assert first_script and first_script.group(0) == TAG[:-len("</script>")], (page, first_script.group(0))


def _run(parent: str) -> dict:
    if not shutil.which("node"):
        pytest.skip("node not installed")
    js = """
const style = { v: null, setProperty(k, v, p) { if (k === 'display') this.v = v + (p ? ' !' + p : ''); } };
const replaced = [];
const self = {};
const origin = 'https://intel.cyberdudebivash.com';
const top = PARENT === 'none' ? self : { location: {
  get origin() { if (PARENT === 'cross') throw new Error('SecurityError'); return origin; },
  replace(u) { if (PARENT === 'cross-blocked') throw new Error('blocked'); replaced.push(u); } } };
self.self = self; self.top = top;
self.location = { origin, href: origin + '/get-api-key.html' };
global.window = self;
global.document = { documentElement: { style } };
""".replace("PARENT", json.dumps(parent)) + GUARD.read_text(encoding="utf-8") + \
        "\nconsole.log(JSON.stringify({ display: style.v, replaced }));"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def test_not_framed_is_untouched():
    assert _run("none") == {"display": None, "replaced": []}


def test_cross_origin_frame_is_hidden_and_busted():
    out = _run("cross")
    assert out["display"] == "none !important"
    assert out["replaced"] == ["https://intel.cyberdudebivash.com/get-api-key.html"]


def test_same_origin_frame_is_allowed():
    # A same-origin parent's location is readable and matches: left visible.
    assert _run("same") == {"display": None, "replaced": []}


def test_cloudflare_rule_covers_static_pages_only():
    rule = json.loads((REPO / "cloudflare/security_headers_transform_rule.json").read_text(encoding="utf-8"))
    rs = rule["ruleset"]
    assert rs["phase"] == "http_response_headers_transform"
    (r,) = rs["rules"]
    assert 'not (http.request.uri.path in {"/api" "/reports" "/taxii" "/auth" "/swarm" "/feed.json" "/latest.json"})' in r["expression"]
    for prefix in ("/api/", "/reports/", "/taxii/", "/auth/", "/swarm/"):
        assert f'not starts_with(http.request.uri.path, "{prefix}")' in r["expression"]
    h = r["action_parameters"]["headers"]
    assert h["X-Frame-Options"]["value"] in ("DENY", "SAMEORIGIN")
    # Header CSP carries only frame-ancestors, so it cannot tighten script/style/connect.
    assert h["Content-Security-Policy"]["value"].startswith("frame-ancestors ")
    assert ";" not in h["Content-Security-Policy"]["value"]
    assert h["X-Content-Type-Options"]["value"] == "nosniff"


def _worker_route_prefixes():
    """Top-level path prefixes a Worker serves on intel.cyberdudebivash.com."""
    prefixes = set()
    for toml in REPO.glob("workers/*/wrangler.toml"):
        for pat in re.findall(r'pattern\s*=\s*"intel\.cyberdudebivash\.com(/[^"]*)"', toml.read_text(encoding="utf-8")):
            prefixes.add("/" + pat.strip("/").split("/")[0] + "/")
    return prefixes


def test_cloudflare_rule_excludes_every_worker_route():
    # The rule "set"s headers, so on a Worker-served path it would replace
    # that Worker's own (often stricter) CSP / X-Frame-Options. 2026-09-28:
    # /swarm/* was missing -- swarm-live's default-src 'none' CSP and DENY
    # would have been weakened to frame-ancestors 'self' / SAMEORIGIN.
    rule = json.loads((REPO / "cloudflare/security_headers_transform_rule.json").read_text(encoding="utf-8"))
    expr = rule["ruleset"]["rules"][0]["expression"]
    prefixes = _worker_route_prefixes()
    assert {"/api/", "/swarm/"} <= prefixes, prefixes
    for prefix in sorted(prefixes):
        assert f'not starts_with(http.request.uri.path, "{prefix}")' in expr, f"rule does not exclude Worker route {prefix}"
        assert f'"{prefix.rstrip("/")}"' in expr, f"rule does not exclude the bare path {prefix.rstrip('/')}"
