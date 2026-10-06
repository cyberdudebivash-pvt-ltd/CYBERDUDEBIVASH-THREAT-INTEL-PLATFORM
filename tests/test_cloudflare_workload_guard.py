"""Negative controls for the repository-wide Cloudflare configuration gate."""
import json
import shutil
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cloudflare_workload_guard as guard

@pytest.fixture
def checkout(tmp_path):
    baseline = json.loads((ROOT / guard.BASELINE).read_text())
    for path in list(baseline["workers"]) + [guard.BASELINE]:
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, dest)
    return tmp_path

def test_current_inventory_matches_baseline():
    assert guard.check() == []

@pytest.mark.parametrize("worker", [
    "intel-gateway", "revenue-engine", "intel-retention-engine", "swarm-live"])
def test_binding_expansion_in_any_worker_is_rejected(checkout, worker):
    path = checkout / "workers" / worker / "wrangler.toml"
    with path.open("a") as file:
        file.write('\n[[r2_buckets]]\nbinding="UNREVIEWED_STORAGE"\nbucket_name="extra-bucket"\n')
    assert any(worker in error for error in guard.check(checkout))

def test_revenue_schedule_change_is_rejected(checkout):
    path = checkout / "workers/revenue-engine/wrangler.toml"
    source = path.read_text().replace('"0 9 * * *"', '"*/1 * * * *"')
    path.write_text(source)
    assert guard.check(checkout)

def test_production_environment_expansion_is_rejected(checkout):
    path = checkout / "workers/revenue-engine/wrangler.toml"
    with path.open("a") as file:
        file.write('\n[[env.production.services]]\nbinding="EXTRA_SERVICE"\nservice="unreviewed-worker"\n')
    assert guard.check(checkout)

def test_new_worker_configuration_is_rejected(checkout):
    path = checkout / "workers/new-worker/wrangler.jsonc"
    path.parent.mkdir()
    path.write_text('{"name":"new-worker"}')
    assert any("inventory" in error.lower() for error in guard.check(checkout))

def test_missing_worker_is_rejected(checkout):
    (checkout / "workers/swarm-live/wrangler.toml").unlink()
    assert guard.check(checkout)

def test_resource_target_change_is_rejected(checkout):
    path = checkout / "workers/intel-retention-engine/wrangler.toml"
    path.write_text(path.read_text().replace('sentinel-apex-data', 'different-bucket'))
    assert guard.check(checkout)

def test_source_release_metadata_can_change_without_expanding_resources(checkout):
    path = checkout / "workers/swarm-live/wrangler.toml"
    path.write_text(path.read_text().replace('compatibility_date = "2026-09-17"',
                                            'compatibility_date = "2026-10-06"'))
    assert guard.check(checkout) == []

def test_corrupt_baseline_fails_closed(checkout):
    (checkout / guard.BASELINE).write_text('{"schema_version":99}')
    with pytest.raises(ValueError):
        guard.check(checkout)

def test_ci_runs_the_guard_and_negative_controls():
    workflow = (ROOT / ".github/workflows/r2-finops-regression-gate.yml").read_text()
    assert "python scripts/cloudflare_workload_guard.py" in workflow
    assert "tests/test_cloudflare_workload_guard.py" in workflow
    assert "'workers/**/wrangler.*'" in workflow

