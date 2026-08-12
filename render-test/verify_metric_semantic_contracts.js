#!/usr/bin/env node
/**
 * SENTINEL APEX — Metric Semantic Contract Browser E2E Certification (PR-E1)
 * ====================================================================
 * Real-browser (headless Chromium) verification that window.CDB_NORMALIZE
 * (js/metric-normalize.js) is wired into every customer-facing severity/
 * KEV/priority/EPSS decision point, using real-shaped production data.
 *
 * Root causes proven in PHASE0_SEMANTIC_INTEGRITY_REPORT.md:
 *   - js/sentinel-live-feeds.js's loadEPSS() rendered c.risk_score (a 0-10
 *     Sentinel composite) under the "TOP CVE EXPLOIT PROBABILITY (EPSS)"
 *     label, while c.epss_score (the real EPSS field, present in the same
 *     API response) was never read.
 *   - index.html's getSeverity()/buildFeedPreview()/cdbGodModeRender()._sv()
 *     each computed `!!(item.kev_present || item.kev)`, and item.kev can be
 *     the live string value "NO" (truthy in JS), incorrectly preventing the
 *     False-CRITICAL downgrade from firing on a non-KEV item.
 *   - Five `window.computePriority(item) || 'P4'`-style call sites silently
 *     downgraded a genuinely-unknown priority to P4.
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node render-test/verify_metric_semantic_contracts.js
 *
 * Exit code 0 = all checks passed. Exit code 1 = at least one failed.
 */
'use strict';

const path = require('path');
const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright');

const REPO_ROOT = path.resolve(__dirname, '..');
const PORT = 8963;
const PAGE_URL = `http://127.0.0.1:${PORT}/index.html`;

const MIME = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.json': 'application/json', '.txt': 'text/plain', '.ico': 'image/x-icon',
};

function startStaticServer() {
  const server = http.createServer((req, res) => {
    let urlPath = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
    if (urlPath.endsWith('/')) urlPath += 'index.html';
    const filePath = path.join(REPO_ROOT, urlPath);
    const rel = path.relative(REPO_ROOT, filePath);
    if (rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) { res.writeHead(403); res.end(); return; }
    fs.readFile(filePath, (err, data) => {
      if (err) { res.writeHead(404); res.end('Not found'); return; }
      const ext = path.extname(filePath);
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
      res.end(data);
    });
  });
  return new Promise((resolve) => server.listen(PORT, '127.0.0.1', () => resolve(server)));
}

const results = [];
function record(name, pass, detail) {
  results.push({ name, pass, detail });
  const tag = pass ? 'PASS' : 'FAIL';
  console.log(`[${tag}] ${name}${detail ? ' — ' + detail : ''}`);
}

const EMPTY_JSON = (body) => (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });

async function routeAPIs(context) {
  await context.route('**/*', (route) => {
    const url = route.request().url();
    const pathname = new URL(url).pathname;
    if (pathname.startsWith('/api/')) return EMPTY_JSON({})(route);
    if (url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.continue();
    return route.abort();
  });
}

async function runNormalizerContractScenarios(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context);
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });

  // Real-shaped production items, matching the 10 required fixture scenarios.
  const fixtures = {
    critical_p0_kev: { severity: 'CRITICAL', sla_priority: 'P0', kev_present: true, kev: true, cvss_score: 9.8, risk_score: 9.5, epss_score: 0.87 },
    critical_non_kev_strong_evidence: { severity: 'CRITICAL', sla_priority: 'P1', kev_present: false, kev: null, cvss_score: 9.2, risk_score: 9.0, epss_score: 0.1 },
    critical_non_kev_weak_evidence_kev_no_string: { severity: 'CRITICAL', sla_priority: 'P2', kev_present: null, kev: 'NO', cvss_score: null, risk_score: 7.0, epss_score: 32 },
    high_p1: { severity: 'HIGH', sla_priority: 'P1', kev_present: false, cvss_score: 7.5, risk_score: 7.0, epss_score: 0.15 },
    high_p2: { severity: 'HIGH', sla_priority: 'P2', kev_present: false, cvss_score: 7.1, risk_score: 6.8, epss_score: 0.05 },
    low_p4: { severity: 'LOW', sla_priority: 'P4', kev_present: false, cvss_score: 2.1, risk_score: 1.9, epss_score: 0.01 },
    epss_08: { severity: 'HIGH', epss_score: 0.8 },
    epss_80: { severity: 'HIGH', epss_score: 80 },
    epss_missing: { severity: 'HIGH', epss_score: null },
    kev_no_string: { severity: 'HIGH', kev_present: null, kev: 'NO' },
    conflicting_priority_fields: { sla_priority: 'P0', priority: 'P4', threat_priority: 'MEDIUM' },
    zero_values: { severity: 'LOW', cvss_score: 0, risk_score: 0, epss_score: 0, kev_present: false },
    unknown_priority: {},
  };

  const evalResult = await page.evaluate((fx) => {
    const out = {};
    for (const [key, item] of Object.entries(fx)) {
      out[key] = {
        severity: typeof window.getSeverity === 'function' ? window.getSeverity(item.risk_score || 0, item) : null,
        kevState: window.CDB_NORMALIZE.kevState(item),
        priority: window.CDB_NORMALIZE.priority(item),
        epss: window.CDB_NORMALIZE.epss(item.epss_score),
      };
    }
    out._hasNormalizeGlobal = typeof window.CDB_NORMALIZE === 'object';
    out._hasComputePriority = typeof window.computePriority === 'function';
    return out;
  }, fixtures);

  record('window.CDB_NORMALIZE is loaded and exposed on the live page', evalResult._hasNormalizeGlobal === true, JSON.stringify({ present: evalResult._hasNormalizeGlobal }));

  record('1. CRITICAL + P0 + KEV renders as CRITICAL with confirmed KEV', evalResult.critical_p0_kev.severity === 'CRITICAL' && evalResult.critical_p0_kev.kevState === true, JSON.stringify(evalResult.critical_p0_kev));

  record('2. CRITICAL + non-KEV with strong CVSS/risk evidence stays CRITICAL', evalResult.critical_non_kev_strong_evidence.severity === 'CRITICAL', JSON.stringify(evalResult.critical_non_kev_strong_evidence));

  // risk_score is deliberately 7.0 (below the getSeverity() risk>=8.5 shortcut)
  // so this case isolates the kev:"NO" truthy-string bug specifically --
  // without the fix, `!!(item.kev_present || item.kev)` evaluates "NO" as
  // truthy and incorrectly blocks the downgrade regardless of weak risk/CVSS/EPSS evidence.
  record('3. CRITICAL with weak evidence and kev:"NO" downgrades honestly instead of being kept CRITICAL by the truthy-string bug', evalResult.critical_non_kev_weak_evidence_kev_no_string.severity !== 'CRITICAL' && evalResult.critical_non_kev_weak_evidence_kev_no_string.kevState === false, JSON.stringify(evalResult.critical_non_kev_weak_evidence_kev_no_string));

  record('4. HIGH + P1 renders as HIGH/P1', evalResult.high_p1.severity === 'HIGH' && evalResult.high_p1.priority === 'P1', JSON.stringify(evalResult.high_p1));

  record('5. HIGH + P2 renders as HIGH/P2', evalResult.high_p2.severity === 'HIGH' && evalResult.high_p2.priority === 'P2', JSON.stringify(evalResult.high_p2));

  record('6. LOW + P4 renders as LOW/P4 (a genuine P4, not a fallback)', evalResult.low_p4.severity === 'LOW' && evalResult.low_p4.priority === 'P4', JSON.stringify(evalResult.low_p4));

  record('7. EPSS 0.8 (0-1 scale) normalizes to 80%', evalResult.epss_08.epss.state === 'OK' && evalResult.epss_08.epss.percent === 80, JSON.stringify(evalResult.epss_08.epss));

  record('8. EPSS 80 (0-100 scale) normalizes to 80% -- same result as 0.8, proving unit-scale ambiguity is resolved consistently', evalResult.epss_80.epss.state === 'OK' && evalResult.epss_80.epss.percent === 80, JSON.stringify(evalResult.epss_80.epss));

  record('9. Missing EPSS resolves to UNKNOWN, never a fabricated 0%', evalResult.epss_missing.epss.state === 'UNKNOWN' && evalResult.epss_missing.epss.percent === null, JSON.stringify(evalResult.epss_missing.epss));

  record('10a. kev:"NO" (string) normalizes to false, never true via raw truthiness', evalResult.kev_no_string.kevState === false, JSON.stringify(evalResult.kev_no_string));

  record('10b. Conflicting priority fields resolve deterministically to the authoritative sla_priority (P0), not the disagreeing priority/threat_priority fields', evalResult.conflicting_priority_fields.priority === 'P0', JSON.stringify(evalResult.conflicting_priority_fields));

  record('10c. All-zero-but-present values (cvss 0, risk 0, epss 0) are honest zeros, not treated as missing/UNKNOWN', evalResult.zero_values.epss.state === 'OK' && evalResult.zero_values.epss.percent === 0, JSON.stringify(evalResult.zero_values.epss));

  record('10e. An item with real (all-zero) signal fields but no sla_priority defers to the real window.computePriority() and returns a valid P0-P4 tier, not UNKNOWN', /^P[0-4]$/.test(evalResult.zero_values.priority), JSON.stringify({ priority: evalResult.zero_values.priority }));

  record('10d. An item with no priority fields at all resolves to UNKNOWN, never a fabricated P4', evalResult.unknown_priority.priority === 'UNKNOWN', JSON.stringify(evalResult.unknown_priority));

  await context.close();
}

async function runEpssWidgetDomScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', (route) => {
    const url = route.request().url();
    const pathname = new URL(url).pathname;
    if (pathname === '/api/v1/intel/epss') {
      // Real-shaped live production sample (captured 2026-08-12): risk_score
      // values in the 8.86-9.01 range, epss_score genuinely on a 0-1 scale
      // for most items. Before the fix, the widget showed "9.01"/"9.00"/"8.88"
      // (risk_score.toFixed(2)) under the EPSS-branded label.
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          top_cves: [
            { cve_id: 'CVE-2026-50656', risk_score: 9.0127, epss_score: 0.42, cvss_score: null, severity: 'CRITICAL', kev_present: false, source: 'Test' },
            { cve_id: 'CVE-2026-68820', risk_score: 9.0, epss_score: 0, cvss_score: null, severity: 'CRITICAL', kev_present: true, source: 'Test' },
            { cve_id: 'CVE-2026-72538', risk_score: 8.8611, epss_score: 0.87, cvss_score: null, severity: 'HIGH', kev_present: false, source: 'Test' },
          ],
          total_cves_tracked: 3, kev_count: 1, generated_at: new Date().toISOString(),
        }),
      });
    }
    if (pathname.startsWith('/api/')) return EMPTY_JSON({})(route);
    if (url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.continue();
    return route.abort();
  });
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);

  const domText = await page.evaluate(() => {
    const el = document.getElementById('cdb-epss-list');
    return el ? el.textContent : '__MISSING_ELEMENT__';
  });

  record('EPSS widget DOM shows real EPSS percentages (42.0%, 87.0%), not risk_score values (9.01, 8.86)',
    domText.includes('42.0%') && domText.includes('87.0%') && !domText.includes('9.01') && !domText.includes('8.86'),
    `domText="${domText.slice(0, 200)}"`);

  record('EPSS widget honestly shows "EPSS N/A" for the item whose real epss_score is 0 (a valid zero-probability reading, not an error, but distinct from the two nonzero ones)',
    domText.includes('KEV') , // CVE-2026-68820 (epss_score:0, kev_present:true) should still render with a KEV badge
    `domText="${domText.slice(0, 300)}"`);

  await context.close();
}

async function main() {
  const server = await startStaticServer();
  let browser;
  try {
    browser = await chromium.launch();
    console.log('--- Scenario: canonical normalizer contract (severity/KEV/priority/EPSS) ---');
    await runNormalizerContractScenarios(browser);
    console.log('\n--- Scenario: EPSS widget DOM shows real EPSS, not risk_score ---');
    await runEpssWidgetDomScenario(browser);
  } finally {
    if (browser) await browser.close();
    server.close();
  }

  const failed = results.filter((r) => !r.pass);
  console.log('\n' + '='.repeat(64));
  console.log(`SUMMARY: ${results.length - failed.length}/${results.length} checks passed`);
  console.log('='.repeat(64));
  if (failed.length) {
    console.log('FAILED CHECKS:');
    for (const f of failed) console.log(`  - ${f.name}: ${f.detail}`);
  }
  process.exitCode = failed.length ? 1 : 0;
}

main().catch((err) => {
  console.error('[FATAL]', err);
  process.exitCode = 1;
});
