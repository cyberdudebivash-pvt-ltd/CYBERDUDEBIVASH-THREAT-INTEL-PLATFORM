// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Feed Item Lookup (pure module)
//
// Extracted into its own dependency-free file, same pattern as
// subscription-lifecycle.js/daily-quota.js/admin-cache-bust.js, so it is
// unit-testable under plain `node --test` without pulling in index.js's
// full import chain (pricing.js -> pricing-data.json fails Node's native
// ESM loader outside the wrangler/esbuild bundler -- see
// subscription-lifecycle.js's header comment for the full explanation).
//
// r2Get() has zero dependencies of its own (only env.INTEL_R2 + JSON.parse)
// and is used 23 times elsewhere in index.js; LATEST_JSON_KEY/
// LATEST_PRO_JSON_KEY similarly have other consumers (13/4 call sites).
// Moving their canonical definitions here and having index.js import them
// is a pure move -- same top-level names, same values, every existing call
// site resolves identically. index.js re-exports findItemBySlug unchanged
// for backward compatibility with any external importer (Principle 5).
// =============================================================================

export const LATEST_JSON_KEY     = "api/v1/intel/latest.json";
export const LATEST_PRO_JSON_KEY = "api/v1/intel/latest_pro.json"; // PRO/ENTERPRISE: includes report_url

// RX-PUB-A0.6C: last-resort fallback source, checked only when none of the
// four enriched feed products above resolve the slug. docs/RX_PUB_A0_6_
// PROOF_BEFORE_CHANGE.md's live evidence (2026-08-14): api/v1/intel/
// latest.json and api/feed.json are kept in sync with each other (472
// items each, identical population) by generate_api_manifests.py, but both
// are a smaller population than data/stix/feed_manifest.json (518 items) --
// the same in-window source scripts/generate_intel_reports.py's Zero-skip
// policy regenerates every run and scripts/r2_reports_verifier.py treats as
// authoritative. 69 confirmed real in-window reports were unresolvable
// through every one of the four sources above, and (per that fail-open gap)
// served straight from R2 with zero evaluatePublicationGate() evaluation.
// feed_manifest.json's leaner per-item schema (no precomputed P20-P26
// scores) is not a problem: evaluatePublicationGate() computes every score
// fresh from base content fields (title, description, severity, iocs, ttps,
// etc.) via the canonical engine functions -- it never reads a precomputed
// score off the item -- and fails CLOSED if any engine errors on a missing
// field, never open. Uploaded every run by scripts/r2_upload.py to this
// exact key (BUCKET_DATA, "intel/feed_manifest.json").
export const FEED_MANIFEST_FALLBACK_KEY = "intel/feed_manifest.json";

/**
 * @param {{INTEL_R2: {get: Function}}} env
 * @param {string} key
 * @returns {Promise<any|null>}
 */
export async function r2Get(env, key) {
  try {
    const obj = await env.INTEL_R2.get(key);
    if (!obj) return null;
    const text = await obj.text();
    if (!text || text.trim() === "") return null;
    return JSON.parse(text);
  } catch (_) { return null; }
}

/**
 * @param {{INTEL_R2: {get: Function}}} env
 * @param {string} slug
 * @returns {Promise<any|null>}
 */
export async function findItemBySlug(env, slug) {
  const sources = [
    LATEST_PRO_JSON_KEY,
    LATEST_JSON_KEY,
    "api/v1/intel/top10.json",
    "api/v1/intel/apex.json",
    FEED_MANIFEST_FALLBACK_KEY,
  ];
  for (const key of sources) {
    try {
      const data = await r2Get(env, key);
      if (!data) continue;
      const items = Array.isArray(data) ? data : (data.items || data.data || []);
      const found = items.find(i => {
        const id = (i.stix_id || i.id || "").replace(/\.html?$/, "");
        return id === slug || id === `intel--${slug}` ||
               slug === id || slug.startsWith(id) || id.startsWith(slug);
      });
      if (found) return found;
    } catch (_) { /* continue to next source */ }
  }
  return null;
}
