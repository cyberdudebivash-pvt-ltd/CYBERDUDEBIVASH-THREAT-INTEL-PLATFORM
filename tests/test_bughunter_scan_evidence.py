"""Recon regeneration preserves scan evidence and never substitutes advisories."""
import json
import sys
from pathlib import Path
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import regenerate_engine_data as regen

def test_stale_scan_remains_same_snapshot(tmp_path):
    data = {"status":"COMPLETED","timestamp":(regen.NOW_UTC-timedelta(days=40)).isoformat(),
            "metrics":{"api_endpoints":7,"critical_findings":0},"findings_summary":[]}
    path=tmp_path/"scan.json"
    path.write_text(json.dumps(data))
    assert regen.generate_bughunter([{"risk_score":10}]*100,str(path)) == data

def test_missing_scan_cannot_be_created_from_advisories(tmp_path):
    result=regen.generate_bughunter([{"risk_score":10}]*100,str(tmp_path/"missing.json"))
    assert result["status"] == "AWAITING_SCAN"
    assert result["metrics"] == {}
    assert result["findings_summary"] == []
    assert "timestamp" not in result and "scan_id" not in result

def test_advisory_generated_snapshot_is_not_scan_evidence(tmp_path):
    path=tmp_path/"scan.json"
    path.write_text(json.dumps({"timestamp":(regen.NOW_UTC-timedelta(hours=1)).isoformat(),
        "metrics":{"api_endpoints":12},"findings_summary":[{"type":"CRITICAL_THREAT_ADVISORY"}]}))
    assert regen.generate_bughunter([],str(path))["status"] == "AWAITING_SCAN"

def test_malformed_and_future_snapshots_are_not_completed_scans(tmp_path):
    path=tmp_path/"scan.json"
    for data in [[],{"metrics":{},"timestamp":"bad"},{"metrics":{},"timestamp":"2026-01-01"},
                 {"metrics":{},"timestamp":(regen.NOW_UTC+timedelta(days=1)).isoformat()}]:
        path.write_text(json.dumps(data))
        assert regen.generate_bughunter([],str(path))["status"] == "AWAITING_SCAN"

