"""Offline post-deploy contract checks; never contact Cloudflare."""
import sys
from pathlib import Path
from datetime import datetime, timezone
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import post_deploy_validator as validator

@pytest.mark.parametrize('body,valid,count', [
    ({'count': 10}, True, 10), ({'count': 0}, True, 0),
    ({'count': '10'}, False, None), ({'count': True}, False, None),
    ({'count': -1}, False, None), ({'count': 10.5}, False, None),
    ({'count': {}}, False, None), ({'count': None}, False, None),
    ({}, False, None), ([], False, None), ('unexpected', False, None),
])
def test_untrusted_feed_payloads_and_single_snapshot(tmp_path, monkeypatch, body, valid, count):
    calls = []
    if isinstance(body, dict):
        body = dict(body, generated_at=datetime.now(timezone.utc).isoformat())
    def probe(url, **kwargs):
        calls.append(url)
        payload = body
        if url.endswith('/api/health/live'):
            payload = {'version': 'test'}
        elif url.endswith('/api/health'):
            payload = {'checks': {'jwt_configured': True, 'r2_intel': 'ok'}}
        return {'ok': True, 'body': payload, 'status': 200, 'latency_ms': 1, 'error': None}
    monkeypatch.setattr(validator, 'probe_json', probe)
    monkeypatch.setattr(validator, 'REPO_ROOT', tmp_path)
    monkeypatch.setenv('ADMIN_SECRET', 'offline-test')
    monkeypatch.setattr(validator._deploy_health, 'probe', lambda base: (None, None))
    monkeypatch.setattr(validator._deploy_health, 'evaluate_deployment', lambda *args: {
        'health': {'http_status': 200}, 'deployment_operational': True,
        'failures': [], 'customer_intelligence_state': 'fresh',
        'customer_intelligence_healthy': True, 'liveness': {'alive': True},
    })
    result, code = validator.run_validation('test')
    gate = result['gates']['D']
    assert gate['measurement_valid'] is valid
    assert gate.get('count') == count
    assert ('count' in gate) is valid
    assert gate['measurement_state'] == ('MEASURED' if valid else 'INVALID_OR_UNAVAILABLE')
    assert gate['passed'] is (valid and count >= validator.MIN_ADVISORY_COUNT)
    assert calls.count(f'{validator.WORKER_BASE}/api/v1/intel/latest.json') == 1
    assert result['overall'] == ('ALL_PASSED' if valid and count >= 10 else 'SOFT_WARNINGS')
    assert code == 0  # Existing operational gate policy is preserved.
    assert (tmp_path / 'data/health/last_deploy_validation.json').is_file()
