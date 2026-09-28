"""Homepage threat panel shows no invented attacks, attributions or telemetry.

2026-09-28: the illustrative canvas map was replaced by the Live Threat Board
(/api/watchdog/brief only); the history below explains what used to be there.

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
BOARD_JS = _block(INDEX, "/* LIVE THREAT BOARD", "</script>")


def test_panel_is_the_live_threat_board_not_an_animation():
    # 2026-09-28 customer escalation: an "ILLUSTRATIVE ANIMATION" on a live
    # production platform. The panel now shows only live feed data.
    assert "LIVE THREAT BOARD" in PANEL
    assert 'id="cdb-live-board"' in PANEL
    for banned in ("<canvas", "ILLUSTRATIVE", "SIMULATED", "NOT LIVE ATTACKS", "LIVE CYBER THREAT MAP",
                   "GLOBAL ATTACK MONITOR", "COUNTRIES MONITORED</span>", "ACTOR GROUPS TRACKED</span>", "⚡ LIVE:"):
        assert banned not in PANEL, banned
    assert "the feed carries no attack geolocation" in PANEL


def test_illustrative_map_engine_is_not_shipped():
    for banned in ("var CITIES = [", "var GROUPS = [", "CDB-RENDERER-ENGINE-V173-START", 'id="cdb-threat-canvas"',
                   "ILLUSTRATIVE — NOT LIVE ATTACKS", "NO ATTACK GEODATA IN FEED", "nuclearCanvasResurrection"):
        assert banned not in INDEX, banned
    # The GPU/RAF governance engines existed only to keep that canvas painted.
    assert "/js/engines/" not in INDEX


def test_board_reads_only_the_freshness_contracted_brief():
    assert "fetch('/api/watchdog/brief?limit=5'" in BOARD_JS
    assert BOARD_JS.count("fetch(") == 1, "one data source only"
    # First render reuses the page's single shared brief request.
    assert "window.APEX_BRIEF" in BOARD_JS
    # A stale feed is shown only through last_authoritative, labelled NOT LIVE.
    assert "last.live === false" in BOARD_JS
    assert "NOT LIVE" in BOARD_JS
    # Feed text is set as text, never parsed as markup.
    assert "innerHTML" not in BOARD_JS and "insertAdjacentHTML" not in BOARD_JS
    assert "Math.random" not in BOARD_JS


def test_ticker_ships_no_invented_attributions():
    ticker = _block(PANEL, 'id="cdb-ticker-text"', "</span>")
    assert not re.search(r"[A-Z]{2}\s*(→|->|&rarr;)\s*[A-Z]{2}", ticker), ticker
    assert "Waiting for the live feed" in ticker


def test_genesis_attack_map_does_not_guess_flows():
    for banned in ("countries = {'CN':'China'", "t.includes('us ')", "desc:'Attack flows mapped'",
                   "' FLOWS'", "mapSum.total_flows", "flows</span>"):
        assert banned not in ENGINE, banned
    # Both render paths (client fallback and genesis.json loader) defer to the
    # one origin-attribution view instead of estimating flows.
    assert ENGINE.count('href="#eicc-heatmap"') == 2
    # The G11 tile is drawn by the engine renderer only; the fallback
    # (renderGenesis) draws no tiles since tests/test_genesis_truth.py.
    assert ENGINE.count("No attack geodata in feed") == 1
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
