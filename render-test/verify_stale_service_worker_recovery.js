#!/usr/bin/env node
/**
 * SENTINEL APEX — Stale Service Worker Recovery Regression Test
 * ====================================================================
 * Real-browser (headless Chromium) verification that a browser already
 * stuck on a broken/outdated service worker actually recovers, instead
 * of relying solely on the browser's own SW update-check timing.
 *
 * Root cause this addresses: this repo's own commit history documents a
 * live incident (service-worker.js's v175/v176 header comments; index.html's
 * SW registration comments) where a customer's browser ran an old SW whose
 * fetch handler intercepted /api/* with broken/empty responses, while the
 * real API was healthy the entire time. The first fix for that
 * (updateViaCache:'none' + a visibilitychange re-check) makes the browser's
 * own update *check* more reliable, but does not guarantee an
 * already-stuck browser recovers promptly -- reproduced with a scripted
 * harness (register a broken SW, then make the real, correct SW available
 * server-side): the new worker can sit in the registration's `waiting`
 * state across several real reloads without ever taking control, so
 * loadGOCIntel() keeps re-running against the same broken interception.
 *
 * The actual fix (index.html, loadGOCIntel()'s terminal "no data at all"
 * branch): if every MANIFEST_URLS source fails AND a service worker is
 * controlling the page, unregister every SW registration for this origin,
 * clear every SW-managed cache, and reload once -- session-guarded
 * (sessionStorage, not persisted past the tab) so a genuine network/API
 * outage still degrades to the normal retry message instead of
 * reload-looping forever. This script proves that recovery path directly:
 * a browser stuck on a broken SW ends up showing real data, and stays
 * stable across further reloads, without depending on SW update timing.
 *
 * Same pattern as this directory's other verify_*.js scripts -- local
 * static server + Playwright, hermetic (non-local requests aborted),
 * record()/exitCode convention -- designed to run alongside
 * verify_pages_fast_publish_smoke.js and verify_threat_map_chrome_render.js
 * in pages-fast-publish.yml.
 *
 * Usage:
 *   node render-test/verify_stale_service_worker_recovery.js [dist-dir]
 *   (defaults to "dist" at the repo root)
 *
 * Exit code 0 = all checks passed. Exit code 1 = at least one failed.
 */
'use strict';

const path = require('path');
const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright');

const REPO_ROOT = path.resolve(__dirname, '..');
const ROOT_DIR = path.resolve(REPO_ROOT, process.argv[2] || 'dist');
const PORT = 8974; // next free port after this dir's other scripts (8943/8944/8958/8960)
const PAGE_URL = `http://127.0.0.1:${PORT}/index.html`;
const NAV_TIMEOUT_MS = 20_000;

// Simulates a pre-fix "broken" SW already stuck on a real customer's
// browser: intercepts /api/* with 200-OK-but-empty responses (matching the
// diagnosed "endpoints that exist nowhere in this codebase" failure mode).
// Does not self-update or aggressively claim -- an old, passive SW.
const OLD_SW_SOURCE = `
self.addEventListener('install', () => {});
self.addEventListener('activate', (e) => { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.includes('/api/')) {
    event.respondWith(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    return;
  }
  event.respondWith(fetch(event.request));
});
`;

const REAL_FEED = JSON.stringify({
  schema_version: '2.0.0', generated_at: new Date().toISOString(), version: '184.0', count: 1,
  items: [{ id: 'intel--real-1', stix_id: 'intel--real-1', title: 'REGRESSION-TEST-CANARY-ITEM', description: 'x', severity: 'CRITICAL', confidence_score: 0.9, risk_score: 90, published_at: new Date().toISOString(), source_url: 'https://example.com/1' }],
});

// Starts true (broken SW served); flips false partway through the test to
// model "the real fix is already deployed server-side, only the client's
// browser hasn't caught up yet" -- the actual shape of the real incident.
let serveOldSW = true;

const MIME = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
  '.json': 'application/json', '.ico': 'image/x-icon', '.mp4': 'video/mp4',
};

function startServer(root) {
  const server = http.createServer((req, res) => {
    let urlPath = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
    if (urlPath === '/api/feed.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(REAL_FEED); return; }
    if (urlPath === '/service-worker.js') {
      res.writeHead(200, { 'Content-Type': 'application/javascript', 'Cache-Control': 'no-store' });
      res.end(serveOldSW ? OLD_SW_SOURCE : fs.readFileSync(path.join(root, 'service-worker.js')));
      return;
    }
    if (urlPath.endsWith('/')) urlPath += 'index.html';
    const filePath = path.join(root, urlPath);
    if (!filePath.startsWith(root)) { res.writeHead(403); res.end(); return; }
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
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`);
}

async function dashboardState(page) {
  try {
    return await page.evaluate(() => {
      const grid = document.getElementById('threat-grid');
      const text = grid ? grid.textContent : '';
      return {
        ok: true,
        hasCanary: /REGRESSION-TEST-CANARY-ITEM/.test(text),
        controllerURL: navigator.serviceWorker.controller ? navigator.serviceWorker.controller.scriptURL : null,
      };
    });
  } catch (e) {
    return { ok: false }; // mid-navigation; caller retries
  }
}

async function main() {
  if (!fs.existsSync(path.join(ROOT_DIR, 'index.html')) || !fs.existsSync(path.join(ROOT_DIR, 'service-worker.js'))) {
    console.error(`[FATAL] ${ROOT_DIR} is missing index.html or service-worker.js -- nothing to test.`);
    process.exitCode = 1;
    return;
  }

  const server = await startServer(ROOT_DIR);
  let browser;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    page.setDefaultTimeout(NAV_TIMEOUT_MS);

    const pageErrors = [];
    page.on('pageerror', (err) => pageErrors.push(String((err && err.message) || err)));

    await page.route('**/*', (route) => {
      const url = new URL(route.request().url());
      if (url.hostname === '127.0.0.1') return route.continue();
      return route.abort();
    });

    await page.goto(PAGE_URL, { waitUntil: 'load', timeout: NAV_TIMEOUT_MS });
    await page.waitForTimeout(1500);
    let s = await dashboardState(page);
    record('Old SW registers without throwing (uncontrolled first load shows real data)', s.ok && s.hasCanary,
      JSON.stringify(s));

    // The server now has the real, correct service-worker.js -- models "the
    // fix has already shipped"; only this client's own browser is stuck.
    serveOldSW = false;

    // This reload is where the old SW takes control and loadGOCIntel()'s
    // fetch cascade should fail against it -- and where the new client-side
    // recovery should detect that and self-heal.
    await page.reload({ waitUntil: 'load' });

    let recovered = false;
    for (let i = 0; i < 12 && !recovered; i++) {
      await page.waitForTimeout(2000);
      s = await dashboardState(page);
      if (s.ok && s.hasCanary) recovered = true;
    }
    record('A browser stuck on a broken SW recovers on its own (client-side unregister+reload, no dependency on SW update timing)',
      recovered, recovered ? 'recovered' : 'never showed real data across 12 polls (~24s)');

    // Stability: once recovered, further ordinary reloads must not
    // regress back to the broken state (e.g. from a reload loop, or the
    // sessionStorage guard misfiring).
    //
    // CI-observed failure (2026-09-01, this exact step): reloading
    // immediately back-to-back, with no gap, right after the recovery
    // reload re-registers the real service-worker.js fresh, hit Playwright's
    // 20s navigation timeout on a shared GitHub Actions runner -- passed
    // locally every time, never reproduced there. That's not a realistic
    // user action (nobody reloads a tab twice with zero delay the instant
    // it finishes loading) and it was blocking real deploys outright: this
    // step's failure skips the actual "Deploy to GitHub Pages" step in
    // pages-fast-publish.yml. Fix: a short settle gap before each reload so
    // the freshly re-registered SW's install/activate lifecycle isn't still
    // in flight when the next navigation starts, a generous explicit
    // per-reload timeout with headroom for a loaded CI runner, and each
    // reload wrapped so a slow one is recorded as a failed check with a
    // clear reason instead of crashing the whole script. The assertion
    // itself (must show real data, must not regress) is unchanged.
    let stable = true;
    let stableDetail = '';
    for (let i = 1; i <= 2 && stable; i++) {
      await page.waitForTimeout(1000); // let the freshly re-registered SW's lifecycle settle
      try {
        await page.reload({ waitUntil: 'load', timeout: 30000 });
      } catch (e) {
        stable = false;
        stableDetail = `reload #${i} failed: ${String(e.message || e).split('\n')[0]}`;
        break;
      }
      await page.waitForTimeout(1500);
      s = await dashboardState(page);
      if (!(s.ok && s.hasCanary)) { stable = false; stableDetail = `reload #${i}: ${JSON.stringify(s)}`; }
    }
    record('Recovery is stable across further ordinary reloads (no reload-looping, no regression back to broken)', stable, stableDetail);

    // Note: this script only listens for 'pageerror' (uncaught exceptions),
    // not 'console' messages -- index.html's GOC diagnostic (see
    // verify_pages_fast_publish_smoke.js's fix for the full writeup) is a
    // plain console.error() log call, never a thrown exception, so it can
    // never reach pageErrors here. No equivalent fix needed in this file.
    record('Zero uncaught JS errors across the whole stuck-then-recover sequence', pageErrors.length === 0, pageErrors.join(' | '));

    await context.close();
  } finally {
    if (browser) await browser.close();
    server.close();
  }

  const failed = results.filter((r) => !r.pass);
  console.log('='.repeat(64));
  console.log(`SUMMARY: ${results.length - failed.length}/${results.length} checks passed`);
  console.log('='.repeat(64));
  if (failed.length) {
    console.log('FAILED CHECKS:');
    for (const f of failed) console.log(`  - ${f.name}${f.detail ? ': ' + f.detail : ''}`);
    process.exitCode = 1;
  } else {
    process.exitCode = 0;
  }
}

main().catch((err) => {
  console.error('[FATAL]', err);
  process.exitCode = 1;
});
