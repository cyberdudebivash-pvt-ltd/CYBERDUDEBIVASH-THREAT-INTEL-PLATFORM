// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- GET /reports/sitemap.xml (2026-09-27)
// -----------------------------------------------------------------------------
// The static sitemaps listed 2 report pages while the Worker serves every
// published report at /reports/YYYY/MM/<id>.html from REPORTS_R2. This module
// turns the certified, customer-ready report catalog -- the same list
// /api/reports/index.json serves, from buildCertifiedReportsFeed() in
// index.js -- into a sitemaps.org urlset, so search engines discover each new
// report as it publishes. Only CUSTOMER_READY reports are listed: a withheld
// report returns 404 from /reports/**, and a sitemap must not list 404s.
//
// The sitemap lives under /reports/, so it may only list /reports/ URLs
// (sitemaps.org location rule) -- which is exactly what it lists. Dependency-
// free so __tests__/reports-sitemap.test.js can import it under node --test.
// =============================================================================

export const SITE_ORIGIN = "https://intel.cyberdudebivash.com";
export const MAX_SITEMAP_URLS = 50000;  // sitemaps.org per-file limit

// Same slug shape the /reports/** handler accepts (canonicalSlugMatch).
const REPORT_PATH_RE = /^\/reports\/\d{4}\/\d{2}\/intel--[A-Za-z0-9_-]+\.html$/;

function xmlEscape(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}

/** The report's site path, or null when it is not a servable report URL. */
export function reportPath(entry) {
  if (!entry || typeof entry !== "object") return null;
  let p = typeof entry.path === "string" ? entry.path : "";
  if (!p && typeof entry.url === "string") {
    try {
      const u = new URL(entry.url);
      if (u.origin === SITE_ORIGIN) p = u.pathname;
    } catch (_) { /* not a URL */ }
  }
  return REPORT_PATH_RE.test(p) ? p : null;
}

/** YYYY-MM-DD (W3C date) of the report's timestamp, or null. */
export function lastmodOf(entry) {
  const t = Date.parse(entry && entry.timestamp ? String(entry.timestamp) : "");
  return Number.isNaN(t) ? null : new Date(t).toISOString().slice(0, 10);
}

/** sitemaps.org urlset for the given catalog entries (deduplicated, capped). */
export function buildReportsSitemapXml(reports) {
  const seen = new Set();
  const lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ];
  for (const entry of Array.isArray(reports) ? reports : []) {
    if (seen.size >= MAX_SITEMAP_URLS) break;
    const p = reportPath(entry);
    if (!p || seen.has(p)) continue;
    seen.add(p);
    const lastmod = lastmodOf(entry);
    lines.push("  <url><loc>" + xmlEscape(SITE_ORIGIN + p) + "</loc>"
      + (lastmod ? "<lastmod>" + lastmod + "</lastmod>" : "") + "</url>");
  }
  lines.push("</urlset>");
  return lines.join("\n") + "\n";
}
