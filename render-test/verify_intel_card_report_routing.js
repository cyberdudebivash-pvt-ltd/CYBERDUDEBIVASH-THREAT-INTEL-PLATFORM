#!/usr/bin/env node
/**
 * SENTINEL APEX — Intel Card Report-Routing Regression Test (v186.0 P0 fix,
 * updated v187.0 P0 fix)
 * ====================================================================
 * Real-browser (headless Chromium) verification that a Threat Intel Card's
 * "view report" link ALWAYS points at the actual report page
 * (/reports/{yyyy}/{mm}/{stix_id}.html) and NEVER at /upgrade.html directly.
 *
 * Root cause covered (v186.0): index.html has three independent card
 * renderers (renderCards -- primary; cdbGodModeRender -- bulletproof
 * fallback used when renderCards() throws or leaves #threat-grid empty;
 * renderTopThreats -- the SOC Priority Feed widget). cdbGodModeRender used
 * to gate its own report link by client-side tier state, sending free-tier
 * users straight to /upgrade.html with no way to read the (always-reachable,
 * server-side masked) report. All three now call the single canonical
 * cdbBuildReportUrl() helper for link construction.
 *
 * Root cause covered (v187.0): cdbBuildReportUrl() used to fabricate a
 * `/reports/{yyyy}/{mm}/{stix_id}.html` URL from stix_id + published_at
 * whenever the backend hadn't supplied report_url/internal_report_url --
 * indistinguishable, client-side, between "not yet synced" and
 * "permanently rejected by the publication gate" (verified live: both
 * shapes have report_url:null). This produced customer-visible 404s for
 * every gate-rejected item. The helper now returns '' in that case, and
 * every caller must render a non-link "processing" state instead of
 * guessing a URL. This file's assertions were updated accordingly: a
 * fabricated /reports/ href for an UNVERIFIED item is now a FAILURE, not
 * a pass condition.
 *
 * This test exercises each renderer directly via page.evaluate() against
 * controlled mock items (one UNVERIFIED -- no report_url/internal_report_url
 * at all; one VERIFIED -- backend-confirmed report_url set), rather than
 * trying to force renderCards() to fail (which is inherently
 * non-deterministic) -- it verifies the fix at the actual site of the
 * regression: the link-building contract itself.
 *
 * Also covers the second, independent card-rendering system
 * (js/card_renderer.js + js/card_renderer_integration.js + js/api_adapter.js,
 * rendering into #sapx-card-grid): confirms api_adapter.js now parses
 * /api/feed.json's plain-items envelope (not only /api/preview's
 * data.preview.items shape), and that card_renderer.js's report link
 * reuses the same cdbBuildReportUrl() helper instead of only trusting
 * item.report_url, so this second system can no longer show a card with
 * no path to the report either.
 *
 * Self-contained: starts a local static file server rooted at the repo
 * root (so root-relative hrefs resolve exactly as they do in production),
 * intercepts /api/* and cross-origin requests so the page's real bootstrap
 * fetches fail fast instead of hitting the network, then shuts down --
 * no external services, no fixtures to maintain.
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node render-test/verify_intel_card_report_routing.js
 *
 * Exit code 0 = all checks passed. Exit code 1 = at least one failed.
 */
'use strict';

const path = require('path');
const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright');

const REPO_ROOT = path.resolve(__dirname, '..');
const PORT = 8944;
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
    if (!filePath.startsWith(REPO_ROOT)) { res.writeHead(403); res.end(); return; }
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

// UNVERIFIED item: has a stix_id and a published date, but deliberately NO
// report_url / internal_report_url -- this is exactly the shape a
// permanently gate-rejected item has (verified live against production:
// REJECTED items and still-pending items are indistinguishable at this
// field), so the client must NEVER guess a report link for it.
const MOCK_ITEM = {
  stix_id: 'intel--test0000000000000000000000000000',
  title: 'Regression Test Advisory — CVE-2099-00001',
  risk_score: 8.7,
  severity: 'HIGH',
  cvss_score: 8.8,
  epss_score: 12.4,
  confidence_score: 72,
  actor_tag: 'UNC-UNKNOWN',
  published_at: '2026-07-28T00:00:00Z',
  timestamp: '2026-07-28T00:00:00Z',
  processed_at: '2026-07-28T00:00:00Z',
  source_url: 'https://example.com/original-article',
  mitre_tactics: ['T1566'],
  ioc_count: 3,
};

// The fabricated path the old (buggy) cdbBuildReportUrl() would have
// guessed for MOCK_ITEM. Used to assert this exact URL is NEVER produced.
const FABRICATED_URL_FOR_MOCK_ITEM = '/reports/2026/07/intel--test0000000000000000000000000000.html';

// VERIFIED item: identical shape, but carries a backend-confirmed
// report_url -- the positive-path counterpart, proving the fix didn't
// regress real, published reports.
const VERIFIED_ITEM = Object.assign({}, MOCK_ITEM, {
  stix_id: 'intel--verified000000000000000000000000',
  report_url: '/reports/2026/07/intel--verified000000000000000000000000.html',
});

function collectHrefs(html) {
  const hrefs = [];
  const re = /href="([^"]*)"/g;
  let m;
  while ((m = re.exec(html))) hrefs.push(m[1]);
  return hrefs;
}

async function main() {
  const server = await startStaticServer();
  let browser;
  let exitCode = 0;
  try {
    browser = await chromium.launch();
    const context = await browser.newContext();

    // Block real network calls (API bootstrap, CDN, analytics) so the test
    // is hermetic and fast -- we only need the page's own function
    // definitions, not a successful live data load.
    await context.route('**/*', (route) => {
      const url = route.request().url();
      if (url.startsWith(`http://127.0.0.1:${PORT}/`)) return route.continue();
      return route.abort();
    });

    const consoleErrors = [];
    const page = await context.newPage();
    page.on('pageerror', (err) => consoleErrors.push(String(err)));
    await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded' });
    // Give inline bootstrap scripts a moment to define all functions;
    // we deliberately don't wait for 'networkidle' since API calls are
    // intercepted/aborted above and would never settle.
    await page.waitForTimeout(1500);

    // --- 0. Canonical helper: '' when unverified, real URL when verified ---
    const helperUnverified = await page.evaluate((item) => {
      try {
        if (typeof window.cdbBuildReportUrl !== 'function') return { ok: false, error: 'cdbBuildReportUrl is not defined on window' };
        return { ok: true, url: window.cdbBuildReportUrl(item) };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, MOCK_ITEM);
    record(
      'cdbBuildReportUrl() returns \'\' (no fabricated URL) for an item with no report_url/internal_report_url',
      helperUnverified.ok && helperUnverified.url === '',
      JSON.stringify(helperUnverified)
    );

    const helperVerified = await page.evaluate((item) => {
      try {
        if (typeof window.cdbBuildReportUrl !== 'function') return { ok: false, error: 'cdbBuildReportUrl is not defined on window' };
        return { ok: true, url: window.cdbBuildReportUrl(item) };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, VERIFIED_ITEM);
    record(
      'cdbBuildReportUrl() returns the backend-confirmed report_url unchanged when present',
      helperVerified.ok && helperVerified.url === VERIFIED_ITEM.report_url,
      JSON.stringify(helperVerified)
    );

    // --- 1. cdbGodModeRender (the fallback that had the v186.0 P0 bug) ---
    for (const tier of ['free', 'pro']) {
      const godModeUnverified = await page.evaluate(({ item, tier }) => {
        try {
          if (typeof window.cdbGodModeRender !== 'function') return { ok: false, error: 'cdbGodModeRender is not defined on window' };
          const grid = document.getElementById('threat-grid');
          if (!grid) return { ok: false, error: '#threat-grid not found in DOM' };
          window._platformTiers = { current: tier };
          grid.innerHTML = '';
          window.cdbGodModeRender([item]);
          return { ok: true, html: grid.innerHTML };
        } catch (e) { return { ok: false, error: String(e) }; }
      }, { item: MOCK_ITEM, tier });

      if (!godModeUnverified.ok) {
        record(`cdbGodModeRender() renders without throwing (tier=${tier}, unverified)`, false, godModeUnverified.error);
      } else {
        const hrefs = collectHrefs(godModeUnverified.html);
        const hitsUpgrade = hrefs.some((h) => h.includes('/upgrade.html'));
        const hitsFabricated = hrefs.includes(FABRICATED_URL_FOR_MOCK_ITEM);
        record(
          `cdbGodModeRender() fallback card NEVER links to /upgrade.html (tier=${tier}, unverified)`,
          !hitsUpgrade,
          `hrefs found: ${JSON.stringify(hrefs)}`
        );
        record(
          `cdbGodModeRender() fallback card NEVER fabricates a /reports/ URL for an unverified item (tier=${tier})`,
          !hitsFabricated,
          `hrefs found: ${JSON.stringify(hrefs)}`
        );
      }

      const godModeVerified = await page.evaluate(({ item, tier }) => {
        try {
          if (typeof window.cdbGodModeRender !== 'function') return { ok: false, error: 'cdbGodModeRender is not defined on window' };
          const grid = document.getElementById('threat-grid');
          if (!grid) return { ok: false, error: '#threat-grid not found in DOM' };
          window._platformTiers = { current: tier };
          grid.innerHTML = '';
          window.cdbGodModeRender([item]);
          return { ok: true, html: grid.innerHTML };
        } catch (e) { return { ok: false, error: String(e) }; }
      }, { item: VERIFIED_ITEM, tier });

      if (!godModeVerified.ok) {
        record(`cdbGodModeRender() renders without throwing (tier=${tier}, verified)`, false, godModeVerified.error);
      } else {
        const hrefs = collectHrefs(godModeVerified.html);
        const hitsUpgrade = hrefs.some((h) => h.includes('/upgrade.html'));
        const hitsRealReport = hrefs.includes(VERIFIED_ITEM.report_url);
        record(
          `cdbGodModeRender() links to the real, backend-confirmed report (tier=${tier}, verified)`,
          hitsRealReport,
          `hrefs found: ${JSON.stringify(hrefs)}`
        );
        record(
          `cdbGodModeRender() still never links to /upgrade.html for a verified item (tier=${tier})`,
          !hitsUpgrade,
          `hrefs found: ${JSON.stringify(hrefs)}`
        );
      }
    }

    // --- 2. renderCards (the primary renderer) -- ".card-link" CTA -------
    // Reads the specific "view report" CTA (class="card-link") via a real
    // DOM query, not the whole card -- a card legitimately carries OTHER,
    // separate upsell links (e.g. the IOC-count banner's "UNLOCK ->") that
    // intentionally point at /upgrade.html as a supplementary cross-sell
    // and are not the bug in question. What must never happen is the
    // PRIMARY "view report" action routing to a bare paywall OR a
    // fabricated report URL that 404s.
    const primaryUnverified = await page.evaluate((item) => {
      try {
        if (typeof window.renderCards !== 'function') return { ok: false, error: 'renderCards is not defined on window' };
        const grid = document.getElementById('threat-grid');
        if (!grid) return { ok: false, error: '#threat-grid not found in DOM' };
        grid.innerHTML = '';
        window.renderCards([item]);
        const cardLinkEl = grid.querySelector('.card-link');
        return {
          ok: true,
          cardLinkHref: cardLinkEl ? cardLinkEl.getAttribute('href') : null,
          cardLinkFound: !!cardLinkEl,
        };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, MOCK_ITEM);

    if (!primaryUnverified.ok) {
      record('renderCards() (primary) renders without throwing (unverified)', false, primaryUnverified.error);
    } else {
      const href = primaryUnverified.cardLinkHref || '';
      record('renderCards() (primary) ".card-link" CTA is present for an unverified item (safe fallback: modal or source link)', primaryUnverified.cardLinkFound, `found=${primaryUnverified.cardLinkFound}`);
      record('renderCards() (primary) "view report" CTA never links to /upgrade.html (unverified)', !href.includes('/upgrade.html'), `href="${href}"`);
      record('renderCards() (primary) "view report" CTA never fabricates the guessed /reports/ URL (unverified)', href !== FABRICATED_URL_FOR_MOCK_ITEM, `href="${href}"`);
    }

    const primaryVerified = await page.evaluate((item) => {
      try {
        if (typeof window.renderCards !== 'function') return { ok: false, error: 'renderCards is not defined on window' };
        const grid = document.getElementById('threat-grid');
        if (!grid) return { ok: false, error: '#threat-grid not found in DOM' };
        grid.innerHTML = '';
        window.renderCards([item]);
        const cardLinkEl = grid.querySelector('.card-link');
        return {
          ok: true,
          cardLinkHref: cardLinkEl ? cardLinkEl.getAttribute('href') : null,
          cardLinkFound: !!cardLinkEl,
        };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, VERIFIED_ITEM);

    if (!primaryVerified.ok) {
      record('renderCards() (primary) renders without throwing (verified)', false, primaryVerified.error);
    } else {
      const href = primaryVerified.cardLinkHref || '';
      record('renderCards() (primary) "view report" CTA links to the real, backend-confirmed report (verified)', href === VERIFIED_ITEM.report_url, `href="${href}"`);
    }

    // --- 3. renderTopThreats: ranks 1-3 (the only individually-clickable
    // cards this widget renders) must link to the real report when
    // verified, and show a non-link "PROCESSING" state -- never a
    // fabricated link -- when unverified. Ranks 4-10 are NOT rendered as
    // individual clickable cards at all -- they're represented by a single
    // shared "N HIGH-RISK THREATS LOCKED" teaser banner (documented in-code
    // as "FREE TIER: 3 Threats visible"), a different, intentional
    // leaderboard-teaser UX pattern, not the per-card routing bug this test
    // guards against. We only pin down that the teaser banner itself still
    // exists, not that it disappear.
    const topThreatsUnverified = await page.evaluate((item) => {
      try {
        if (typeof window.renderTopThreats !== 'function') return { ok: false, error: 'renderTopThreats is not defined on window' };
        const section = document.getElementById('top-threats-section');
        if (!section) return { ok: false, error: '#top-threats-section not found in DOM' };
        const items = Array.from({ length: 10 }, (_, i) => ({
          ...item,
          stix_id: `${item.stix_id}-${i}`,
          risk_score: 9 - i * 0.3,
        }));
        section.innerHTML = '';
        window.renderTopThreats(items);
        return { ok: true, html: section.innerHTML, text: section.textContent };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, MOCK_ITEM);

    if (!topThreatsUnverified.ok) {
      record('renderTopThreats() renders without throwing (unverified)', false, topThreatsUnverified.error);
    } else {
      const hrefs = collectHrefs(topThreatsUnverified.html);
      const reportHrefs = hrefs.filter((h) => h.startsWith('reports/') || h.startsWith('/reports/'));
      record(
        'renderTopThreats() ranks #1-3 NEVER show a fabricated/guessed report link when unverified (v187.0 P0 fix)',
        reportHrefs.length === 0,
        `report-like hrefs found (expected none): ${JSON.stringify(reportHrefs)}`
      );
      const processingCount = (topThreatsUnverified.text.match(/PROCESSING/g) || []).length;
      record(
        'renderTopThreats() ranks #1-3 show the "PROCESSING" state instead of "FULL INTEL" when unverified',
        processingCount >= 3,
        `PROCESSING occurrences: ${processingCount}`
      );
      record(
        'renderTopThreats() still shows the documented ranks #4-10 teaser banner (unrelated leaderboard-gate pattern, not this P0)',
        /HIGH-RISK THREATS LOCKED/.test(topThreatsUnverified.text || ''),
        'banner text present: ' + /HIGH-RISK THREATS LOCKED/.test(topThreatsUnverified.text || '')
      );
    }

    const topThreatsVerified = await page.evaluate((item) => {
      try {
        if (typeof window.renderTopThreats !== 'function') return { ok: false, error: 'renderTopThreats is not defined on window' };
        const section = document.getElementById('top-threats-section');
        if (!section) return { ok: false, error: '#top-threats-section not found in DOM' };
        const items = Array.from({ length: 10 }, (_, i) => ({
          ...item,
          stix_id: `${item.stix_id}-${i}`,
          report_url: item.report_url,
          risk_score: 9 - i * 0.3,
        }));
        section.innerHTML = '';
        window.renderTopThreats(items);
        return { ok: true, html: section.innerHTML, text: section.textContent };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, VERIFIED_ITEM);

    if (!topThreatsVerified.ok) {
      record('renderTopThreats() renders without throwing (verified)', false, topThreatsVerified.error);
    } else {
      const hrefs = collectHrefs(topThreatsVerified.html);
      const reportHrefs = hrefs.filter((h) => h === VERIFIED_ITEM.report_url);
      record(
        'renderTopThreats() ranks #1-3 link to the real report when verified',
        reportHrefs.length >= 3,
        `matching report hrefs found: ${reportHrefs.length}`
      );
      record(
        'renderTopThreats() ranks #1-3 do NOT show "PROCESSING" when a verified report link exists',
        !/PROCESSING/.test(topThreatsVerified.text || ''),
        'PROCESSING text present: ' + /PROCESSING/.test(topThreatsVerified.text || '')
      );
    }

    // --- 4. #sapx-card-grid system (card_renderer.js / card_renderer_integration.js
    // / api_adapter.js) -- a second, independent card-rendering system that used
    // to hardcode /api/preview (always free-tier-masked by Worker design, per
    // its own doc comment) with no report-link fallback, guaranteeing a
    // dead-end paywall for 100% of visitors. Now: (a) api_adapter.js parses
    // /api/feed.json's plain-array/plain-items envelope, not only /api/preview's
    // data.preview.items shape; (b) card_renderer.js's report link reuses the
    // same cdbBuildReportUrl() helper instead of only trusting item.report_url.
    // v187.0: since cdbBuildReportUrl() no longer fabricates a URL, an
    // unverified item now safely renders NO "VIEW REPORT" CTA at all rather
    // than a link that would 404 -- this is the correct, safe behavior (no
    // dead-end navigation), not a regression.
    const sapxAdapterResult = await page.evaluate(() => {
      try {
        if (typeof window.SentinelApexAdapter !== 'object') return { ok: false, error: 'SentinelApexAdapter is not defined on window' };
        // Shape as returned by /api/feed.json: plain { items: [...] }, NOT
        // wrapped in { preview: { items: [...] } } like /api/preview.
        const feedJsonShape = { items: [{ stix_id: 'intel--feedjson-shape-test', title: 'Feed JSON shape test', severity: 'HIGH', risk_score: 7.5 }], generated_at: '2026-07-28T00:00:00Z' };
        const normalized = window.SentinelApexAdapter.normalizeApiResponse(feedJsonShape);
        return { ok: true, itemCount: normalized.items.length, firstId: normalized.items[0] && normalized.items[0].stix_id };
      } catch (e) { return { ok: false, error: String(e) }; }
    });
    record(
      'api_adapter.js normalizeApexResponse() correctly parses /api/feed.json\'s plain-items envelope (not just /api/preview\'s data.preview.items)',
      sapxAdapterResult.ok && sapxAdapterResult.itemCount === 1 && sapxAdapterResult.firstId === 'intel--feedjson-shape-test',
      JSON.stringify(sapxAdapterResult)
    );

    const sapxUnverified = await page.evaluate((item) => {
      try {
        if (typeof window.SentinelApexCardRenderer !== 'object') return { ok: false, error: 'SentinelApexCardRenderer is not defined on window' };
        if (typeof window.SentinelApexAdapter !== 'object') return { ok: false, error: 'SentinelApexAdapter is not defined on window' };
        const container = document.getElementById('sapx-card-grid');
        if (!container) return { ok: false, error: '#sapx-card-grid not found in DOM' };
        const normalizedItem = window.SentinelApexAdapter.normalizeIntelItem(item, 0);
        container.innerHTML = '';
        window.SentinelApexCardRenderer.renderGrid(container, [normalizedItem], { maxCards: 5 });
        return { ok: true, html: container.innerHTML };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, MOCK_ITEM);

    if (!sapxUnverified.ok) {
      record('SentinelApexCardRenderer.renderGrid() (#sapx-card-grid) renders without throwing (unverified)', false, sapxUnverified.error);
    } else {
      const hrefs = collectHrefs(sapxUnverified.html);
      const hitsFabricated = hrefs.includes(FABRICATED_URL_FOR_MOCK_ITEM);
      record(
        '#sapx-card-grid card NEVER shows a fabricated "VIEW REPORT" link when report_url is empty (v187.0 P0 fix)',
        !hitsFabricated,
        `hrefs found: ${JSON.stringify(hrefs)}`
      );
    }

    const sapxVerified = await page.evaluate((item) => {
      try {
        if (typeof window.SentinelApexCardRenderer !== 'object') return { ok: false, error: 'SentinelApexCardRenderer is not defined on window' };
        if (typeof window.SentinelApexAdapter !== 'object') return { ok: false, error: 'SentinelApexAdapter is not defined on window' };
        const container = document.getElementById('sapx-card-grid');
        if (!container) return { ok: false, error: '#sapx-card-grid not found in DOM' };
        const normalizedItem = window.SentinelApexAdapter.normalizeIntelItem(item, 0);
        container.innerHTML = '';
        window.SentinelApexCardRenderer.renderGrid(container, [normalizedItem], { maxCards: 5 });
        return { ok: true, html: container.innerHTML };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, VERIFIED_ITEM);

    if (!sapxVerified.ok) {
      record('SentinelApexCardRenderer.renderGrid() (#sapx-card-grid) renders without throwing (verified)', false, sapxVerified.error);
    } else {
      const hrefs = collectHrefs(sapxVerified.html);
      const hitsReport = hrefs.includes(VERIFIED_ITEM.report_url);
      record(
        '#sapx-card-grid card gets a working "VIEW REPORT" link to the real report when verified',
        hitsReport,
        `hrefs found: ${JSON.stringify(hrefs)}`
      );
    }

    const knownPreexistingErrors = consoleErrors.filter((e) =>
      /Unexpected number|_hEsc is not defined/.test(e)
    );
    const unexpectedErrors = consoleErrors.filter((e) => !knownPreexistingErrors.includes(e));
    if (knownPreexistingErrors.length) {
      console.log(`[INFO] ${knownPreexistingErrors.length} known pre-existing, unrelated page error(s) observed (see FORENSIC-AUDIT note in PR description) -- not counted against this test: ${JSON.stringify(knownPreexistingErrors)}`);
    }
    record('No NEW/unexpected uncaught page errors during test run', unexpectedErrors.length === 0, unexpectedErrors.join(' | '));

    await context.close();
  } finally {
    if (browser) await browser.close();
    server.close();
  }

  const failed = results.filter((r) => !r.pass);
  console.log('\n' + '='.repeat(64));
  console.log(`SUMMARY: ${results.length - failed.length}/${results.length} checks passed`);
  console.log('='.repeat(64));
  if (failed.length) {
    exitCode = 1;
    console.log('FAILED CHECKS:');
    for (const f of failed) console.log(`  - ${f.name}: ${f.detail}`);
  }
  process.exitCode = exitCode;
}

main().catch((err) => {
  console.error('[FATAL]', err);
  process.exitCode = 1;
});
