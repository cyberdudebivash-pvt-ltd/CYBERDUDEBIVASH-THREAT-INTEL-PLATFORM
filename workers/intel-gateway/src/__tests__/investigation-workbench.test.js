import test from 'node:test';
import assert from 'node:assert/strict';

import {
  INVESTIGATION_WORKBENCH_VERSION,
  routeInvestigationWorkbench,
  __test,
} from '../investigation-workbench.js';

const baseItem = {
  id: 'intel--workbench-test-001',
  stix_id: 'indicator--11111111-1111-4111-8111-111111111111',
  title: 'Synthetic customer-release intelligence fixture CVE-2026-99999',
  description: 'Controlled fixture for investigation composition.',
  severity: 'CRITICAL',
  risk_score: 9.8,
  cvss_score: 9.8,
  epss_score: 0.91,
  kev_present: true,
  source: 'CISA',
  source_url: 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog',
  published_at: '2026-10-03T18:00:00Z',
  processed_at: '2026-10-03T18:01:00Z',
  threat_type: 'ransomware',
  actor_tag: 'APT41',
  actor_confidence: 75,
  confidence: 88,
  tlp: 'TLP:AMBER',
  cve_ids: ['CVE-2026-99999'],
  ttps: ['T1190', 'T1071.001'],
  mitre_tactics: ['Initial Access', 'Command and Control'],
  ioc_count: 2,
  ioc_counts: { ipv4: 1, domain: 1 },
  iocs: ['192.0.2.99', 'do-not-leak.example'],
  sigma_rule: [
    'title: Workbench fixture',
    'status: experimental',
    'logsource:',
    '  product: windows',
    'detection:',
    '  selection:',
    '    EventID: 1',
    '  condition: selection',
  ].join('\n'),
  kql_query: 'SecurityEvent | where EventID == 1 | project TimeGenerated, Computer',
  report_url: '/reports/2026/10/intel--workbench-test-001.html',
  pdf_url: '/reports/pdf/intel--workbench-test-001.pdf',
};

const relatedItem = {
  ...baseItem,
  id: 'intel--workbench-test-002',
  stix_id: 'indicator--22222222-2222-4222-8222-222222222222',
  title: 'Related synthetic fixture',
  risk_score: 8.1,
  cvss_score: 8.1,
  kev_present: false,
  report_url: '',
  pdf_url: '',
};

function envWith(items = [baseItem, relatedItem]) {
  return {
    INTEL_R2: {
      async get(key) {
        assert.equal(key, 'api/v1/intel/latest.json');
        return {
          async json() {
            return { items };
          },
        };
      },
    },
  };
}

function req(path, method = 'GET') {
  return new Request('https://intel.cyberdudebivash.com' + path, { method });
}

const paidAuth = {
  tier: 'PRO',
  key: 'p'.repeat(32),
  sub: 'customer-test',
  scopes: ['read:intel'],
};

async function call(path, { method = 'GET', auth = paidAuth, env = envWith() } = {}) {
  return routeInvestigationWorkbench({
    path: new URL('https://intel.cyberdudebivash.com' + path).pathname,
    request: req(path, method),
    env,
    auth,
    requestId: 'rid-test',
  });
}

test('capabilities truthfully declare a read-only surface', async () => {
  const res = await call('/api/v1/investigation/capabilities', { auth: { tier: 'FREE' } });
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.workbench_version, INVESTIGATION_WORKBENCH_VERSION);
  assert.equal(body.mode, 'read_only');
  assert.equal(body.safety.mutations, false);
  assert.equal(body.safety.binary_detonation, false);
  assert.equal(body.safety.raw_ioc_arrays_in_workbench_response, false);
});

test('synthetic replay is public, deterministic in structure and explicitly non-operational', async () => {
  const res = await call('/api/v1/demo/replay?scenario=ransomware', { auth: { tier: 'FREE' } });
  assert.equal(res.status, 200);
  assert.match(res.headers.get('cache-control'), /public/);
  const body = await res.json();
  assert.equal(body.synthetic, true);
  assert.equal(body.customer_data, false);
  assert.equal(body.network_actions, false);
  assert.equal(body.malware_execution, false);
  assert.equal(body.scenario_id, 'ransomware');
  assert.ok(body.events.length >= 5);
  assert.ok(body.events.every(e => /^T\d{4}(?:\.\d{3})?$/.test(e.technique)));
  const serialized = JSON.stringify(body);
  assert.match(serialized, /203\.0\.113\./);
  assert.match(serialized, /\.example/);
});

test('invalid replay scenario fails closed', async () => {
  const res = await call('/api/v1/demo/replay?scenario=not-real', { auth: { tier: 'FREE' } });
  assert.equal(res.status, 400);
  const body = await res.json();
  assert.equal(body.error, 'invalid_scenario');
  assert.deepEqual(body.valid_scenarios, ['ransomware', 'credential', 'cloud']);
});

test('workbench is GET-only', async () => {
  const res = await call('/api/v1/demo/replay', { method: 'POST', auth: { tier: 'FREE' } });
  assert.equal(res.status, 405);
  assert.equal(res.headers.get('allow'), 'GET');
});

test('live investigation requires an authenticated customer identity', async () => {
  const res = await call('/api/v1/investigation/item?id=' + encodeURIComponent(baseItem.id), {
    auth: { tier: 'FREE', key: null, jwt: false },
  });
  assert.equal(res.status, 401);
});

test('FREE identity cannot cross the graph entitlement boundary', async () => {
  const res = await call('/api/v1/investigation/item?id=' + encodeURIComponent(baseItem.id), {
    auth: { tier: 'FREE', key: 'f'.repeat(32), sub: 'free-test' },
  });
  assert.equal(res.status, 402);
});

test('unknown or legacy tier strings fail closed instead of inheriting paid access', async () => {
  const res = await call('/api/v1/investigation/item?id=' + encodeURIComponent(baseItem.id), {
    auth: { tier: 'LEGACY_PRO', key: 'l'.repeat(32), sub: 'legacy-test', scopes: ['read:intel'] },
  });
  assert.equal(res.status, 402);
  const body = await res.json();
  assert.equal(body.status, 'locked');
});

test('explicit restrictive scope fails closed on paid identity', async () => {
  const res = await call('/api/v1/investigation/item?id=' + encodeURIComponent(baseItem.id), {
    auth: { ...paidAuth, scopes: ['read:cves'] },
  });
  assert.equal(res.status, 403);
  const body = await res.json();
  assert.equal(body.reason, 'insufficient_scope');
  assert.equal(body.required, 'read:intel');
});

test('live investigation validates id before reading feed data', async () => {
  let reads = 0;
  const env = { INTEL_R2: { async get() { reads += 1; return null; } } };
  const res = await call('/api/v1/investigation/item', { env });
  assert.equal(res.status, 400);
  assert.equal(reads, 0);
});

test('live investigation returns 404 for an unknown current-feed id', async () => {
  const res = await call('/api/v1/investigation/item?id=missing');
  assert.equal(res.status, 404);
  const body = await res.json();
  assert.equal(body.error, 'not_found');
});

test('paid investigation composes canonical engines without leaking raw IOC values', async () => {
  const res = await call('/api/v1/investigation/item?id=' + encodeURIComponent(baseItem.id));
  assert.equal(res.status, 200);
  assert.match(res.headers.get('cache-control'), /no-store/);
  assert.equal(res.headers.get('x-sentinel-read-only'), 'true');

  const body = await res.json();
  assert.equal(body.read_only, true);
  assert.equal(body.intelligence.id, baseItem.id);
  assert.equal(body.intelligence.kev_present, true);
  assert.ok(body.risk_explanation.why_this_matters.length > 0);
  assert.ok(body.evidence_claims.length >= 3);
  assert.ok(body.mitre.techniques.includes('T1190'));
  assert.ok(body.correlation.related_items.some(i => i.id === relatedItem.id));
  assert.ok(body.correlation.graph.nodes.length > 0);
  assert.ok(body.evidence_timeline.length > 0);
  assert.ok(body.evidence_timeline.some(e => e.label === 'Detection Rules Published'));
  assert.ok(body.investigation_playbook);
  assert.equal(body.detection_availability.sigma, true);
  assert.equal(body.detection_availability.kql, true);
  assert.equal(body.detection_availability.artifact_count, 2);
  assert.equal(body.detection_availability.validation, 'canonical_detection_registry');
  assert.equal(body.customer_outputs.report.html, baseItem.report_url);
  assert.equal(body.customer_outputs.report.pdf, baseItem.pdf_url);
  assert.equal(body.customer_outputs.item_scoped.detections, '/api/v1/detections?intel_id=' + encodeURIComponent(baseItem.id));
  assert.equal(body.customer_outputs.item_scoped.stix, '/api/stix?id=' + encodeURIComponent(baseItem.id));

  const serialized = JSON.stringify(body);
  assert.doesNotMatch(serialized, /192\.0\.2\.99/);
  assert.doesNotMatch(serialized, /do-not-leak\.example/);
});

test('composite risk is never mislabeled as CVSS in analyst evidence', async () => {
  const riskOnly = {
    ...baseItem,
    id: 'intel--risk-only',
    stix_id: 'indicator--33333333-3333-4333-8333-333333333333',
    title: 'Risk-only fixture',
    risk_score: 9.4,
    cvss_score: null,
    epss_score: null,
    kev_present: false,
    actor_tag: '',
    actor_confidence: null,
    ioc_count: 0,
    ioc_counts: {},
    iocs: [],
    sigma_rule: '',
    kql_query: '',
    report_url: '',
    pdf_url: '',
  };
  const res = await call('/api/v1/investigation/item?id=' + encodeURIComponent(riskOnly.id), {
    env: envWith([riskOnly]),
  });
  assert.equal(res.status, 200);
  const body = await res.json();
  const claims = body.evidence_claims.map(c => c.claim);
  assert.ok(claims.some(v => /SENTINEL APEX composite risk score 9\.4\/10/.test(v)));
  assert.ok(!claims.some(v => /CVSS score 9\.4/.test(v)));
  assert.ok(body.risk_explanation.why_this_matters.some(v => /this value is not CVSS/.test(v)));
});

test('unsafe report targets are never projected to the customer response', () => {
  assert.equal(__test.safeReportPath('https://evil.example/report.pdf'), null);
  assert.equal(__test.safeReportPath('/reports/../secret'), null);
  assert.equal(__test.safeReportPath('/reports/pdf/good-report.pdf'), '/reports/pdf/good-report.pdf');
});

test('store outage returns retryable 503 instead of misclassifying customer auth', async () => {
  const env = { INTEL_R2: { async get() { throw new Error('r2 outage'); } } };
  const res = await call('/api/v1/investigation/item?id=' + encodeURIComponent(baseItem.id), { env });
  assert.equal(res.status, 503);
  assert.equal(res.headers.get('retry-after'), '30');
  const body = await res.json();
  assert.equal(body.error, 'intelligence_store_unavailable');
});
