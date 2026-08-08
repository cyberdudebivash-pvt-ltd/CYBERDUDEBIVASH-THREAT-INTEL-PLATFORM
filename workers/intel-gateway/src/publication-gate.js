/**
 * workers/intel-gateway/src/publication-gate.js
 * CUSTOMER PUBLICATION AUTHORIZATION GATE — P0 incident remediation.
 *
 * INCIDENT: intel--ba996dad34540150b8ea1b5f was publicly served through
 * /reports/** despite P21=4/100 (BELOW_MINIMUM), P25=28% (BELOW THRESHOLD),
 * P26=29/100 (REJECTED), P23=4/10 (INCOMPLETE — DO NOT PUBLISH). Root cause,
 * traced (not guessed):
 *
 *   1. The /reports/** route (index.js) never consulted ANY certification
 *      result before serving. It resolves an item (via findItemBySlug or a
 *      direct R2 hit), generates/serves HTML, and caches it — the actual
 *      P20-P26 verdicts only ever appeared as DISPLAY content inside the
 *      generated report, never as a gate on whether to serve it at all.
 *   2. The one function that superficially resembles a "release gate"
 *      (p32-handlers.js:_computeReleaseGate, "P32.13") only treats 4 basic
 *      data-completeness checks as blockers (title/description/severity/
 *      CVSS-or-severity present) — genuine quality/trust-score failures are
 *      demoted to non-blocking warnings, so it reports PUBLICATION_APPROVED
 *      even when P21/P25/P26/P23 all reject the same item. It was also
 *      never wired into the serving decision anywhere — a display block,
 *      not a gate.
 *   3. Pipeline ordering (.github/workflows/sentinel-blogger.yml): STAGE 3.2
 *      (report generation, scripts/report_generator.py) runs BEFORE STAGE
 *      3.93.15d/h/i (P21/P25/P26 certification) — confirmed by exact line
 *      numbers in that file. Reports can be generated before certification
 *      has even run.
 *
 * THIS MODULE is the single authoritative publication decision this
 * incident's remediation policy requires: DENY OVERRIDES ALLOW across every
 * existing certification engine, FAIL CLOSED on missing/erroring data, and
 * it reuses the canonical engine functions unchanged (computeP20QualityScore,
 * getP21CertificationLevel, the newly-extracted computeOperationalReadiness,
 * computeEnterpriseTrustScore, computeP26Grade) rather than re-implementing
 * any scoring logic. It does NOT consult P32's release gate at all — the
 * most permissive engine must never be allowed to win.
 *
 * SCOPE (documented, not silent): this closes the confirmed, actively
 * exploited path — the Worker's /reports/** synthesis + direct R2 serving.
 * It does NOT modify scripts/report_generator.py or
 * scripts/generate_intel_reports.py (the Python-side generators that also
 * write into the same reports/ R2 keyspace, per STAGE 3.6.5's own comment:
 * "no shared ownership model"). Reordering that 50+ stage production
 * pipeline safely requires its own dedicated, carefully-tested change — see
 * the incident report's Root Cause / Residual Risk sections.
 */

import { computeP20QualityScore } from './p20-handlers.js';
import { getP21CertificationLevel } from './p21-handlers.js';
import { computeOperationalReadiness } from './p23-handlers.js';
import { computeEnterpriseTrustScore } from './p25-handlers.js';
import { computeP26Grade } from './p26-handlers.js';

export const PUBLICATION_GATE_VERSION = '1.0.0';

// Below this, P20 is "critically low" per P26's own existing C-P20 warning
// threshold (p26-handlers.js) — reused here as a blocking condition, not a
// new number invented for this gate.
const P20_CRITICAL_THRESHOLD = 25;

/**
 * Evaluates the ONE authoritative publication decision for an intelligence
 * item. Fail-closed: any engine erroring, or any single engine rejecting,
 * blocks publication — deny overrides allow, unconditionally.
 *
 * Returns:
 *   publication_state:  'CUSTOMER_READY' | 'REJECTED' | 'BLOCKED'
 *   customer_ready:     boolean — the ONLY field callers should branch on
 *   blocking_gates:      reason codes, e.g. ['P21_BELOW_MINIMUM','P26_REJECTED']
 *   plus the individual engine scores/tiers for transparency (Section 21 —
 *   explicit, non-ambiguous names, never a bare "quality: 83").
 */
export function evaluatePublicationGate(item) {
  const evaluatedAt = new Date().toISOString();
  const base = { evaluated_at: evaluatedAt, certification_version: PUBLICATION_GATE_VERSION };

  if (!item || typeof item !== 'object') {
    return { ...base, publication_state: 'BLOCKED', customer_ready: false,
             blocking_gates: ['ITEM_MISSING'] };
  }

  let p20, p21, p23, p25, p26;
  try {
    p20 = computeP20QualityScore(item);
    p21 = getP21CertificationLevel(p20.total);
    p23 = computeOperationalReadiness(item);
    p25 = computeEnterpriseTrustScore(item);
    p26 = computeP26Grade(item);
  } catch (e) {
    // FAIL CLOSED — a certification engine throwing must never be treated
    // as "unknown = approved" (Section 8's explicit prohibition).
    return { ...base, publication_state: 'BLOCKED', customer_ready: false,
             blocking_gates: ['CERTIFICATION_ENGINE_ERROR'],
             error: String((e && e.message) || e) };
  }

  const blockingGates = [];
  if (p21.id === 'BELOW_MINIMUM')            blockingGates.push('P21_BELOW_MINIMUM');
  if (p20.total < P20_CRITICAL_THRESHOLD)    blockingGates.push('P20_QUALITY_CRITICALLY_LOW');
  if (p25.tier === 'BELOW THRESHOLD')        blockingGates.push('P25_BELOW_THRESHOLD');
  if (p23.pct < 50)                          blockingGates.push('P23_OPERATIONAL_READINESS_DO_NOT_PUBLISH');
  if (p26.certFlags.certTier === 'REJECTED') blockingGates.push('P26_REJECTED');

  const customerReady = blockingGates.length === 0;
  const publicationState = customerReady
    ? 'CUSTOMER_READY'
    : (p26.certFlags.certTier === 'REJECTED' ? 'REJECTED' : 'BLOCKED');

  return {
    ...base,
    publication_state: publicationState,
    customer_ready: customerReady,
    P20_SCORE: p20.total,
    P21_CERTIFICATION: p21.id,
    P23_OPERATIONAL_READINESS_PCT: p23.pct,
    P25_TRUST_SCORE: p25.pct,
    P25_TRUST_TIER: p25.tier,
    P26_COMMERCIAL_SCORE: p26.composite,
    P26_GRADE: p26.grade,
    P26_CERT_TIER: p26.certFlags.certTier,
    blocking_gates: blockingGates,
  };
}

/** Convenience boolean-only check for hot filtering paths (index building). */
export function isCustomerReady(item) {
  return evaluatePublicationGate(item).customer_ready === true;
}
