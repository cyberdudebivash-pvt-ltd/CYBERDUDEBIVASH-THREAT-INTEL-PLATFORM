"""Homepage threat maps show no invented attacks, attributions or telemetry.

The feed carries no attack source/target geolocation. The canvas threat map
(index.html) used to present random arcs between hardcoded cities as a "LIVE
... GLOBAL ATTACK MONITOR", labelled with invented actor groups, with fixed
"threat-source" cities and per-city threat levels, a sine-wave "AI-CONF",
fixed satellite/storm counts, and a hardcoded "RU->US CRITICAL" ticker. The
Genesis "GLOBAL ATTACK MAP" (js/homepage-dashboard-engine.js) guessed attack
flows per country from title keywords. These checks keep all of that out.
Local files only; no network.
"""
from __future__ import annotations

import re
from pathlib import Path

from scripts.homepage_source import stale_asset_versions

REPO = Path(__file__).resolve().parent.parent
INDEX = (REPO / "index.html").read_text(encoding="utf-8")
ENGINE = (REPO / "js/homepage-dashboard-engine.js").read_text(encoding="utf-8")


def _block(src: str, start: str, end: str) -> str:
    i = src.index(start)
    return src[i:src.index(end, i)]


PANEL = _block(INDEX, '<div id="cdb-threat-map-panel">', "@keyframes ticker-scroll")
MAP_JS = _block(INDEX, "var CITIES = [", "/* ── BOOT SCHEDULE")


def test_panel_does_not_claim_live_attack_monitoring():
    for banned in ("LIVE CYBER THREAT MAP", "GLOBAL ATTACK MONITOR", "cdb-map-live-dot",
                   "COUNTRIES MONITORED</span>", "ACTOR GROUPS TRACKED</span>", "⚡ LIVE:"):
        assert banned not in PANEL, banned
    assert "ILLUSTRATIVE ANIMATION" in PANEL
    assert "do not represent observed attacks" in PANEL


def test_ticker_ships_no_invented_attributions():
    ticker = _block(PANEL, 'id="cdb-ticker-text"', "</span>")
    assert not re.search(r"[A-Z]{2}\s*(→|->|&rarr;)\s*[A-Z]{2}", ticker), ticker
    assert "Waiting for the live feed" in ticker


def test_cities_are_coordinates_only():
    rows = re.findall(r"^\s*\[('[^']*'[^\]]*)\]", _block(MAP_JS, "var CITIES = [", "];"), re.M)
    assert len(rows) >= 10
    for row in rows:
        assert len(row.split(",")) == 3, f"city row carries more than name/lat/lon: [{row}]"
    assert "city[3]" not in MAP_JS and "city[4]" not in MAP_JS
    assert "threat-source region" not in MAP_JS and "Threat level ' + level" not in MAP_JS


def test_arcs_carry_no_actor_names():
    groups = _block(MAP_JS, "var GROUPS = [", "];")
    assert "name:" not in groups
    for banned in ("APT-LAZARUS", "APT-COZY", "APT-FANCY", "grp.name", "a.group", "['LAZ',"):
        assert banned not in MAP_JS, banned


def test_canvas_overlay_has_no_invented_telemetry():
    for banned in ("AI-CONF", "aiConf", "SATS: 4 ACTIVE", "STORMS: 3 DETECTED",
                   "CONSTELLATIONS: 4", "LIVE INTEL", "LIVE — GLOBAL THREAT MONITOR",
                   "label:'DEFCON'", "label:'ESCALATE'", "ctx.fillText(con.name",
                   "LAZARUS-NEXUS", "BEAR-CLUSTER", "DRAGON-ARRAY", "PANDA-GRID"):
        assert banned not in MAP_JS, banned
    assert "ILLUSTRATIVE — NOT LIVE ATTACKS" in MAP_JS
    assert "NO ATTACK GEODATA IN FEED" in MAP_JS
    # No country is boxed and labelled as a threat zone.
    assert "var THREAT_ZONES = [];" in MAP_JS
    assert not re.search(r"label:'(RU|CN|KP|IR|BY)'", MAP_JS)


def test_genesis_attack_map_does_not_guess_flows():
    for banned in ("countries = {'CN':'China'", "t.includes('us ')", "desc:'Attack flows mapped'",
                   "' FLOWS'", "mapSum.total_flows", "flows</span>"):
        assert banned not in ENGINE, banned
    # Both render paths (client fallback and genesis.json loader) defer to the
    # one origin-attribution view instead of estimating flows.
    assert ENGINE.count('href="#eicc-heatmap"') == 2
    assert ENGINE.count("No attack geodata in feed") == 2
    assert 'id="eicc-heatmap"' in INDEX


def test_map_ticker_never_prints_a_placeholder_as_an_origin():
    # The feed writes "UNKNOWN" when nothing is attributed; the ticker used to
    # render "UNKNOWN CRITICAL ..." on every item. It must drop the same
    # placeholder set the EICC geographic panel excludes.
    placeholder = "/^(unknown|unattributed|n\\/a|none|null|-)$/i"
    assert placeholder in INDEX  # buildHeatmap()
    ticker = _block(ENGINE, "function renderMapTicker(data) {", "tickerEl.innerHTML")
    assert placeholder + ".test(String(geoSrc).trim())) geoSrc = ''" in ticker


def test_engine_cache_busting_hash_is_current():
    assert stale_asset_versions() == []
