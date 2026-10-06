#!/usr/bin/env node
/**
 * SENTINEL APEX — TOP10 Report Resolution + Live IOC Lookup Regression Test (PR-D2)
 * ====================================================================
 * Real-browser (headless Chromium) verification of two independent P0
 * defects on the TOP10 "SOC PRIORITY FEED":
 *
 * 1. cdbBuildReportUrl(item) (index.html) only ever trusted
 *    report_url/internal_report_url on the feed item itself -- fields
 *    written by a separate sync step (scripts/sync_report_urls.py) that
 *    can lag behind the backend's own report registry
 *    (/api/reports/index.json). Live production evidence: 5 of the
 *    current 10 TOP10 items were confirmed customer-ready with a real,
 *    working (HTTP 200) report page, while the TOP10 API's own
 *    report_url field was null for all 10 -- rendering a real report as
 *    "UNAVAILABLE".
 * 2. GADGET 3 "Live IOC Lookup" markup calls
 *    window.CDB_GADGETS.iocLookup() directly from inline
 *    onclick/onkeydown handlers, but that namespace was never defined
 *    anywhere in the codebase -- every click/Enter threw
 *    "CDB_GADGETS is not defined" and the feature was 100%
 *    non-functional, unrelated to entitlement or backend health.
 *
 * Fix under test:
 *   - js/sentinel-live-feeds.js's loadReports() now populates
 *     window._cdbReportRegistry (id -> url) from /api/reports/index.json
 *     regardless of whether the (separate, already-working) Reports Archive
 *     DOM panel exists on the page.
 *   - cdbBuildReportUrl() now falls back to that registry when the feed
 *     item's own fields are empty, before returning '' (UNAVAILABLE) --
 *     it only ever ADDS a link, never removes one the primary check found.
 *   - window.CDB_GADGETS.iocLookup() is now defined, wired to the real
 *     /api/v1/ioc/lookup endpoint and the real #cdb-ioc-query/
 *     #cdb-ioc-result/#cdb-ioc-total DOM ids.
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node render-test/verify_report_resolution_and_ioc_lookup.js
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
const PORT = 8959;
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

const EMPTY_FEED = JSON.stringify({
  schema_version: "2.0.0", generated_at: "2026-08-12T06:00:00Z", version: "184.0",
  count: 0, items: [],
});

const REPORTS_REGISTRY = JSON.stringify({
  schema_version: "2.0.0", feed_type: "customer_ready_latest",
  total_candidates: 500, customer_ready_count: 1, withheld_count: 499,
  total_reports: 12662, reports_listed: 1,
  reports: [{
    id: "intel--8aa6740706d81c88",
    url: "https://intel.cyberdudebivash.com/reports/2026/08/intel--8aa6740706d81c88.html",
    path: "/reports/2026/08/intel--8aa6740706d81c88.html",
    title: "Exploit for Injection in Glpi-Project Glpi",
    severity: "CRITICAL", risk_score: 9, cve: [], kev_present: true,
    timestamp: "2026-08-11T14:42:31Z",
  }],
});

async function routeAPIs(context, overrides) {
  await context.route('**/*', (route) => {
    const url = route.request().url();
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body });

    if (/\/api\/reports\/index\.json/.test(url)) return overrides.reportsIndex === false
      ? route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
      : json(overrides.reportsIndex || REPORTS_REGISTRY);
    if (/\/api\/v1\/ioc\/lookup/.test(url)) return json(overrides.iocLookup || JSON.stringify({ found: false, results: [], total_iocs_checked: 148 }));
    if (/\/api\/(feed\.json|preview\/?|v1\/intel\/(latest|apex|top10|stats)\.json)/.test(url)) return json(EMPTY_FEED);
    if (/^\/api\//.test(new URL(url).pathname)) return route.abort();

    if (url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.continue();
    return route.abort();
  });
}

async function runReportRegistryScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, {});
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  // Let sentinel-live-feeds.js's loadReports() populate window._cdbReportRegistry
  await page.waitForTimeout(3000);

  const outcome = await page.evaluate(() => {
    // Item whose OWN report_url/internal_report_url are empty (simulating a
    // sync_report_urls.py lag) but IS present in the report registry.
    const readyButUnsynced = { id: 'intel--8aa6740706d81c88', validation_status: 'ok', report_url: '', internal_report_url: '' };
    // Item that is genuinely not in the registry and has no report_url --
    // must still resolve to '' (UNAVAILABLE), not a fabricated link.
    const genuinelyUnavailable = { id: 'intel--does-not-exist', validation_status: 'ok', report_url: '', internal_report_url: '' };
    // A rejected item must never get a link, even if by coincidence its id
    // is in the registry.
    const rejected = { id: 'intel--8aa6740706d81c88', validation_status: 'quality_fail', report_url: '', internal_report_url: '' };

    return {
      registryLoaded: !!(window._cdbReportRegistry && Object.keys(window._cdbReportRegistry).length),
      readyButUnsyncedUrl: typeof cdbBuildReportUrl === 'function' ? cdbBuildReportUrl(readyButUnsynced) : '__FN_MISSING__',
      genuinelyUnavailableUrl: typeof cdbBuildReportUrl === 'function' ? cdbBuildReportUrl(genuinelyUnavailable) : '__FN_MISSING__',
      rejectedUrl: typeof cdbBuildReportUrl === 'function' ? cdbBuildReportUrl(rejected) : '__FN_MISSING__',
    };
  });
  await context.close();

  record('window._cdbReportRegistry is populated from /api/reports/index.json', outcome.registryLoaded, JSON.stringify(outcome.registryLoaded));
  record('A customer-ready report whose feed-level report_url lags now resolves via the registry fallback', outcome.readyButUnsyncedUrl === 'https://intel.cyberdudebivash.com/reports/2026/08/intel--8aa6740706d81c88.html', `got="${outcome.readyButUnsyncedUrl}"`);
  record('An item genuinely absent from the registry still resolves to UNAVAILABLE (no fabricated link)', outcome.genuinelyUnavailableUrl === '', `got="${outcome.genuinelyUnavailableUrl}"`);
  record('A quality_fail item never gets a report link, even if its id is in the registry', outcome.rejectedUrl === '', `got="${outcome.rejectedUrl}"`);
}

async function runRegistryUnavailableScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, { reportsIndex: false });
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  const outcome = await page.evaluate(() => {
    const item = { id: 'intel--8aa6740706d81c88', validation_status: 'ok', report_url: '', internal_report_url: '' };
    return { url: typeof cdbBuildReportUrl === 'function' ? cdbBuildReportUrl(item) : '__FN_MISSING__' };
  });
  await context.close();

  record('A failed registry fetch degrades to UNAVAILABLE (not a crash, not a fabricated link)', outcome.url === '', `got="${outcome.url}"`);
}

async function runIOCLookupScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, { iocLookup: JSON.stringify({ found: true, results: [{ severity: 'CRITICAL', risk_score: 9.6, title: 'Test Advisory', ioc_count: 3, source: 'CVE Feed', published: '2026-08-12T00:00:00Z' }], total_iocs_checked: 148 }) });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  const before = await page.evaluate(() => typeof window.CDB_GADGETS);
  record('window.CDB_GADGETS is defined (was previously undefined -- ReferenceError on every click)', before === 'object', `typeof window.CDB_GADGETS === "${before}"`);

  await page.fill('#cdb-ioc-query', '1.2.3.4');
  await page.click('.cdb-ioc-btn');
  await page.waitForTimeout(1500);
  const hitResult = await page.evaluate(() => ({
    text: document.getElementById('cdb-ioc-result').textContent,
    cls: document.getElementById('cdb-ioc-result').className,
  }));
  // "_hEsc is not defined" is a separate, PRE-EXISTING bug in the unrelated
  // "Real-Time Cybersecurity Intelligence Feed" widget (initLiveCyberNews())
  // -- reproduced independently of any IOC lookup interaction, on unmodified
  // main, via a dedicated one-off repro script. Not caused by and out of
  // scope for this PR-D2 fix; filtered here so it doesn't mask a genuine
  // regression in the code this test actually exercises.
  const newPageErrors = pageErrors.filter(e => !e.includes('_hEsc is not defined'));
  record('Clicking SCAN with a matching IOC calls the real API and renders a hit result, no new ReferenceError', hitResult.cls.includes('hit') && hitResult.text.includes('Test Advisory') && newPageErrors.length === 0, JSON.stringify({ cls: hitResult.cls, hasTitle: hitResult.text.includes('Test Advisory'), newPageErrors }));

  await context.close();
}

async function runIOCLookupMissScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, {});
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  await page.fill('#cdb-ioc-query', '192.168.1.1');
  await page.press('#cdb-ioc-query', 'Enter');
  await page.waitForTimeout(1500);
  const missResult = await page.evaluate(() => ({
    text: document.getElementById('cdb-ioc-result').textContent,
    cls: document.getElementById('cdb-ioc-result').className,
  }));
  record('Pressing Enter with no matching IOC shows an honest "no matches" state, not stuck scanning', missResult.cls.includes('miss') && missResult.text.includes('No matches'), JSON.stringify(missResult));
}

async function main() {
  const server = await startStaticServer(REPO_ROOT, PORT, MIME);
  let browser;
  try {
    browser = await chromium.launch();
    console.log('--- Scenario: report registry fallback resolves an unsynced-but-ready report ---');
    await runReportRegistryScenario(browser);
    console.log('\n--- Scenario: registry fetch itself fails ---');
    await runRegistryUnavailableScenario(browser);
    console.log('\n--- Scenario: IOC lookup hit (CDB_GADGETS.iocLookup wired and callable) ---');
    await runIOCLookupScenario(browser);
    console.log('\n--- Scenario: IOC lookup miss via Enter key ---');
    await runIOCLookupMissScenario(browser);
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
