"""The homepage REPORTS tab loads the report catalog when clicked.

index.html's reports block wrapped window.cdbSwitchTab to call _loadReports()
on the REPORTS tab, but js/homepage-dashboard-engine.js loads later and
declares its own global cdbSwitchTab, which replaced the wrapper. Clicking
REPORTS then fetched nothing and the panel stayed hidden by its inline
display:none (reproduced in Chromium against production code with live data:
0 cards, panel hidden). The engine's cdbSwitchTab now calls the explicit
window.cdbOpenReportsPanel entry point. Local files + node only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INDEX = (REPO / "index.html").read_text(encoding="utf-8")
ENGINE = (REPO / "js/homepage-dashboard-engine.js").read_text(encoding="utf-8")


def _block(src: str, start: str) -> str:
    i = src.index(start)
    depth, j = 0, src.index("{", i)
    for k in range(j, len(src)):
        depth += {"{": 1, "}": -1}.get(src[k], 0)
        if depth == 0:
            return src[i:k + 1]
    raise AssertionError(start)


def test_engine_tab_switch_opens_the_reports_panel():
    fn = _block(ENGINE, "function cdbSwitchTab(tab, btn)")
    assert "if (tab === 'reports')" in fn
    assert "window.cdbOpenReportsPanel()" in fn
    # It must be handled before the manifestData-empty early return, which
    # would otherwise replace the panel (and its grid) with "DATA UNAVAILABLE".
    assert fn.index("if (tab === 'reports')") < fn.index("if (!manifestData || !manifestData.length)")


def test_reports_entry_point_is_defined_before_the_engine_loads():
    define = INDEX.index("window.cdbOpenReportsPanel = function()")
    engine_tag = INDEX.index('src="/js/homepage-dashboard-engine.js')
    assert define < engine_tag
    assert 'id="cdb-tab-reports-btn"' in INDEX and "cdbSwitchTab('reports', this)" in INDEX


def test_engine_switch_calls_entry_point_in_a_dom_stub():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    fn = _block(ENGINE, "function cdbSwitchTab(tab, btn)")
    js = """
const calls = [];
const panels = {};
const mk = id => ({ id, classList: { s: new Set(), add(c){this.s.add(c)}, remove(c){this.s.delete(c)} }, innerHTML: 'GRID' });
global.document = {
  querySelectorAll: () => [],
  getElementById: id => (panels[id] = panels[id] || mk(id)),
};
global.window = { cdbOpenReportsPanel: () => calls.push('open') };
let _cdbActiveTab = 'live';
let manifestData = [];   // empty feed: must not blank the reports panel
function cdbFallbackLive(){ calls.push('fallback'); }
""" + fn + """
cdbSwitchTab('reports', mk('btn'));
console.log(JSON.stringify({ calls, active: [...panels['cdb-panel-reports'].classList.s], html: panels['cdb-panel-reports'].innerHTML }));
"""
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert out == {"calls": ["open"], "active": ["active"], "html": "GRID"}
