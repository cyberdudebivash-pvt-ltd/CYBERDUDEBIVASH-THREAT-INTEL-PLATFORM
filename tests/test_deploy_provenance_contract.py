from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "workers" / "intel-gateway" / "src" / "index.js"
BUILD_INFO = ROOT / "workers" / "intel-gateway" / "src" / "build-info.js"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-worker.yml"


def test_liveness_exposes_version_and_exact_deploy_provenance():
    src = INDEX.read_text(encoding="utf-8")
    assert "import { DEPLOY_COMMIT_SHA, DEPLOY_RUN_ID } from './build-info.js';" in src
    assert "deploy_commit_sha: DEPLOY_COMMIT_SHA" in src
    assert "deploy_run_id: DEPLOY_RUN_ID" in src


def test_repository_build_info_defaults_never_claim_production_commit():
    src = BUILD_INFO.read_text(encoding="utf-8")
    assert 'DEPLOY_COMMIT_SHA = "development"' in src
    assert 'DEPLOY_RUN_ID = "local"' in src
    assert len(BUILD_INFO.read_bytes()) >= 1024
    assert src.rstrip().endswith("});")


def test_deploy_workflow_injects_full_github_sha_before_worker_validation():
    src = WORKFLOW.read_text(encoding="utf-8")
    inject = src.index('name: "Inject immutable deploy provenance"')
    preflight = src.index('name: " Pre-flight: Validate Worker source"')
    assert inject < preflight
    assert 'SHA="\${GITHUB_SHA}"' in src
    assert '^[0-9a-f]{40}$' in src
    assert 'export const DEPLOY_COMMIT_SHA = "$SHA";' in src
    assert 'export const DEPLOY_RUN_ID = "$RUN_ID";' in src
    assert 'export const DEPLOY_PROVENANCE = Object.freeze({' in src
    assert 'source: "github-actions-production-deploy"' in src


def test_post_deploy_provenance_assertion_is_hard_fail_not_informational():
    src = WORKFLOW.read_text(encoding="utf-8")
    marker = 'name: "[OK] Post-deploy smoke test (version + exact commit assertion)"'
    assert marker in src
    block = src[src.index(marker):]
    assert "continue-on-error: true" not in block.split("notify-on-failure:", 1)[0]
    assert 'if [ "$LIVE_SHA" = "$GITHUB_SHA" ]; then' in block
    assert 'FATAL: public route did not converge to GITHUB_SHA=$GITHUB_SHA' in block
    assert "Deploy provenance mismatch" in block
    assert "Smoke test skipped -- worker still propagating" not in block
