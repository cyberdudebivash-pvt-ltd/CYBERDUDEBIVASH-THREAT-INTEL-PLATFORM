// CDB_NORMALIZE -- canonical metric semantic contract (PR-E1).
// Single source of truth for EPSS/KEV/priority normalization, consumed by
// index.html's inline severity/priority helpers, js/sentinel-live-feeds.js,
// and scripts/ai_brain_patch.js's injected output. Loaded early (before any
// consumer) so window.CDB_NORMALIZE is always defined by the time a
// data-driven renderer actually runs.
//
// Contract:
//   epss(raw)     -> { probability: 0..1|null, percent: 0..100|null, state: 'OK'|'UNKNOWN'|'INVALID' }
//                    0..1 values are treated as already-probability; values in
//                    (1,100] are treated as a percentage and divided by 100.
//                    Negative or >100 values are INVALID, never silently clamped.
//   kevState(item) -> true | false | 'UNKNOWN'
//                    Trusts item.kev_present when it is an actual boolean
//                    (the clean canonical field); otherwise parses the legacy
//                    item.kev field (which carries string values like "NO"
//                    that are truthy in JS -- never use raw !!item.kev).
//   priority(item) -> 'P0'..'P4' | 'UNKNOWN'
//                    Presentation-boundary resolver only -- does not
//                    recompute priority from risk signals (that remains
//                    window.computePriority's job). Prefers the backend's
//                    own authoritative field, in order, and never invents P4
//                    for a genuinely-unknown item.
(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory(null);
  } else {
    root.CDB_NORMALIZE = factory(root);
  }
})(typeof window !== 'undefined' ? window : this, function (root) {
  'use strict';

  function normalizeEpss(raw) {
    if (raw === null || raw === undefined || raw === '') {
      return { probability: null, percent: null, state: 'UNKNOWN' };
    }
    var n = typeof raw === 'number' ? raw : parseFloat(raw);
    if (!Number.isFinite(n) || n < 0 || n > 100) {
      return { probability: null, percent: null, state: 'INVALID' };
    }
    if (n <= 1) {
      return { probability: n, percent: n * 100, state: 'OK' };
    }
    return { probability: n / 100, percent: n, state: 'OK' };
  }

  function normalizeKevValue(raw) {
    if (raw === true) return true;
    if (raw === false) return false;
    if (raw === null || raw === undefined || raw === '') return 'UNKNOWN';
    if (typeof raw === 'number') {
      if (raw === 1) return true;
      if (raw === 0) return false;
      return 'UNKNOWN';
    }
    if (typeof raw === 'string') {
      var s = raw.trim().toUpperCase();
      if (s === 'YES' || s === 'TRUE' || s === '1') return true;
      if (s === 'NO' || s === 'FALSE' || s === '0') return false;
      return 'UNKNOWN';
    }
    return 'UNKNOWN';
  }

  function kevState(item) {
    if (!item) return 'UNKNOWN';
    if (typeof item.kev_present === 'boolean') return item.kev_present;
    return normalizeKevValue(item.kev);
  }

  var PRIORITY_RE = /^P[0-4]$/i;
  function validPriority(v) {
    return typeof v === 'string' && PRIORITY_RE.test(v.trim()) ? v.trim().toUpperCase() : null;
  }

  function priority(item) {
    if (!item) return 'UNKNOWN';
    var fromSla = validPriority(item.sla_priority);
    if (fromSla) return fromSla;
    var fromSoc = item.apex_ai ? validPriority(item.apex_ai.soc_priority) : null;
    if (fromSoc) return fromSoc;
    var fromField = validPriority(item.priority);
    if (fromField) return fromField;
    // Only defer to computePriority() (a real derivation engine) when the
    // item actually carries at least one raw signal it derives from --
    // otherwise computePriority() just returns its own internal default
    // (P4), which would leak through here as if it were a genuine
    // computation on a genuinely-unknown item.
    var hasSignal = item.kev_present !== undefined || item.cvss_score != null
      || item.risk_score != null || item.epss_score != null;
    if (hasSignal && root && typeof root.computePriority === 'function') {
      var computed = validPriority(root.computePriority(item));
      if (computed) return computed;
    }
    return 'UNKNOWN';
  }

  return {
    epss: normalizeEpss,
    kevState: kevState,
    priority: priority,
  };
});
