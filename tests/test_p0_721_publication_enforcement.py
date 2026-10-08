#!/usr/bin/env python3
"""
tests/test_p0_721_publication_enforcement.py
P0 #721 -- last-mile TLP enforcement at the R2 report publisher (the sole sentinel-apex-reports writer,
run by both STAGE 3.5a and STAGE 5.4.0c).  A generated restricted report that is already on disk must not
reach R2 through this publisher, and the gate must never delete anything by itself.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_report_publisher as pub  # noqa: E402

NOW = datetime.now(timezone.utc)
TS = (NOW - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _item(iid, **kw):
    return dict({"id": iid, "title": iid, "timestamp": TS}, **kw)


FEED = [
    _item("intel--clear", tlp="TLP:CLEAR"),
    _item("intel--green", tlp="TLP:GREEN"),
    _item("intel--amber", tlp="TLP:AMBER"),
    _item("intel--red", tlp="TLP:RED"),
    _item("intel--unlabelled"),
    _item("intel--invalid", tlp="TLP:PURPLE"),
    _item("intel--laundered", tlp="TLP:CLEAR", evidence_chain=[{"tlp": "TLP:AMBER"}]),
]


def test_gate_passes_only_clear_and_reports_ids_with_reason_codes_only():
    state = {"items": {"intel--green": {"html_key": "reports/2026/10/intel--green.html"}}}
    ok, held = pub.apply_tlp_gate(FEED, state)
    assert [i["id"] for i in ok] == ["intel--clear"]
    assert {r["id"] for r in held} == {"intel--green", "intel--amber", "intel--red", "intel--unlabelled",
                                       "intel--invalid", "intel--laundered"}
    by_id = {r["id"]: r for r in held}
    assert by_id["intel--green"]["already_in_r2"] is True and by_id["intel--red"]["already_in_r2"] is False
    assert by_id["intel--unlabelled"]["reason_code"] == "MISSING_LABEL"
    assert by_id["intel--laundered"]["reason_code"] == "RESTRICTED_UPSTREAM_LABEL"
    for r in held:  # quarantine rows must never carry report content
        assert set(r) <= {"id", "reason_code", "reason", "label", "already_in_r2"}


def test_main_never_plans_a_put_for_a_denied_item_and_deletes_nothing(tmp_path):
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps(FEED))
    report = tmp_path / "r2_tlp_quarantine_report.json"
    state = {"items": {"intel--green": {"html_key": "reports/2026/10/intel--green.html",
                                        "canonical_ts": TS}}}
    seen = {}
    real_build_plan = pub.build_plan

    def spy(candidates, st, window_hours, now, max_deletes=None):
        seen["ids"] = [c["id"] for c in candidates]
        plan, puts, dels = real_build_plan(candidates, st, window_hours, now, max_deletes=max_deletes)
        seen["puts"], seen["dels"] = puts, dels
        return plan, puts, dels

    with patch.object(pub, "FEED_JSON", feed), patch.object(pub, "TLP_QUARANTINE_REPORT", report), \
            patch.object(pub, "load_publish_state", return_value=state), patch.object(pub, "build_plan", spy), \
            patch.object(pub, "emit_summary"), patch.object(pub, "report_publishing_enabled", return_value=True), \
            patch.object(sys, "argv", ["r2_report_publisher.py", "--dry-run"]):
        assert pub.main() == 0

    assert seen["ids"] == ["intel--clear"], "only the TLP:CLEAR item may become a publish candidate"
    assert all(p["id"] == "intel--clear" for p in seen["puts"])
    assert seen["dels"] == [], "the gate must not delete previously published objects by itself"
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert rep["quarantined"] == 6 and rep["needing_retraction_review"] == ["intel--green"]


def test_gate_is_wired_into_main_before_candidates_are_built():
    src = (REPO_ROOT / "scripts" / "r2_report_publisher.py").read_text(encoding="utf-8")
    main_src = src[src.index("def main()"):]
    assert main_src.index("apply_tlp_gate(") < main_src.index("build_publish_candidates(")
