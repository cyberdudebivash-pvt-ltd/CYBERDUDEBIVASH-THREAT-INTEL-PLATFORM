// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- TAXII 2.1 Collection Registry & Pagination
// (pure module)
//
// The real TAXII 2.1 server this extends already lives in index.js
// (handleTAXII, "NEW v184.0") at /taxii/ -- discovery, two collections
// (sentinel-apex-main, sentinel-apex-kev), PRO/ENTERPRISE gating via
// resolveEntitlement(), R2 pre-built-bundle-first with an inline STIX
// fallback. That implementation is NOT duplicated here: this file only
// adds the net-new pieces requested (more collections, added_after/limit/
// next pagination, a real "upgrade" payload for under-tier callers) as
// pure, unit-testable functions index.js's existing handleTAXII calls
// into -- same extraction pattern as daily-quota.js/feeds.js/feed-
// lookup.js, and for the same reason: index.js's import chain pulls in
// pricing.js -> pricing-data.json, which Node's native ESM loader (used by
// `node --test`) rejects outside the wrangler/esbuild bundler.
//
// Collection ids sentinel-apex-main and sentinel-apex-kev are NOT renamed
// or removed here (Principle 5, backward compatibility) -- three new
// collection ids are added alongside them. c2-indicators/active-ransomware/
// apt-attribution are additive filtered views over the exact same
// loadFeedItems(env) source index.js already reads for /api/feed, /feeds/*
// and the existing two TAXII collections -- one feed, five views, not a
// second data source.
// =============================================================================

/**
 * Registry of every TAXII collection this server exposes. `minTier` is the
 * lowest auth.tier that can read it (checked by index.js via
 * resolveEntitlement(), which this file does not call -- it has no ctx/env
 * dependency by design). PRO already gates the whole /taxii/ surface
 * (existing behavior, unchanged); ENTERPRISE gates the two highest-value
 * collections (KEV-confirmed exploits, APT attribution), matching the
 * existing KEV-collection precedent exactly.
 */
export const TAXII_COLLECTIONS = [
  {
    id: "sentinel-apex-main",
    title: "SENTINEL APEX - Primary Threat Intelligence",
    description: "CVEs, IOCs, APT activity, ransomware alerts, dark web findings",
    minTier: "PRO",
  },
  {
    id: "sentinel-apex-kev",
    title: "SENTINEL APEX - CISA KEV Confirmed",
    description: "Known Exploited Vulnerabilities confirmed in CISA KEV catalog (ENTERPRISE only)",
    minTier: "ENTERPRISE",
  },
  {
    id: "c2-indicators",
    title: "SENTINEL APEX - Active C2 Indicators",
    description: "Indicators tied to active malicious infrastructure (malware, ransomware, APT, phishing, DDoS, supply-chain) -- same classification as the public /feeds/active-c2-ips.txt teaser, full STIX detail",
    minTier: "PRO",
  },
  {
    id: "active-ransomware",
    title: "SENTINEL APEX - Active Ransomware",
    description: "Items classified Ransomware or attributed to a tracked ransomware operator",
    minTier: "PRO",
  },
  {
    id: "apt-attribution",
    title: "SENTINEL APEX - APT Attribution",
    description: "Items classified APT or attributed to a tracked nation-state/APT actor (ENTERPRISE only)",
    minTier: "ENTERPRISE",
  },
];

const TIER_RANK = { FREE: 0, PRO: 1, ENTERPRISE: 2, MSSP: 2 };

/** Whether `tier` clears a collection's minTier requirement. */
export function tierMeetsCollection(tier, collection) {
  const rank = TIER_RANK[tier] ?? 0;
  const need = TIER_RANK[collection.minTier] ?? 0;
  return rank >= need;
}

export function findCollection(collId) {
  return TAXII_COLLECTIONS.find((c) => c.id === collId) || null;
}

/**
 * Filters the platform's real feed items down to one TAXII collection's
 * scope. sentinel-apex-main/sentinel-apex-kev reproduce index.js's
 * pre-existing inline logic exactly (all items / kev_present-only) so
 * switching index.js to call this changes zero existing output.
 */
export function filterItemsForCollection(items, collId) {
  switch (collId) {
    case "sentinel-apex-kev":
      return items.filter((i) => i.kev_present);
    case "c2-indicators": {
      // Local copy of feeds.js's C2_THREAT_TYPES membership test -- kept as
      // a plain string-set check here (not an import) so this module has
      // zero cross-file coupling beyond loadFeedItems' item shape; the
      // exported C2_THREAT_TYPES in feeds.js is the source of truth index.js
      // itself passes through when it wires the two together.
      return items.filter((i) => i._c2Eligible);
    }
    case "active-ransomware":
      return items.filter((i) => i.threat_type === "Ransomware" || /^CDB-RAN-/.test(i.actor_tag || ""));
    case "apt-attribution":
      return items.filter((i) => i.threat_type === "APT" || /^CDB-APT-/.test(i.actor_tag || ""));
    case "sentinel-apex-main":
    default:
      return items;
  }
}

/**
 * Marks each item with whether it qualifies for the c2-indicators
 * collection, using the SAME C2_THREAT_TYPES set feeds.js exports (passed
 * in by index.js, which already imports it) -- avoids this pure module
 * importing feeds.js directly (keeping both independently unit-testable
 * with no import-order coupling) while guaranteeing one classification.
 * @param {Array<object>} items
 * @param {Set<string>} c2ThreatTypes
 * @returns {Array<object>} same items, each with a non-enumerable-free
 *   `_c2Eligible` boolean added (shallow-copied, originals untouched)
 */
export function tagC2Eligibility(items, c2ThreatTypes) {
  return items.map((i) => ({ ...i, _c2Eligible: c2ThreatTypes.has(i.threat_type) }));
}

// -- Pagination ---------------------------------------------------------------
// TAXII 2.1 (S3.1) objects endpoints accept added_after (RFC 3339 timestamp,
// only objects added after it) and limit (page size), and return an opaque
// `next` token the client echoes back on the following request. The prior
// implementation had none of this -- a hard `.slice(0, 200)` cap with no way
// to reach anything beyond it. Cursor is a plain base64 offset: nothing
// sensitive in it (just a position in an already-authorized result set), so
// an opaque-but-not-cryptographic token matches the spec's requirement
// without inventing signed-cursor infrastructure this single index doesn't need.

const DEFAULT_PAGE_LIMIT = 100;
const MAX_PAGE_LIMIT = 500;

// btoa/atob (Web-standard globals, available in both the Workers runtime
// and Node >=16 under `node --test`) -- not Buffer, which is Node-only and
// unavailable in production without the nodejs_compat flag this project
// does not set. Same base64url encoding index.js's own b64url() already
// uses for JWTs (index.js:254).
export function encodeCursor(offset) {
  return btoa(String(Math.max(0, offset | 0))).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

export function decodeCursor(token) {
  if (!token) return 0;
  try {
    const n = parseInt(atob(String(token).replace(/-/g, "+").replace(/_/g, "/")), 10);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

/**
 * Applies added_after + cursor + limit to a list of already-collection-
 * filtered feed items (pre-STIX-conversion), returning the page plus
 * pagination metadata. index.js converts `page` to STIX objects same as
 * before; this function only decides which items are on this page.
 * @param {Array<object>} items - collection-filtered feed items, each with
 *   a `published` (or `published_at`/`timestamp`) field usable as its
 *   TAXII "date added"
 * @param {{addedAfter?: string, limit?: string|number, cursor?: string}} params
 */
export function paginateFeedItems(items, { addedAfter, limit, cursor } = {}) {
  let pool = items;
  if (addedAfter) {
    const cutoff = Date.parse(addedAfter);
    if (Number.isFinite(cutoff)) {
      pool = pool.filter((i) => {
        const added = Date.parse(i.published || i.published_at || i.timestamp || 0);
        return Number.isFinite(added) && added > cutoff;
      });
    }
  }

  // parseInt(limit) || DEFAULT would silently treat an explicit `?limit=0`
  // as "not provided" (0 is falsy) instead of clamping it to 1 like every
  // other out-of-range value -- checked with Number.isFinite instead so
  // only a genuinely missing/unparseable limit falls back to the default.
  const parsedLimit = parseInt(limit, 10);
  const requestedLimit = Number.isFinite(parsedLimit) ? parsedLimit : DEFAULT_PAGE_LIMIT;
  const pageSize = Math.min(MAX_PAGE_LIMIT, Math.max(1, requestedLimit));
  const offset = decodeCursor(cursor);
  const page = pool.slice(offset, offset + pageSize);
  const more = offset + pageSize < pool.length;

  return { page, more, next: more ? encodeCursor(offset + pageSize) : null, total: pool.length };
}

// -- Access-denied payload ------------------------------------------------

/**
 * JSON body + companion headers for a TAXII request an authenticated-but-
 * under-tier key (or a request with no credentials at all) cannot access.
 * A real, provisioned FREE/Community key (auth.key is set) is distinct
 * from "no credentials presented" (auth.key is null): callers with an
 * actual key get 403 Forbidden ("you are who you say, that's not enough"),
 * bare requests get 401 Unauthorized ("who are you") -- index.js decides
 * which status to use; this only builds the shared body.
 * @param {{id:string, title:string, minTier:string}} collection
 * @param {string} upgradeUrl - from billing-checkout.js's resolveCheckoutUrl()
 */
export function buildTaxiiUpgradeBody(collection, upgradeUrl) {
  return {
    title: "Forbidden",
    description: collection
      ? `Collection '${collection.id}' requires ${collection.minTier}. POST your api_key to /auth/login for a JWT, or upgrade below.`
      : `TAXII data endpoints require PRO or ENTERPRISE tier. POST your api_key to /auth/login for a JWT, or upgrade below.`,
    required_tier: collection ? collection.minTier : "PRO",
    upgrade_url: upgradeUrl,
  };
}
