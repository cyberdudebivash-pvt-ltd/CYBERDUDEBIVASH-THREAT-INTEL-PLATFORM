#!/usr/bin/env node
/**
 * SENTINEL APEX — REPORTS Tab Badge Regression Test (v187.0 P0 fix)
 * ====================================================================
 * Real-browser (headless Chromium) verification of the REPORTS tab badge
 * (#cdb-tab-reports-count), which used to render a bare "0" placeholder
 * in the initial HTML and then silently stay at "0" forever whenever the
 * count-loading fetch failed (the fetch's final .catch() was an empty
 * `function() {}` -- no logging, no retry, no distinction between "count
 * is genuinely zero" and "count could not be determined").
 *
 * Root cause covered: the badge is populated by a 500ms-delayed preload
 * fetch of /api/reports/index.json (_preloadReportsBadge), independent of
 * whether the user ever clicks the REPORTS tab. This is the code path a
 * customer actually sees on page load -- the tab-click path (_loadReports)
 * shares the same _setReportsBadgeCount()/_setReportsBadgeUnavailable()
 * helpers and is not separately exercised here.
 *
 * Fix under test:
 *   - Initial HTML placeholder is now an em dash ("&#8212;"), never "0".
 *   - _setReportsBadgeCount(value): numeric values (including a genuine 0)
 *     render via .toLocaleString(); anything else routes to
 *     _setReportsBadgeUnavailable() instead of silently rendering "0".
 *   - _setReportsBadgeUnavailable(reason): sets the badge to "—" and
 *     console.warns with the reason -- no more silent catch(){}.
 *   - _preloadReportsBadge(attempt): bounded retry (3 attempts, 1.5s apart)
 *     on HTTP/network failure before giving up and marking unavailable.
 *
 * Each scenario below launches a FRESH browser context (so the page's
 * IIFE-scoped state resets) and mocks /api/reports/index.json's response
 * per-call via Playwright route interception, then asserts the exact
 * textContent of #cdb-tab-reports-count and the console.warn trail.
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node render-test/verify_reports_badge.js
 *
 * Exit code 0 = all checks passed. Exit code 1 = at least one failed.
 */
'use strict';

const path = require('path');
const { startStaticServer } = require('./lib/static-server');
const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright');

const REPO_ROOT = path.resolve(__dirname, '..');
const PORT = 8945; // distinct from verify_intel_card_report_routing.js's 8944
const PAGE_URL = `http://127.0.0.1:${PORT}/index.html`;

const MIME = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.json': 'application/json', '.txt': 'text/plain', '.ico': 'image/x-icon',
};

const results = [];
function record(name, pass, detail) {
  results.push({ name, pass, detail });
  const tag = pass ? 'PASS' : 'FAIL';
  console.log(`[${tag}] ${name}${detail ? ' — ' + detail : ''}`);
}

const EM_DASH = '—';

// Each scenario supplies a sequence of mock responses for successive calls
// to /api/reports/index.json (the last entry repeats for any further
// calls), a wait time long enough for the badge's async retry chain to
// settle, and an assertion function receiving { badgeText, callCount,
// consoleText }.
const SCENARIOS = [
  {
    name: 'Successful response with a non-zero production-like count renders the count',
    mockResponses: [{ status: 200, body: { total_reports: 483 } }],
    waitMs: 1200,
    assert: ({ badgeText }) => {
      record('Badge shows the fetched non-zero count', badgeText === '483', `badgeText="${badgeText}"`);
    },
  },
  {
    name: 'Transient failure followed by a successful retry updates the badge (not stuck)',
    mockResponses: [{ status: 500, body: {} }, { status: 200, body: { total_reports: 483 } }],
    waitMs: 2600,
    assert: ({ badgeText, callCount, consoleText }) => {
      record('Badge recovers to the real count after a transient failure + retry', badgeText === '483', `badgeText="${badgeText}"`);
      // >=2 rather than an exact count: the static <a href="/api/reports/index.json">
      // links elsewhere on the page can trigger the browser's own speculative
      // link prefetching independent of this retry logic, so the mocked
      // endpoint may see more hits than the badge code alone issues. What
      // matters here is that the retry path actually engaged at least once.
      record('At least one retry engaged after the initial failure', callCount >= 2, `callCount=${callCount}`);
      record('Retry attempt was logged via console.warn (observable, not silent)', /Badge preload attempt 1\/3 failed, retrying/.test(consoleText), consoleText);
    },
  },
  {
    name: 'Persistent failure (all retries exhausted) shows unavailable, never a false "0"',
    mockResponses: [{ status: 500, body: {} }],
    waitMs: 4200,
    assert: ({ badgeText, callCount, consoleText }) => {
      record('Badge shows the unavailable placeholder ("—"), not "0", after retries are exhausted', badgeText === EM_DASH, `badgeText="${badgeText}"`);
      record('The bounded retry loop actually ran to exhaustion (>= 3 attempts)', callCount >= 3, `callCount=${callCount}`);
      record('Exhausted-retries failure was logged via console.warn (observable, not silent)', /Badge preload attempt 2\/3 failed, retrying/.test(consoleText) && /preload exhausted 3 attempts/.test(consoleText), consoleText);
    },
  },
  {
    name: 'Malformed response (200 OK, non-numeric/missing total_reports) shows unavailable, not "0"',
    mockResponses: [{ status: 200, body: { some_other_field: 'unexpected shape' } }],
    waitMs: 1200,
    assert: ({ badgeText, consoleText }) => {
      record('Badge shows the unavailable placeholder ("—") for a malformed 200 response, not "0"', badgeText === EM_DASH, `badgeText="${badgeText}"`);
      record('Malformed-response failure was logged via console.warn with the offending value', /non-numeric total_reports/.test(consoleText), consoleText);
    },
  },
  {
    name: 'Genuine zero count renders as "0", distinct from the unavailable placeholder',
    mockResponses: [{ status: 200, body: { total_reports: 0 } }],
    waitMs: 1200,
    assert: ({ badgeText }) => {
      record('Badge shows a literal "0" for a genuine zero count (not confused with "unavailable")', badgeText === '0', `badgeText="${badgeText}"`);
      record('Badge is NOT the unavailable placeholder for a genuine zero', badgeText !== EM_DASH, `badgeText="${badgeText}"`);
    },
  },
];

async function runScenario(browser, scenario) {
  // serviceWorkers: 'block' -- the page registers a service worker that can
  // intercept/cache fetches outside Playwright's route mocking, which would
  // make the per-scenario /api/reports/index.json mock non-deterministic
  // across scenarios. Not needed for this test: we only care about the
  // badge's direct fetch() calls.
  const context = await browser.newContext({ serviceWorkers: 'block' });
  let callCount = 0;
  const consoleMessages = [];

  await context.route('**/*', (route) => {
    const url = route.request().url();
    if (!url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.abort();
    const u = new URL(url);
    if (u.pathname === '/api/reports/index.json') {
      const idx = Math.min(callCount, scenario.mockResponses.length - 1);
      const resp = scenario.mockResponses[idx];
      callCount++;
      return route.fulfill({
        status: resp.status,
        contentType: 'application/json',
        body: JSON.stringify(resp.body),
      });
    }
    if (u.pathname.startsWith('/api/')) return route.abort();
    return route.continue();
  });

  const page = await context.newPage();
  page.on('console', (msg) => consoleMessages.push(msg.text()));
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(scenario.waitMs);
  const badgeText = await page.textContent('#cdb-tab-reports-count');

  console.log(`\n--- Scenario: ${scenario.name} ---`);
  await scenario.assert({ badgeText, callCount, consoleText: consoleMessages.join('\n') });

  await context.close();
}

// _setReportsBadgeCount() and _setReportsBadgeUnavailable() are written to
// independently by more than one caller (the preload IIFE here, and
// _loadReports() on a REPORTS-tab click). Once ANY caller has rendered a
// real, resolved count, a slower-running _preloadReportsBadge() retry chain
// that ultimately fails must not clobber it back to "unavailable" --
// window._cdbReportsBadgeResolved is the guard added for this. This test
// exercises the guard directly (setting it the same way _setReportsBadgeCount
// does) rather than through _loadReports()/cdbSwitchTab, since a separate,
// pre-existing issue in that wiring (a later <script> tag's plain
// `function cdbSwitchTab(...)` declaration overwrites the earlier wrapper
// that calls _loadReports()) makes that path unreachable today -- out of
// scope for this fix, noted for a future, separate pass.
async function runBadgeResolvedGuardScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', (route) => {
    const url = route.request().url();
    if (!url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.abort();
    const u = new URL(url);
    if (u.pathname === '/api/reports/index.json') {
      // Always fails -- forces _preloadReportsBadge() through all 3 bounded
      // retries and into its terminal "exhausted" branch.
      return route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
    }
    if (u.pathname.startsWith('/api/')) return route.abort();
    return route.continue();
  });

  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  // Before the preload's first attempt (~500ms), simulate what
  // _setReportsBadgeCount(483) does: render the real count and set the
  // resolved flag it sets on every numeric render.
  await page.waitForTimeout(150);
  await page.evaluate(() => {
    document.getElementById('cdb-tab-reports-count').textContent = '483';
    window._cdbReportsBadgeResolved = true;
  });
  const beforeExhaustion = await page.textContent('#cdb-tab-reports-count');
  // Let the preload's 3 bounded retries (500 + 1500 + 1500 = 3500ms) fully
  // exhaust and hit its terminal branch.
  await page.waitForTimeout(4200);
  const afterPreloadExhausted = await page.textContent('#cdb-tab-reports-count');

  record(
    'Simulated real count is in place before the preload retry chain exhausts',
    beforeExhaustion === '483',
    `badgeText="${beforeExhaustion}"`
  );
  record(
    'A later-exhausted _preloadReportsBadge() retry chain does NOT clobber an already-resolved real count',
    afterPreloadExhausted === '483',
    `badgeText="${afterPreloadExhausted}" (expected to still be "483", not "—")`
  );

  await context.close();
}

async function main() {
  const server = await startStaticServer(REPO_ROOT, PORT, MIME);
  let browser;
  try {
    browser = await chromium.launch();
    for (const scenario of SCENARIOS) {
      await runScenario(browser, scenario);
    }
    console.log('\n--- Scenario: An already-resolved real count survives a later-failing _preloadReportsBadge() retry chain ---');
    await runBadgeResolvedGuardScenario(browser);
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
