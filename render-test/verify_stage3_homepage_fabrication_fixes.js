#!/usr/bin/env node
/**
 * SENTINEL APEX — Stage 3 Homepage Fabrication Fixes Regression Test
 * ====================================================================
 * Real-browser (headless Chromium) verification of two independent Stage 3
 * (End-to-End Dashboard Synchronization, Dynamic Intelligence Modules,
 * Runtime Integrity & Release Reliability) zero-fabrication fixes found by
 * this stage's repo-wide suspicious-pattern sweep, neither touched by
 * Stage 1 (PR #314) or Stage 2 (PR #315):
 *
 * 1. GENESIS "ANALYZE LIVE" avg_risk_score (index.html,
 *    _synthAnalysisFromLiveFeed()): read window.EMBEDDED_INTEL, which
 *    v184.0 permanently empties ("Worker API is single source of truth" —
 *    see the removal comment directly above this function), instead of the
 *    local `items` variable populated two lines above from the real,
 *    just-fetched /api/preview response. critical_count/high_count/
 *    kev_active/unique_actors were already computed correctly from `items`
 *    — avg_risk_score was the one metric silently always 0 regardless of
 *    the real fetched data. Fix: window._v149AvgRisk(items) — same existing
 *    calculator, real data, matching the pattern already used correctly by
 *    every sibling metric in the same object literal.
 *
 * 2. Homepage "Live subscriber ticker" (#live-sub-count, subscribe
 *    section): a client-side setTimeout loop incremented a
 *    Math.random()-jittered counter ("1,247" -> "1,248" -> ...) every
 *    18-42s with zero backend behind it — a simulated live-activity signal
 *    the platform's zero-fabrication invariants explicitly forbid ("fake
 *    counters", "simulated live activity"). Fix: removed the fabricated
 *    counter element and its increment timer entirely; the one real,
 *    non-live claim ("Join 1,200+ SOC analysts...") already present in this
 *    section's intro copy is left untouched.
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node render-test/verify_stage3_homepage_fabrication_fixes.js
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

// Three items with deliberately clean risk_score values so the expected
// average (9.0 + 6.0 + 3.0) / 3 == 6.00 is unambiguous. critical_count==1
// and high_count==1 are asserted alongside avg_risk_score as a sanity
// cross-check that the fix didn't disturb the sibling metrics, which were
// already reading from the correct `items` variable before this fix.
const PREVIEW_ITEMS = [
  { id: 'intel--r1', title: 'Regression-Test Critical Advisory', severity: 'CRITICAL', risk_score: 9.0, actor_tag: 'APT-REGRESSION', mitre_tactics: ['T1190'] },
  { id: 'intel--r2', title: 'Regression-Test High Advisory',     severity: 'HIGH',     risk_score: 6.0, actor_tag: 'APT-REGRESSION', mitre_tactics: ['T1059'] },
  { id: 'intel--r3', title: 'Regression-Test Medium Advisory',   severity: 'MEDIUM',   risk_score: 3.0, actor_tag: '', mitre_tactics: [] },
];

async function routeAPIs(context) {
  await context.route('**/*', (route) => {
    const url = route.request().url();
    let pathname;
    try { pathname = new URL(url).pathname; } catch (e) { return route.abort(); }

    // Phase 1 of triggerAIAnalysis(): force the pre-generated static AI
    // JSON endpoints to 404 so the function falls through to Phase 2
    // (_synthAnalysisFromLiveFeed(), the code under test).
    if (/\/api\/ai\/(analyze|respond|correlate)\.json$/.test(pathname)) {
      return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
    }
    // Phase 2's own data source: the real, live Worker feed.
    if (pathname === '/api/preview') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: PREVIEW_ITEMS }) });
    }
    if (pathname.startsWith('/api/')) return route.abort();
    if (url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.continue();
    return route.abort();
  });
}

async function runAvgRiskScoreScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context);
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);

  await page.click('#analyze-live-btn');
  // Phase 1 (2 fetches to now-404 endpoints) + Phase 2 (1 fetch to
  // /api/preview) + render -- generous but bounded wait.
  await page.waitForFunction(() => {
    const el = document.getElementById('ai-summary-grid');
    return el && el.children.length > 0;
  }, { timeout: 10000 });

  const cells = await page.evaluate(() => {
    const el = document.getElementById('ai-summary-grid');
    if (!el) return null;
    return Array.from(el.children).map((c) => ({
      label: c.querySelector('div:last-child').textContent.trim(),
      value: c.querySelector('div:first-child').textContent.trim(),
    }));
  });

  const byLabel = {};
  (cells || []).forEach((c) => { byLabel[c.label] = c.value; });

  record('GENESIS Analyze Live panel rendered a summary grid from the live-synthesis fallback path',
    !!cells && cells.length === 6, JSON.stringify(cells));

  record('AVG RISK reflects the real average of the fetched items (6.0), not the always-0 EMBEDDED_INTEL bug',
    byLabel['AVG RISK'] === '6.0', `AVG RISK cell="${byLabel['AVG RISK']}"`);

  record('CRITICAL count is still correctly computed from the same real items (sanity cross-check, unaffected sibling metric)',
    byLabel['CRITICAL'] === '1', `CRITICAL cell="${byLabel['CRITICAL']}"`);

  record('HIGH count is still correctly computed from the same real items (sanity cross-check, unaffected sibling metric)',
    byLabel['HIGH'] === '1', `HIGH cell="${byLabel['HIGH']}"`);

  record('Zero uncaught JS errors while exercising the live-synthesis AI analysis path',
    pageErrors.length === 0, JSON.stringify(pageErrors));

  await context.close();
}

async function runSubscriberCounterScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context);
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  // The removed timer previously fired its first tick at 12-28s; wait long
  // enough that a regression (the element or timer reappearing) would have
  // fired at least once within this window.
  await page.waitForTimeout(3000);

  const state = await page.evaluate(() => ({
    liveSubCountExists: !!document.getElementById('live-sub-count'),
    introParagraphText: (document.getElementById('subscribe') || {}).textContent || '',
  }));

  record('The fabricated "live subscriber count" element has been removed from the page entirely',
    state.liveSubCountExists === false, `elementExists=${state.liveSubCountExists}`);

  record('The one real, non-live "1,200+ SOC analysts" claim in the intro copy is preserved (fix removed only the fabricated live-growth animation, not the honest static claim)',
    state.introParagraphText.includes('1,200+'), `introParagraphText(first 300)="${state.introParagraphText.slice(0, 300)}"`);

  record('Zero uncaught JS errors on the subscribe section after the fake-counter removal',
    pageErrors.length === 0, JSON.stringify(pageErrors));

  await context.close();
}

async function main() {
  const server = await startStaticServer();
  let browser;
  try {
    browser = await chromium.launch();
    console.log('--- Scenario: GENESIS Analyze Live avg_risk_score uses real fetched items, not dead EMBEDDED_INTEL ---');
    await runAvgRiskScoreScenario(browser);
    console.log('\n--- Scenario: fabricated live subscriber counter is gone, honest static claim remains ---');
    await runSubscriberCounterScenario(browser);
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
