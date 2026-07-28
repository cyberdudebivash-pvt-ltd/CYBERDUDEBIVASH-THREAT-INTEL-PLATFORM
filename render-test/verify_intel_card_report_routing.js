#!/usr/bin/env node
/**
 * SENTINEL APEX — Intel Card Report-Routing Regression Test (v186.0 P0 fix)
 * ====================================================================
 * Real-browser (headless Chromium) verification that a Threat Intel Card's
 * "view report" link ALWAYS points at the actual report page
 * (/reports/{yyyy}/{mm}/{stix_id}.html) and NEVER at /upgrade.html directly.
 *
 * Root cause covered: index.html has three independent card renderers
 * (renderCards -- primary; cdbGodModeRender -- bulletproof fallback used
 * when renderCards() throws or leaves #threat-grid empty; renderTopThreats
 * -- the SOC Priority Feed widget). cdbGodModeRender used to gate its own
 * report link by client-side tier state, sending free-tier users straight
 * to /upgrade.html with no way to read the (always-reachable, server-side
 * masked) report. All three now call the single canonical
 * cdbBuildReportUrl() helper for link construction.
 *
 * This test exercises each renderer directly via page.evaluate() against
 * a controlled mock item, rather than trying to force renderCards() to
 * fail (which is inherently non-deterministic) -- it verifies the fix at
 * the actual site of the regression: the link-building contract itself.
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

// A minimal, representative FREE-tier item: has a stix_id and a published
// date, but deliberately NO report_url / internal_report_url -- this is
// exactly the shape that used to trip cdbGodModeRender's broken gate.
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

    // --- 0. Canonical helper exists and is tier-agnostic -----------------
    const helperResult = await page.evaluate((item) => {
      try {
        if (typeof window.cdbBuildReportUrl !== 'function') return { ok: false, error: 'cdbBuildReportUrl is not defined on window' };
        return { ok: true, url: window.cdbBuildReportUrl(item) };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, MOCK_ITEM);
    record(
      'cdbBuildReportUrl() is defined and returns the constructed /reports/ path',
      helperResult.ok && /^\/reports\/2026\/07\/intel--test0+\.html$/.test(helperResult.url || ''),
      JSON.stringify(helperResult)
    );

    // --- 1. cdbGodModeRender (the fallback that had the P0 bug) ----------
    for (const tier of ['free', 'pro']) {
      const godModeResult = await page.evaluate(({ item, tier }) => {
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

      if (!godModeResult.ok) {
        record(`cdbGodModeRender() renders without throwing (tier=${tier})`, false, godModeResult.error);
        continue;
      }
      const hrefs = collectHrefs(godModeResult.html);
      const hitsUpgrade = hrefs.some((h) => h.includes('/upgrade.html'));
      const hitsReport = hrefs.some((h) => h.startsWith('/reports/'));
      record(
        `cdbGodModeRender() fallback card NEVER links to /upgrade.html (tier=${tier})`,
        !hitsUpgrade,
        `hrefs found: ${JSON.stringify(hrefs)}`
      );
      record(
        `cdbGodModeRender() fallback card links to the real report (tier=${tier})`,
        hitsReport,
        `hrefs found: ${JSON.stringify(hrefs)}`
      );
    }

    // --- 2. renderCards (the primary renderer) still correct post-refactor ---
    // Reads the specific "view report" CTA (class="card-link") via a real
    // DOM query, not the whole card -- a card legitimately carries OTHER,
    // separate upsell links (e.g. the IOC-count banner's "UNLOCK ->") that
    // intentionally point at /upgrade.html as a supplementary cross-sell
    // and are not the bug in question. What must never happen is the
    // PRIMARY "view report" action routing to a bare paywall.
    const primaryResult = await page.evaluate((item) => {
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

    if (!primaryResult.ok) {
      record('renderCards() (primary) renders without throwing', false, primaryResult.error);
    } else {
      const href = primaryResult.cardLinkHref || '';
      record('renderCards() (primary) ".card-link" CTA is present', primaryResult.cardLinkFound, `found=${primaryResult.cardLinkFound}`);
      record('renderCards() (primary) "view report" CTA never links to /upgrade.html', !href.includes('/upgrade.html'), `href="${href}"`);
      record('renderCards() (primary) "view report" CTA links to the real report', href.startsWith('/reports/'), `href="${href}"`);
    }

    // --- 3. renderTopThreats: ranks 1-3 (the only individually-clickable
    // cards this widget renders) must link to the real report. Ranks 4-10
    // are NOT rendered as individual clickable cards at all -- they're
    // represented by a single shared "N HIGH-RISK THREATS LOCKED" teaser
    // banner (documented in-code as "FREE TIER: 3 Threats visible"), which
    // is a different, intentional leaderboard-teaser UX pattern, not the
    // per-card routing bug this test guards against. We only pin down that
    // the teaser banner itself still exists, not that it disappear.
    const topThreatsResult = await page.evaluate((item) => {
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

    if (!topThreatsResult.ok) {
      record('renderTopThreats() renders without throwing', false, topThreatsResult.error);
    } else {
      const hrefs = collectHrefs(topThreatsResult.html);
      const reportHrefs = hrefs.filter((h) => h.startsWith('reports/') || h.startsWith('/reports/'));
      record(
        'renderTopThreats() ranks #1-3 link to the real report',
        reportHrefs.length >= 3,
        `report-like hrefs found: ${JSON.stringify(reportHrefs)}`
      );
      record(
        'renderTopThreats() still shows the documented ranks #4-10 teaser banner (unrelated leaderboard-gate pattern, not this P0)',
        /HIGH-RISK THREATS LOCKED/.test(topThreatsResult.text || ''),
        'banner text present: ' + /HIGH-RISK THREATS LOCKED/.test(topThreatsResult.text || '')
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
