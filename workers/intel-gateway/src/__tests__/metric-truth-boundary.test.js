import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import {
  explicitCvss,
  explicitRiskScore,
  hasExplicitCvss,
  metricTruth,
} from '../metric-semantics.js';
import { buildAnalystExplainabilityBlock } from '../p25-handlers.js';
import { buildP27MultiAudienceBlock } from '../p27-handlers.js';
import { buildP28BusinessImpactBlock } from '../p28-handlers.js';
import { buildP29LifecycleBlock, handleP29CustomerValueAnalytics } from '../p29-handlers.js';
import { buildP30SLABlock } from '../p30-handlers.js';
import { buildP32DecisionBlock, buildP32LifecycleBlock, handleP32Customer } from '../p32-handlers.js';
import {
  buildP33CaseBlock,
  buildP33OperationalDashboardBlock,
  handleP33Metrics,
  handleP33Mission,
  handleP33Observability,
} from '../p33-handlers.js';

const riskOnly = {
  id: 'intel--metric-truth-risk-only',
  title: 'Controlled metric truth fixture',
  description: 'A controlled fixture used to prove risk_score is never relabeled as CVSS.',
  severity: 'CRITICAL',
  risk_score: 9.8,
  epss_score: 0.42,
  confidence: 0.8,
  source: 'controlled-test',
  timestamp: '2026-10-04T00:00:00Z',
  processed_at: '2026-10-04T00:05:00Z',
  _score_details: { cvss: 9.8, kev: false },
  cve_ids: ['CVE-2026-99999'],
  ioc_count: 2,
  ioc_counts: { ipv4: 1, domain: 1 },
  ttps: ['T1190', 'T1078'],
  mitre_tactics: ['Initial Access'],
};

test('metric truth boundary never manufactures CVSS from risk_score or contaminated _score_details', () => {
  assert.equal(explicitCvss(riskOnly), null);
  assert.equal(hasExplicitCvss(riskOnly), false);
  assert.equal(explicitRiskScore(riskOnly), 9.8);
  assert.deepEqual(metricTruth(riskOnly), {
    cvss: null,
    risk_score: 9.8,
    cvss_is_explicit: false,
    risk_is_cvss: false,
  });

  const withCvss = { ...riskOnly, cvss_score: 7.4 };
  assert.equal(explicitCvss(withCvss), 7.4);
  assert.equal(explicitRiskScore(withCvss), 9.8);

  const explicitZero = { ...riskOnly, cvss_score: 0 };
  assert.equal(explicitCvss(explicitZero), 0);
  assert.equal(hasExplicitCvss(explicitZero), true);
});

test('customer-facing P25-P33 surfaces do not relabel composite risk as CVSS', () => {
  const surfaces = [
    buildAnalystExplainabilityBlock(riskOnly),
    buildP27MultiAudienceBlock(riskOnly),
    buildP28BusinessImpactBlock(riskOnly),
    buildP29LifecycleBlock(riskOnly),
    buildP30SLABlock(riskOnly),
    buildP32DecisionBlock(riskOnly),
    buildP33CaseBlock(riskOnly),
    buildP33OperationalDashboardBlock(riskOnly, [riskOnly]),
  ];

  for (const html of surfaces) {
    assert.doesNotMatch(html, /CVSS\s*9\.8/i);
  }

  assert.match(surfaces[1], /not CVSS/i);
  assert.match(surfaces[4], /composite risk/i);
  assert.match(surfaces[6], /not CVSS/i);
});

test('P30 response timing never invents a customer SLA or arbitrary patch deadline', () => {
  const html = buildP30SLABlock(riskOnly);
  assert.match(html, /No authoritative external deadline recorded/i);
  assert.match(html, /customer.*documented.*SLA/i);
  assert.doesNotMatch(html, /Patch Window|Detection Window|Remediation Window/i);
  assert.doesNotMatch(html, /\b(?:15|30|45|60|90) days\b/i);

  const withDeadline = {
    ...riskOnly,
    kev_present: true,
    kev_due_date: '2026-12-01',
  };
  const deadlineHtml = buildP30SLABlock(withDeadline);
  assert.match(deadlineHtml, /2026-12-01/);
  assert.match(deadlineHtml, /CISA KEV|authoritative/i);
});

test('P28 business impact is qualitative and never fabricates monetary loss or breach status', () => {
  const html = buildP28BusinessImpactBlock({ ...riskOnly, kev_present: true });
  assert.match(html, /Not quantified from threat intelligence/i);
  assert.match(html, /does not prove outage, breach, data loss, financial loss/i);
  assert.doesNotMatch(html, /\$\s*(?:100K|500K|1M|10M)/i);
  assert.doesNotMatch(html, /estimated exposure/i);
});

test('P32 lifecycle is intelligence-readiness only and never asserts customer remediation completion', () => {
  const html = buildP32LifecycleBlock(riskOnly);
  assert.match(html, /Intelligence Readiness Lifecycle/i);
  assert.match(html, /not customer incident\/remediation progress/i);
  assert.doesNotMatch(html, /threat remediated|Recovery|Patch\/mitigation guidance published/i);
});

test('P33 case readiness does not manufacture customer incident lifecycle state', () => {
  const html = buildP33CaseBlock(riskOnly);
  assert.match(html, /INTELLIGENCE READINESS/i);
  assert.match(html, /does not represent customer incident triage, containment, recovery or closure/i);
  assert.doesNotMatch(html, /ACTIVE_INVESTIGATION|IN_PROGRESS/i);
  assert.doesNotMatch(html, /INVESTIGATION PHASES/i);
});

test('P33 operational dashboard does not manufacture patch completion or business risk', () => {
  const html = buildP33OperationalDashboardBlock(riskOnly, [riskOnly]);
  assert.match(html, /Feed Priority Index/i);
  assert.match(html, /not a customer business-risk/i);
  assert.match(html, /Customer patch status.*not inferred/i);
  assert.doesNotMatch(html, /Patch Completion Status|estimated compliant/i);
  assert.doesNotMatch(html, /Business Risk.*\/100/i);
});

test('P29 value analytics leaves customer outcome estimates unavailable without measurement telemetry', async () => {
  const env = {
    INTEL_R2: {
      async get(key) {
        assert.equal(key, 'api/v1/intel/latest.json');
        return {
          async json() {
            return { items: [riskOnly] };
          },
        };
      },
    },
  };
  const res = await handleP29CustomerValueAnalytics(
    new Request('https://intel.cyberdudebivash.com/api/v1/p29/customer-value'),
    env,
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.estimated_impact.analyst_hours_saved, null);
  assert.equal(body.estimated_impact.high_risk_items_mitigated, null);
  assert.equal(body.estimated_impact.financial_loss_avoided, null);
  assert.equal(body.estimated_impact.measurement_status, 'UNAVAILABLE');
  assert.ok(body.operational_capacity_signals.priority_review_items >= 1);
});

test('P32 customer summary keeps composite risk distinct from explicit CVSS', async () => {
  const env = {
    INTEL_R2: {
      async get() {
        return { async json() { return { items: [riskOnly] }; } };
      },
    },
  };
  const res = await handleP32Customer(
    new Request('https://intel.cyberdudebivash.com/api/v1/p32/customer'),
    env,
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.exposure_summary.high_risk_count, 1);
});

test('P33 mission and metrics never manufacture customer outcome or CVSS semantics', async () => {
  const env = {
    INTEL_R2: {
      async get() {
        return { async json() { return { items: [riskOnly] }; } };
      },
    },
  };

  const missionRes = await handleP33Mission(
    new Request('https://intel.cyberdudebivash.com/api/v1/p33/mission'),
    env,
  );
  assert.equal(missionRes.status, 200);
  const mission = await missionRes.json();
  for (const queue of Object.values(mission.queues)) {
    for (const item of queue) {
      assert.equal(item.cvss, null);
      assert.equal(item.risk_score, 9.8);
      assert.equal(item.risk_is_cvss, false);
    }
  }

  const metricsRes = await handleP33Metrics(
    new Request('https://intel.cyberdudebivash.com/api/v1/p33/metrics'),
    env,
  );
  assert.equal(metricsRes.status, 200);
  const metrics = await metricsRes.json();
  assert.equal(metrics.customer_success.measurement_status, 'UNAVAILABLE');
  assert.equal(metrics.customer_success.patch_completion_pct, null);
  assert.equal(metrics.customer_success.ioc_deployment_pct, null);
  assert.equal(metrics.customer_success.operational_maturity, null);
  assert.equal(metrics.marketplace_tiers.pro.usd_monthly, 49);
  assert.equal(metrics.marketplace_tiers.enterprise.usd_monthly, 499);
  assert.equal(metrics.marketplace_tiers.mssp.usd_monthly, 999);
  assert.equal(metrics.marketplace_tiers.pricing_source, '/api/pricing');
  assert.ok(metrics.intelligence_output_coverage);
  assert.equal(typeof metrics.intelligence_output_coverage.mitre_mapping_pct, 'number');

  const obsRes = await handleP33Observability(
    new Request('https://intel.cyberdudebivash.com/api/v1/p33/observability'),
    env,
  );
  assert.equal(obsRes.status, 200);
  const obs = await obsRes.json();
  assert.equal(obs.pipeline.health_pct, null);
  assert.equal(obs.pipeline.measurement_status, 'UNAVAILABLE');
});

test('source guard forbids risk-to-CVSS fallback across hardened customer P25-P33 layers', () => {
  const files = [
    '../p25-handlers.js',
    '../p27-handlers.js',
    '../p28-handlers.js',
    '../p29-handlers.js',
    '../p30-handlers.js',
    '../p31-handlers.js',
    '../p32-handlers.js',
    '../p33-handlers.js',
  ];
  const forbidden = [
    /risk_score\s*\|\|\s*item\.cvss_score/,
    /item\.cvss_score\s*\|\|\s*item\.risk_score/,
    /sd\.cvss\s*\|\|\s*item\.cvss_score\s*\|\|\s*item\.risk_score/,
    /risk_score\s*\|\|\s*i\.cvss_score/,
    /i\.risk_score\s*\|\|\s*i\.cvss_score/,
  ];
  for (const rel of files) {
    const source = fs.readFileSync(new URL(rel, import.meta.url), 'utf8');
    for (const pattern of forbidden) {
      assert.doesNotMatch(source, pattern, `${rel} reintroduced risk/CVSS conflation`);
    }
  }
});

test('enterprise operations UI fails closed, keeps credentials memory-only, and consumes current P32 contracts', () => {
  const source = fs.readFileSync(
    new URL('../../../../enterprise-operations.html', import.meta.url),
    'utf8',
  );
  assert.doesNotMatch(source, /sessionStorage\.(?:setItem|getItem)\(['"]apex_token/);
  assert.doesNotMatch(source, /localStorage\.(?:setItem|getItem)\([^\n]*token/i);
  assert.match(source, /Authentication failed\. Access remains locked\./);
  assert.match(source, /\/api\/v1\/p32\/observability/);
  assert.match(source, /exposure_summary/);
  assert.match(source, /top_required_actions/);
  assert.match(source, /stage_distribution/);
  assert.doesNotMatch(source, /Patch within 30 days|CISA mandatory patches|Operational Lifecycle \(9-Stage\)/i);
});

test('enterprise trust dashboard fails closed and never persists API keys in Web Storage', () => {
  const source = fs.readFileSync(
    new URL('../../../../enterprise-trust-dashboard.html', import.meta.url),
    'utf8',
  );
  assert.doesNotMatch(source, /sessionStorage\.setItem\(['"]apex_api_key/);
  assert.doesNotMatch(source, /localStorage\.setItem\(['"]apex_api_key/);
  assert.doesNotMatch(source, /sessionStorage\.getItem\(['"]apex_api_key/);
  assert.match(source, /Unable to validate dashboard access\. Access remains locked\./);
  assert.match(source, /\/api\/v1\/p25\/observability/);
  assert.doesNotMatch(source, /sd\.cvss\s*\|\|\s*item\.cvss_score\s*\|\|\s*item\.risk_score/);
});
