#!/usr/bin/env node
/**
 * SENTINEL APEX — Real-Time Feed / Global Cyber Intel Recovery Regression Test (PR-D1)
 * ====================================================================
 * Real-browser (headless Chromium) verification of two independent P0
 * defects in the real-time content sections:
 *
 * 1. "LIVE FEEDS SYNCING — DISPLAYING CACHED INTEL" (Real-Time Cybersecurity
 *    Intelligence Feed, #lcn-grid): index.html's initLiveCyberNews() IIFE
 *    called `_hEsc()` inside its _render() function, but that helper was
 *    never defined in this IIFE's own scope -- a same-named helper exists,
 *    but inside a separate, earlier <script> block's own closure, out of
 *    reach here. The very first call, `_render(STATIC_FALLBACK, true)`,
 *    threw synchronously on page load and aborted the rest of the IIFE --
 *    _loadAll(1) (the actual live-fetch attempt) and the auto-refresh
 *    setInterval were never reached. This feature never even attempted a
 *    live fetch, independent of the separate CSP connect-src gap (also
 *    fixed in this PR -- see _headers) that would otherwise have blocked
 *    the fetches anyway.
 * 2. "CYBERDUDEBIVASH GLOBAL CYBER INTEL — LIVE" (#cdb-news-grid):
 *    refreshNews() was only ever called from boot()/bootEnterprise() at
 *    DOMContentLoaded, at which instant window.__GOC_LIVE_INTEL is always
 *    still unset. Nothing re-invoked refreshNews() once _fetchLiveIntel()
 *    later populated real data.
 *
 * Fix under test:
 *   - A local _hEsc() is now defined inside initLiveCyberNews()'s own scope.
 *   - _render() gained a third `isExhausted` state so a customer can tell
 *     "still retrying" from "gave up until the next 5-minute cycle" instead
 *     of an indefinite "Auto-retrying" claim.
 *   - _startAIBrainPoller()'s _fetchLiveIntel() success callbacks now also
 *     call refreshNews().
 *   - _headers' connect-src now whitelists the 3 CORS-proxy domains this
 *     feature depends on (verified directly against the file below, since
 *     Cloudflare Pages' _headers mechanism isn't interpreted by this test's
 *     plain Node static server).
 *
 * STAGE 3 ADDITION: also verifies that STATIC_FALLBACK's cached headlines
 * no longer claim a fabricated relative age (was: pubDate computed as
 * `Date.now() - fixed_offset` at page-render time, so "15m ago"-style text
 * was always fresh on every load regardless of true content age) -- see
 * runCachedFallbackHonestTimestampScenario() below.
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node render-test/verify_live_news_feed_recovery.js
 *
 * Exit code 0 = all checks passed. Exit code 1 = at least one failed.
 */
'use strict';

const path = require('path');
const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright');

const REPO_ROOT = path.resolve(__dirname, '..');
const PORT = 8961;
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

const EMPTY_FEED = JSON.stringify({
  schema_version: "2.0.0", generated_at: "2026-08-12T06:00:00Z", version: "184.0",
  count: 0, items: [],
});

const REAL_ISH_INTEL = JSON.stringify([
  { id: "intel--test1", title: "CVE-2026-99999 Critical RCE in Example Widget", severity: "CRITICAL", date: "2026-08-12T00:00:00Z" },
  { id: "intel--test2", title: "Ransomware group targets healthcare sector", severity: "HIGH", date: "2026-08-12T01:00:00Z" },
]);

async function routeAPIs(context, { proxiesSucceed }) {
  await context.route('**/*', (route) => {
    const url = route.request().url();
    const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body });

    if (/api\.allorigins\.win|corsproxy\.io|api\.rss2json\.com/.test(url)) {
      if (proxiesSucceed) {
        return route.fulfill({
          status: 200, contentType: 'application/rss+xml',
          body: '<rss><channel><item><title>Live Test Advisory From Proxy</title><link>https://example.com/a</link><pubDate>' + new Date().toUTCString() + '</pubDate></item></channel></rss>',
        });
      }
      return route.abort();
    }
    if (/\/api\/apex_v2\/(priority|critical)\.json/.test(url)) return json(REAL_ISH_INTEL);
    if (/\/api\/(feed\.json|preview\/?|v1\/intel\/(latest|apex|top10|stats)\.json)/.test(url)) return json(EMPTY_FEED);
    if (/^\/api\//.test(new URL(url).pathname)) return route.abort();

    if (url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.continue();
    return route.abort();
  });
}

async function runNoCrashScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, { proxiesSucceed: false });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);

  const hEscErrors = pageErrors.filter(e => e.includes('_hEsc is not defined'));
  record('initLiveCyberNews() no longer throws "_hEsc is not defined" on initial render', hEscErrors.length === 0, JSON.stringify(hEscErrors));

  const bannerText = await page.evaluate(() => {
    const el = document.getElementById('lcn-error');
    return el ? el.textContent.trim() : '__MISSING_ELEMENT__';
  });
  record('The SYNCING banner renders immediately on load (proves _render(STATIC_FALLBACK) completed instead of crashing)', bannerText.includes('LIVE FEEDS SYNCING'), `bannerText="${bannerText}"`);

  const gridPopulated = await page.evaluate(() => {
    const grid = document.getElementById('lcn-grid');
    return grid ? grid.children.length : -1;
  });
  record('The feed grid is populated with the static fallback cards (proves the .map()/_hEsc() loop completed, not aborted mid-render)', gridPopulated > 0, `childCount=${gridPopulated}`);

  await context.close();
}

async function runExhaustedRetryScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, { proxiesSucceed: false });
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  // Backoff schedule: attempt 1 fails immediately -> wait 3s -> attempt 2
  // fails -> wait 6s -> attempt 3 fails -> terminal state. ~10s total.
  await page.waitForTimeout(11000);

  const bannerText = await page.evaluate(() => {
    const el = document.getElementById('lcn-error');
    return el ? el.textContent.trim() : '__MISSING_ELEMENT__';
  });
  record('After all retries are exhausted, the banner shows an honest "UNAVAILABLE" terminal state, not an indefinite "Auto-retrying" claim', bannerText.includes('LIVE FEEDS UNAVAILABLE') && bannerText.includes('Retrying in 5 min'), `bannerText="${bannerText}"`);

  await context.close();
}

async function runLiveSuccessScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, { proxiesSucceed: true });
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  const state = await page.evaluate(() => {
    const err = document.getElementById('lcn-error');
    const grid = document.getElementById('lcn-grid');
    return {
      bannerHidden: err ? (err.style.display === 'none') : null,
      gridText: grid ? grid.textContent : '',
    };
  });
  record('When the proxy fetch succeeds, the SYNCING banner clears and real live content replaces the cached fallback', state.bannerHidden === true && state.gridText.includes('Live Test Advisory From Proxy'), JSON.stringify(state));

  await context.close();
}

async function runGlobalIntelBootRaceScenario(browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, { proxiesSucceed: false });
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  // _startAIBrainPoller() fires _fetchLiveIntel() on load; give it time to
  // resolve against the mocked /api/apex_v2/priority.json and re-invoke
  // refreshNews().
  await page.waitForTimeout(3000);

  const gridText = await page.evaluate(() => {
    const grid = document.getElementById('cdb-news-grid');
    return grid ? grid.textContent : '__MISSING_ELEMENT__';
  });
  record('Global Cyber Intel — LIVE (#cdb-news-grid) populates once real intel data actually arrives, not stuck on its initial shimmer', gridText.includes('CVE-2026-99999') || gridText.includes('Ransomware group targets healthcare sector'), `gridText(first 200)="${gridText.slice(0, 200)}"`);

  await context.close();
}

/**
 * Asserts STATIC_FALLBACK's cached headlines show the honest "Cached
 * headline" label instead of a fabricated "Xm/Xh/Xd ago" relative age.
 * @param {import('playwright').Browser} browser
 */
async function runCachedFallbackHonestTimestampScenario(browser) {
  // STAGE 3 FIX: STATIC_FALLBACK's pubDate previously read
  // `new Date(Date.now()-N).toISOString()`, computed from the page-render
  // clock at evaluation time rather than any real publication/capture
  // timestamp -- so every fresh page load showed these 11 cached headlines
  // as "15m ago", "1h ago", etc. regardless of their true (unknown) age. No
  // real timestamp exists for this illustrative cached content, so pubDate
  // is now explicitly null and cached cards render honest "Cached headline"
  // text instead of a fabricated relative age.
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await routeAPIs(context, { proxiesSucceed: false });
  const page = await context.newPage();
  await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);

  const dateTexts = await page.evaluate(() =>
    Array.from(document.querySelectorAll('#lcn-grid .lcn-date')).map((el) => el.textContent.trim()));

  record('Cached fallback headlines never claim a fabricated relative age (no "Xm/Xh/Xd ago" derived from the page-render clock)',
    dateTexts.length > 0 && dateTexts.every((t) => !/\d+\s*[mhd]\s*ago/i.test(t)),
    JSON.stringify(dateTexts));

  record('Cached fallback headlines instead show the honest, non-time-claiming "Cached headline" label',
    dateTexts.length > 0 && dateTexts.every((t) => t.includes('Cached headline')),
    JSON.stringify(dateTexts));

  await context.close();
}

function runCSPAllowlistScenario() {
  // STAGE 3 FIX: this previously matched the FIRST line containing the
  // substring "Content-Security-Policy" -- but _headers' own explanatory
  // comment ("# CSP is the <meta http-equiv="Content-Security-Policy">
  // tag in index.html.") also contains that substring and sorts earlier in
  // the file than the real `Content-Security-Policy:` response header
  // line, so .find() always returned the comment, never the real directive
  // -- every hasAllorigins/hasCorsproxy/hasRss2json check below was
  // silently false regardless of the real header's content. The real
  // _headers directive was (and is) correctly configured with all three
  // domains the whole time; only this check's own line-selection was
  // broken. Excluding comment lines fixes the false negative.
  const headersContent = fs.readFileSync(path.join(REPO_ROOT, '_headers'), 'utf-8');
  const cspLine = headersContent.split('\n').find(l => !l.trim().startsWith('#') && l.includes('Content-Security-Policy'));
  const hasAllorigins = /connect-src[^;]*api\.allorigins\.win/.test(cspLine || '');
  const hasCorsproxy = /connect-src[^;]*corsproxy\.io/.test(cspLine || '');
  const hasRss2json = /connect-src[^;]*api\.rss2json\.com/.test(cspLine || '');
  record('_headers connect-src whitelists api.allorigins.win, corsproxy.io, and api.rss2json.com (the domains initLiveCyberNews() actually fetches)', hasAllorigins && hasCorsproxy && hasRss2json, JSON.stringify({ hasAllorigins, hasCorsproxy, hasRss2json }));
}

async function main() {
  const server = await startStaticServer();
  let browser;
  try {
    browser = await chromium.launch();
    console.log('--- Scenario: page load no longer crashes on _hEsc ---');
    await runNoCrashScenario(browser);
    console.log('\n--- Scenario: CSP allowlist (static config check) ---');
    runCSPAllowlistScenario();
    console.log('\n--- Scenario: cached fallback headlines show an honest label, not a fabricated relative age ---');
    await runCachedFallbackHonestTimestampScenario(browser);
    console.log('\n--- Scenario: live proxy fetch succeeds -> real content replaces fallback ---');
    await runLiveSuccessScenario(browser);
    console.log('\n--- Scenario: Global Cyber Intel LIVE populates once real data arrives ---');
    await runGlobalIntelBootRaceScenario(browser);
    console.log('\n--- Scenario: all retries exhausted -> honest terminal state (slow, ~11s) ---');
    await runExhaustedRetryScenario(browser);
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
