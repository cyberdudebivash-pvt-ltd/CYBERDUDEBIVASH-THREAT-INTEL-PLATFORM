"""P0 R18 private evidence preflight: positive and mutation/negative controls.

Synthetic bytes here only test gate behavior; they are NEVER dossier evidence.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import p0_r18_private_evidence_gate as gate


SHA = "a" * 40


def _save(root, path, content):
    dest = root / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    dest.write_bytes(raw)
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest()}


def _bundle(root):
    cases = []
    for cve in sorted(gate.REQUIRED_CVES):
        base = cve.lower()
        obj = {"cve_id": cve, "tlp": "TLP:CLEAR"}
        row = {
            "cve": cve,
            "record": _save(root, f"records/{base}.json", json.dumps(obj)),
            "html": _save(root, f"html/{base}.html", f"<!doctype html><html><body>{cve}</body></html>"),
            "pdf": _save(root, f"pdf/{base}.pdf", b"%PDF-1.4\n1 0 obj\n%%EOF"),
            "stix": _save(root, f"stix/{base}.json", json.dumps({
                "type": "bundle", "id": "bundle--123e4567-e89b-42d3-a456-426614174000",
                "objects": [{"type": "indicator", "id": "indicator--123e4567-e89b-42d3-a456-426614174000"}],
            })),
            "source_evidence": [_save(root, f"source/{base}.txt", f"synthetic negative-control for {cve}")],
        }
        cases.append(row)
    index = {"schema_version": 1, "deployment_sha": SHA, "cases": cases}
    _write_index(root, index)
    return index


def _write_index(root, index):
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")


def test_synthetic_complete_fixture_only_passes_preflight(tmp_path):
    _bundle(tmp_path)
    result = gate.verify_bundle(tmp_path, SHA)
    assert result == {"status": "EVIDENCE_BYTES_VERIFIED_NOT_RELEASE_GO", "cases_verified": 8, "errors": []}
    assert "GO" not in {"GO", "PRODUCTION_GO"} & {result["status"]}


def test_missing_private_index_fails_closed(tmp_path):
    assert gate.verify_bundle(tmp_path, SHA)["status"] == "BLOCKED"


def test_missing_case_fails_closed(tmp_path):
    index = _bundle(tmp_path)
    index["cases"].pop()
    _write_index(tmp_path, index)
    assert gate.verify_bundle(tmp_path, SHA)["status"] == "BLOCKED"


def test_duplicate_case_cannot_satisfy_eight(tmp_path):
    index = _bundle(tmp_path)
    index["cases"][-1]["cve"] = index["cases"][0]["cve"]
    _write_index(tmp_path, index)
    assert gate.verify_bundle(tmp_path, SHA)["status"] == "BLOCKED"


def test_restricted_record_cannot_be_certified_public(tmp_path):
    index = _bundle(tmp_path)
    ref = index["cases"][0]["record"]
    index["cases"][0]["record"] = _save(tmp_path, ref["path"], json.dumps({
        "cve_id": index["cases"][0]["cve"], "tlp": "TLP:RED"
    }))
    _write_index(tmp_path, index)
    assert gate.verify_bundle(tmp_path, SHA)["status"] == "BLOCKED"


def test_changed_artifact_detected_by_hash(tmp_path):
    index = _bundle(tmp_path)
    (tmp_path / index["cases"][0]["pdf"]["path"]).write_bytes(b"%PDF-1.4\nmalicious mutation")
    assert gate.verify_bundle(tmp_path, SHA)["status"] == "BLOCKED"


def test_path_traversal_rejected(tmp_path):
    index = _bundle(tmp_path)
    index["cases"][0]["source_evidence"][0]["path"] = "../outside.txt"
    _write_index(tmp_path, index)
    assert gate.verify_bundle(tmp_path, SHA)["status"] == "BLOCKED"


def test_deployed_version_mismatch_blocks(tmp_path):
    _bundle(tmp_path)
    assert gate.verify_bundle(tmp_path, "b" * 40)["status"] == "BLOCKED"


def test_missing_corrob_source_evidence_blocks(tmp_path):
    index = _bundle(tmp_path)
    index["cases"][0]["source_evidence"] = []
    _write_index(tmp_path, index)
    assert gate.verify_bundle(tmp_path, SHA)["status"] == "BLOCKED"


def test_fake_stix_object_identifier_blocks(tmp_path):
    index = _bundle(tmp_path)
    ref = index["cases"][0]["stix"]
    index["cases"][0]["stix"] = _save(tmp_path, ref["path"], json.dumps({
        "type": "bundle", "objects": [{"type": "indicator", "id": "intel--badhex"}],
    }))
    _write_index(tmp_path, index)
    assert gate.verify_bundle(tmp_path, SHA)["status"] == "BLOCKED"
