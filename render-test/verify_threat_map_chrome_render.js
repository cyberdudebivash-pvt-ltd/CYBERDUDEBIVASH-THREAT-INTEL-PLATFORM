#!/usr/bin/env node
/**
 * 2026-09-28: the homepage threat panel is now the LIVE THREAT BOARD, built
 * only from GET /api/watchdog/brief. The illustrative canvas map (and the
 * GPU/compositor governance it needed) was removed: the feed carries no
 * attack geolocation, so the animation could not show observed attacks.
 * Sections 1-4 below verify the board (fresh, degraded and escaping);
 * the demo video, console-error and lead-modal checks are unchanged. The
 * history below describes the removed canvas and is kept for context.
 *
 * SENTINEL APEX — Threat Map / Demo Video Chrome Render Regression Test
 * ====================================================================
 * Real-browser (headless Chromium) verification that the homepage's
 * "Premium interactive threat map" (#299) and self-hosted demo video
 * (#299/#309/#310) actually render, and stay rendered through the exact
 * new user interactions those PRs added -- immersive fullscreen expand
 * and city hover tooltips -- instead of only checking for thrown errors.
 *
 * Root cause this closes: #cdb-threat-canvas has a long documented
 * history (index.html's RC1-RC13 / v159-v186 governance CSS comments;
 * js/engines/renderer-recovery-engine.js's blank-frame scanner;
 * js/engines/compositor-governance-engine.js) of going silently blank
 * on real hardware-accelerated Chrome from GPU compositor layer
 * pre-promotion -- a failure mode that throws no JS error and 404s
 * nothing, so it is invisible to verify_pages_fast_publish_smoke.js and
 * every other existing render-test/*.js script (grepped: none reference
 * the threat map or demo video). That blind spot is exactly why this
 * one panel reached production broken 13+ times before being caught by
 * a real customer's bug report each time. This script is the first
 * automated check that samples actual canvas pixel content instead of
 * only watching for thrown errors, and the first to exercise the new
 * (#299) fullscreen-toggle and tooltip interaction code at all.
 *
 * It cannot reproduce the GPU-hardware-specific trigger itself --
 * headless Chromium here runs on SwiftShader software rendering, not
 * the D3D11/ANGLE hardware path prior incidents were traced to -- but it
 * locks in what IS deterministic and host-independent: the canvas must
 * never be left with no painted content, the governed CSS properties
 * the RC1-RC13 history traced the trap to (will-change/transform/
 * box-shadow/border-radius on the canvas) must stay neutralized, and
 * none of the new interaction-layer code may throw. A future regression
 * that reintroduces any of those properties, or that leaves the canvas
 * zero-sized after the immersive toggle, fails this check even without
 * hardware acceleration, because the properties are asserted directly.
 *
 * Same pattern as this directory's other verify_*.js scripts -- local
 * static server + Playwright, hermetic (non-local requests aborted),
 * record()/exitCode convention -- and designed to run alongside
 * verify_pages_fast_publish_smoke.js in pages-fast-publish.yml.
 *
 * Usage:
 *   node render-test/verify_threat_map_chrome_render.js [dist-dir]
 *   (defaults to "dist" at the repo root, same default as
 *   verify_pages_fast_publish_smoke.js)
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
const ROOT_DIR = path.resolve(REPO_ROOT, process.argv[2] || 'dist');
const PORT = 8960; // next free port after this dir's other scripts (8943/8944/8958) to avoid collision if ever run together
const PAGE_URL = `http://127.0.0.1:${PORT}/index.html`;
const NAV_TIMEOUT_MS = 20_000;

const MIME = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.json': 'application/json', '.txt': 'text/plain', '.ico': 'image/x-icon',
  '.mp4': 'video/mp4',
};

const results = [];
function record(name, pass, detail) {
  results.push({ name, pass, detail });
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`);
}

// Brief fixtures served for /api/watchdog/brief (hermetic: no production API).
const BRIEF_ITEMS = [
  { id: 'fx-1', title: 'Citrix confirms two NetScaler RCE zero-days exploited in attacks', severity: 'CRITICAL', source: 'BleepingComputer',
    observed_at: new Date(Date.now() - 3600e3).toISOString(), priority: { band: 'CRITICAL', score: 70 },
    corroboration: { reports: 2, sources: ['BleepingComputer', 'SecurityAffairs'], related: [] } },
  { id: 'fx-2', title: '<img src=x onerror="window.__boardXss=1"> hostile title', severity: 'HIGH', source: 'Fixture',
    observed_at: new Date(Date.now() - 7200e3).toISOString(), priority: { band: 'HIGH', score: 40 } },
];
const LIVE_BRIEF = {
  status: 200,
  body: { freshness_status: 'FRESH', count: 2, stories: 2, feed_generated_at: new Date(Date.now() - 600e3).toISOString(), items: BRIEF_ITEMS,
    situation: { feed_items_seen: 3, by_severity: { CRITICAL: 1, HIGH: 1 } } },
};
const STALE_BRIEF = {
  status: 503,
  // Deliberately simulate an older Worker response. The page must ignore its
  // nested expired records even before all upstream caches have converged.
  body: { error: 'intelligence_degraded', freshness_status: 'STALE', count: 0, items: [], last_authoritative: { live: false, label: 'LAST AUTHORITATIVE INTELLIGENCE - NOT LIVE',
    feed_generated_at: new Date(Date.now() - 9 * 3600e3).toISOString(), count: 1, items: BRIEF_ITEMS.slice(0, 1), situation: {} } },
};

async function boardState(page) {
  return page.evaluate(() => {
    const panel = document.getElementById('cdb-threat-map-panel');
    const board = document.getElementById('cdb-live-board');
    const status = document.getElementById('cdb-board-status');
    return {
      panel: !!panel,
      board: !!board,
      canvas: !!document.getElementById('cdb-threat-canvas') || !!(panel && panel.querySelector('canvas')),
      illustrative: !!(panel && /illustrative|simulated|not live attacks/i.test(panel.textContent || '')),
      cards: board ? board.querySelectorAll('.cdb-board-card').length : 0,
      injectedImg: board ? board.querySelectorAll('img').length : -1,
      xss: !!window.__boardXss,
      hostileShownAsText: !!(board && (board.textContent || '').includes('<img src=x')),
      status: status ? status.getAttribute('data-state') + ' ' + status.textContent : null,
      banner: board && board.querySelector('.cdb-board-banner') ? board.querySelector('.cdb-board-banner').textContent : null,
      panelWidth: panel ? panel.getBoundingClientRect().width : 0,
    };
  });
}

async function main() {
  if (!fs.existsSync(path.join(ROOT_DIR, 'index.html'))) {
    console.error(`[FATAL] ${path.join(ROOT_DIR, 'index.html')} does not exist -- nothing to test.`);
    process.exitCode = 1;
    return;
  }

  const server = await startStaticServer(ROOT_DIR, PORT, MIME);
  let browser;
  try {
    browser = await chromium.launch();
    // Service workers blocked: index.html registers one, which would
    // intercept fetches ahead of this script's own route handler below --
    // same precaution verify_gadget_runtime_recovery.js takes, for the
    // same reason.
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' });
    const page = await context.newPage();
    page.setDefaultTimeout(NAV_TIMEOUT_MS);

    const pageErrors = [];
    page.on('pageerror', (err) => pageErrors.push(String((err && err.message) || err)));
    page.on('console', (msg) => {
      if (msg.type() === 'error' && !/Failed to load resource:|frame-ancestors' is ignored/.test(msg.text())) {
        pageErrors.push('console.error: ' + msg.text());
      }
    });

    // Hermetic, same convention as verify_pages_fast_publish_smoke.js:
    // local requests pass through, everything cross-origin (production
    // API, CDN fonts/icons, CORS-proxied news feed) is aborted.
    let briefFixture = LIVE_BRIEF;
    let briefRequests = 0;
    await page.route('**/*', (route) => {
      const url = new URL(route.request().url());
      if (url.hostname === '127.0.0.1' && url.pathname === '/api/watchdog/brief') {
        briefRequests++;
        return route.fulfill({ status: briefFixture.status, contentType: 'application/json', body: JSON.stringify(briefFixture.body) });
      }
      if (url.hostname === '127.0.0.1') return route.continue();
      return route.abort();
    });

    let videoRequestStatus = null;
    page.on('response', (resp) => {
      const url = new URL(resp.url());
      if (url.hostname === '127.0.0.1' && /DASHBOARD-OVERVIEW-LIVE-VIDEO\.mp4$/.test(url.pathname)) {
        videoRequestStatus = resp.status();
      }
    });

    // Pre-suppress the unrelated #apex-lead-modal (timed/scroll-depth/
    // exit-intent lead popup, live since #281 -- see index.html's
    // apex_lead_suppressed localStorage key) for THIS page's checks below.
    // Discovered live while first writing this script: Playwright's
    // click-target auto-scroll for step 5's demo-video click crosses the
    // modal's 60%-scroll-depth trigger, popping it open over the whole
    // viewport (z-index 99999) an instant before the click lands -- so the
    // click hits the modal's backdrop instead of the button under it,
    // hanging until Playwright's click-retry timeout. That is a real
    // click-trap (see the Escape/backdrop-click dismissal added alongside
    // this script, same commit), but it is a separate concern from what
    // this script exists to verify; §7 below exercises that fix directly
    // and deliberately does NOT rely on this suppression.
    await page.addInitScript(() => {
      try { localStorage.setItem('apex_lead_suppressed', String(Date.now() + 999999999)); } catch (e) {}
    });

    await page.goto(PAGE_URL, { waitUntil: 'load', timeout: NAV_TIMEOUT_MS });
    await page.waitForTimeout(3000); // let the board's first /api/watchdog/brief load settle

    // ── 1. The live board renders the brief it was served ────────────────
    const live = await boardState(page);
    record('Threat panel and live board are present', live.panel && live.board, JSON.stringify({ panel: live.panel, board: live.board }));
    record('Live board renders one card per brief story', live.cards === BRIEF_ITEMS.length, `cards=${live.cards}`);
    record('Board status reads LIVE for a fresh brief', /^live LIVE/.test(live.status || ''), `status=${live.status}`);
    record('Panel has a non-zero rendered width', live.panelWidth > 0, `width=${live.panelWidth}`);
    record('Page load makes one shared brief request (board reuses window.APEX_BRIEF)', briefRequests === 1, `requests=${briefRequests}`);

    // ── 2. Nothing illustrative or simulated is shipped ──────────────────
    record('No canvas animation in the threat panel', !live.canvas);
    record('Panel carries no illustrative / simulated labels', !live.illustrative);

    // ── 3. Feed text is rendered as text, never as markup ────────────────
    record('A hostile advisory title is rendered as text (no injected element)', live.injectedImg === 0 && !live.xss && live.hostileShownAsText,
      JSON.stringify({ injectedImg: live.injectedImg, xss: live.xss, shownAsText: live.hostileShownAsText }));

    // ── 4. Expired or uncontracted responses cannot populate the board ───
    briefFixture = STALE_BRIEF;
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(1500);
    const stale = await boardState(page);
    record('Stale feed: no expired cards or nested fallback banner', stale.cards === 0 && stale.banner === null, `cards=${stale.cards} banner=${stale.banner}`);
    record('Stale feed: status reads DEGRADED', /^down DEGRADED/.test(stale.status || ''), `status=${stale.status}`);
    briefFixture = { status: 200, body: { ...LIVE_BRIEF.body, freshness_status: undefined } };
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(1500);
    const uncontracted = await boardState(page);
    record('Missing freshness contract: HTTP 200 cannot expose cards', uncontracted.cards === 0 && /^down DEGRADED/.test(uncontracted.status || ''), `cards=${uncontracted.cards} status=${uncontracted.status}`);
    briefFixture = LIVE_BRIEF;
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(1500);
    const recovered = await boardState(page);
    record('Fresh recovery: cards and LIVE status return', recovered.cards === BRIEF_ITEMS.length && /^live LIVE/.test(recovered.status || ''), `cards=${recovered.cards} status=${recovered.status}`);

    // ── 5. Demo video: click-to-play cover swaps in the real <video>, and
    //      its <source> resolves instead of 404ing (#309's regression
    //      class -- present at repo root but missing from dist/). ────────
    const demoPlaceholder = page.locator('#apex-demo-placeholder');
    if (await demoPlaceholder.count() > 0) {
      await demoPlaceholder.click();
      await page.waitForTimeout(1500);
      const videoVisible = await page.evaluate(() => {
        const v = document.getElementById('apex-demo-video');
        const ph = document.getElementById('apex-demo-placeholder');
        return !!(v && ph && getComputedStyle(v).display !== 'none' && getComputedStyle(ph).display === 'none');
      });
      record('Demo video element replaces the click-to-play cover on click', videoVisible);
      record('Demo video <source> resolves (not a 404 -- the #309 regression class)', videoRequestStatus !== null && videoRequestStatus < 400,
        `HTTP ${videoRequestStatus === null ? 'never requested' : videoRequestStatus}`);
    } else {
      record('Demo video click-to-play cover (#apex-demo-placeholder) is present in the DOM', false, 'not found');
    }

    // ── 6. No uncaught errors from boot or any interaction above ─────────
    // index.html's feed-state resolver (js/feed-state.js resolveFeedTerminalState(),
    // P0 incident 2026-09-03) can legitimately compute a healthy LIVE/STALE/
    // EMPTY state from within its own "terminal failure" logging branch and
    // still log its one-line diagnostic via console.error regardless -- see
    // verify_pages_fast_publish_smoke.js's identical, already-shipped fix for
    // the full root-cause writeup (confirmed live: this exact line fired
    // twice here, once at boot and once after the fullscreen/video
    // interactions above re-triggered the fetch chain, both with a healthy
    // LIVE state). Checked once here, after every interaction that could
    // have logged it, deferring to the app's own authoritative
    // window.__FEED_TERMINAL_STATE__.isTerminalFailure rather than guessing
    // from log text. A genuine terminal failure still fails this script.
    const termState = await page.evaluate(() => window.__FEED_TERMINAL_STATE__ || null).catch(() => null);
    if (termState && termState.isTerminalFailure === false) {
      const goc = 'console.error: [GOC v201.0] Primary feed terminal state:';
      for (let i = pageErrors.length - 1; i >= 0; i--) {
        if (pageErrors[i].startsWith(goc)) pageErrors.splice(i, 1);
      }
    }
    record('Zero uncaught JS errors / console errors across boot + all interactions', pageErrors.length === 0, pageErrors.join(' | '));

    // ── 7. #apex-lead-modal click-trap fix (discovered live while writing
    //      this script -- see the addInitScript comment above and this
    //      script's own commit for the Escape/backdrop-click dismissal
    //      added to index.html alongside it). Forces the modal open
    //      directly (bypassing its own timers/suppression, which are
    //      trigger-only -- classList itself doesn't check them) so this
    //      doesn't race real timing, then proves both new dismissal paths
    //      actually reach the same apexLeadDismiss() the [x] button uses. ──
    await page.evaluate(() => document.getElementById('apex-lead-modal').classList.add('open'));
    const modalOpen = await page.evaluate(() => document.getElementById('apex-lead-modal').classList.contains('open'));
    record('Lead modal opens (pre-condition for the two checks below)', modalOpen);

    await page.keyboard.press('Escape');
    const modalClosedByEscape = await page.evaluate(() => !document.getElementById('apex-lead-modal').classList.contains('open'));
    record('Lead modal dismisses on Escape (previously: no handler, modal was a permanent click-trap)', modalClosedByEscape);

    await page.evaluate(() => document.getElementById('apex-lead-modal').classList.add('open'));
    // Click the backdrop itself, not the centered .apex-lead-box content --
    // top-left corner of a position:fixed;inset:0 element is always outside
    // the box's max-width:480px centered card.
    await page.mouse.click(5, 5);
    const modalClosedByBackdrop = await page.evaluate(() => !document.getElementById('apex-lead-modal').classList.contains('open'));
    record('Lead modal dismisses on a backdrop click (previously: no handler, modal was a permanent click-trap)', modalClosedByBackdrop);

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
