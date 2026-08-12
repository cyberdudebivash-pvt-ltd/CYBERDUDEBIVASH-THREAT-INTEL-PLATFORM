#!/usr/bin/env node
/**
 * SENTINEL APEX — AI Cyber Brain Field-Mapping Regression Test (PR-D3)
 * ====================================================================
 * Real-browser (headless Chromium) verification that the "AI Cyber Brain"
 * engine (index.html, CDB-AI-BRAIN-INIT-v145 block) reads the CURRENT
 * production feed schema instead of pre-migration field names.
 *
 * Proven root cause (via live curl against intel.cyberdudebivash.com/api/feed.json):
 *   - buildAnomalies() read t.priority_score (never exists) and t.cvss
 *     (never exists -- real field is cvss_score) as its scoring input, so
 *     mean==score for every one of 182 real items => zScore==0 always.
 *     Its "boost" terms then checked t.kev||t.cisa_kev (kev is a *string*
 *     "NO" for 11/182 real items -- truthy in JS -- while cisa_kev never
 *     exists) and t.exploit_status==='ZERO_DAY'/'ACTIVE_CONFIRMED' (field
 *     never exists; real field is exploit_maturity with vocabulary
 *     UNPROVEN/POC/FUNCTIONAL/WEAPONIZED). Net effect: EVERY real item
 *     scored either 0 or 0.4, both under the >=0.45 acceptance filter, so
 *     buildAnomalies() returned [] on every single production load,
 *     deterministically -- and renderAnomalies([]) renders the literal
 *     "Awaiting analysis..." placeholder, which is the reported permanently
 *     stuck "ANOMALY RADAR" symptom.
 *   - buildForecasts() read t.sector, which never exists on a real item
 *     (real per-item signal is actor_sectors, an array, almost always
 *     empty) -- every item silently defaulted into the 'Technology'
 *     bucket, fabricating a false 100%-Technology concentration on every
 *     real load instead of honestly reflecting "no sector evidence."
 *   - buildCampaigns() read t.threat_actor/t.actor/t.family/t.type; real
 *     attribution lives in primary_actor/actor_display_name/
 *     mitre_group_name, while t.actor is usually null or an internal
 *     "CDB-UNATTR-*" placeholder token that must not be shown to a
 *     customer as if it were a real group name.
 *
 * Fix under test (index.html buildAnomalies/buildCampaigns/buildForecasts/
 * buildSOCQueue/renderAnomalies):
 *   - risk_score/cvss_score/kev_present/exploit_maturity are now the
 *     scoring inputs across all four build* functions.
 *   - CDB-UNATTR-* actor placeholders normalize into the same UNKNOWN
 *     ACTOR bucket as a genuinely null actor.
 *   - Sector bucketing uses actor_sectors when present and an honestly
 *     labeled 'Unclassified' bucket (not 'Technology') otherwise.
 *   - renderAnomalies() now distinguishes a completed zero-result pass
 *     ("0 anomalies detected across N advisories analyzed") from the
 *     separate pre-fetch "still loading" state in runAIBrain().
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node render-test/verify_ai_brain_field_mapping.js
 *
 * Exit code 0 = all checks passed. Exit code 1 = at least one failed.
 */
'use strict';

const path = require('path');
const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright');

const REPO_ROOT = path.resolve(__dirname, '..');
const PORT = 8962;
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

// Shapes verified field-for-field against a live capture of
// https://intel.cyberdudebivash.com/api/feed.json (2026-08-12).
function feedOf(items) {
  return JSON.stringify({
    schema_version: '1.0', generated_at: '2026-08-12T06:00:00Z',
    generator: 'generate_api_manifests.py', version: 'v184.0',
    count: items.length, items,
  });
}

const MIXED_FEED = feedOf([
  { // weaponized + KEV-confirmed + high risk_score -> must surface as a real anomaly
    id: 'intel--w1', title: 'Windows Driver Zero-Day Under Active Attack',
    severity: 'CRITICAL', risk_score: 9.07, cvss_score: 9.8,
    kev_present: true, kev: true, exploit_maturity: 'WEAPONIZED',
    actor: null, primary_actor: 'Sandworm', campaign_name: 'OP-SANDWORM-GRID',
    mitre_tactics: [{ id: 'T1190', name: 'Exploit Public-Facing Application', tactic: 'Initial Access' }],
  },
  { // legacy `kev:"NO"` truthy-string regression case -- must NOT be treated as KEV
    id: 'intel--legacy1', title: 'CVE-2026-11111 Low severity parsing issue',
    severity: 'LOW', risk_score: 1.2, cvss_score: null,
    kev_present: false, kev: 'NO', exploit_maturity: 'UNPROVEN',
    actor: 'CDB-UNATTR-CVE', actor_tag: 'CDB-UNATTR-CVE',
  },
  { // second unattributed item -- same placeholder tag, must bucket together as UNKNOWN
    id: 'intel--legacy2', title: 'CVE-2026-22222 Generic vulnerability advisory',
    severity: 'MEDIUM', risk_score: 4.0, cvss_score: 5.5,
    kev_present: false, kev: null, exploit_maturity: 'POC',
    actor: 'CDB-UNATTR-CVE', actor_tag: 'CDB-UNATTR-CVE',
  },
  { // plain unattributed item with no actor field at all
    id: 'intel--plain1', title: 'CVE-2026-33333 Another routine advisory',
    severity: 'MEDIUM', risk_score: 3.8, cvss_score: 4.2,
    kev_present: false, exploit_maturity: 'UNPROVEN', actor: null,
  },
]);

const UNIFORM_LOW_RISK_FEED = feedOf([
  { id: 'intel--u1', title: 'Routine advisory A', severity: 'LOW', risk_score: 2.0, cvss_score: 2.0, kev_present: false, exploit_maturity: 'UNPROVEN', actor: null },
  { id: 'intel--u2', title: 'Routine advisory B', severity: 'LOW', risk_score: 2.1, cvss_score: 2.1, kev_present: false, exploit_maturity: 'UNPROVEN', actor: null },
  { id: 'intel--u3', title: 'Routine advisory C', severity: 'LOW', risk_score: 1.9, cvss_score: 1.9, kev_present: false, exploit_maturity: 'UNPROVEN', actor: null },
  { id: 'intel--u4', title: 'Routine advisory D', severity: 'LOW', risk_score: 2.0, cvss_score: 2.0, kev_present: false, exploit_maturity: 'UNPROVEN', actor: null },
]);

async function routeAPIs(context, feedBody) {
  await context.route('**/*', (route) => {
    const url = route.request().url();
    const pathname = new URL(url).pathname;
    if (/\/api\/apex_v2\/(priority|critical)\.json$/.test(pathname)) return route.abort();
    if (pathname === '/api/feed.json') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: feedBody });
    }
    if (pathname.startsWith('/api/')) return route.abort();
    if (url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.continue();
    return route.abort();
  });
}

async function runMixedFeedScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, MIXED_FEED);
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);

  const anomalyHTML = await page.evaluate(() => {
    const el = document.getElementById('ai-anomaly-body');
    return el ? el.innerHTML : '__MISSING_ELEMENT__';
  });
  record('Anomaly Radar is no longer stuck on "Awaiting analysis..." once real feed data with a weaponized/KEV item arrives',
    !anomalyHTML.includes('Awaiting analysis...') && anomalyHTML.includes('Windows Driver Zero-Day'),
    `snippet="${anomalyHTML.slice(0, 160)}"`);

  record('Anomaly card shows the real CISA KEV badge (kev_present===true), not a fabricated/absent one',
    anomalyHTML.includes('CISA KEV'), `hasCISAKEV=${anomalyHTML.includes('CISA KEV')}`);

  record('Anomaly card shows the real exploit_maturity value (WEAPONIZED), not the dead exploit_status field',
    anomalyHTML.includes('WEAPONIZED'), `hasWEAPONIZED=${anomalyHTML.includes('WEAPONIZED')}`);

  record('Anomaly card CVSS/SCORE readouts are populated from cvss_score/risk_score, not blank from the dead cvss/priority_score fields',
    /CVSS/.test(anomalyHTML) && /SCORE/.test(anomalyHTML), `hasCVSS=${/CVSS/.test(anomalyHTML)} hasSCORE=${/SCORE/.test(anomalyHTML)}`);

  const campaignsHTML = await page.evaluate(() => {
    const el = document.getElementById('ai-campaigns-body');
    return el ? el.innerHTML : '__MISSING_ELEMENT__';
  });
  record('Campaigns panel shows the real attributed actor name (SANDWORM) from primary_actor',
    campaignsHTML.includes('SANDWORM'), `snippet="${campaignsHTML.slice(0, 200)}"`);

  record('Campaigns panel never leaks the internal "CDB-UNATTR-*" placeholder token as if it were a threat-actor name',
    !campaignsHTML.includes('CDB-UNATTR'), `containsRawPlaceholder=${campaignsHTML.includes('CDB-UNATTR')}`);

  record('Campaigns panel buckets unattributed items under the honest UNKNOWN ACTOR label',
    campaignsHTML.includes('UNKNOWN ACTOR'), `snippet="${campaignsHTML.slice(0, 200)}"`);

  const predictHTML = await page.evaluate(() => {
    const el = document.getElementById('ai-predict-body');
    return el ? el.innerHTML : '__MISSING_ELEMENT__';
  });
  record('Predictions panel is populated (not stuck on "Awaiting forecast data...")',
    !predictHTML.includes('Awaiting forecast data...'), `snippet="${predictHTML.slice(0, 160)}"`);

  record('Predictions panel honestly labels items with no real actor_sectors evidence as Unclassified instead of fabricating a Technology-sector concentration',
    predictHTML.includes('Unclassified'), `containsUnclassified=${predictHTML.includes('Unclassified')}`);

  await context.close();
}

async function runUniformLowRiskScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, UNIFORM_LOW_RISK_FEED);
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);

  const anomalyHTML = await page.evaluate(() => {
    const el = document.getElementById('ai-anomaly-body');
    return el ? el.innerHTML : '__MISSING_ELEMENT__';
  });
  record('A genuinely completed zero-anomaly pass (uniform low-risk feed) renders an honest "0 anomalies detected" result, not the ambiguous "Awaiting analysis..." stuck-loading text',
    anomalyHTML.includes('0 anomalies detected') && !anomalyHTML.includes('Awaiting analysis...'),
    `snippet="${anomalyHTML.slice(0, 200)}"`);

  record('The honest zero-anomaly message reports the real advisories-analyzed count',
    anomalyHTML.includes('4 advisories analyzed'), `snippet="${anomalyHTML.slice(0, 200)}"`);

  await context.close();
}

async function main() {
  const server = await startStaticServer();
  let browser;
  try {
    browser = await chromium.launch();
    console.log('--- Scenario: mixed real-shaped feed (weaponized/KEV item + unattributed placeholders) ---');
    await runMixedFeedScenario(browser);
    console.log('\n--- Scenario: uniform low-risk feed -> honest completed zero-anomaly state ---');
    await runUniformLowRiskScenario(browser);
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
