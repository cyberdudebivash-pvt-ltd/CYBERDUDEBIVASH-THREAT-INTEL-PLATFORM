// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Premium Threat Report Engine v201.0
// Routes: POST /api/reports/premium  .  GET /api/reports/list  .  GET /api/reports/:id
// Included with Pro and above (plan prices: the runtime pricing provider).
// 2026-09-28: the "$49/report" and "$149/mo unlimited" offers were removed --
// neither is in config/commercial-contract.json nor sold through Razorpay.
// Architecture:
//   - JSON report generation (structured intelligence package)
//   - PDF generation metadata (served as downloadable JSON until PDF render service wired)
//   - Full CVE summary, MITRE ATT&CK coverage, actor attribution, IOC table
//   - Stored in R2 for persistent retrieval (90-day retention)
//   - Revenue tracked in ANALYTICS_KV per report generation
// =============================================================================

// Canonical price reader and the Watchdog evidence-cited priority engine:
// reused, not re-implemented (report advisories are ranked with the same
// engine and projection as Watchdog brief rows and match events).
import { LAST_AUTHORITATIVE_MAX_AGE_SECONDS, planPrice, projectItem, watchdogPublication } from "./cyber-watchdog.js";
import { computeEventPriority, priorityRank } from "./watchdog-priority.js";

// -- Tier & Pricing Config -----------------------------------------------------
const REPORT_CONFIG = {
  VERSION: "201.0",
  MAX_ITEMS_FREE:         0,    // free: no reports
  MAX_ITEMS_PRO:          50,   // pro: up to 50 items per report
  MAX_ITEMS_ENTERPRISE:   500,  // enterprise: full feed
  REPORT_TTL_DAYS:        90,
  R2_PREFIX:              "reports/premium/",
  LIST_MAX_PAGES:         10,   // x1000 objects per R2 list page
};

// -- Helpers -------------------------------------------------------------------
function safeStr(v, maxLen = 256) {
  if (!v || typeof v !== "string") return "";
  return v.replace(/[\x00-\x1F\x7F<>"'`\\]/g, "").slice(0, maxLen).trim();
}

function safeInt(v, def = 0, min = 0, max = 9999) {
  const n = parseInt(v);
  return isNaN(n) ? def : Math.max(min, Math.min(max, n));
}

function _json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: {
      "Content-Type":                "application/json; charset=utf-8",
      "Cache-Control":               "no-store",
      // Access-Control-Allow-Origin intentionally not set here -- SENTINEL
      // APEX PUBLIC-REPO ZERO-TRUST PHASE 3: this is a $49/report PRO+
      // commercial route (index.js's own route comment), never genuinely
      // public -- index.js's withBaselineHeaders() applies the real,
      // origin-aware decision via cors-policy.js to every response
      // including this one; see that file's header comment.
      "X-Sentinel-Module":           "premium-reports/201.0",
      ...extra,
    },
  });
}

async function sha256hex(text) {
  const data = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, "0")).join("");
}

function genReportId() {
  const b = crypto.getRandomValues(new Uint8Array(8));
  return "rpt_" + Array.from(b).map(x => x.toString(16).padStart(2, "0")).join("");
}

// -- MITRE ATT&CK Coverage Analyser -------------------------------------------
const TECHNIQUE_RE = /^T\d{4}(\.\d{3})?$/;
export function analyseMitreCoverage(items) {
  const tacticMap  = {};
  const techniqueSet = new Set();

  for (const item of items) {
    const tactics = Array.isArray(item.mitre_tactics) ? item.mitre_tactics : [];
    const ttps    = Array.isArray(item.ttps) ? item.ttps : [];

    for (const tactic of tactics) {
      // The feed stores mitre_tactics as {id, name, tactic} objects (plus
      // some legacy strings). String(object) produced "[object Object]" as a
      // customer-facing tactic name; read the tactic name and count the
      // technique id it carries.
      // A legacy string that is a technique id ("T1190") is a technique, not a tactic.
      const isObj = tactic !== null && typeof tactic === "object";
      const raw = safeStr(isObj ? String(tactic.tactic || tactic.name || "") : String(tactic || ""), 50);
      const tid = safeStr(isObj ? String(tactic.id || "") : raw, 20).toUpperCase();
      if (TECHNIQUE_RE.test(tid)) techniqueSet.add(tid);
      if (raw && !TECHNIQUE_RE.test(raw.toUpperCase())) tacticMap[raw] = (tacticMap[raw] || 0) + 1;
    }
    for (const ttp of ttps) {
      const id = typeof ttp === "object" ? (ttp.id || ttp.technique_id || "") : String(ttp || "");
      if (id) techniqueSet.add(safeStr(id, 20));
    }
  }

  const topTactics = Object.entries(tacticMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([tactic, count]) => ({ tactic, count }));

  const coverageScore = Math.min(100, Math.round((techniqueSet.size / 193) * 100)); // 193 = ATT&CK Enterprise technique count

  return {
    unique_techniques:    techniqueSet.size,
    top_tactics:          topTactics,
    coverage_score_pct:   coverageScore,
    coverage_label:       coverageScore >= 60 ? "COMPREHENSIVE" : coverageScore >= 30 ? "MODERATE" : "LIMITED",
    techniques_list:      [...techniqueSet].slice(0, 50),
    enterprise_matrix_url:"https://attack.mitre.org/techniques/enterprise/",
  };
}

// -- CVE Summary Builder -------------------------------------------------------
const CVE_RE = /^CVE-\d{4}-\d{4,}$/i;

/** Every CVE an item names: cve_id plus cve_ids (multi-CVE advisories carry all of them there). */
export function itemCveIds(item) {
  const ids = new Set();
  const add = (v) => { const c = safeStr(typeof v === "string" ? v : "", 30).toUpperCase(); if (CVE_RE.test(c)) ids.add(c); };
  add(item.cve_id);
  if (Array.isArray(item.cve_ids)) item.cve_ids.slice(0, 50).forEach(add);
  return [...ids];
}

/**
 * Public exploit evidence from fields the feed actually carries
 * (exploit_maturity, metasploit_available, poc_github_count, exploit_count).
 * The old check read item.exploit_available, which the feed never sets, so
 * every CVE was reported exploit_available: false.
 */
function exploitAvailable(item) {
  if (item.exploit_available === true || item.metasploit_available === true) return true;
  if (/^(POC|FUNCTIONAL|WEAPONIZED|ACTIVE|HIGH)/i.test(String(item.exploit_maturity || ""))) return true;
  return Number(item.poc_github_count) > 0 || Number(item.exploit_count) > 0;
}

export function buildCVESummary(items) {
  const cves = {};

  for (const item of items) {
    for (const cveId of itemCveIds(item)) {
      if (cves[cveId]) continue; // first (highest-priority) advisory naming a CVE describes it
      cves[cveId] = {
        id:          cveId,
        title:       safeStr(item.title || "", 200),
        cvss_score:  typeof item.cvss_score  === "number" ? item.cvss_score  : null,
        epss_score:  typeof item.epss_score  === "number" ? item.epss_score  : null,
        severity:    safeStr(item.severity || "UNKNOWN", 20),
        kev_present: item.kev_present === true,
        actor_tag:   safeStr(item.actor_tag || "UNATTRIBUTED", 60),
        exploit_available: exploitAvailable(item),
        exploit_maturity: safeStr(String(item.exploit_maturity || ""), 30) || null,
        source:      safeStr(item.source || item.feed_source || "", 100),
        processed_at:item.processed_at || item.timestamp || null,
      };
    }
  }

  // Patch order: CISA KEV first, then CVSS, then EPSS.
  const cveList = Object.values(cves)
    .sort((a, b) => (b.kev_present - a.kev_present)
      || (b.cvss_score || 0) - (a.cvss_score || 0)
      || (b.epss_score || 0) - (a.epss_score || 0));
  // Counted per unique CVE (was per advisory, so a CVE reported by two
  // sources counted twice and a two-CVE advisory counted once).
  const kev_count = cveList.filter((c) => c.kev_present).length;
  const critical_count = cveList.filter((c) => c.severity.toUpperCase() === "CRITICAL").length;
  const high_count = cveList.filter((c) => c.severity.toUpperCase() === "HIGH").length;

  return {
    total_cves:       cveList.length,
    kev_count,
    critical_count,
    high_count,
    exploit_available_count: cveList.filter((c) => c.exploit_available).length,
    top_cves:         cveList.slice(0, 20),
    exploitation_risk: kev_count > 0 ? "CRITICAL -- CISA KEV entries require immediate patching" : "MODERATE",
  };
}

// -- Actor Intelligence Summary ------------------------------------------------
function buildActorIntelligence(items) {
  const actorMap = {};

  for (const item of items) {
    const actor = safeStr(item.actor_tag || "UNATTRIBUTED", 80);
    if (!actorMap[actor]) {
      actorMap[actor] = {
        actor_tag:    actor,
        advisory_count: 0,
        max_risk:     0,
        severities:   {},
        campaigns:    new Set(),
        ioc_count:    0,
        ttp_count:    0,
        first_seen:   item.processed_at || item.timestamp || null,
        last_seen:    item.processed_at || item.timestamp || null,
      };
    }
    const a = actorMap[actor];
    a.advisory_count++;
    const risk = typeof item.risk_score === "number" ? item.risk_score : 0;
    if (risk > a.max_risk) a.max_risk = risk;
    const sev = (item.severity || "UNKNOWN").toUpperCase();
    a.severities[sev] = (a.severities[sev] || 0) + 1;
    const campaign = safeStr((item.apex && item.apex.campaign_id) || "", 60);
    if (campaign && campaign !== "UNCLASSIFIED") a.campaigns.add(campaign);
    a.ioc_count += Array.isArray(item.iocs) ? item.iocs.length : (item.ioc_count || 0);
    a.ttp_count += Array.isArray(item.ttps) ? item.ttps.length : (item.ttp_count || 0);
    if (item.processed_at > (a.last_seen || "")) a.last_seen = item.processed_at;
  }

  return Object.values(actorMap)
    .map(a => ({ ...a, campaigns: [...a.campaigns] }))
    .sort((a, b) => b.advisory_count - a.advisory_count)
    .slice(0, 20);
}

// -- IOC Table Builder ---------------------------------------------------------
export function buildIOCTable(items, maxItems = 200) {
  const iocs = [];
  const seen = new Set();

  for (const item of items) {
    const rawIocs = Array.isArray(item.iocs) ? item.iocs : [];
    for (const ioc of rawIocs) {
      if (iocs.length >= maxItems) break;
      // CodeRabbit finding (PR #246): typeof null === "object" in JS, so a
      // malformed entry like iocs: [null] passed the old type check and then
      // crashed on ioc.value below, 500ing the whole report. Plain-string
      // IOC entries are still valid and handled by the branch below.
      if (ioc === null) continue;
      const val = safeStr(typeof ioc === "object" ? (ioc.value || ioc.indicator || "") : String(ioc || ""), 512);
      const key = val.toLowerCase();
      if (!val || seen.has(key)) continue;
      seen.add(key);
      iocs.push({
        value:      val,
        type:       safeStr(typeof ioc === "object" ? (ioc.type || "unknown") : "unknown", 30),
        confidence: typeof ioc === "object" && typeof ioc.confidence === "number" ? ioc.confidence : 50,
        source:     safeStr(item.source || item.feed_source || "", 80),
        context:    safeStr(item.title || "", 120),
        severity:   safeStr(item.severity || "UNKNOWN", 20),
        actor_tag:  safeStr(item.actor_tag || "UNATTRIBUTED", 60),
      });
    }
    if (iocs.length >= maxItems) break;
  }

  return {
    total_iocs:   iocs.length,
    ioc_table:    iocs,
    types_summary: iocs.reduce((acc, i) => { acc[i.type] = (acc[i.type] || 0) + 1; return acc; }, {}),
  };
}

// -- Executive Summary Generator -----------------------------------------------
export function buildExecutiveSummary(items, mitre, cve, actors, reportPeriod) {
  const totalAdvisories   = items.length;
  const criticalCount     = items.filter(i => (i.severity || "").toUpperCase() === "CRITICAL").length;
  const highCount         = items.filter(i => (i.severity || "").toUpperCase() === "HIGH").length;
  const kevCount          = items.filter(i => i.kev_present).length;
  const avgRisk           = items.length > 0
    ? parseFloat((items.reduce((s, i) => s + (typeof i.risk_score === "number" ? i.risk_score : 0), 0) / items.length).toFixed(2))
    : 0;

  const threatLandscape = criticalCount > 5
    ? "ELEVATED -- Multiple critical-severity threats active in current intelligence cycle"
    : criticalCount > 0
    ? "HIGH -- Critical threats identified requiring immediate SOC response"
    : highCount > 10
    ? "MODERATE-HIGH -- Significant high-severity advisory volume detected"
    : "MODERATE -- Standard threat activity within normal baseline";

  return {
    report_period:       reportPeriod,
    total_advisories:    totalAdvisories,
    critical_count:      criticalCount,
    high_count:          highCount,
    kev_confirmed:       kevCount,
    avg_risk_score:      avgRisk,
    threat_landscape:    threatLandscape,
    mitre_coverage:      `${mitre.unique_techniques} techniques across ${Object.keys(mitre.top_tactics.reduce((a, t) => { a[t.tactic] = 1; return a; }, {})).length} tactics`,
    top_actor:           actors[0] ? `${actors[0].actor_tag} (${actors[0].advisory_count} advisories)` : "UNATTRIBUTED",
    cve_exposure:        cve.total_cves > 0 ? `${cve.total_cves} CVEs identified -- ${cve.kev_count} CISA KEV confirmed` : "No CVEs in scope",
    key_recommendations: [
      cve.kev_count > 0 ? `CRITICAL: Patch ${cve.kev_count} CISA KEV-confirmed CVE(s) immediately` : null,
      kevCount > 0 && cve.kev_count === 0 ? `CRITICAL: Review ${kevCount} advisory(ies) linked to CISA KEV exploitation` : null,
      criticalCount > 0 ? `Deploy detection rules for ${criticalCount} CRITICAL-severity threat(s)` : null,
      mitre.unique_techniques > 10 ? `Review MITRE coverage gaps -- ${mitre.unique_techniques} techniques active in this period` : null,
      avgRisk > 6    ? "Activate incident response workflow -- average risk score exceeds HIGH threshold" : null,
      "Subscribe to real-time webhook push for immediate alert delivery",
    ].filter(Boolean),
  };
}

// -- Report period coverage ----------------------------------------------------
/** Publication time of an advisory in ms, or null when it carries no parseable date. */
export function itemPublishedMs(item) {
  for (const k of ["published_at", "published", "timestamp", "processed_at"]) {
    const v = item && item[k];
    if (typeof v === "string" && v) {
      const t = Date.parse(v);
      if (Number.isFinite(t)) return t;
    }
  }
  return null;
}

/** What the report actually covers, beside the period it claims. */
export function periodCoverage(items, periodStart, periodEnd, excludedOutsidePeriod) {
  const times = items.map(itemPublishedMs).filter((t) => t !== null);
  return {
    period_start:            periodStart,
    period_end:              periodEnd,
    earliest_published:      times.length ? new Date(Math.min(...times)).toISOString() : null,
    latest_published:        times.length ? new Date(Math.max(...times)).toISOString() : null,
    undated_advisories:      items.length - times.length,
    excluded_outside_period: excludedOutsidePeriod,
    basis:                   "Advisories on the live Sentinel APEX feed published within the period. The feed is a rolling window, so a period can contain fewer advisories than were published worldwide.",
  };
}

// -- Main Report Handler -------------------------------------------------------

export async function handlePremiumReport(request, env, auth, rid) {
  const tier = (auth.tier || "free").toLowerCase();
  // ZERO-TRUST HARDENING FIX (2026-08-24): was missing .toLowerCase() --
  // real auth.tier is always uppercase (TIERS.FREE/PRO/ENTERPRISE/MSSP,
  // index.js:317), so every tier === "free"/"enterprise" comparison below
  // silently never matched for a real customer. Same bug class fixed
  // repeatedly elsewhere this session (revenue-enforcement.js, sla-monitor.js,
  // alert-engine.js). CORRECTION (post-#369 production assurance audit):
  // this file's routes were wired live into index.js's router by commit
  // 5004465c (PR #313, 2026-09-01) -- POST /api/reports/premium and GET
  // /api/reports/list/{id} are real, tier-gated, revenue-generating
  // endpoints (see index.js's "premium-reports.js routes" block), not
  // dead code. This fix was therefore already live-exploitable before
  // this correction; treat every defect found in this file as real and
  // customer-facing, not latent.

  // Tier gate -- free users get upsell
  if (tier === "free") {
    return _json({
      error:      "tier_required",
      feature:    "premium_reports",
      // Pro price from the runtime pricing provider (the value Razorpay
      // charges). This literal said "$29/mo" while Pro is billed $49/mo.
      message:    "Premium Threat Intelligence Reports are included with Pro ($" + planPrice("PRO").usd_monthly + "/mo) and above.",
      pricing: {
        // DEPRECATED (2026-09-28): per-report and report-only plans are not
        // sold. Kept as null so existing clients read "no price" rather than
        // a price that is never charged. Removal: next premium-reports major.
        per_report_usd:     null,
        per_report_inr:     null,
        monthly_unlimited:  null,
        included_from:      "PRO",
        pro_usd_monthly:    planPrice("PRO").usd_monthly,
        pro_inr_monthly:    planPrice("PRO").inr_monthly,
        price_source:       "gateway runtime pricing provider (the values Razorpay charges)",
      },
      upgrade_url: "/upgrade.html?plan=pro&feature=reports",
      // DEPRECATED (2026-09-28): the store has no threat-report product.
      store_url:   null,
      request_id:  rid,
    }, 403);
  }

  if (request.method === "GET") {
    return handleReportList(request, env, auth, rid);
  }

  if (request.method !== "POST") {
    return _json({ error: "method_not_allowed", allowed: ["GET", "POST"], request_id: rid }, 405);
  }

  // Parse report request
  let body = {};
  try { body = await request.json(); } catch { /* optional body */ }

  const reportType  = ["weekly", "monthly", "custom", "cve_focused", "actor_focused"].includes(body.type)
    ? body.type : "weekly";
  const reportTitle = safeStr(body.title || `SENTINEL APEX Threat Intelligence Report -- ${reportType.toUpperCase()}`, 200);
  // MSSP ($999/mo) is above Enterprise; it received Pro-sized reports because
  // only "enterprise" was checked here and at the IOC / advisory caps below.
  const fullTier    = tier === "enterprise" || tier === "mssp";
  const maxItems    = fullTier ? REPORT_CONFIG.MAX_ITEMS_ENTERPRISE : REPORT_CONFIG.MAX_ITEMS_PRO;
  const severityFilter = body.severity_filter
    ? (Array.isArray(body.severity_filter) ? body.severity_filter.map(s => safeStr(s, 20).toUpperCase()) : [])
    : [];

  // Load feed from R2 (primary) or KV cache (fallback)
  let feedItems = [];
  let rawFeed = null;
  try {
    if (env?.INTEL_R2) {
      // PRODUCTION-VERIFICATION FIX (2026-08-24): "feeds/feed.json" is a
      // dead R2 key nothing ever writes -- see p18-handlers.js's matching
      // _loadFeed fix note for the full cross-file root cause. Redirected
      // to the live, continuously updated key.
      const r2obj = await env.INTEL_R2.get("api/v1/intel/latest.json");
      if (r2obj) {
        const raw = await r2obj.json();
        rawFeed = raw;
        feedItems = Array.isArray(raw)
          ? raw
          : Array.isArray(raw?.advisories)
          ? raw.advisories
          : Array.isArray(raw?.items)
          ? raw.items
          : [];
      }
    }
  } catch (e) {
    rawFeed = null;
  }

  // Freshness: the same canonical contract as Cyber Watchdog and the AI feed.
  // Before this, an unreadable feed produced an EMPTY report that was still
  // stored and counted as a generated report, and a days-old feed was
  // presented as current. Now: no feed -> 503 and nothing stored; STALE
  // within 48h -> generated but labelled NOT LIVE; older / invalid -> 503.
  const nowMs = Date.now();
  const pub = watchdogPublication(rawFeed, nowMs);
  const staleUsable = pub.freshness_status === "STALE"
    && Number.isFinite(pub.feed_age_seconds) && pub.feed_age_seconds <= LAST_AUTHORITATIVE_MAX_AGE_SECONDS;
  if (!pub.serve_live && !staleUsable) {
    return _json({
      error:            rawFeed ? "intelligence_degraded" : "intelligence_unavailable",
      message:          rawFeed
        ? "INTELLIGENCE DEGRADED - LAST AUTHORITATIVE UPDATE " + (pub.feed_generated_at || "unknown") + ". No report was generated or charged against your usage."
        : "The intelligence feed could not be read. No report was generated or charged against your usage.",
      freshness_status: pub.freshness_status,
      feed_generated_at:pub.feed_generated_at,
      feed_age_seconds: pub.feed_age_seconds,
      request_id:       rid,
    }, 503, { "Retry-After": "300" });
  }
  const intelligenceFreshness = {
    live:               pub.serve_live,
    label:              pub.serve_live ? "LIVE" : "LAST AUTHORITATIVE INTELLIGENCE - NOT LIVE",
    freshness_status:   pub.freshness_status,
    feed_generated_at:  pub.feed_generated_at,
    feed_age_seconds:   pub.feed_age_seconds,
    freshness_threshold_seconds: pub.freshness_threshold_seconds,
  };

  // PRODUCTION-VERIFICATION FIX (2026-08-24): isCustomerReady() runs the
  // narrative-report certification chain (P20+P21+P23+P25+P26) built for the
  // free, public /reports/** HTML surface (P0 incident scope -- see
  // publication-gate.js header). Live-verified this session against the
  // production feed: 0/474 current items clear that bar, so this filter
  // silently produced an EMPTY report for every paying premium-reports
  // customer ($49/report, $149/mo) regardless of tier. A premium report is a
  // curated digest of raw feed data the customer already has paid API access
  // to (via /api/feed) -- it does not need the same narrative certification
  // as the polished public HTML page, and publication-gate.js's own docs
  // forbid lowering that gate's thresholds to make it pass. Filtering on
  // real underlying signal instead (title plus at least one of
  // severity/cve_id/iocs) keeps out empty stub items without imposing
  // certification thresholds this endpoint was never designed to need.
  feedItems = feedItems.filter(i => i && i.title && (i.severity || itemCveIds(i).length > 0 || (Array.isArray(i.iocs) && i.iocs.length > 0)));

  // Determine report period
  const now = new Date(nowMs);
  const periodEnd   = now.toISOString().slice(0, 10);
  const periodStart = reportType === "monthly"
    ? new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString().slice(0, 10)
    : new Date(now.getTime() - 7 * 86400000).toISOString().slice(0, 10);
  const reportPeriod = `${periodStart} to ${periodEnd}`;

  // The period is a filter, not only a label: an advisory published before
  // the period start is left out (it was included while the report claimed
  // the period). Undated advisories are kept and counted.
  const periodStartMs = Date.parse(periodStart + "T00:00:00Z");
  let excludedOutsidePeriod = 0;
  feedItems = feedItems.filter((i) => {
    const t = itemPublishedMs(i);
    if (t !== null && t < periodStartMs) { excludedOutsidePeriod++; return false; }
    return true;
  });

  // Apply filters
  let filtered = feedItems;
  if (severityFilter.length > 0) {
    filtered = filtered.filter(i => severityFilter.includes((i.severity || "").toUpperCase()));
  }
  if (reportType === "cve_focused") {
    filtered = filtered.filter(i => itemCveIds(i).length > 0);
  }
  if (reportType === "actor_focused" && body.actor) {
    const actor = safeStr(body.actor, 80).toLowerCase();
    filtered = filtered.filter(i => (i.actor_tag || "").toLowerCase().includes(actor));
  }
  // Rank by evidence-cited priority (KEV, CVSS, EPSS, severity, activity)
  // before the tier cap, so a capped report keeps the most urgent advisories
  // rather than whichever came first in feed order.
  const priorityOf = new Map(filtered.map((i) => [i, computeEventPriority(projectItem(i))]));
  filtered = filtered
    .map((item, index) => ({ item, index, p: priorityOf.get(item) }))
    .sort((a, b) => priorityRank(b.p.band) - priorityRank(a.p.band) || (b.p.score ?? -1) - (a.p.score ?? -1) || a.index - b.index)
    .map((r) => r.item)
    .slice(0, maxItems);


  // Build report sections
  const mitre   = analyseMitreCoverage(filtered);
  const cve     = buildCVESummary(filtered);
  const actors  = buildActorIntelligence(filtered);
  const iocTable= buildIOCTable(filtered, fullTier ? 500 : 100);
  const execSum = buildExecutiveSummary(filtered, mitre, cve, actors, reportPeriod);
  // "What to act on first": the five highest-priority advisories, each with
  // the feed evidence behind its band.
  execSum.priority_actions = filtered.slice(0, 5).map((item) => {
    const p = priorityOf.get(item);
    return {
      id: item.id, title: safeStr(item.title || "", 200), band: p.band, score: p.score,
      cve_ids: itemCveIds(item),
      evidence: p.factors.filter((f) => f.known && f.evidence).map((f) => f.evidence),
    };
  });

  const reportId = genReportId();
  const report = {
    report_id:        reportId,
    report_type:      reportType,
    report_title:     reportTitle,
    generated_at:     now.toISOString(),
    generated_by:     "CYBERDUDEBIVASH(R) SENTINEL APEX v201.0",
    report_period:    reportPeriod,
    classification:   "TLP:AMBER -- Restricted to authorised recipients",
    tier:             tier,
    advisories_count: filtered.length,
    intelligence_freshness: intelligenceFreshness,
    coverage:         periodCoverage(filtered, periodStart, periodEnd, excludedOutsidePeriod),

    // Section 1 -- Executive Summary
    executive_summary: execSum,

    // Section 2 -- CVE Intelligence
    cve_intelligence: cve,

    // Section 3 -- MITRE ATT&CK Coverage
    mitre_attack_coverage: mitre,

    // Section 4 -- Threat Actor Intelligence
    actor_intelligence: {
      total_actors: actors.length,
      actors,
    },

    // Section 5 -- IOC Table
    ioc_intelligence: iocTable,

    // Section 6 -- Raw advisories (limited)
    advisories: filtered.slice(0, fullTier ? 500 : 50).map(item => ({
      id:          item.id,
      title:       safeStr(item.title || "", 200),
      severity:    item.severity,
      risk_score:  item.risk_score,
      cve_id:      item.cve_id || null,
      cve_ids:     itemCveIds(item),
      priority:    { band: priorityOf.get(item).band, score: priorityOf.get(item).score },
      actor_tag:   item.actor_tag || "UNATTRIBUTED",
      kev_present: item.kev_present || false,
      source:      item.source || item.feed_source,
      processed_at:item.processed_at || item.timestamp,
      apex_ai: item.apex_ai ? {
        soc_priority:    item.apex_ai.soc_priority,
        threat_level:    item.apex_ai.threat_level,
        predictive_risk: item.apex_ai.predictive_risk,
        ai_summary:      item.apex_ai.ai_summary,
      } : null,
    })),

    // Section 7 -- Metadata
    metadata: {
      platform:         "CYBERDUDEBIVASH(R) SENTINEL APEX",
      platform_version: "201.0",
      dashboard_url:    "https://intel.cyberdudebivash.com",
      api_docs_url:     "https://intel.cyberdudebivash.com/api-docs.html",
      pricing_url:      "https://intel.cyberdudebivash.com/pricing.html",
      report_ttl_days:  REPORT_CONFIG.REPORT_TTL_DAYS,
      expires_at:       new Date(now.getTime() + REPORT_TTL_MS).toISOString(),
      pdf_download_url: `https://intel.cyberdudebivash.com/api/reports/${reportId}/pdf`,
      csv_download_url: `https://intel.cyberdudebivash.com/api/reports/${reportId}/csv`,
      print_url:        `https://intel.cyberdudebivash.com/api/reports/${reportId}/print`,
      json_download_url:`https://intel.cyberdudebivash.com/api/reports/${reportId}`,
      export_formats:   ["json", "csv", "pdf"],
      contact:          "root@cyberdudebivash.in",
      copyright:        `(C) ${now.getFullYear()} CYBERDUDEBIVASH(R) -- All rights reserved. TLP:AMBER.`,
    },

    request_id: rid,
    gateway:    "SENTINEL-APEX/201.0",
  };

  // Store in R2 (if available)
  try {
    if (env?.INTEL_R2) {
      await env.INTEL_R2.put(
        `${REPORT_CONFIG.R2_PREFIX}${reportId}.json`,
        JSON.stringify(report),
        {
          httpMetadata: { contentType: "application/json" },
          customMetadata: {
            report_id:    reportId,
            report_type:  reportType,
            generated_at: now.toISOString(),
            tier:         tier,
            // TENANT-ISOLATION FIX (CodeRabbit, PR #242 pre-merge review):
            // was `auth.key_id`, a field that does not exist anywhere on the
            // object resolveAuth() returns (index.js:328-382 -- only tier,
            // key, sub, jwt, kv, error). Every report was therefore stored
            // with key_id: "", and since (auth.key_id || "") also always
            // evaluated to "" for every real request, handleReportList's and
            // handleReportGet's ownership checks below both matched "" === ""
            // for any authenticated PRO/ENTERPRISE customer -- full
            // cross-tenant read access to every other customer's reports.
            // Caught before this route was ever wired into index.js's
            // router (PR #242), so no real customer traffic was exposed.
            // auth.sub is the correct per-customer identity (customer_id for
            // API-key auth, JWT sub for JWT auth) -- same field already used
            // for tenant scoping and audit logging elsewhere in this file
            // (getUsageSummary(env, auth.sub, ...) equivalents) and in
            // index.js's own auditLog(..., sub: auth.sub) call sites.
            key_id:       auth.sub || "",
          },
        }
      );
    }
  } catch { /* Non-fatal -- report is still returned in response */ }

  // Track revenue event in KV
  try {
    if (env?.ANALYTICS_KV) {
      const revKey   = `report_generated:${now.toISOString().slice(0, 10)}`;
      const existing = (await env.ANALYTICS_KV.get(revKey, { type: "json" }).catch(() => null)) || { count: 0, tier_breakdown: {} };
      existing.count++;
      existing.tier_breakdown[tier] = (existing.tier_breakdown[tier] || 0) + 1;
      await env.ANALYTICS_KV.put(revKey, JSON.stringify(existing), { expirationTtl: 86400 * 90 });
    }
  } catch { /* Non-fatal */ }

  return _json(report, 201, {
    "X-Report-ID":   reportId,
    "X-Report-Type": reportType,
  });
}

// -- GET /api/reports/list -----------------------------------------------------
export async function handleReportList(request, env, auth, rid) {
  const tier = (auth.tier || "free").toLowerCase();
  // ZERO-TRUST HARDENING FIX (2026-08-24): was missing .toLowerCase() --
  // real auth.tier is always uppercase (TIERS.FREE/PRO/ENTERPRISE/MSSP,
  // index.js:317), so every tier === "free"/"enterprise" comparison below
  // silently never matched for a real customer. Same bug class fixed
  // repeatedly elsewhere this session (revenue-enforcement.js, sla-monitor.js,
  // alert-engine.js). CORRECTION (post-#369 production assurance audit):
  // this file's routes were wired live into index.js's router by commit
  // 5004465c (PR #313, 2026-09-01) -- POST /api/reports/premium and GET
  // /api/reports/list/{id} are real, tier-gated, revenue-generating
  // endpoints (see index.js's "premium-reports.js routes" block), not
  // dead code. This fix was therefore already live-exploitable before
  // this correction; treat every defect found in this file as real and
  // customer-facing, not latent.

  if (tier === "free") {
    return _json({
      error:      "tier_required",
      message:    "Report listing requires Pro tier or above.",
      upgrade_url:"/upgrade.html?plan=pro&feature=reports",
      request_id: rid,
    }, 403);
  }

  const reports = [];
  let listTruncated = false;
  try {
    if (env?.INTEL_R2) {
      // LIVE-VERIFICATION FIX (post-merge, PR #242): R2Bucket.list() does not
      // return customMetadata by default -- it must be explicitly requested
      // via `include`. Without it, obj.customMetadata was always {} for
      // every listed object, so meta.key_id below was always undefined --
      // the ownership filter correctly failed closed (no cross-tenant leak),
      // but that also meant NO customer, including the true owner, ever saw
      // any report in their own list. Caught live immediately after deploy:
      // customer A generated a report (confirmed via direct GET
      // /api/reports/{id}) but their own /api/reports/list came back empty.
      // PAGINATION FIX (2026-09-28): this read ONE page of 50 objects across
      // ALL customers' reports and filtered by owner afterwards, so once the
      // prefix held more than 50 reports a customer's own reports dropped
      // out of their list. Walk the pages (bounded) and filter each.
      const objects = [];
      let cursor;
      let pages = 0;
      do {
        const page = await env.INTEL_R2.list({ prefix: REPORT_CONFIG.R2_PREFIX, limit: 1000, include: ["customMetadata"], ...(cursor ? { cursor } : {}) });
        objects.push(...(page.objects || []));
        cursor = page.truncated ? page.cursor : undefined;
        pages++;
      } while (cursor && pages < REPORT_CONFIG.LIST_MAX_PAGES);
      listTruncated = !!cursor;
      for (const obj of objects) {
        const meta = obj.customMetadata || {};
        // TENANT-ISOLATION FIX (CodeRabbit, PR #242 pre-merge review): was
        // `meta.key_id === (auth.key_id || "")` -- auth.key_id does not
        // exist on resolveAuth()'s return object, so this always compared
        // "" === "" and matched every report for every customer. Require a
        // real, non-empty match against auth.sub (the correct per-customer
        // identity -- see the matching fix note where key_id is written,
        // above in handlePremiumReport). A report with no recorded owner
        // (key_id: "", e.g. any generated before this fix) now matches no
        // one rather than everyone -- fails closed, not open.
        // 90-day retention: an expired report is no longer listed (the cron purge deletes it).
        if (reportExpired(meta.generated_at, obj.uploaded, Date.now())) continue;
        if (auth.is_admin || (meta.key_id && auth.sub && meta.key_id === auth.sub)) {
          reports.push({
            report_id:    meta.report_id || obj.key.split("/").pop().replace(".json", ""),
            report_type:  meta.report_type || "unknown",
            generated_at: meta.generated_at || obj.uploaded.toISOString(),
            tier:         meta.tier || "unknown",
            size_bytes:   obj.size,
            download_url: `https://intel.cyberdudebivash.com/api/reports/${meta.report_id}`,
            pdf_url:      `https://intel.cyberdudebivash.com/api/reports/${meta.report_id}/pdf`,
            csv_url:      `https://intel.cyberdudebivash.com/api/reports/${meta.report_id}/csv`,
            print_url:    `https://intel.cyberdudebivash.com/api/reports/${meta.report_id}/print`,
          });
        }
      }
    }
  } catch { /* Return empty list on error */ }

  return _json({
    status:  "ok",
    count:   reports.length,
    truncated: listTruncated,
    reports: reports.sort((a, b) => b.generated_at.localeCompare(a.generated_at)),
    request_id: rid,
    gateway: "SENTINEL-APEX/201.0",
  });
}

// -- GET /api/reports/:id ------------------------------------------------------
export async function handleReportGet(request, env, auth, rid, reportId) {
  const tier = (auth.tier || "free").toLowerCase();
  // ZERO-TRUST HARDENING FIX (2026-08-24): was missing .toLowerCase() --
  // real auth.tier is always uppercase (TIERS.FREE/PRO/ENTERPRISE/MSSP,
  // index.js:317), so every tier === "free"/"enterprise" comparison below
  // silently never matched for a real customer. Same bug class fixed
  // repeatedly elsewhere this session (revenue-enforcement.js, sla-monitor.js,
  // alert-engine.js). CORRECTION (post-#369 production assurance audit):
  // this file's routes were wired live into index.js's router by commit
  // 5004465c (PR #313, 2026-09-01) -- POST /api/reports/premium and GET
  // /api/reports/list/{id} are real, tier-gated, revenue-generating
  // endpoints (see index.js's "premium-reports.js routes" block), not
  // dead code. This fix was therefore already live-exploitable before
  // this correction; treat every defect found in this file as real and
  // customer-facing, not latent.
  const safeId = safeStr(reportId || "", 30);

  if (!safeId || !/^rpt_[a-f0-9]{16}$/.test(safeId)) {
    return _json({ error: "invalid_report_id", request_id: rid }, 400);
  }

  if (tier === "free") {
    return _json({ error: "tier_required", upgrade_url: "/upgrade.html?plan=pro", request_id: rid }, 403);
  }

  const loaded = await loadOwnedReport(env, auth, safeId);
  if (loaded.state === "forbidden") return _json({ error: "not_found", request_id: rid }, 404);
  if (loaded.state === "expired") return expiredResponse(safeId, loaded.expired_at, rid);
  if (loaded.state === "found") return _json(loaded.data);
  return _json({ error: "report_not_found", report_id: safeId, request_id: rid }, 404);
}

// -- Retention (90 days) ------------------------------------------------------
// 2026-09-28: reports advertised report_ttl_days: 90 but nothing expired or
// deleted them. Now: an expired report is not served (410) or listed, and
// purgeExpiredReports() -- run from the Worker's 6-hourly cron -- deletes it.
// Age comes from the report's generated_at, else R2's upload time; a report
// whose age cannot be determined is kept, never deleted on a guess.
export const REPORT_TTL_MS = REPORT_CONFIG.REPORT_TTL_DAYS * 86400000;
const REPORT_KEY_RE = /^reports\/premium\/rpt_[a-f0-9]{16}\.json$/;

function reportBornMs(generatedAt, uploaded) {
  const g = Date.parse(typeof generatedAt === "string" ? generatedAt : "");
  if (Number.isFinite(g)) return g;
  const u = uploaded instanceof Date ? uploaded.getTime() : Date.parse(uploaded || "");
  return Number.isFinite(u) ? u : null;
}

export function reportExpired(generatedAt, uploaded, nowMs) {
  const born = reportBornMs(generatedAt, uploaded);
  return born !== null && nowMs - born > REPORT_TTL_MS;
}

function reportExpiresAt(generatedAt, uploaded) {
  const born = reportBornMs(generatedAt, uploaded);
  return born === null ? null : new Date(born + REPORT_TTL_MS).toISOString();
}

function expiredResponse(safeId, expiredAt, rid) {
  return _json({
    error: "report_expired", report_id: safeId, expired_at: expiredAt,
    message: "Premium reports are retained for " + REPORT_CONFIG.REPORT_TTL_DAYS + " days. Generate a new report with POST /api/reports/premium.",
    request_id: rid,
  }, 410);
}

/**
 * Deletes expired premium reports. Bounded per run (pages listed, keys
 * deleted); only keys matching reports/premium/rpt_<16 hex>.json are ever
 * deleted. Returns counts for the cron log; never throws.
 */
export async function purgeExpiredReports(env, nowMs = Date.now(), { maxPages = REPORT_CONFIG.LIST_MAX_PAGES, maxDeletes = 1000 } = {}) {
  const out = { scanned: 0, expired: 0, deleted: 0, truncated: false, error: null };
  if (!env?.INTEL_R2) return { ...out, error: "no_r2_binding" };
  try {
    const doomed = [];
    let cursor; let pages = 0;
    do {
      const page = await env.INTEL_R2.list({ prefix: REPORT_CONFIG.R2_PREFIX, limit: 1000, include: ["customMetadata"], ...(cursor ? { cursor } : {}) });
      for (const obj of page.objects || []) {
        out.scanned++;
        if (!REPORT_KEY_RE.test(obj.key)) continue;
        if (!reportExpired(obj.customMetadata?.generated_at, obj.uploaded, nowMs)) continue;
        out.expired++;
        if (doomed.length < maxDeletes) doomed.push(obj.key);
      }
      cursor = page.truncated ? page.cursor : undefined;
      pages++;
    } while (cursor && pages < maxPages);
    out.truncated = !!cursor || out.expired > doomed.length;
    for (let i = 0; i < doomed.length; i += 1000) {
      const batch = doomed.slice(i, i + 1000);
      await env.INTEL_R2.delete(batch);
      out.deleted += batch.length;
    }
  } catch (e) {
    out.error = String(e && e.message || e).slice(0, 200);
  }
  return out;
}

/**
 * A stored report the caller owns: { state: "found", data } | { state:
 * "forbidden" } | { state: "expired", expired_at } | { state: "missing" }. One ownership check for JSON and
 * CSV. Behaviour is unchanged from the inline version it replaces.
 *
 * TENANT-ISOLATION FIX (CodeRabbit, PR #242 pre-merge review): two
 * compounded bugs here -- (1) `auth.key_id` does not exist on
 * resolveAuth()'s return object (index.js:328-382), so this
 * ownership check never activated for any real request; (2) even
 * with the field name fixed, the old code read `data.metadata.key_id`
 * -- the report BODY's own `metadata` object (platform_version,
 * dashboard_url, pdf_download_url, etc.) -- which never had a
 * key_id field at all; the real owner was only ever written to the
 * R2 OBJECT's customMetadata (a separate side-channel from the JSON
 * body), in handlePremiumReport above. Fixed to read
 * obj.customMetadata.key_id and compare against auth.sub (the
 * correct per-customer identity), and to fail closed: a report
 * with no recorded owner, or a requester that doesn't match it, is
 * treated as not found rather than allowed through.
 */
async function loadOwnedReport(env, auth, safeId) {
  try {
    if (env?.INTEL_R2) {
      const obj = await env.INTEL_R2.get(`${REPORT_CONFIG.R2_PREFIX}${safeId}.json`);
      if (obj) {
        const ownerId = obj.customMetadata?.key_id || "";
        if (!auth.is_admin && (!ownerId || ownerId !== (auth.sub || ""))) return { state: "forbidden" };
        if (reportExpired(obj.customMetadata?.generated_at, obj.uploaded, Date.now())) {
          return { state: "expired", expired_at: reportExpiresAt(obj.customMetadata?.generated_at, obj.uploaded) };
        }
        return { state: "found", data: await obj.json() };
      }
    }
  } catch { /* Fall through to missing */ }
  return { state: "missing" };
}

// -- GET /api/reports/:id/csv --------------------------------------------------
export const CSV_SECTIONS = Object.freeze(["advisories", "cves", "iocs"]);

// A cell starting with = + - @ (or tab / CR) is a formula in Excel and
// Sheets; prefix a quote so a hostile advisory title cannot execute on the
// analyst's machine (CSV injection). Numbers are written as numbers.
function csvCell(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  let t = Array.isArray(v) ? v.join(";") : String(v);
  if (/^[=+\-@\t\r]/.test(t)) t = "'" + t;
  return /[",\r\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
}

/** A stored report section as RFC 4180 CSV (CRLF line endings). */
export function buildReportCsv(report, section = "advisories") {
  const r = report && typeof report === "object" ? report : {};
  let cols; let rows;
  if (section === "cves") {
    cols = ["cve_id", "title", "severity", "cvss_score", "epss_score", "kev_present", "exploit_available", "exploit_maturity", "actor_tag", "source", "processed_at"];
    rows = ((r.cve_intelligence || {}).top_cves || []).map((c) => ({ ...c, cve_id: c.id }));
  } else if (section === "iocs") {
    cols = ["value", "type", "confidence", "severity", "actor_tag", "source", "context"];
    rows = (r.ioc_intelligence || {}).ioc_table || [];
  } else {
    cols = ["id", "title", "severity", "priority_band", "priority_score", "risk_score", "cve_ids", "kev_present", "actor_tag", "source", "processed_at"];
    rows = (r.advisories || []).map((a) => ({
      ...a,
      priority_band: a.priority ? a.priority.band : null,
      priority_score: a.priority ? a.priority.score : null,
      cve_ids: Array.isArray(a.cve_ids) ? a.cve_ids : (a.cve_id ? [a.cve_id] : []),
    }));
  }
  return [["report_id", ...cols].join(","), ...rows.map((row) => [csvCell(r.report_id), ...cols.map((c) => csvCell(row[c]))].join(","))].join("\r\n") + "\r\n";
}

export async function handleReportCsv(request, env, auth, rid, reportId) {
  const tier = (auth.tier || "free").toLowerCase();
  const safeId = safeStr(reportId || "", 30);
  if (!safeId || !/^rpt_[a-f0-9]{16}$/.test(safeId)) return _json({ error: "invalid_report_id", request_id: rid }, 400);
  if (tier === "free") return _json({ error: "tier_required", upgrade_url: "/upgrade.html?plan=pro", request_id: rid }, 403);
  let section = "advisories";
  try { section = new URL(request.url).searchParams.get("section") || "advisories"; } catch { /* default */ }
  if (!CSV_SECTIONS.includes(section)) return _json({ error: "invalid_section", allowed: CSV_SECTIONS, request_id: rid }, 400);
  const loaded = await loadOwnedReport(env, auth, safeId);
  if (loaded.state === "forbidden") return _json({ error: "not_found", request_id: rid }, 404);
  if (loaded.state === "expired") return expiredResponse(safeId, loaded.expired_at, rid);
  if (loaded.state !== "found") return _json({ error: "report_not_found", report_id: safeId, request_id: rid }, 404);
  return new Response(buildReportCsv(loaded.data, section), {
    status: 200,
    headers: {
      "Content-Type":        "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${safeId}-${section}.csv"`,
      "Cache-Control":       "no-store",
      "X-Content-Type-Options": "nosniff",
      "X-Sentinel-Module":   "premium-reports/201.0",
    },
  });
}


// -- GET /api/reports/:id/print ------------------------------------------------
// Print-ready HTML of a stored report: the browser's Print -> Save as PDF
// produces the PDF, so no render service is needed. /api/reports/:id/pdf
// redirects here (index.js). The page carries no script and loads nothing
// external (CSP below); every value is HTML-escaped.
//
// @page margin 0 turns off the browser's printed header / footer, which
// would otherwise print the page URL -- including ?api_key= when a browser
// opened the report that way -- onto every page of the PDF.
export const PRINT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";
const PRINT_MAX_ROWS = Object.freeze({ cves: 50, iocs: 200, advisories: 200, actors: 20 });

function esc(v) {
  if (v === null || v === undefined || v === "") return "&mdash;";
  return String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function num(v, digits = 1) {
  return typeof v === "number" && Number.isFinite(v) ? esc(Number.isInteger(v) ? v : v.toFixed(digits)) : "&mdash;";
}
function sevTag(v) {
  const k = String(v || "").toUpperCase();
  const cls = ["CRITICAL", "HIGH", "MEDIUM", "LOW"].includes(k) ? k.toLowerCase() : "none";
  return `<span class="sev sev-${cls}">${esc(k || "N/A")}</span>`;
}
function table(cols, rows, empty) {
  if (!rows.length) return `<p class="empty">${esc(empty)}</p>`;
  return `<div class="tw"><table><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function capNote(total, shown, what) {
  return total > shown ? `<p class="note">Showing ${shown} of ${total} ${esc(what)}. The complete list is in the JSON and CSV exports.</p>` : "";
}

/** A stored report as a self-contained, print-ready HTML document. */
export function buildReportPrintHtml(report) {
  const r = report && typeof report === "object" ? report : {};
  const ex = r.executive_summary || {};
  const cve = r.cve_intelligence || {};
  const mitre = r.mitre_attack_coverage || {};
  const actors = (r.actor_intelligence || {}).actors || [];
  const ioc = r.ioc_intelligence || {};
  const advisories = Array.isArray(r.advisories) ? r.advisories : [];
  const fresh = r.intelligence_freshness || null;
  const cov = r.coverage || null;
  const tlp = r.classification || "TLP:AMBER";

  const kpi = (label, value) => `<div class="kpi"><div class="kpi-v">${value}</div><div class="kpi-l">${esc(label)}</div></div>`;
  const freshness = fresh
    ? (fresh.live ? `<p class="status ok">Generated from LIVE intelligence (feed generated ${esc(fresh.feed_generated_at)}).</p>`
      : `<p class="status warn">${esc(fresh.label)}: feed generated ${esc(fresh.feed_generated_at)} (${esc(fresh.freshness_status)}).</p>`)
    : `<p class="status">Feed freshness was not recorded for this report (generated before freshness tracking).</p>`;

  const priority = Array.isArray(ex.priority_actions) ? ex.priority_actions : [];
  const topCves = Array.isArray(cve.top_cves) ? cve.top_cves : [];
  const iocRows = Array.isArray(ioc.ioc_table) ? ioc.ioc_table : [];
  const tactics = Array.isArray(mitre.top_tactics) ? mitre.top_tactics : [];
  const techniques = Array.isArray(mitre.techniques_list) ? mitre.techniques_list : [];

  const body = `
<header class="cover">
  <div class="brand">CYBERDUDEBIVASH&reg; SENTINEL APEX</div>
  <div class="tlp">${esc(tlp)}</div>
  <h1>${esc(r.report_title || "Threat Intelligence Report")}</h1>
  <dl class="meta">
    <dt>Report ID</dt><dd>${esc(r.report_id)}</dd>
    <dt>Type</dt><dd>${esc(r.report_type)}</dd>
    <dt>Period</dt><dd>${esc(r.report_period)}</dd>
    <dt>Generated</dt><dd>${esc(r.generated_at)}</dd>
    <dt>Advisories</dt><dd>${num(r.advisories_count)}</dd>
  </dl>
  ${freshness}
  ${cov ? `<p class="note">Coverage: advisories published ${esc(cov.earliest_published)} to ${esc(cov.latest_published)}; ${num(cov.undated_advisories)} undated; ${num(cov.excluded_outside_period)} excluded as outside the period. ${esc(cov.basis)}</p>` : ""}
</header>

<section>
  <h2>1. Executive summary</h2>
  <div class="kpis">
    ${kpi("Advisories", num(ex.total_advisories))}${kpi("Critical", num(ex.critical_count))}${kpi("High", num(ex.high_count))}${kpi("CISA KEV advisories", num(ex.kev_confirmed))}${kpi("CVEs", num(cve.total_cves))}
  </div>
  <p><strong>Threat landscape:</strong> ${esc(ex.threat_landscape)}</p>
  <p><strong>CVE exposure:</strong> ${esc(ex.cve_exposure)} &nbsp; <strong>ATT&amp;CK:</strong> ${esc(ex.mitre_coverage)} &nbsp; <strong>Top actor:</strong> ${esc(ex.top_actor)}</p>
  <h3>Recommendations</h3>
  ${(ex.key_recommendations || []).length ? `<ol>${ex.key_recommendations.map((k) => `<li>${esc(k)}</li>`).join("")}</ol>` : `<p class="empty">None recorded.</p>`}
  <h3>Act first</h3>
  ${table(["Priority", "Score", "Advisory", "CVEs", "Evidence"], priority.map((p) => [sevTag(p.band), num(p.score, 0), esc(p.title), (p.cve_ids || []).map((c) => `<span class="id">${esc(c)}</span>`).join(", ") || "&mdash;", esc((p.evidence || []).join("; "))]), "Not recorded for this report (generated before priority ranking).")}
</section>

<section>
  <h2>2. CVE intelligence</h2>
  <p>${num(cve.total_cves)} CVEs &middot; ${num(cve.kev_count)} CISA KEV &middot; ${num(cve.exploit_available_count)} with public exploit evidence &middot; ${esc(cve.exploitation_risk)}</p>
  ${table(["CVE", "Severity", "CVSS", "EPSS %", "KEV", "Exploit", "Title"], topCves.slice(0, PRINT_MAX_ROWS.cves).map((c) => [`<span class="mono id">${esc(c.id)}</span>`, sevTag(c.severity), num(c.cvss_score), num(c.epss_score, 2), c.kev_present ? "<strong>YES</strong>" : "no", c.exploit_available ? esc(c.exploit_maturity || "yes") : "no", esc(c.title)]), "No CVEs in scope.")}
  ${capNote(topCves.length, Math.min(topCves.length, PRINT_MAX_ROWS.cves), "CVEs")}
</section>

<section>
  <h2>3. MITRE ATT&amp;CK coverage</h2>
  <p>${num(mitre.unique_techniques)} unique techniques &middot; coverage ${num(mitre.coverage_score_pct, 0)}% (${esc(mitre.coverage_label)})</p>
  ${table(["Tactic", "Advisories"], tactics.map((t) => [esc(t.tactic), num(t.count)]), "No tactics recorded.")}
  ${techniques.length ? `<p class="mono small">${techniques.map(esc).join(" &middot; ")}</p>` : ""}
</section>

<section>
  <h2>4. Threat actor intelligence</h2>
  ${table(["Actor", "Advisories", "Max risk", "Campaigns", "IOCs", "TTPs"], actors.slice(0, PRINT_MAX_ROWS.actors).map((a) => [esc(a.actor_tag), num(a.advisory_count), num(a.max_risk, 2), esc((a.campaigns || []).join(", ")), num(a.ioc_count), num(a.ttp_count)]), "No actors recorded.")}
</section>

<section>
  <h2>5. Indicators of compromise</h2>
  ${table(["Indicator", "Type", "Confidence", "Severity", "Actor", "Context"], iocRows.slice(0, PRINT_MAX_ROWS.iocs).map((i) => [`<span class="mono">${esc(i.value)}</span>`, esc(i.type), num(i.confidence, 0), sevTag(i.severity), esc(i.actor_tag), esc(i.context)]), "No indicators in scope.")}
  ${capNote(iocRows.length, Math.min(iocRows.length, PRINT_MAX_ROWS.iocs), "indicators")}
</section>

<section>
  <h2>6. Advisories</h2>
  ${table(["Priority", "Severity", "Advisory", "CVEs", "KEV", "Source", "Processed"], advisories.slice(0, PRINT_MAX_ROWS.advisories).map((a) => [a.priority ? sevTag(a.priority.band) + " " + num(a.priority.score, 0) : "&mdash;", sevTag(a.severity), esc(a.title), (Array.isArray(a.cve_ids) ? a.cve_ids : (a.cve_id ? [a.cve_id] : [])).map((c) => `<span class="id">${esc(c)}</span>`).join(", ") || "&mdash;", a.kev_present ? "<strong>YES</strong>" : "no", esc(a.source), esc(a.processed_at)]), "No advisories in scope.")}
  ${capNote(advisories.length, Math.min(advisories.length, PRINT_MAX_ROWS.advisories), "advisories")}
</section>

<footer>
  <p>${esc(tlp)}. ${esc((r.metadata || {}).copyright || "CYBERDUDEBIVASH(R) SENTINEL APEX")}</p>
  <p>Prepared from the Sentinel APEX feed. Scores cite the feed fields they came from; missing evidence is never counted as zero risk.</p>
</footer>`;

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${esc(r.report_title || "Threat Intelligence Report")} - ${esc(r.report_id)}</title>
<style>
@page { size: A4; margin: 0; }
:root { --ink:#111827; --muted:#4b5563; --line:#d1d5db; --band:#f3f4f6; --accent:#0f3d6e; }
* { box-sizing: border-box; }
html { background:#e5e7eb; }
body { margin:0 auto; max-width:210mm; min-height:297mm; padding:14mm 14mm 16mm; background:#fff; color:var(--ink);
  font:10pt/1.45 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.screen-hint { font-size:9pt; color:var(--muted); border:1px dashed var(--line); padding:6px 10px; margin-bottom:10px; }
.cover { border-bottom:3px solid var(--accent); padding-bottom:8px; margin-bottom:10px; }
.brand { font-weight:800; letter-spacing:.08em; color:var(--accent); font-size:9pt; }
.tlp { float:right; margin-top:-14px; background:#b45309; color:#fff; font-weight:800; font-size:8.5pt; padding:2px 8px; border-radius:3px; }
h1 { font-size:17pt; margin:6px 0 8px; }
h2 { font-size:12.5pt; color:var(--accent); border-bottom:1px solid var(--line); padding-bottom:3px; margin:16px 0 6px; break-after:avoid; }
h3 { font-size:10.5pt; margin:10px 0 4px; break-after:avoid; }
dl.meta { display:grid; grid-template-columns:auto 1fr auto 1fr; gap:2px 10px; margin:0 0 6px; font-size:9pt; }
dl.meta dt { color:var(--muted); } dl.meta dd { margin:0; }
.status { padding:5px 8px; border-left:4px solid var(--line); background:var(--band); font-size:9pt; }
.status.ok { border-color:#15803d; } .status.warn { border-color:#b91c1c; background:#fef2f2; font-weight:700; }
.note { color:var(--muted); font-size:8.5pt; }
.kpis { display:flex; gap:6px; margin:6px 0 8px; }
.kpi { flex:1; border:1px solid var(--line); border-radius:4px; padding:5px 7px; }
.kpi-v { font-size:15pt; font-weight:800; } .kpi-l { font-size:8pt; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
table { width:100%; border-collapse:collapse; font-size:8.5pt; margin:4px 0 6px; }
thead { display:table-header-group; }
th { text-align:left; background:var(--band); border-bottom:1px solid var(--line); padding:3px 5px; font-size:8pt; text-transform:uppercase; letter-spacing:.03em; }
td { border-bottom:1px solid #e5e7eb; padding:3px 5px; vertical-align:top; overflow-wrap:break-word; }
.tw { overflow-x:auto; }
.id { white-space:nowrap; }
tr { break-inside:avoid; }
.mono { font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace; } .small { font-size:8pt; }
.sev { display:inline-block; font-size:7.5pt; font-weight:800; padding:0 5px; border-radius:3px; border:1px solid currentColor; white-space:nowrap; }
.sev-critical { color:#b91c1c; } .sev-high { color:#c2410c; } .sev-medium { color:#a16207; } .sev-low { color:#15803d; } .sev-none { color:var(--muted); }
.empty { color:var(--muted); font-style:italic; }
footer { margin-top:18px; border-top:1px solid var(--line); padding-top:6px; font-size:8pt; color:var(--muted); }
@media print { html { background:#fff; } body { max-width:none; min-height:0; } .screen-hint { display:none; } .tw { overflow:visible; } }
@media (max-width:640px) { body { padding:16px; } dl.meta { grid-template-columns:auto 1fr; } .kpis { flex-wrap:wrap; } .kpi { flex:1 1 40%; } .tlp { float:none; display:inline-block; margin:4px 0 0; } }
</style></head>
<body>
<p class="screen-hint">Print-ready report. Use your browser's Print, then "Save as PDF", to download it as a PDF.</p>
${body}
</body></html>`;
}

export async function handleReportPrint(request, env, auth, rid, reportId) {
  const tier = (auth.tier || "free").toLowerCase();
  const safeId = safeStr(reportId || "", 30);
  if (!safeId || !/^rpt_[a-f0-9]{16}$/.test(safeId)) return _json({ error: "invalid_report_id", request_id: rid }, 400);
  if (tier === "free") return _json({ error: "tier_required", upgrade_url: "/upgrade.html?plan=pro", request_id: rid }, 403);
  const loaded = await loadOwnedReport(env, auth, safeId);
  if (loaded.state === "forbidden") return _json({ error: "not_found", request_id: rid }, 404);
  if (loaded.state === "expired") return expiredResponse(safeId, loaded.expired_at, rid);
  if (loaded.state !== "found") return _json({ error: "report_not_found", report_id: safeId, request_id: rid }, 404);
  return new Response(buildReportPrintHtml(loaded.data), {
    status: 200,
    headers: {
      "Content-Type":            "text/html; charset=utf-8",
      "Content-Security-Policy": PRINT_CSP,
      "Cache-Control":           "no-store",
      "X-Robots-Tag":            "noindex, nofollow",
      "X-Content-Type-Options":  "nosniff",
      "X-Sentinel-Module":       "premium-reports/201.0",
    },
  });
}
