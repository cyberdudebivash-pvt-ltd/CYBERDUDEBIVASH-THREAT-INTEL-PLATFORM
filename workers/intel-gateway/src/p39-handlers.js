/**
 * workers/intel-gateway/src/p39-handlers.js
 * P39.0 Commercial Quality Orchestrator (JS composition layer)
 *
 * Approved by: COMMERCIAL_QUALITY_GOVERNANCE_AUDIT.md +
 *              COMMERCIAL_QUALITY_ORCHESTRATOR_ARCHITECTURE.md (PR #131, merged to main)
 * Program: Project TITAN Stage 20A -- Enterprise Commercial Quality Orchestrator
 *
 * ARCHITECTURE NOTE -- INTERNAL ONLY, DELIBERATELY NOT ROUTED:
 *   Per the explicit implementation directive for this stage ("Integrate with
 *   Gateway composition layer only. Never expose publicly. Remain internal."),
 *   this file is, unlike every P16-P38 handler file before it, deliberately:
 *     - NOT imported by index.js
 *     - NOT registered in index.js's route-dispatch chain
 *     - NOT listed in index.js's API endpoint index
 *   It lives inside workers/intel-gateway/src/ (the Gateway) and composes the
 *   Gateway's own existing engines, but is reachable only by direct in-process
 *   import (tests, or a future, separately-authorized caller) -- never by
 *   HTTP. This mirrors the precedented "TITAN-lineage, never-wired-into-
 *   index.js" pattern already used by product-platform/, knowledge-platform/,
 *   and intelligence-platform/ in this same src/ tree, and is mechanically
 *   enforced by scripts/titan_architecture_governance_check.py's
 *   check_commercial_orchestrator_still_unwired().
 *
 * DESIGN PRINCIPLE (architecture doc Sec 0): this file COMPOSES. It never
 * computes what an existing engine already computes. Every dimension score,
 * grade, tier, and publication citation below is read verbatim from an
 * existing, already-certified engine's own output. The only genuinely new
 * computation in this file is computeCommercialApplicability() (architecture
 * doc Sec 5) -- everything else is reconciliation, explanation, and
 * presentation over engines that already exist and are NEVER modified here.
 *
 * Reuse map (all imported UNCHANGED, zero modification to any of them):
 *   computeP20QualityScore      -> p20-handlers.js (unchanged)
 *   getP21CertificationLevel    -> p21-handlers.js (unchanged)
 *   computeEnterpriseTrustScore -> p25-handlers.js (unchanged; ADR-0007 canonical A1)
 *   computeP26Grade             -> p26-handlers.js (unchanged; already composes P20/P21/P22/P23/P25)
 *
 * P29/P35/P36/P37 are feed-level, (request, env)-shaped HTTP handlers, not
 * pure per-item functions -- composing them here would require this file to
 * fabricate a synthetic Request, which the architecture doc's "reads output
 * only" rule does not require and this implementation deliberately avoids.
 * Callers that already have that context (env/KV access) may pass their
 * already-fetched JSON bodies in via the `feedContext` parameter; if omitted,
 * those citations are honestly reported as "not supplied," never fabricated.
 *
 * 7 exported composition functions (the 7 components the approved
 * architecture authorizes -- see
 * COMMERCIAL_QUALITY_ORCHESTRATOR_ARCHITECTURE.md Sec 1.2 and the Stage 20A
 * resume brief's "IMPLEMENT ONLY" list):
 *   computeCommercialApplicability      - Applicability Engine (Sec 5; the one new computation)
 *   buildCommercialQualityView          - Commercial Quality Orchestrator (Sec 1-2)
 *   buildCommercialReadinessSummary     - Commercial Readiness Summary
 *   buildCommercialPublicationDecision  - Commercial Publication Decision (Sec 3; cites only, never decides)
 *   buildCommercialExplanation          - Commercial Explanation Engine / Executive Commercial Explanation (Sec 6)
 *   buildCommercialRecommendationLayer  - Commercial Recommendation Layer / presentation tier (Sec 7)
 *   buildCommercialReleaseDecision      - Commercial Release Decision (final packaged view)
 *
 * Never fabricates evidence: every field this module cannot obtain from an
 * existing engine's real output is reported as UNKNOWN / not supplied, never
 * defaulted to a value that looks like a real citation.
 */

import { computeP20QualityScore }      from './p20-handlers.js';
import { getP21CertificationLevel }    from './p21-handlers.js';
import { computeEnterpriseTrustScore } from './p25-handlers.js';
import { computeP26Grade }             from './p26-handlers.js';

// ---------------------------------------------------------------------------
// Commercial Applicability Engine (Sec 5) -- the one genuinely new computation
// ---------------------------------------------------------------------------
// Four states per architecture doc Sec 5.1: APPLICABLE / NOT_APPLICABLE /
// UNKNOWN / (whole-item) EXCLUDED. NOT_APPLICABLE dimensions are excluded
// from both numerator and denominator of the applicability-adjusted
// composite (Sec 5.3) -- they are never scored as a failure.
// ---------------------------------------------------------------------------

const DETECTION_FORMATS = {
  sigma:    'sigma_rule',
  kql:      'kql_query',
  spl:      'spl_query',
  suricata: 'suricata_rule',
  yara:     'yara_rule',
  elastic:  'elastic_rule',
  snort:    'snort_rule',
};

function _hasCve(item) {
  return !!(
    item.cve_id ||
    (Array.isArray(item.cve_ids) && item.cve_ids.length > 0) ||
    /^CVE-/i.test(String(item.id || ''))
  );
}

function _hasBehavioralEvidence(item) {
  // Signals that this item describes observed/inferred adversary BEHAVIOR,
  // not a bare vulnerability disclosure (architecture doc Sec 5.2 worked
  // example: "an empty MITRE mapping on a pure vulnerability disclosure with
  // no observed exploitation behavior is genuinely inapplicable").
  return !!(
    (item.actor_tag && String(item.actor_tag).trim()) ||
    item.active_exploit || item.exploit_maturity ||
    item.kev_present || item.kev ||
    (Array.isArray(item.exploit_refs) && item.exploit_refs.length > 0) ||
    (parseInt(item.poc_github_count || 0, 10) > 0) ||
    item.metasploit_available ||
    (Array.isArray(item.kill_chain_phases) && item.kill_chain_phases.length > 0) ||
    (item.threat_type && !/^(vulnerability|patch|advisory)$/i.test(String(item.threat_type)))
  );
}

function _daysSince(dateStr) {
  if (!dateStr) return null;
  const t = Date.parse(dateStr);
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / 86400000;
}

/**
 * computeCommercialApplicability(item)
 * Per-dimension APPLICABLE / NOT_APPLICABLE / UNKNOWN classification for the
 * five dimensions named in the approved architecture (Sec 5.2's worked-
 * example table): MITRE ATT&CK mapping, EPSS score, KEV listing, IOC
 * presence, and detection rule coverage (per format). Applicability rules
 * are explicit and per-dimension, never inferred from bare absence (Sec 5.2).
 */
export function computeCommercialApplicability(item) {
  if (!item || typeof item !== 'object' || !item.id) {
    return {
      excluded: true,
      reason: 'Unsupported report type -- item missing minimum identity fields (id).',
      dimensions: {},
      summary: { applicable: 0, not_applicable: 0, unknown: 0, passed: 0, failed: 0 },
    };
  }

  const hasCve   = _hasCve(item);
  const hasBehav = _hasBehavioralEvidence(item);
  const dims = {};

  // --- MITRE ATT&CK mapping ---
  {
    const hasMitre = (Array.isArray(item.mitre_tactics) && item.mitre_tactics.length > 0) ||
                      (Array.isArray(item.ttps) && item.ttps.length > 0) ||
                      (Array.isArray(item.attck_technique_ids) && item.attck_technique_ids.length > 0);
    if (!hasBehav) {
      dims.mitre_attack = {
        status: 'NOT_APPLICABLE',
        rationale: 'No observed/inferred adversary behavior signal (no actor_tag, exploit, KEV, or kill-chain data) -- reads as a bare vulnerability disclosure, which has no technique to map.',
      };
    } else if (hasMitre) {
      dims.mitre_attack = { status: 'APPLICABLE', result: 'PASS', rationale: 'Behavioral evidence present and MITRE ATT&CK mapping populated.' };
    } else {
      dims.mitre_attack = { status: 'APPLICABLE', result: 'FAIL', rationale: 'Behavioral evidence present (actor/exploit/KEV/kill-chain) but no MITRE ATT&CK mapping recorded -- a real gap, not inapplicable.' };
    }
  }

  // --- EPSS score ---
  {
    if (!hasCve) {
      dims.epss = { status: 'NOT_APPLICABLE', rationale: 'Item carries no CVE identifier -- EPSS is CVE-scoped and cannot apply.' };
    } else {
      const hasEpss = item.epss_score !== undefined && item.epss_score !== null && item.epss_score !== '';
      if (hasEpss) {
        dims.epss = { status: 'APPLICABLE', result: 'PASS', rationale: `EPSS score present (${item.epss_score}).` };
      } else {
        const ageDays = _daysSince(item.nvd_disclosure || item.published_at || item.timestamp);
        if (ageDays !== null && ageDays < 3) {
          dims.epss = { status: 'UNKNOWN', rationale: `CVE disclosed ${ageDays.toFixed(1)}d ago -- EPSS has a real publication lag; too early to call this a gap (Sec 5.2: "not yet available" vs. "will never apply").` };
        } else {
          dims.epss = { status: 'APPLICABLE', result: 'FAIL', rationale: 'CVE-bearing item with no EPSS score and sufficient age for one to plausibly exist.' };
        }
      }
    }
  }

  // --- KEV listing -- "should almost never be NOT_APPLICABLE" (Sec 5.2) ---
  {
    if (!hasCve) {
      dims.kev = { status: 'NOT_APPLICABLE', rationale: 'Item carries no CVE identifier -- KEV is CVE-scoped.' };
    } else {
      const kevVal = !!(item.kev_present || item.kev);
      dims.kev = {
        status: 'APPLICABLE',
        result: 'PASS',
        rationale: kevVal ? 'Listed on CISA KEV.' : 'Not on CISA KEV -- itself a meaningful, scoreable signal per Sec 5.2, not a gap.',
      };
    }
  }

  // --- IOC presence ---
  {
    const policyOnly = item.threat_type && /^(policy|compliance|advisory-only)$/i.test(String(item.threat_type));
    if (policyOnly) {
      dims.ioc_presence = { status: 'NOT_APPLICABLE', rationale: 'Pure policy/compliance advisory -- not the kind of item that plausibly carries IOCs.' };
    } else {
      const iocCnt = parseInt(item.ioc_count || (Array.isArray(item.iocs) ? item.iocs.length : 0) || 0, 10);
      dims.ioc_presence = iocCnt > 0
        ? { status: 'APPLICABLE', result: 'PASS', rationale: `${iocCnt} IOC(s) present.` }
        : { status: 'APPLICABLE', result: 'FAIL', rationale: 'Item type plausibly carries IOCs but none are present.' };
    }
  }

  // --- Detection rule coverage, per format ---
  // Absence alone does not prove inapplicability (Sec 5.2). Without confirmed
  // producing-pipeline metadata on the item itself, an absent format is
  // honestly UNKNOWN -- never a guessed NOT_APPLICABLE and never a false FAIL.
  {
    const cov = {};
    for (const [fmt, field] of Object.entries(DETECTION_FORMATS)) {
      cov[fmt] = item[field]
        ? { status: 'APPLICABLE', result: 'PASS', rationale: `${field} present.` }
        : { status: 'UNKNOWN', rationale: `${field} absent; producing pipeline's by-design format set is not determinable from this item alone (Sec 5.5).` };
    }
    dims.detection_coverage = cov;
  }

  const flat = [];
  for (const [key, val] of Object.entries(dims)) {
    if (key === 'detection_coverage') { Object.values(val).forEach(v => flat.push(v)); }
    else { flat.push(val); }
  }
  const summary = {
    applicable:     flat.filter(d => d.status === 'APPLICABLE').length,
    not_applicable: flat.filter(d => d.status === 'NOT_APPLICABLE').length,
    unknown:        flat.filter(d => d.status === 'UNKNOWN').length,
    passed:         flat.filter(d => d.status === 'APPLICABLE' && d.result === 'PASS').length,
    failed:         flat.filter(d => d.status === 'APPLICABLE' && d.result === 'FAIL').length,
  };

  return { excluded: false, dimensions: dims, summary };
}

function _applicabilityAdjustedComposite(applicability) {
  // Sec 5.3: composite = (sum of scores for applicable D) / (count of applicable D)
  // -- NOT_APPLICABLE dimensions never enter numerator or denominator.
  if (!applicability || applicability.excluded) return null;
  let numerator = 0, denominator = 0;
  const walk = (d) => { if (d.status === 'APPLICABLE') { denominator += 1; if (d.result === 'PASS') numerator += 1; } };
  for (const [key, val] of Object.entries(applicability.dimensions || {})) {
    if (key === 'detection_coverage') { Object.values(val).forEach(walk); } else { walk(val); }
  }
  return denominator > 0 ? Math.round((numerator / denominator) * 100) : null;
}

// ---------------------------------------------------------------------------
// Commercial Quality Orchestrator (Sec 1-2) -- reads existing outputs only
// ---------------------------------------------------------------------------

/**
 * buildCommercialQualityView(item, feedContext)
 * The Commercial Quality Orchestrator. Composes P20/P21/P25/P26's own,
 * already-computed per-item outputs plus the Applicability Model, and
 * produces the "Commercial Quality View" the architecture doc Sec 1.1
 * describes: a citation-and-reconciliation artifact, never a new score.
 *
 * `feedContext` (optional) carries caller-supplied, already-fetched JSON
 * bodies from feed-level handlers (handleP29CustomerValueAnalytics,
 * handleP36CustomerValue, handleP35Scorecard, handleP37IQScore) -- this
 * function never invokes them itself (see file header). Omitted keys are
 * reported as "not supplied," never fabricated.
 */
export function buildCommercialQualityView(item, feedContext = {}) {
  const applicability = computeCommercialApplicability(item);
  const inputsCited = [];

  let p20 = null, p21 = null, p25 = null, p26 = null;
  try {
    p20 = computeP20QualityScore(item);
    inputsCited.push({ source: 'P20 computeP20QualityScore', value: p20.total, kind: 'quality_score_0_100' });
  } catch (e) {
    inputsCited.push({ source: 'P20 computeP20QualityScore', error: String((e && e.message) || e) });
  }
  try {
    p21 = getP21CertificationLevel(p20 ? p20.total : 0);
    inputsCited.push({ source: 'P21 getP21CertificationLevel', value: p21.id, kind: 'certification_tier' });
  } catch (e) {
    inputsCited.push({ source: 'P21 getP21CertificationLevel', error: String((e && e.message) || e) });
  }
  try {
    p25 = computeEnterpriseTrustScore(item);
    inputsCited.push({ source: 'P25 computeEnterpriseTrustScore', value: `${p25.tier} (${p25.pct})`, kind: 'trust_tier' });
  } catch (e) {
    inputsCited.push({ source: 'P25 computeEnterpriseTrustScore', error: String((e && e.message) || e) });
  }
  try {
    p26 = computeP26Grade(item);
    inputsCited.push({ source: 'P26 computeP26Grade', value: `${p26.grade} (${p26.composite}) ${p26.gradeLabel}`, kind: 'composite_grade' });
  } catch (e) {
    inputsCited.push({ source: 'P26 computeP26Grade', error: String((e && e.message) || e) });
  }

  const feedCitations = {};
  for (const key of ['p29CustomerValue', 'p36CustomerValue', 'p35Scorecard', 'p37IQScore']) {
    if (feedContext && feedContext[key] !== undefined) {
      feedCitations[key] = feedContext[key];
      inputsCited.push({ source: key, value: 'supplied by caller', kind: 'feed_level_context' });
    } else {
      feedCitations[key] = null;
    }
  }

  const applicabilityComposite = _applicabilityAdjustedComposite(applicability);

  const positiveSignals = [];
  if (p26 && ['A', 'B', 'C'].includes(p26.grade)) positiveSignals.push('P26');
  if (p25 && ['ENTERPRISE CERTIFIED', 'ENTERPRISE READY'].includes(p25.tier)) positiveSignals.push('P25');
  if (p21 && ['PREMIUM_CERTIFIED', 'ENTERPRISE_READY'].includes(p21.id)) positiveSignals.push('P21');
  if (applicabilityComposite !== null && applicabilityComposite >= 75) positiveSignals.push('Applicability Model');

  return {
    schema_version: 'p39.0',
    item_id: item && item.id,
    generated_at: new Date().toISOString(),
    inputs_cited: inputsCited,
    applicability,
    applicability_adjusted_composite: applicabilityComposite,
    agreement_summary: {
      systems_evaluated: inputsCited.filter(c => !c.error).length,
      positive_signals: positiveSignals,
      agreement_count: positiveSignals.length,
      note: 'Full citation, not arbitration -- disagreement between systems is surfaced, never resolved by this layer (Architecture Sec 2).',
    },
    p20, p21, p25, p26,
    feed_context: feedCitations,
    engines_reused: ['computeP20QualityScore', 'getP21CertificationLevel', 'computeEnterpriseTrustScore', 'computeP26Grade'],
  };
}

// ---------------------------------------------------------------------------
// Commercial Readiness Summary
// ---------------------------------------------------------------------------

export function buildCommercialReadinessSummary(view) {
  if (!view) return null;
  const a = view.applicability || {};
  const s = a.summary || {};
  const missingEvidence = [];
  for (const [key, val] of Object.entries(a.dimensions || {})) {
    const entries = key === 'detection_coverage' ? Object.entries(val) : [[key, val]];
    for (const [name, dim] of entries) {
      if (dim.status === 'UNKNOWN') missingEvidence.push(key === 'detection_coverage' ? `detection_coverage.${name}` : name);
    }
  }
  return {
    schema_version: 'p39.0',
    item_id: view.item_id,
    applicable_gates: s.applicable ?? 0,
    non_applicable_gates: s.not_applicable ?? 0,
    unknown_gates: s.unknown ?? 0,
    passed_applicable_gates: s.passed ?? 0,
    failed_applicable_gates: s.failed ?? 0,
    applicability_adjusted_composite: view.applicability_adjusted_composite,
    p26_composite: view.p26 ? view.p26.composite : null,
    p26_grade: view.p26 ? view.p26.grade : null,
    p25_tier: view.p25 ? view.p25.tier : null,
    zero_applicable_failures: (s.failed ?? 0) === 0 && (s.applicable ?? 0) > 0,
    missing_evidence: missingEvidence,
  };
}

// ---------------------------------------------------------------------------
// Commercial Publication Decision -- cites only, never decides (Sec 3)
// ---------------------------------------------------------------------------

/**
 * buildCommercialPublicationDecision(item, view, feedContext)
 * Publication BLOCK/QUARANTINE/PUBLISH is owned exclusively by
 * scripts/commercial_readiness_governor.py (Python runtime). This function
 * never decides -- it surfaces whatever citation is available, verbatim, and
 * is honest (UNKNOWN) when none is available. The JS Worker runtime has no
 * direct access to the Python governor's file-based output at request time,
 * so a value is only ever shown here if the caller explicitly supplies it
 * (e.g. an already-synced KV record) or if it is already present on the item
 * itself.
 */
export function buildCommercialPublicationDecision(item, view, feedContext = {}) {
  const governorCitation = (feedContext && feedContext.governorPublicationDecision) || (item && item.publication_decision) || null;
  return {
    schema_version: 'p39.0',
    item_id: view ? view.item_id : (item && item.id),
    publication_decision_citation: governorCitation,
    source: governorCitation ? 'commercial_readiness_governor.py (Python runtime; cited verbatim)' : null,
    status: governorCitation ? 'CITED' : 'UNKNOWN -- not supplied for this request; never fabricated.',
    js_native_proxy_signal: view && view.p26 ? { source: 'P26 certFlags', certFlags: view.p26.certFlags } : null,
    governance_note: 'This function is a downstream reader only. It never overrides or re-decides publication (Architecture Sec 3).',
  };
}

// ---------------------------------------------------------------------------
// Commercial Explanation Engine (Sec 6 -- Explainability Flow)
// ---------------------------------------------------------------------------

export function buildCommercialExplanation(view) {
  if (!view) return null;
  const readiness = buildCommercialReadinessSummary(view);
  const lines = [];
  lines.push(`${view.agreement_summary.systems_evaluated} system(s) evaluated this item.`);
  if (view.agreement_summary.positive_signals.length > 0) {
    lines.push(`${view.agreement_summary.positive_signals.length} agree on a positive commercial signal: ${view.agreement_summary.positive_signals.join(', ')}.`);
  }
  lines.push(`${readiness.applicable_gates} applicable gate(s); ${readiness.non_applicable_gates} not applicable for this item type (excluded from scoring, not penalized); ${readiness.unknown_gates} unknown/pending.`);
  lines.push(`${readiness.failed_applicable_gates} applicable gate(s) failed.`);
  if (view.applicability_adjusted_composite !== null && view.applicability_adjusted_composite !== undefined) {
    lines.push(`Applicability-adjusted composite: ${view.applicability_adjusted_composite}/100.`);
  }
  return {
    schema_version: 'p39.0',
    item_id: view.item_id,
    narrative: lines.join(' '),
    citations: view.inputs_cited,
    generated_at: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Commercial Recommendation Layer (Sec 7 -- presentation-only 9th tier)
// ---------------------------------------------------------------------------

const RECOMMENDATION_TIERS = [
  { min: 98, id: 'PREMIUM_INTELLIGENCE', label: 'Premium Intelligence' },
  { min: 90, id: 'COMMERCIAL_CERTIFIED', label: 'Commercial Certified' },
  { min: 75, id: 'ENTERPRISE_READY',     label: 'Enterprise Ready' },
  { min: 60, id: 'ANALYST_REVIEW',       label: 'Analyst Review' },
  { min: 0,  id: 'INTERNAL_DRAFT',       label: 'Internal Draft' },
];

export function buildCommercialRecommendationLayer(view) {
  if (!view) return null;
  const readiness = buildCommercialReadinessSummary(view);
  const composite = view.applicability_adjusted_composite;
  let tier = RECOMMENDATION_TIERS[RECOMMENDATION_TIERS.length - 1];
  if (composite !== null && composite !== undefined) {
    tier = RECOMMENDATION_TIERS.find(t => composite >= t.min) || tier;
  }
  // Premium Intelligence additionally requires zero applicable failures
  // (Architecture Sec 7's qualifying language, structurally satisfied by the
  // Applicability Model rather than any extra logic).
  if (tier.id === 'PREMIUM_INTELLIGENCE' && !readiness.zero_applicable_failures) {
    tier = RECOMMENDATION_TIERS.find(t => t.id === 'COMMERCIAL_CERTIFIED');
  }
  return {
    schema_version: 'p39.0',
    item_id: view.item_id,
    tier: tier.id,
    tier_label: tier.label,
    composite_used: composite,
    presentation_only: true,
    non_authoritative_note: 'A 9th, clearly-labeled, presentation-only tier -- never replaces or outranks P20/P21/P25/P26/P36/P37\'s own tier outputs (Architecture Sec 7).',
    explainability_trace: buildCommercialExplanation(view),
  };
}

// ---------------------------------------------------------------------------
// Commercial Release Decision -- final packaged view
// ---------------------------------------------------------------------------

export function buildCommercialReleaseDecision(view, publicationDecision) {
  if (!view) return null;
  const recommendation = buildCommercialRecommendationLayer(view);
  const publication = publicationDecision || buildCommercialPublicationDecision({ id: view.item_id }, view, {});
  return {
    schema_version: 'p39.0',
    item_id: view.item_id,
    generated_at: new Date().toISOString(),
    recommendation_tier: recommendation.tier,
    recommendation_label: recommendation.tier_label,
    publication_decision: publication,
    readiness_summary: buildCommercialReadinessSummary(view),
    explanation: recommendation.explainability_trace,
    governance_note: 'Composed view only. Never overrides P20/P21/P25/P26/P29/P35/P36/P37, commercial_readiness_governor.py, or dossier_quality_engine.py (Architecture Sec 0-3).',
  };
}

// ---------------------------------------------------------------------------
// Observability self-descriptor (not an HTTP handler -- see file header)
// ---------------------------------------------------------------------------

export function getCommercialQualityOrchestratorObservability() {
  return {
    schema_version: 'p39.0',
    layer: 'P39',
    status: 'OPERATIONAL_INTERNAL_ONLY',
    wired_into_index_js: false,
    public_routes: [],
    note: 'Internal composition layer only -- never expose publicly, remain internal (Stage 20A implementation directive). Reachable by direct in-process import only.',
    engines_reused: ['computeP20QualityScore', 'getP21CertificationLevel', 'computeEnterpriseTrustScore', 'computeP26Grade'],
    exported_components: [
      'computeCommercialApplicability',
      'buildCommercialQualityView',
      'buildCommercialReadinessSummary',
      'buildCommercialPublicationDecision',
      'buildCommercialExplanation',
      'buildCommercialRecommendationLayer',
      'buildCommercialReleaseDecision',
    ],
  };
}
