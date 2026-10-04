// =============================================================================
// SENTINEL APEX -- Customer-facing metric truth boundary
// =============================================================================
// CVSS and SENTINEL APEX risk_score are different metrics. This module exists
// to prevent report/UI/decision code from silently substituting one for the
// other. A missing CVSS remains unknown; it is never manufactured from risk.
// =============================================================================

function finiteInRange(value, min, max) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= min && n <= max ? n : null;
}

export function explicitCvss(item = {}) {
  // Deliberately excludes _score_details.cvss: legacy governance code can
  // populate that field through a risk_score fallback. Only source-facing
  // CVSS fields are accepted here.
  const candidates = [
    item.cvss_score,
    item.cvss,
    item.cvss_v3,
    item.cvss3_score,
    item.cvss_base_score,
  ];
  for (const value of candidates) {
    const n = finiteInRange(value, 0, 10);
    if (n !== null && n > 0) return n;
  }
  return null;
}

export function explicitRiskScore(item = {}) {
  const candidates = [item.risk_score, item.threat_score];
  for (const value of candidates) {
    const n = finiteInRange(value, 0, 10);
    if (n !== null) return n;
  }
  return null;
}

export function hasExplicitCvss(item = {}) {
  return explicitCvss(item) !== null;
}

export function metricTruth(item = {}) {
  return {
    cvss: explicitCvss(item),
    risk_score: explicitRiskScore(item),
    cvss_is_explicit: hasExplicitCvss(item),
    risk_is_cvss: false,
  };
}
