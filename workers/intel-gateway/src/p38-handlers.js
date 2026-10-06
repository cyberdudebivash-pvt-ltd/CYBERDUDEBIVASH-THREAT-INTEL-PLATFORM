/**
 * workers/intel-gateway/src/p38-handlers.js
 * P38.0 Enterprise Platform Governance & Permanent Stabilization
 *
 * ADR-P38-002: This handler layer exposes the governance framework
 * as queryable API endpoints.  All heavy computation is delegated
 * to existing P20/P25/P26 engines via import  -  no business logic
 * is re-implemented here.
 *
 * Reuse map:
 *   computeP20QualityScore      -> p20-handlers.js (unchanged)
 *   computeEnterpriseTrustScore -> p25-handlers.js (unchanged)
 *   computeP26Grade             -> p26-handlers.js (unchanged)
 *
 * 12 exported handlers / 12 API routes:
 *   /api/v1/p38/schema-registry   - canonical field definitions
 *   /api/v1/p38/feed-governance   - feed registry + health
 *   /api/v1/p38/schema-drift      - unknown / deprecated field detection
 *   /api/v1/p38/enrichment-audit  - enrichment coverage across feeds
 *   /api/v1/p38/confidence-audit  - confidence calibration status
 *   /api/v1/p38/iq-index          - Intelligence Quality Index (composite)
 *   /api/v1/p38/source-diversity  - weighted source diversity metrics
 *   /api/v1/p38/certification     - P38 certification chain status
 *   /api/v1/p38/executive         - executive governance dashboard
 *   /api/v1/p38/reliability       - reliability / dedup / drift metrics
 *   /api/v1/p38/metrics           - platform-wide governance KPIs
 *   /api/v1/p38/observability     - observability health endpoint
 */

import { computeP20QualityScore }      from './p20-handlers.js';
import { computeEnterpriseTrustScore } from './p25-handlers.js';
import { computeP26Grade }             from './p26-handlers.js';

// ---------------------------------------------------------------------------
// Internal helpers  -  feed loading, field coverage, diversity
// These mirror the Python canonical validators in p38_shared_validators.py
// but are scoped to the Worker runtime (no filesystem access  -  reads KV/R2).
// ---------------------------------------------------------------------------

const REQUIRED_FIELDS = ['id', 'title', 'severity'];

const ENRICHMENT_FIELDS = {
  cvss_score:  x => x.cvss_score != null && parseFloat(x.cvss_score) > 0,
  epss:        x => x.epss != null && x.epss !== '',
  kev:         x => !!(x.kev || x.kev_confirmed),
  confidence:  x => x.confidence != null && x.confidence !== '',
  actor_tag:   x => !!(x.actor_tag || x.actor || x.threat_actor || '').toString().trim(),
  iocs:        x => Array.isArray(x.iocs) && x.iocs.length > 0,
  ttps:        x => (Array.isArray(x.ttps) && x.ttps.length > 0) || (Array.isArray(x.mitre_tactics) && x.mitre_tactics.length > 0),
  sigma_rule:  x => !!x.sigma_rule,
  cve_ids:     x => (Array.isArray(x.cve_ids) && x.cve_ids.length > 0) || !!x.cve_id,
  description: x => (x.description || '').length >= 50,
};

function _fieldPct(items, check) {
  if (!items.length) return 0;
  return 100 * items.filter(check).length / items.length;
}

function _enrichmentAudit(items) {
  const out = {};
  for (const [field, check] of Object.entries(ENRICHMENT_FIELDS)) {
    out[field + '_pct'] = Math.round(_fieldPct(items, check) * 10) / 10;
  }
  return out;
}

function _sourceDiversity(items) {
  if (!items.length) return { distinct: 0, top_dominance_pct: 0, top_source: '' };
  const counts = {};
  for (const x of items) {
    const s = x.source || x.feed_source || 'unknown';
    counts[s] = (counts[s] || 0) + 1;
  }
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return {
    distinct:          sorted.length,
    top_source:        sorted[0][0],
    top_dominance_pct: Math.round(1000 * sorted[0][1] / items.length) / 10,
    sources:           Object.fromEntries(sorted.slice(0, 10)),
  };
}

function _detectFeedType(items) {
  if (!items.length) return 'UNKNOWN';
  const counts = {};
  for (const x of items) {
    const s = (x.source || x.feed_source || '').toLowerCase();
    counts[s] = (counts[s] || 0) + 1;
  }
  const topSrc = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || '';
  return ['nvd_cve', 'cve', 'nvd', 'mitre_cve'].some(k => topSrc.includes(k))
    ? 'CVE_FEED' : 'BROAD_THREAT_INTEL';
}

function _schemaDrift(items) {
  // Both sets are derived from SCHEMA_REGISTRY (single source within this
  // file) rather than hand-typed, so the drift detector cannot itself drift
  // from the registry it is checking against.
  const KNOWN_FIELDS = new Set(Object.keys(SCHEMA_REGISTRY));
  const DEPRECATED = new Set(SCHEMA_DEPRECATED_FIELDS);
  const observed = new Set();
  for (const item of items.slice(0, 50)) {
    Object.keys(item).forEach(k => observed.add(k));
  }
  return {
    unknown_fields:    [...observed].filter(f => !KNOWN_FIELDS.has(f)).sort(),
    deprecated_fields: [...observed].filter(f => DEPRECATED.has(f)).sort(),
    drift_count:       [...observed].filter(f => !KNOWN_FIELDS.has(f)).length,
  };
}

function _computeIQIndex(items) {
  if (!items.length) return { iq_index: 0, dimensions: {} };
  const sample = items.slice(0, 30);
  let p20sum = 0, p25sum = 0, p26gradeSum = 0;
  const GRADE_MAP = { 'A+': 100, 'A': 95, 'A-': 90, 'B+': 85, 'B': 80,
    'B-': 75, 'C+': 70, 'C': 65, 'C-': 60, 'D': 50, 'F': 30 };
  for (const item of sample) {
    try { const r = computeP20QualityScore(item); p20sum += (r?.score ?? r?.total ?? 0); } catch {}
    try { const r = computeEnterpriseTrustScore(item); p25sum += (r?.score ?? 0); } catch {}
    try { const r = computeP26Grade(item); p26gradeSum += (GRADE_MAP[r?.grade] ?? 50); } catch {}
  }
  const n = sample.length;
  const p20avg  = n > 0 ? p20sum  / n : 0;
  const p25avg  = n > 0 ? p25sum  / n : 0;
  const p26avg  = n > 0 ? p26gradeSum / n : 0;
  const enrich  = _enrichmentAudit(items);
  const enrichScore = (
    enrich.cvss_score_pct * 0.25 +
    enrich.epss_pct       * 0.20 +
    enrich.confidence_pct * 0.20 +
    enrich.cve_ids_pct    * 0.15 +
    enrich.iocs_pct       * 0.10 +
    enrich.ttps_pct       * 0.10
  ) / 100;
  const iqIndex = Math.round(
    p20avg  * 0.30 +
    p25avg  * 0.25 +
    p26avg  * 0.20 +
    enrichScore * 100 * 0.25
  );
  return {
    iq_index: Math.min(100, Math.max(0, iqIndex)),
    dimensions: {
      p20_quality_avg:      Math.round(p20avg  * 10) / 10,
      p25_trust_avg:        Math.round(p25avg  * 10) / 10,
      p26_grade_score_avg:  Math.round(p26avg  * 10) / 10,
      enrichment_composite: Math.round(enrichScore * 1000) / 10,
    },
  };
}

function _reliabilityMetrics(items) {
  const n = items.length;
  if (!n) return { dedup_ok: false, freshness_pct: 0, ceiling_violations: 0 };
  const ids = items.map(x => x.id);
  const unique = new Set(ids).size;
  const fresh  = items.filter(x => x.processed_at || x.published_at || x.timestamp).length;
  const ceiling = items.filter(x => (x.risk_score || 0) > 10).length;
  return {
    total_items:        n,
    unique_ids:         unique,
    dedup_ok:           unique === n,
    freshness_pct:      Math.round(100 * fresh / n),
    ceiling_violations: ceiling,
  };
}

// ---------------------------------------------------------------------------
// FEED REGISTRY  -  mirrors Python FEED_REGISTRY for JS consumption
// ---------------------------------------------------------------------------
const FEED_REGISTRY = {
  root:       { label: 'Root Snapshot Feed',       purpose: 'CI snapshot; NOT live production', feed_type: 'SNAPSHOT',      items_expected: 72,  enrichment: false, commercial: false },
  live:       { label: 'Live Production CVE Feed', purpose: 'Primary enriched production feed', feed_type: 'CVE_FEED',       items_expected: 58,  enrichment: true,  commercial: true  },
  research:   { label: 'Aggregate Research Feed',  purpose: 'Broad APT/malware/campaign feed',  feed_type: 'BROAD_INTEL',    items_expected: 159, enrichment: false, commercial: false },
  baseline:   { label: 'Commercial Baseline',      purpose: '491-item commercial feed',         feed_type: 'COMMERCIAL_CVE', items_expected: 491, enrichment: true,  commercial: true  },
  gold:       { label: 'Commercial Gold',          purpose: '260-item premium feed',            feed_type: 'COMMERCIAL_CVE', items_expected: 260, enrichment: true,  commercial: true  },
  silver:     { label: 'Commercial Silver',        purpose: '397-item mid-tier feed',           feed_type: 'COMMERCIAL_CVE', items_expected: 397, enrichment: true,  commercial: true  },
  standard:   { label: 'Commercial Standard',      purpose: '491-item entry-level feed',        feed_type: 'COMMERCIAL_CVE', items_expected: 491, enrichment: true,  commercial: true  },
  executive:  { label: 'Executive Intelligence',   purpose: '220-item curated summary',         feed_type: 'EXECUTIVE',      items_expected: 220, enrichment: true,  commercial: true  },
  trial:      { label: 'Trial / Demo Feed',        purpose: '10-item demo sample',              feed_type: 'TRIAL',          items_expected: 10,  enrichment: false, commercial: true  },
  enterprise: { label: 'Enterprise Dedicated',     purpose: '23-item enterprise feed',          feed_type: 'ENTERPRISE',     items_expected: 23,  enrichment: true,  commercial: true  },
  mssp:       { label: 'MSSP Feed',                purpose: '58-item MSSP-grade feed',          feed_type: 'MSSP',           items_expected: 58,  enrichment: true,  commercial: true  },
  public:     { label: 'Public API Feed',          purpose: '58-item public-facing feed',       feed_type: 'PUBLIC',         items_expected: 58,  enrichment: true,  commercial: false },
};

// ---------------------------------------------------------------------------
// SCHEMA REGISTRY  -  mirrors Python SCHEMA_REGISTRY for JS/Worker consumption
// (Workers have no Python runtime, so this cannot import the source directly.)
// Generated field-for-field from scripts/p38_shared_validators.py:SCHEMA_REGISTRY
// by scripts/p38_schema_mirror_check.py, which also CI-checks the two stay in
// sync. Regenerate via that script rather than hand-editing on schema changes.
// ---------------------------------------------------------------------------
const SCHEMA_REGISTRY = {
  // -- identity ----------------------------------------------------
  "id": { required: true, type: "str", domain: "identity", nullable: false, version_introduced: "v1.0" },
  "title": { required: true, type: "str", domain: "identity", nullable: false, version_introduced: "v1.0" },
  "severity": { required: true, type: "str", domain: "identity", nullable: false, version_introduced: "v1.0" },
  "description": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v1.0" },
  "source": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v1.0" },
  "feed_source": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v2.0" },
  "source_url": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v1.0" },
  "published_at": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v1.0" },
  "timestamp": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v1.0" },
  "processed_at": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v2.0" },
  "schema_version": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v3.0" },
  "status": { required: false, type: "str", domain: "identity", nullable: true, version_introduced: "v2.0" },
  "is_published": { required: false, type: "bool", domain: "identity", nullable: true, version_introduced: "v2.0" },
  "is_new": { required: false, type: "bool", domain: "identity", nullable: true, version_introduced: "v2.0" },
  // -- vulnerability -----------------------------------------------
  "cve_id": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v1.0" },
  "cve_ids": { required: false, type: "list", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "cves": { required: false, type: "list", domain: "vulnerability", nullable: true, version_introduced: "v2.0", deprecated: true, replacement: "cve_ids" },
  "cvss_score": { required: false, type: "float", domain: "vulnerability", nullable: true, version_introduced: "v1.0" },
  "cvss_vector": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "cvss_source": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "cvss_estimated": { required: false, type: "bool", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "epss": { required: false, type: "float", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "epss_score": { required: false, type: "float", domain: "vulnerability", nullable: true, version_introduced: "v3.0", deprecated: true, replacement: "epss" },
  "epss_normalized": { required: false, type: "float", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "kev": { required: false, type: "bool", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "kev_confirmed": { required: false, type: "bool", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "kev_date": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "kev_due": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "kev_name": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "kev_action": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "kev_product": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "kev_present": { required: false, type: "bool", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "nvd_status": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "nvd_checked_at": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "nvd_disclosure": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "vuln_class": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "exploit_maturity": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "exploit_count": { required: false, type: "int", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "exploit_refs": { required: false, type: "list", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "poc_github_count": { required: false, type: "int", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "metasploit_available": { required: false, type: "bool", domain: "vulnerability", nullable: true, version_introduced: "v3.0" },
  "attack_vector": { required: false, type: "str", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  "affected_products": { required: false, type: "list", domain: "vulnerability", nullable: true, version_introduced: "v2.0" },
  // -- actor -------------------------------------------------------
  "actor_tag": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v2.0", note: "canonical actor field" },
  "actor": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v1.0", deprecated: true, replacement: "actor_tag" },
  "actor_name": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v2.0" },
  "actor_display_name": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "actor_aliases": { required: false, type: "list", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "actor_code": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v2.0" },
  "actor_type": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v2.0" },
  "actor_country": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v2.0" },
  "actor_region": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "actor_motivation": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v2.0" },
  "actor_sectors": { required: false, type: "list", domain: "actor", nullable: true, version_introduced: "v2.0" },
  "actor_threat_level": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "actor_ttps": { required: false, type: "list", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "actor_malware": { required: false, type: "list", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "actor_mitre_id": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "actor_confidence_label": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "verified_actor": { required: false, type: "bool", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "attribution_status": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v3.0" },
  "attribution_assessment": { required: false, type: "dict", domain: "actor", nullable: true, version_introduced: "v3.0" },
  // -- confidence --------------------------------------------------
  "confidence": { required: false, type: "float", domain: "confidence", nullable: true, version_introduced: "v1.0" },
  "confidence_score": { required: false, type: "float", domain: "confidence", nullable: true, version_introduced: "v2.0", deprecated: true, replacement: "confidence" },
  "confidence_score_v2": { required: false, type: "float", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "confidence_label": { required: false, type: "str", domain: "confidence", nullable: true, version_introduced: "v2.0" },
  "confidence_rationale": { required: false, type: "str", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "confidence_reason": { required: false, type: "str", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "confidence_factors": { required: false, type: "dict", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "confidence_engine_version": { required: false, type: "str", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "confidence_enriched_at": { required: false, type: "str", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "source_trust_score": { required: false, type: "float", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "source_reliability": { required: false, type: "str", domain: "confidence", nullable: true, version_introduced: "v2.0" },
  "source_quality": { required: false, type: "str", domain: "confidence", nullable: true, version_introduced: "v2.0" },
  "corroboration_score": { required: false, type: "float", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "corroboration_strength": { required: false, type: "str", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "corroboration_count": { required: false, type: "int", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "corroborating_sources": { required: false, type: "list", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  "corroboration_sources": { required: false, type: "list", domain: "confidence", nullable: true, version_introduced: "v3.0", deprecated: true, replacement: "corroborating_sources" },
  "ioc_confidence": { required: false, type: "float", domain: "confidence", nullable: true, version_introduced: "v3.0" },
  // -- ioc ---------------------------------------------------------
  "iocs": { required: false, type: "list", domain: "ioc", nullable: true, version_introduced: "v1.0" },
  "iocs_by_type": { required: false, type: "dict", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "ioc_types": { required: false, type: "list", domain: "ioc", nullable: true, version_introduced: "v2.0" },
  "ioc_count": { required: false, type: "int", domain: "ioc", nullable: true, version_introduced: "v2.0" },
  "ioc_counts": { required: false, type: "dict", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "real_ioc_count": { required: false, type: "int", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "indicator_count": { required: false, type: "int", domain: "ioc", nullable: true, version_introduced: "v2.0" },
  "ioc_quality": { required: false, type: "str", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "ioc_quality_label": { required: false, type: "str", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "ioc_quality_score": { required: false, type: "float", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "ioc_threat_level": { required: false, type: "str", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "ioc_fp_removed": { required: false, type: "int", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "ioc_note": { required: false, type: "str", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "ioc_paywall": { required: false, type: "bool", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  "ioc_extraction_meta": { required: false, type: "dict", domain: "ioc", nullable: true, version_introduced: "v3.0" },
  // -- detection ---------------------------------------------------
  "ttps": { required: false, type: "list", domain: "detection", nullable: true, version_introduced: "v1.0" },
  "ttp_count": { required: false, type: "int", domain: "detection", nullable: true, version_introduced: "v2.0" },
  "ttp_quality": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "mitre_tactics": { required: false, type: "list", domain: "detection", nullable: true, version_introduced: "v2.0" },
  "attck_techniques": { required: false, type: "list", domain: "detection", nullable: true, version_introduced: "v2.0" },
  "attck_technique_ids": { required: false, type: "list", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "attck_notes": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "attck_verification": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "kill_chain_phase": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v2.0" },
  "kill_chain_phases": { required: false, type: "list", domain: "detection", nullable: true, version_introduced: "v2.0" },
  "sigma_rule": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v2.0" },
  "suricata_rule": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v2.0" },
  "kql_query": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "detection_generated_at": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "detection_production_ready": { required: false, type: "bool", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "detection_quality_status": { required: false, type: "str", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "detection_rules_production_ready": { required: false, type: "bool", domain: "detection", nullable: true, version_introduced: "v3.0" },
  "detection_rules_total": { required: false, type: "int", domain: "detection", nullable: true, version_introduced: "v3.0" },
  // -- quality -----------------------------------------------------
  "intelligence_grade": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v2.0" },
  "iq_score": { required: false, type: "float", domain: "quality", nullable: true, version_introduced: "v3.0" },
  "iq_breakdown": { required: false, type: "dict", domain: "quality", nullable: true, version_introduced: "v3.0" },
  "enrichment_score": { required: false, type: "float", domain: "quality", nullable: true, version_introduced: "v3.0" },
  "report_quality": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v2.0" },
  "grade_notes": { required: false, type: "list", domain: "quality", nullable: true, version_introduced: "v2.0" },
  "grade_notes_v2": { required: false, type: "list", domain: "quality", nullable: true, version_introduced: "v3.0" },
  "graded_at": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v2.0" },
  "graded_at_v2": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v3.0" },
  "grade_engine_version": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v3.0" },
  "validation_status": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v2.0" },
  "verification_status": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v2.0" },
  "analyst_verdict": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v3.0" },
  "publication_decision": { required: false, type: "str", domain: "quality", nullable: true, version_introduced: "v3.0" },
  // -- risk --------------------------------------------------------
  "risk_score": { required: false, type: "float", domain: "risk", nullable: true, version_introduced: "v1.0" },
  "risk_score_reasoning": { required: false, type: "str", domain: "risk", nullable: true, version_introduced: "v3.0" },
  "threat_level": { required: false, type: "str", domain: "risk", nullable: true, version_introduced: "v1.0" },
  "threat_priority": { required: false, type: "str", domain: "risk", nullable: true, version_introduced: "v2.0" },
  "threat_category": { required: false, type: "str", domain: "risk", nullable: true, version_introduced: "v1.0" },
  "threat_type": { required: false, type: "str", domain: "risk", nullable: true, version_introduced: "v1.0" },
  "sla_priority": { required: false, type: "str", domain: "risk", nullable: true, version_introduced: "v2.0" },
  "recommended_sla_action": { required: false, type: "str", domain: "risk", nullable: true, version_introduced: "v3.0" },
  "action_deadline_hours": { required: false, type: "int", domain: "risk", nullable: true, version_introduced: "v3.0" },
  // -- evidence ----------------------------------------------------
  "evidence_chain": { required: false, type: "list", domain: "evidence", nullable: true, version_introduced: "v2.0" },
  "evidence_count": { required: false, type: "int", domain: "evidence", nullable: true, version_introduced: "v2.0" },
  "evidence_ledger": { required: false, type: "dict", domain: "evidence", nullable: true, version_introduced: "v3.0" },
  "sources_reporting": { required: false, type: "list", domain: "evidence", nullable: true, version_introduced: "v2.0" },
  // -- commercial --------------------------------------------------
  "allowed_content_tier": { required: false, type: "str", domain: "commercial", nullable: true, version_introduced: "v2.0" },
  "cti_tier": { required: false, type: "str", domain: "commercial", nullable: true, version_introduced: "v3.0" },
  "premium_eligible": { required: false, type: "bool", domain: "commercial", nullable: true, version_introduced: "v2.0" },
  "enterprise_eligible": { required: false, type: "bool", domain: "commercial", nullable: true, version_introduced: "v3.0" },
  "mssp_eligible": { required: false, type: "bool", domain: "commercial", nullable: true, version_introduced: "v3.0" },
  "revenue_opportunities": { required: false, type: "list", domain: "commercial", nullable: true, version_introduced: "v3.0" },
  "pdf_available": { required: false, type: "bool", domain: "commercial", nullable: true, version_introduced: "v2.0" },
  "pdf_url": { required: false, type: "str", domain: "commercial", nullable: true, version_introduced: "v2.0" },
  "report_url": { required: false, type: "str", domain: "commercial", nullable: true, version_introduced: "v1.0" },
  "blog_url": { required: false, type: "str", domain: "commercial", nullable: true, version_introduced: "v2.0" },
  "internal_report_url": { required: false, type: "str", domain: "commercial", nullable: true, version_introduced: "v2.0" },
  // -- governance --------------------------------------------------
  "_enriched_at": { required: false, type: "str", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "_enriched_by": { required: false, type: "str", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "_governance_rules": { required: false, type: "list", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "_kev_marked_at": { required: false, type: "str", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "_kev_source": { required: false, type: "str", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "_quality_hardened_at": { required: false, type: "str", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "_quality_version": { required: false, type: "str", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "_risk_micro_adj": { required: false, type: "float", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "_score_details": { required: false, type: "dict", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "governed_at": { required: false, type: "str", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "governor_audit_log": { required: false, type: "list", domain: "governance", nullable: true, version_introduced: "v3.0" },
  "governor_version": { required: false, type: "str", domain: "governance", nullable: true, version_introduced: "v3.0" },
  // -- campaign ----------------------------------------------------
  "campaign_id": { required: false, type: "str", domain: "campaign", nullable: true, version_introduced: "v2.0" },
  "campaign_name": { required: false, type: "str", domain: "campaign", nullable: true, version_introduced: "v2.0" },
  "campaign_status": { required: false, type: "str", domain: "campaign", nullable: true, version_introduced: "v3.0" },
  "tags": { required: false, type: "list", domain: "campaign", nullable: true, version_introduced: "v1.0" },
  "tlp": { required: false, type: "str", domain: "campaign", nullable: true, version_introduced: "v1.0" },
  "stix_id": { required: false, type: "str", domain: "campaign", nullable: true, version_introduced: "v2.0" },
  "research_based": { required: false, type: "bool", domain: "campaign", nullable: true, version_introduced: "v3.0" },
  "intelligence_age_days": { required: false, type: "int", domain: "campaign", nullable: true, version_introduced: "v3.0" },
  // -- actor -------------------------------------------------------
  "actor_id": { required: false, type: "str", domain: "actor", nullable: true, version_introduced: "v3.1", note: "internal actor ID used by attribution pipeline" },
  // -- ioc ---------------------------------------------------------
  "ioc_enforced": { required: false, type: "bool", domain: "ioc", nullable: true, version_introduced: "v3.1" },
  "ioc_enforced_at": { required: false, type: "str", domain: "ioc", nullable: true, version_introduced: "v3.1" },
  // -- identity ----------------------------------------------------
  "published": { required: false, type: "bool", domain: "identity", nullable: true, version_introduced: "v3.1", note: "boolean publication flag (distinct from is_published which is also bool)" },
  // -- apex --------------------------------------------------------
  "apex": { required: false, type: "dict", domain: "apex", nullable: true, version_introduced: "v2.0" },
  "apex_ai": { required: false, type: "dict", domain: "apex", nullable: true, version_introduced: "v3.0" },
  "apex_ai_score": { required: false, type: "float", domain: "apex", nullable: true, version_introduced: "v3.0" },
  "apex_ai_summary": { required: false, type: "str", domain: "apex", nullable: true, version_introduced: "v3.0" },
};

const SCHEMA_DOMAINS = [...new Set(Object.values(SCHEMA_REGISTRY).map(f => f.domain))];
const SCHEMA_DEPRECATED_FIELDS = Object.entries(SCHEMA_REGISTRY).filter(([, v]) => v.deprecated).map(([k]) => k);

// ---------------------------------------------------------------------------
// COMMON RESPONSE HELPERS
// ---------------------------------------------------------------------------
function _json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

async function _loadKvFeed(env) {
  // PRODUCTION-VERIFICATION FIX (2026-09-02): env.INTEL_KV is not a bound
  // namespace anywhere in wrangler.toml (see p18/p34/p36/p37-handlers.js's
  // matching _loadFeed fix notes for the identical THREAT_INTEL_KV defect).
  // env.INTEL_KV?.get(...) never throws (optional chaining short-circuits
  // to undefined on the missing binding), so every P38 handler silently
  // returned NO_FEED / all-zero metrics in production with no visible
  // error. Redirected to the live R2 key every sibling P-layer already
  // reads, normalized the same way (bare array or {items:[...]}).
  try {
    const r2obj = await env.INTEL_R2.get('api/v1/intel/latest.json');
    if (!r2obj) return [];
    const data = await r2obj.json();
    return Array.isArray(data) ? data : (data?.items || []);
  } catch (_) {
    return [];
  }
}

// ---------------------------------------------------------------------------
// HANDLER: Schema Registry
// ---------------------------------------------------------------------------
export async function handleP38SchemaRegistry(request, env) {
  const full = new URL(request.url).searchParams.get('full') === 'true';
  const base = {
    schema_version: 'p38.0',
    total_fields:   Object.keys(SCHEMA_REGISTRY).length,
    deprecated_fields: SCHEMA_DEPRECATED_FIELDS.length,
    domains:        SCHEMA_DOMAINS,
    schema_source:  'scripts/p38_shared_validators.py:SCHEMA_REGISTRY',
    note:           'Canonical schema registry is the Python SCHEMA_REGISTRY. This endpoint surfaces metadata for API consumers. Full field definitions available at /api/v1/p38/schema-registry?full=true (see p38_shared_validators.py).',
    governance:     { single_source_of_truth: 'scripts/p38_shared_validators.py', version_introduced: 'p38.0', backward_compatible: true },
  };
  if (!full) return _json(base);
  // ?full=true  -  the full per-field registry, for cross-repo / external consumers
  // that need the canonical schema contract without a shared code package
  // (e.g. cyberdudebivash-blog validating intelligence objects it consumes).
  return _json({ ...base, fields: SCHEMA_REGISTRY, deprecated_field_names: SCHEMA_DEPRECATED_FIELDS });
}

// ---------------------------------------------------------------------------
// HANDLER: Feed Governance
// ---------------------------------------------------------------------------
export async function handleP38FeedGovernance(request, env) {
  const feeds = Object.entries(FEED_REGISTRY).map(([key, meta]) => ({
    key, ...meta,
    governance_status: 'REGISTERED',
    lifecycle: 'ACTIVE',
  }));
  return _json({
    schema_version:   'p38.0',
    total_feeds:      feeds.length,
    commercial_feeds: feeds.filter(f => f.commercial).length,
    enriched_feeds:   feeds.filter(f => f.enrichment).length,
    registry_source:  'scripts/p38_shared_validators.py:FEED_REGISTRY',
    feeds,
    governance_note:  'Every feed has a documented purpose, type, expected item count, enrichment requirement, and commercial flag. Purpose overlap is prohibited per P38 governance rules.',
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Schema Drift
// ---------------------------------------------------------------------------
export async function handleP38SchemaDrift(request, env) {
  const items = await _loadKvFeed(env);
  if (!items.length) {
    return _json({ schema_version: 'p38.0', status: 'NO_FEED', drift_count: 0, message: 'Feed not available in KV; run p38_production_certification.py for full drift analysis.' });
  }
  const drift = _schemaDrift(items);
  return _json({
    schema_version:  'p38.0',
    items_sampled:   Math.min(items.length, 50),
    drift_count:     drift.drift_count,
    deprecated_count: drift.deprecated_fields.length,
    drift_status:    drift.drift_count === 0 ? 'CLEAN' : 'DRIFT_DETECTED',
    unknown_fields:  drift.unknown_fields,
    deprecated_fields: drift.deprecated_fields,
    remediation:     drift.drift_count > 0 ? 'Add unknown fields to SCHEMA_REGISTRY in p38_shared_validators.py' : 'None required',
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Enrichment Audit
// ---------------------------------------------------------------------------
export async function handleP38EnrichmentAudit(request, env) {
  const items = await _loadKvFeed(env);
  if (!items.length) {
    return _json({ schema_version: 'p38.0', status: 'NO_FEED', message: 'Feed not available in KV.' });
  }
  const audit  = _enrichmentAudit(items);
  const feedType = _detectFeedType(items);
  return _json({
    schema_version: 'p38.0',
    feed_type:      feedType,
    item_count:     items.length,
    enrichment:     audit,
    assessment: {
      cvss_adequate:   audit.cvss_score_pct >= (feedType === 'CVE_FEED' ? 50 : 20),
      epss_adequate:   audit.epss_pct >= 30,
      conf_adequate:   audit.confidence_pct >= 50,
      actor_adequate:  feedType !== 'CVE_FEED' ? audit.actor_tag_pct >= 20 : true,
    },
    governance_note: 'Thresholds are feed-type-aware. CVE feeds tolerate 0% actor attribution. See p38_shared_validators.py:FEED_TYPE_RULES.',
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Confidence Audit
// ---------------------------------------------------------------------------
export async function handleP38ConfidenceAudit(request, env) {
  const items = await _loadKvFeed(env);
  const sample = items.slice(0, 20);
  const scores = [];
  for (const item of sample) {
    try {
      const r = computeEnterpriseTrustScore(item);
      scores.push({ id: item.id, p25_score: r?.score ?? 0, declared: item.confidence ?? null });
    } catch {}
  }
  const avg = scores.length ? scores.reduce((s, x) => s + x.p25_score, 0) / scores.length : 0;
  return _json({
    schema_version:      'p38.0',
    sample_size:         sample.length,
    p25_avg_trust_score: Math.round(avg * 10) / 10,
    confidence_declared_pct: Math.round(_fieldPct(items, x => x.confidence != null && x.confidence !== '') * 10) / 10,
    sample_scores:       scores.slice(0, 10),
    governance_note:     'Confidence calibration delegates to computeEnterpriseTrustScore() in p25-handlers.js. No confidence logic is re-implemented here.',
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Intelligence Quality Index
// ---------------------------------------------------------------------------
export async function handleP38IQIndex(request, env) {
  const items = await _loadKvFeed(env);
  if (!items.length) {
    return _json({ schema_version: 'p38.0', iq_index: 0, status: 'NO_FEED' });
  }
  const iq = _computeIQIndex(items);
  const tier = iq.iq_index >= 85 ? 'WORLD_CLASS' : iq.iq_index >= 70 ? 'ENTERPRISE_READY'
    : iq.iq_index >= 55 ? 'COMMERCIAL' : iq.iq_index >= 40 ? 'DEVELOPING' : 'BASELINE';
  return _json({
    schema_version: 'p38.0',
    iq_index:       iq.iq_index,
    tier:           tier,
    dimensions:     iq.dimensions,
    target_iq:      85,
    gap:            Math.max(0, 85 - iq.iq_index),
    engines_used:   ['computeP20QualityScore (p20)', 'computeEnterpriseTrustScore (p25)', 'computeP26Grade (p26)'],
    governance_note: 'IQ Index is a read-only composite from existing P20/P25/P26 engines. No new scoring logic is introduced.',
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Source Diversity
// ---------------------------------------------------------------------------
export async function handleP38SourceDiversity(request, env) {
  const items = await _loadKvFeed(env);
  if (!items.length) return _json({ schema_version: 'p38.0', status: 'NO_FEED' });
  const div      = _sourceDiversity(items);
  const feedType = _detectFeedType(items);
  const maxDom   = feedType === 'CVE_FEED' ? 98 : 75;
  const minSrc   = feedType === 'CVE_FEED' ? 1  : 3;
  const domOk    = div.top_dominance_pct < maxDom;
  const srcOk    = div.distinct >= minSrc;
  return _json({
    schema_version:   'p38.0',
    feed_type:        feedType,
    item_count:       items.length,
    diversity:        div,
    thresholds:       { max_dominance_pct: maxDom, min_distinct_sources: minSrc },
    assessment: {
      dominance_ok:  domOk,
      sources_ok:    srcOk,
      overall:       domOk && srcOk ? 'HEALTHY' : 'NEEDS_ATTENTION',
    },
    governance_note: 'Thresholds are feed-type-aware. NVD-heavy CVE feeds are expected to show high concentration  -  this is not a defect.',
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Certification
// ---------------------------------------------------------------------------
export async function handleP38Certification(request, env) {
  return _json({
    schema_version:    'p38.0',
    layer:             'P38',
    scope:             'enterprise_platform_governance',
    certification_source: 'data/quality/p38_certification_report.json',
    chain: ['P38->P37->P36->P35->P34->P33 (all WORLDWIDE_RELEASE)'],
    governance_note:   'Full certification is run by scripts/p38_production_certification.py. This endpoint surfaces chain metadata for API consumers.',
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Executive Governance Dashboard
// ---------------------------------------------------------------------------
export async function handleP38Executive(request, env) {
  const items = await _loadKvFeed(env);
  const enrich  = items.length ? _enrichmentAudit(items) : {};
  const div     = items.length ? _sourceDiversity(items) : {};
  const iq      = items.length ? _computeIQIndex(items)  : { iq_index: 0, dimensions: {} };
  const rel     = items.length ? _reliabilityMetrics(items) : {};
  const drift   = items.length ? _schemaDrift(items) : { drift_count: 0, deprecated_count: 0 };
  return _json({
    schema_version:   'p38.0',
    generated_at:     new Date().toISOString(),
    platform_health: {
      feed_items:         items.length,
      iq_index:           iq.iq_index,
      enrichment_cvss:    enrich.cvss_score_pct ?? 0,
      enrichment_conf:    enrich.confidence_pct ?? 0,
      source_diversity:   div.distinct ?? 0,
      top_source_dom_pct: div.top_dominance_pct ?? 0,
      dedup_ok:           rel.dedup_ok ?? false,
      freshness_pct:      rel.freshness_pct ?? 0,
      schema_drift:       drift.drift_count,
      deprecated_fields:  drift.deprecated_count,
    },
    commercial_readiness: {
      live_feed_healthy:    items.length > 0,
      enrichment_adequate:  (enrich.cvss_score_pct ?? 0) >= 50,
      confidence_adequate:  (enrich.confidence_pct ?? 0) >= 50,
      iq_target_met:        iq.iq_index >= 85,
    },
    governance_layers: {
      schema_registry:   'p38_shared_validators.py:SCHEMA_REGISTRY',
      feed_registry:     'p38_shared_validators.py:FEED_REGISTRY',
      shared_validators: 'scripts/p38_shared_validators.py',
      cert_chain:        'P38->P37->P36->P35->P34->P33',
    },
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Reliability
// ---------------------------------------------------------------------------
export async function handleP38Reliability(request, env) {
  const items = await _loadKvFeed(env);
  const rel   = items.length ? _reliabilityMetrics(items) : { total_items: 0 };
  return _json({
    schema_version: 'p38.0',
    ...rel,
    governance_note: 'Reliability covers deduplication, freshness metadata presence, and risk_score ceiling compliance.',
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Metrics
// ---------------------------------------------------------------------------
export async function handleP38Metrics(request, env) {
  const items   = await _loadKvFeed(env);
  const enrich  = items.length ? _enrichmentAudit(items) : {};
  const div     = items.length ? _sourceDiversity(items) : {};
  const iq      = items.length ? _computeIQIndex(items)  : { iq_index: 0 };
  return _json({
    schema_version:     'p38.0',
    feed_items:         items.length,
    iq_index:           iq.iq_index,
    enrichment_metrics: enrich,
    source_diversity:   { distinct: div.distinct, top_dom_pct: div.top_dominance_pct },
    governance_surface: {
      schema_fields:     Object.keys(SCHEMA_REGISTRY).length,
      deprecated_fields: SCHEMA_DEPRECATED_FIELDS.length,
      feed_variants:     12,
      p_layers:          22,
      api_routes:        209,
    },
  });
}

// ---------------------------------------------------------------------------
// HANDLER: Observability
// ---------------------------------------------------------------------------
export async function handleP38Observability(request, env) {
  return _json({
    schema_version:   'p38.0',
    layer:            'P38',
    status:           'OPERATIONAL',
    endpoints: [
      '/api/v1/p38/schema-registry',
      '/api/v1/p38/feed-governance',
      '/api/v1/p38/schema-drift',
      '/api/v1/p38/enrichment-audit',
      '/api/v1/p38/confidence-audit',
      '/api/v1/p38/iq-index',
      '/api/v1/p38/source-diversity',
      '/api/v1/p38/certification',
      '/api/v1/p38/executive',
      '/api/v1/p38/reliability',
      '/api/v1/p38/metrics',
      '/api/v1/p38/observability',
    ],
    shared_validators: 'scripts/p38_shared_validators.py',
    engines_reused:    ['computeP20QualityScore', 'computeEnterpriseTrustScore', 'computeP26Grade'],
  });
}
