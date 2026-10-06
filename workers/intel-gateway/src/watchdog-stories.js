/**
 * CYBER WATCHDOG STORIES -- one brief row per story, not per article.
 *
 * Production 2026-09-28: the same Citrix NetScaler zero-day reached the
 * brief as 3-4 rows from BleepingComputer, SecurityAffairs and
 * CyberSecurity News, crowding distinct threats off an 8-row free brief.
 *
 * Grouping is evidence-only and deliberately conservative: leaving a
 * duplicate costs a row, merging two different threats hides one. Two
 * items are one story only when:
 *   1. they name a common CVE id, or
 *   2. they cite the same source article (sourceKey), or
 *   3. one carries a CISA KEV product (kev_product, e.g. "Citrix
 *      NetScaler"), the other names no CVE, its title contains every word
 *      of that product, the titles share at least two further specific
 *      words, and they were published within 7 days of each other.
 * Every merged report stays visible on the row (related[]) with the rule
 * that matched it. Nothing is dropped and nothing is invented.
 *
 * Pure and synchronous. Input: items already in display order (priority
 * ranked), so each story is represented by its highest-ranked report.
 */

export const STORY_VERSION = "watchdog-stories-1";
export const STORY_WINDOW_MS = 7 * 86400000;
export const STORY_MAX_RELATED = 10;

// Query parameters that only track the click, never select the page.
const TRACKING_PARAM = /^(utm_[a-z_]+|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|source)$/i;

/**
 * Source article identity: scheme + lower-case host + path without a
 * trailing slash + the query minus tracking parameters (sorted). The query is
 * kept: cvename.cgi?name=CVE-A and ?name=CVE-B are different pages.
 * (Canonical home since watchdog-stories-1; ai-threat-feed.js re-exports it.)
 */
export function sourceKey(url) {
  try {
    const u = new URL(url);
    const params = [...u.searchParams.entries()].filter(([k]) => !TRACKING_PARAM.test(k)).sort(([a, x], [b, y]) => (a + "=" + x).localeCompare(b + "=" + y));
    const query = params.length ? "?" + params.map(([k, v]) => k + "=" + v).join("&") : "";
    return u.protocol + "//" + u.hostname.toLowerCase() + (u.pathname.replace(/\/+$/, "") || "/") + query;
  } catch { return null; }
}

// Words that say nothing about WHICH threat a headline is about.
const GENERIC = new Set([
  "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "by", "with", "as", "at", "from", "its", "it", "is", "are",
  "be", "now", "new", "via", "over", "into", "after", "amid", "about", "their", "your", "this", "that", "these",
  "attack", "attacker", "hacker", "flaw", "bug", "vulnerability", "vulnerabilitie", "issue", "patch", "update", "fix",
  "security", "warn", "urge", "say", "report", "cisa", "us", "u", "s", "cve", "actively", "wild", "known", "catalog", "kev",
  "add", "adds", "feds", "order", "orders",
]);

function words(title) {
  return String(title || "").toLowerCase()
    .replace(/\b(zero|0)[- ]?days?\b/g, " zeroday ")
    .split(/[^a-z0-9]+/)
    .filter(Boolean)
    .map((w) => (w.length > 4 ? w.replace(/(ing|ed|es|s)$/, "") : w));
}

function cvesOf(item) {
  const out = new Set();
  const add = (v) => { if (typeof v === "string" && /^CVE-\d{4}-\d{4,}$/i.test(v.trim())) out.add(v.trim().toUpperCase()); };
  add(item.cve_id);
  if (Array.isArray(item.cve_ids)) item.cve_ids.slice(0, 50).forEach(add);
  return out;
}

function timeOf(item) {
  for (const k of ["published_at", "published", "timestamp", "processed_at"]) {
    const t = Date.parse(item[k] || "");
    if (Number.isFinite(t)) return t;
  }
  return null;
}

function productWords(item) {
  const p = typeof item.kev_product === "string" ? item.kev_product : "";
  const w = words(p).filter((x) => x.length > 1);
  return w.length >= 2 ? w : null; // a bare vendor name is too broad to identify a story
}

function profile(item) {
  const title = words(item.title || item.name);
  return {
    cves: cvesOf(item),
    source: sourceKey(item.source_url),
    product: productWords(item),
    titleWords: new Set(title),
    specific: new Set(title.filter((w) => !GENERIC.has(w) && w.length > 1)),
    at: timeOf(item),
  };
}

/** Why b belongs to the story led by a, or null. */
export function storyMatch(a, b) {
  const pa = a.__p || profile(a);
  const pb = b.__p || profile(b);
  for (const c of pb.cves) if (pa.cves.has(c)) return { rule: "shared_cve", evidence: c };
  if (pa.source && pa.source === pb.source) return { rule: "same_source_article", evidence: pa.source };
  const byProduct = (pp, other, product) => {
    if (!product || other.cves.size) return null;
    if (!product.every((w) => other.titleWords.has(w))) return null;
    const extra = [...pp.specific].filter((w) => other.specific.has(w) && !product.includes(w));
    if (extra.length < 2) return null;
    if (pp.at === null || other.at === null || Math.abs(pp.at - other.at) > STORY_WINDOW_MS) return null;
    return { rule: "kev_product_in_title", evidence: product.join(" ") + " + " + extra.slice(0, 4).join(", ") };
  };
  return byProduct(pa, pb, pa.product) || byProduct(pb, pa, pb.product);
}

/**
 * Group items (already in display order) into stories.
 * @returns {Array<{lead: object, members: Array<{item, match}>}>}
 */
export function groupStories(items) {
  const stories = [];
  for (const item of items || []) {
    if (!item || typeof item !== "object") continue;
    const probe = { ...item, __p: profile(item) };
    let home = null; let match = null;
    for (const s of stories) {
      for (const m of [s.lead, ...s.members.map((x) => x.probe)]) {
        match = storyMatch(m, probe);
        if (match) break;
      }
      if (match) { home = s; break; }
    }
    if (home) home.members.push({ item, match, probe });
    else stories.push({ lead: probe, leadItem: item, members: [] });
  }
  return stories.map((s) => ({ lead: s.leadItem, members: s.members.map(({ item, match }) => ({ item, match })) }));
}

/** The public corroboration block for a story row. */
export function corroboration(story) {
  const reports = 1 + story.members.length;
  const sources = [...new Set([story.lead, ...story.members.map((m) => m.item)]
    .map((i) => String(i.source || i.source_name || "").trim()).filter(Boolean))];
  return {
    version: STORY_VERSION,
    reports,
    sources,
    related: story.members.slice(0, STORY_MAX_RELATED).map(({ item, match }) => ({
      id: String(item.id || "").slice(0, 128) || null,
      title: String(item.title || item.name || "").slice(0, 240),
      source: String(item.source || item.source_name || "").slice(0, 80) || null,
      rule: match.rule,
      evidence: String(match.evidence).slice(0, 160),
    })),
  };
}
