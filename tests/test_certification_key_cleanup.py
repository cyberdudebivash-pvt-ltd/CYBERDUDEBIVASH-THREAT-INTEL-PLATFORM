"""Execute the real lifecycle workflow's rotation/cleanup shell offline."""
import os
from pathlib import Path
import subprocess

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/commercial-customer-ops-certification.yml'


def cleanup_scenario(tmp_path, *, rotation='missing', status='200', workflow=WORKFLOW):
    jobs = yaml.safe_load(workflow.read_text())['jobs']
    run = jobs['lifecycle-state-matrix']['steps'][0]['run']
    # Execute the checked-in functions, real rotation assignment and real
    # terminal cleanup. Unrelated live lifecycle probes are deliberately
    # excluded: this test is about revoking whichever controlled key remains.
    prefix = run[:run.index('echo "--- Provisioning')]
    start = run.index('echo "--- ROTATED:')
    end = run.index('ST=$(wait_key_state "$KEY" denied)', start)
    footer = run[run.index('echo "--- Cleanup:'):]
    shell = prefix + 'KEY="fixture-original"\nCURRENT_KEY="$KEY"\n' + run[start:end] + footer
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    curl = bin_dir / 'curl'
    curl.write_text('''#!/bin/bash
if [[ "$*" == *"/rotate"* ]]; then
  if [[ "$ROTATION" == "transport" ]]; then exit 7; fi
  if [[ "$ROTATION" == "success" ]]; then printf '{"new_key":"fixture-new"}'; else printf '{"error":"rotation_rejected"}'; fi
  exit 0
fi
if [[ "$*" == *"DELETE"* ]]; then
  for arg in "$@"; do
    if [[ "$arg" == https://example.test/api/admin/keys/* ]]; then printf '%s\\n' "$arg" >> "$DELETE_LOG"; fi
  done
  if [[ "$CLEANUP_STATUS" == "transport" ]]; then exit 7; fi
  if [[ "$*" == *"%{http_code}"* ]]; then printf '%s' "$CLEANUP_STATUS"; fi
  exit 0
fi
exit 99
''')
    curl.chmod(0o755)
    log = tmp_path / 'deleted'
    env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}', WORKER_BASE='https://example.test',
               ADMIN_SECRET='fixture-admin-secret', ROTATION=rotation, CLEANUP_STATUS=status, DELETE_LOG=str(log))
    result = subprocess.run(['/bin/bash', '-c', shell], env=env, capture_output=True, text=True, timeout=10)
    deleted = log.read_text().splitlines() if log.exists() else []
    assert 'fixture-admin-secret' not in result.stdout + result.stderr
    assert 'fixture-original' not in result.stdout + result.stderr
    assert 'fixture-new' not in result.stdout + result.stderr
    return result, deleted


@pytest.mark.parametrize('status', ['200', '204', '404'])
def test_failed_rotation_revokes_original_and_preserves_failure(tmp_path, status):
    result, deleted = cleanup_scenario(tmp_path, status=status)
    assert result.returncode == 1, 'failed rotation must keep certification failed'
    assert deleted == ['https://example.test/api/admin/keys/fixture-original']
    assert 'Cleanup complete.' in result.stdout


@pytest.mark.parametrize('status', ['200', '204', '404'])
def test_successful_rotation_revokes_replacement_once(tmp_path, status):
    result, deleted = cleanup_scenario(tmp_path, rotation='success', status=status)
    assert result.returncode == 0
    assert deleted == ['https://example.test/api/admin/keys/fixture-new']


@pytest.mark.parametrize('rotation', ['missing', 'success'])
@pytest.mark.parametrize('status', ['401', '403', '500', 'transport'])
def test_cleanup_failure_remains_blocking_and_exit_trap_retains_key(tmp_path, rotation, status):
    result, deleted = cleanup_scenario(tmp_path, rotation=rotation, status=status)
    assert result.returncode != 0
    expected = 'fixture-new' if rotation == 'success' else 'fixture-original'
    # One explicit attempt plus the existing EXIT safety net; no retry loop.
    assert deleted == [f'https://example.test/api/admin/keys/{expected}'] * 2
    assert 'Cleanup complete.' not in result.stdout


def test_rotation_transport_failure_still_revokes_original_via_exit_trap(tmp_path):
    result, deleted = cleanup_scenario(tmp_path, rotation='transport')
    assert result.returncode != 0
    assert deleted == ['https://example.test/api/admin/keys/fixture-original']
