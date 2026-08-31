// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Public Lead-Magnet Feeds (pure module)
//
// GET /feeds/active-c2-ips.txt, /feeds/ransomware-domains.txt,
// /feeds/cve-exploited-summary.json -- free, unauthenticated feeds that
// double as an upgrade funnel (embedded conversion banner) for security
// engineers who find them while configuring firewall/EDR block rules.
//
// Pure computation only, no KV/R2/network of its own -- same pattern as
// daily-quota.js/billing-checkout.js/admin-cache-bust.js/feed-lookup.js:
// index.js calls loadFeedItems(env) (the same real feed every other
// endpoint reads) and passes items in, so there is one source of feed
// data, not a second one.
//
// Field note: real feed items carry CVE identifiers under
// iocs_by_type.cve (confirmed against a real local data/feed.json
// sample), not a top-level cve_ids array -- buildCveExploitedSummary()
// checks both so it works whichever shape the live R2 payload uses,
// without assuming index.js's existing computeEPSS()'s cve_ids reference
// is populated (that function is untouched here either way).
// =============================================================================

// Threat types plausible as "active malicious infrastructure" for a C2 IP
// blocklist. Deliberately narrower than "every item with an ipv4 IOC" --
// a Vulnerability or Threat Intel advisory's incidental IP reference
// (e.g. a PoC host) is not the same claim as "this IP is C2
// infrastructure," and labeling it that way in a feed security teams
// paste into firewall rules would be a real, actionable false claim.
// Exported so taxii.js's "c2-indicators" TAXII collection classifies items
// the identical way this public teaser feed does -- one definition of
// "active malicious infrastructure," not two that could quietly drift.
export const C2_THREAT_TYPES = new Set(["Malware", "Ransomware", "APT", "Phishing", "DDoS", "Supply Chain"]);

const SITE_BASE = "https://intel.cyberdudebivash.com";

function cveIdsOf(item) {
  if (Array.isArray(item.cve_ids) && item.cve_ids.length) return item.cve_ids;
  const fromIocs = (item.iocs_by_type && item.iocs_by_type.cve) || [];
  return fromIocs;
}

/**
 * Distinct C2-candidate IPv4 addresses from active-infrastructure-typed
 * feed items, most-recent-first, capped at `limit`.
 * @param {Array<Record<string, any>>} items
 * @param {number} limit
 * @returns {string[]}
 */
export function buildC2IpList(items, limit = 100) {
  const seen = new Set();
  const ips = [];
  for (const item of items) {
    if (!C2_THREAT_TYPES.has(item.threat_type)) continue;
    for (const ip of (item.iocs_by_type && item.iocs_by_type.ipv4) || []) {
      if (seen.has(ip)) continue;
      seen.add(ip);
      ips.push(ip);
      if (ips.length >= limit) return ips;
    }
  }
  return ips;
}

/**
 * Distinct domains from Ransomware-typed feed items, most-recent-first,
 * capped at `limit`.
 * @param {Array<Record<string, any>>} items
 * @param {number} limit
 * @returns {string[]}
 */
export function buildRansomwareDomainList(items, limit = 100) {
  const seen = new Set();
  const domains = [];
  for (const item of items) {
    if (item.threat_type !== "Ransomware") continue;
    for (const d of (item.iocs_by_type && item.iocs_by_type.domain) || []) {
      if (seen.has(d)) continue;
      seen.add(d);
      domains.push(d);
      if (domains.length >= limit) return domains;
    }
  }
  return domains;
}

/**
 * Top `limit` actively-exploited CVEs: CISA KEV-confirmed first (KEV
 * listing is itself CISA's own definition of "confirmed actively
 * exploited"), then the highest-EPSS remaining candidates, both tiers
 * sorted by risk_score descending.
 * @param {Array<Record<string, any>>} items
 * @param {number} limit
 */
export function buildCveExploitedSummary(items, limit = 25) {
  const candidates = [];
  const seenCve = new Set();
  for (const item of items) {
    const cves = cveIdsOf(item);
    if (!cves.length) continue;
    const cveId = cves[0];
    if (seenCve.has(cveId)) continue;
    seenCve.add(cveId);
    candidates.push({
      cve_id: cveId,
      title: item.title || "",
      severity: item.severity || "",
      risk_score: parseFloat(item.risk_score || 0),
      epss_score: item.epss_score != null ? parseFloat(item.epss_score) : null,
      kev_present: !!item.kev_present,
      source: item.source || item.feed_source || "",
      published: item.published || item.published_at || "",
    });
  }

  const kev = candidates.filter((c) => c.kev_present).sort((a, b) => b.risk_score - a.risk_score);
  const nonKev = candidates
    .filter((c) => !c.kev_present)
    .sort((a, b) => (b.epss_score || 0) - (a.epss_score || 0) || b.risk_score - a.risk_score);

  const cves = [...kev, ...nonKev].slice(0, limit);

  return {
    cves,
    total_candidates: candidates.length,
    kev_confirmed_count: kev.length,
    generated_at: new Date().toISOString(),
    source: "CYBERDUDEBIVASH SENTINEL APEX",
    upgrade: {
      message: "Full CVE feed (all severities, live EPSS refresh, STIX 2.1 export) requires Sentinel Pro.",
      url: `${SITE_BASE}/pricing.html?ref=cve_feed`,
    },
  };
}

/**
 * The conversion banner prepended to every plaintext feed. `matchedCount`
 * is the real number of indicators actually returned (never a hardcoded
 * claim that could be wrong in either direction), `cap` is the limit
 * this feed enforces.
 * @param {string} feedLabel - human label, e.g. "Active C2 IP"
 * @param {number} matchedCount
 * @param {number} cap
 * @param {string} ref - upgrade URL ?ref= tag for this specific feed
 */
export function renderConversionBanner(feedLabel, matchedCount, cap, ref) {
  const today = new Date().toISOString().slice(0, 10);
  const sampleNote = matchedCount >= cap
    ? `This free feed contains a limited sample (Top ${cap} indicators).`
    : `This free feed contains every ${feedLabel.toLowerCase()} indicator currently tracked (${matchedCount}) -- below the ${cap}-indicator free-tier cap.`;
  return [
    "# -------------------------------------------------------------------",
    `# Sentinel APEX (TM) Community Threat Feed -- ${feedLabel} (Updated: ${today})`,
    `# Provided by CYBERDUDEBIVASH (${SITE_BASE})`,
    "#",
    `# NOTICE: ${sampleNote}`,
    "# For full real-time STIX 2.1 streaming, 50,000+ indicators, ASN filtering,",
    "# and automated YARA rules, upgrade to Sentinel Pro ($49/mo):",
    `# Direct Upgrade: ${SITE_BASE}/pricing.html?ref=${ref}`,
    "# -------------------------------------------------------------------",
    "",
  ].join("\n");
}

/**
 * Full plaintext feed body: banner + one indicator per line.
 * @param {string} feedLabel
 * @param {string[]} indicators
 * @param {number} cap
 * @param {string} ref
 */
export function renderPlaintextFeed(feedLabel, indicators, cap, ref) {
  const banner = renderConversionBanner(feedLabel, indicators.length, cap, ref);
  return banner + indicators.join("\n") + (indicators.length ? "\n" : "");
}
