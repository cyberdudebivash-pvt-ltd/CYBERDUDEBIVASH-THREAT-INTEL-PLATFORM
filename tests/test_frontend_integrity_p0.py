#!/usr/bin/env python3
"""
test_frontend_integrity_p0.py  —  SENTINEL APEX  v184.0
=========================================================
P0 Regression Suite: Frontend Integrity Registry (GATE E)

Context: GATE E ("Frontend integrity", post-deploy-validation.yml,
master-deployment-orchestrator.yml, self-healing.yml) hard-fails a deploy
when scripts/frontend_integrity.py's `verify` mode detects a mismatch
between config/frontend_checksums.json and the real protected assets.
This suite exercises `verify()` directly, against a hermetic tmp_path
sandbox (never the real repo's protected assets or registry), covering
the exact test matrix a security review of GATE E requires:

  unmodified source          -> PASS
  tampered source            -> FAIL (TAMPERED)
  deleted protected file     -> FAIL (MISSING)
  modified registry hash     -> FAIL (TAMPERED, symmetric to tampered source)
  missing registry entry     -> FAIL (UNREGISTERED)  [P0 fix, 2026-08-11 --
                                 this used to be a warning only, meaning an
                                 attacker (or an accidental edit) could delete
                                 a file's registry entry and `verify` would
                                 still report PASS with the file's tampering
                                 invisible, since the comparison loop only
                                 ever iterates *registered* assets]

Run:
  pytest tests/test_frontend_integrity_p0.py -v --tb=short
"""
import importlib.util
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "frontend_integrity.py"


def _load_module_against(tmp_path, protected_assets):
    """Loads a fresh copy of frontend_integrity.py with its module-level
    REPO_ROOT/PROTECTED_ASSETS/REGISTRY_PATH repointed at an isolated
    tmp_path sandbox, so tests never touch the real repo's registry or
    protected assets."""
    spec = importlib.util.spec_from_file_location("frontend_integrity_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.REPO_ROOT = tmp_path
    mod.PROTECTED_ASSETS = protected_assets
    mod.REGISTRY_PATH = tmp_path / "config" / "frontend_checksums.json"
    return mod


@pytest.fixture
def sandbox(tmp_path):
    assets = ["index.html", "js/a.js", "css/b.css"]
    (tmp_path / "js").mkdir()
    (tmp_path / "css").mkdir()
    (tmp_path / "index.html").write_text("<html>original</html>")
    (tmp_path / "js" / "a.js").write_text("console.log('a');")
    (tmp_path / "css" / "b.css").write_text("body{color:red}")
    mod = _load_module_against(tmp_path, assets)
    (tmp_path / "config").mkdir()
    registry = mod.generate_registry()
    mod.REGISTRY_PATH.write_text(__import__("json").dumps(registry, indent=2))
    return mod, tmp_path


def test_unmodified_source_passes(sandbox):
    mod, _ = sandbox
    exit_code, violations, warnings = mod.verify()
    assert exit_code == 0
    assert violations == []


def test_tampered_source_fails(sandbox):
    mod, tmp_path = sandbox
    (tmp_path / "index.html").write_text("<html>TAMPERED</html>")
    exit_code, violations, warnings = mod.verify()
    assert exit_code == 1
    assert any("TAMPERED: index.html" in v for v in violations)


def test_deleted_protected_file_fails(sandbox):
    mod, tmp_path = sandbox
    (tmp_path / "js" / "a.js").unlink()
    exit_code, violations, warnings = mod.verify()
    assert exit_code == 1
    assert any("MISSING: js/a.js" in v for v in violations)


def test_modified_registry_hash_fails(sandbox):
    mod, tmp_path = sandbox
    import json
    registry = json.loads(mod.REGISTRY_PATH.read_text())
    registry["assets"]["css/b.css"]["sha256"] = "deadbeef" * 8
    mod.REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    exit_code, violations, warnings = mod.verify()
    assert exit_code == 1
    assert any("TAMPERED: css/b.css" in v for v in violations)


def test_missing_registry_entry_fails_not_warns(sandbox):
    """P0 fix: a protected file with no registry entry has unverifiable
    integrity and must fail the gate, not merely warn. Regresses the exact
    bypass this review's Phase 3 test matrix caught: deleting a file's
    registry entry used to leave `verify()` reporting PASS."""
    mod, tmp_path = sandbox
    import json
    registry = json.loads(mod.REGISTRY_PATH.read_text())
    del registry["assets"]["js/a.js"]
    mod.REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    exit_code, violations, warnings = mod.verify()
    assert exit_code == 1, "an unregistered protected file must fail the gate, not just warn"
    assert any("UNREGISTERED: js/a.js" in v for v in violations)


def test_tampering_combined_with_stale_missing_entry_still_caught(sandbox):
    """Defense in depth: even if an attacker both tampers with a file AND
    removes its registry entry (hiding the tamper from the TAMPERED check),
    the UNREGISTERED check still catches it independently."""
    mod, tmp_path = sandbox
    import json
    (tmp_path / "index.html").write_text("<html>TAMPERED-AND-HIDDEN</html>")
    registry = json.loads(mod.REGISTRY_PATH.read_text())
    del registry["assets"]["index.html"]
    mod.REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    exit_code, violations, warnings = mod.verify()
    assert exit_code == 1
    assert any("UNREGISTERED: index.html" in v for v in violations)


def test_generate_then_verify_round_trip_is_clean(sandbox):
    """The exact production sequence: generate() regenerates the registry
    from current disk state, and an immediate verify() against that same
    state must report zero violations and zero warnings -- the multi-commit
    concurrency scenario's end state (Phase 4 of the GATE E review)."""
    mod, tmp_path = sandbox
    (tmp_path / "js" / "a.js").write_text("console.log('changed');")
    registry = mod.generate_registry()
    import json
    mod.REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    exit_code, violations, warnings = mod.verify()
    assert exit_code == 0
    assert violations == []
    assert warnings == []
