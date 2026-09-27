"""EPSS is displayed on one scale, whatever scale the feed item carries.

Feed items carry epss_score as a 0-1 probability or a 0-100 percent depending
on the source (sentinel_blogger.py writes percent, apex_intelligence_upgrade.py
a probability); the customer catalog served e.g. 18.166. Renders that assumed
one scale showed it as "EPSS 1816.6%" (index.html reports grid, cve.html,
threat/index.html) or printed a 0.09 probability as "0.09%" and never let it
reach the >=50 priority thresholds (homepage-dashboard-engine.js). Every render
now goes through CDB_NORMALIZE.epss (js/metric-normalize.js) or the same rule
inline on pages that do not load it. Local files + node only; no network.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENGINE = (REPO / "js/homepage-dashboard-engine.js").read_text(encoding="utf-8")
INDEX = (REPO / "index.html").read_text(encoding="utf-8")
CVE = (REPO / "cve.html").read_text(encoding="utf-8")
THREAT = (REPO / "threat/index.html").read_text(encoding="utf-8")
ENT = (REPO / "dashboard/enterprise_dashboard_v2.html").read_text(encoding="utf-8")

# (value, expected percent string); None -> not shown.
CASES = [(0.0942, "9.4%"), (0.5, "50.0%"), (1, "100.0%"), (18.166, "18.2%"),
         (97.3, "97.3%"), ("0.25", "25.0%"), (None, None), ("", None), (-1, None), (250, None)]


def _node(js: str) -> str:
    if not shutil.which("node"):
        pytest.skip("node not installed")
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout


def _fn(src: str, start: str) -> str:
    i = src.index(start)
    depth, j = 0, src.index("{", i)
    for k in range(j, len(src)):
        depth += {"{": 1, "}": -1}.get(src[k], 0)
        if depth == 0:
            return src[i:k + 1]
    raise AssertionError(start)


def test_no_render_assumes_a_single_scale():
    banned = {
        "index.html": (INDEX, ["(r.epss_score * 100)"]),
        "js/homepage-dashboard-engine.js": (ENGINE, [
            "${item.epss_score}%", "item.epss_score + '%'", "d.epss_score + '%'",
            "parseFloat(item.epss_score).toFixed(1) + '%'", "Math.min(item.epss_score,100)",
            "epss=parseFloat(item.epss_score)||0,", "const epss = parseFloat(item.epss_score)||0;",
            "item.epss_score >= 50 ?"]),
        "cve.html": (CVE, ["Math.round(x * 100)"]),
        "threat/index.html": (THREAT, ["epss=i.epss_score!=null?parseFloat(i.epss_score):null"]),
        "dashboard/enterprise_dashboard_v2.html": (ENT, ["i.epss_score.toFixed(1)+'%'"]),
    }
    for name, (src, pats) in banned.items():
        for p in pats:
            assert p not in src, f"{name}: {p!r}"


def test_engine_and_reports_grid_use_the_canonical_normalizer():
    assert "window.CDB_NORMALIZE.epss(r.epss_score)" in INDEX
    assert ENGINE.count("CDB_NORMALIZE.epss(item.epss_score)") >= 12
    assert "CDB_NORMALIZE.epss(d.epss_score)" in ENGINE  # CSV export


def test_canonical_normalizer_scale_rule():
    js = f"const N=require({json.dumps(str(REPO / 'js/metric-normalize.js'))});" + \
        f"console.log(JSON.stringify({json.dumps([c[0] for c in CASES])}.map(v=>{{const r=N.epss(v);return r.state==='OK'?r.percent.toFixed(1)+'%':null}})))"
    assert json.loads(_node(js)) == [c[1] for c in CASES]


def test_cve_page_formatter_matches_the_rule():
    fn = _fn(CVE, "function fmtPct(x)")
    out = json.loads(_node(fn + f";console.log(JSON.stringify({json.dumps([c[0] for c in CASES])}.map(fmtPct)))"))
    assert out == [c[1] if c[1] else "&mdash;" for c in CASES]


def test_threat_page_probability_matches_the_rule():
    fn = _fn(THREAT, "function _epssProb(v)")
    out = json.loads(_node(fn + f";console.log(JSON.stringify({json.dumps([c[0] for c in CASES])}.map(v=>{{const p=_epssProb(v);return p==null?null:(p*100).toFixed(1)+'%'}})))"))
    assert out == [c[1] for c in CASES]
    # Downstream consumers treat it as a probability (x100 for display, >.5 threshold).
    assert re.search(r"epss\*100\)\.toFixed\(1\)", THREAT)
