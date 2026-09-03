/**
 * ═══════════════════════════════════════════════════════════════════════════════
 *  SENTINEL APEX — Primary Feed Terminal-State Resolver v1.0.0
 *
 *  P0 incident 2026-09-03. index.html's loadGOCIntel() walks MANIFEST_URLS and,
 *  when every source fails, painted:
 *
 *      SYNC: ⚡ LOADING     +     ⚡ NO DATA
 *
 *  That is a TERMINAL failure state wearing a LOADING label. Nothing further
 *  runs after it, so the customer dashboard sat on "LOADING" indefinitely
 *  while /api/health simultaneously reported 500 healthy advisories. Two
 *  separate truth defects sat in that one branch:
 *
 *    1. An infrastructure denial (HTTP 429 from the API entitlement gate)
 *       was rendered identically to "we are still fetching", and one step
 *       later identically to "there is no intelligence" — so a quota error
 *       masqueraded as an empty feed.
 *    2. When a NON-authoritative fallback source did answer (the
 *       raw.githubusercontent.com mirror, which carries a stale 109-item
 *       snapshot against the authority's 500), the page still displayed
 *       "SYNC: LIVE" and "MANIFEST VERIFIED" — asserting freshness and
 *       verification for data that was neither.
 *
 *  This module is the single pure decision function for what the feed's
 *  terminal state actually is, given what the network returned. It holds no
 *  DOM references and performs no I/O so it can be unit-tested directly with
 *  `node --test` (js/__tests__/, the same convention as api_adapter and
 *  apex-data-plane's tests).
 *
 *  It deliberately reuses the state vocabulary that already exists rather
 *  than inventing a third one: the names below are the canonical dashboard
 *  states (js/dashboard-state.js) plus RATE_LIMITED, which the mandate
 *  requires be distinguishable from EMPTY and which apex-data-plane.js
 *  already treats as its own customer-facing failure message
 *  ("Rate limited. Please try again shortly.", messageForFailure/429).
 *
 *  PURELY ADDITIVE. Loading this file changes nothing on its own; index.html
 *  calls resolveFeedTerminalState() at the single point where it previously
 *  hard-coded the LOADING label.
 * ═══════════════════════════════════════════════════════════════════════════════
 */
'use strict';

(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.SentinelFeedState = factory();
  }
})(typeof window !== 'undefined' ? window : this, function () {

  var VERSION = '1.0.0';

  /**
   * Terminal states the primary feed may end in. LOADING is intentionally
   * ABSENT: it is not a terminal state, and the whole point of this module is
   * that no failure path may end on it.
   */
  var STATES = Object.freeze({
    LIVE:         'LIVE',          // authoritative source answered with items
    STALE:        'STALE',         // a non-authoritative fallback answered
    EMPTY:        'EMPTY',         // authoritative source answered, genuinely 0 items
    RATE_LIMITED: 'RATE_LIMITED',  // denied by an entitlement/quota gate (429)
    ERROR:        'ERROR',         // every source failed for some other reason
    OFFLINE:      'OFFLINE',       // browser reports no network at all
  });

  /**
   * Customer-facing copy per terminal state. Never says "no threat
   * intelligence" for anything that is not a genuine, authoritative empty
   * feed — an infrastructure failure must never be reported as an editorial
   * fact about the threat landscape.
   */
  var COPY = Object.freeze({
    LIVE:         { sync: 'LIVE',         badge: 'MANIFEST VERIFIED',     detail: '' },
    STALE:        { sync: 'STALE',        badge: 'FALLBACK SOURCE',       detail: 'Showing a cached mirror — not the live feed.' },
    EMPTY:        { sync: 'NO ADVISORIES', badge: 'FEED EMPTY',           detail: 'The feed is reachable and currently contains no advisories.' },
    RATE_LIMITED: { sync: 'RATE LIMITED', badge: 'REQUEST LIMIT REACHED', detail: 'Too many requests from this network. Intelligence is available — this view is temporarily throttled.' },
    ERROR:        { sync: 'ERROR',        badge: 'FEED UNAVAILABLE',      detail: 'Could not reach the intelligence feed. This is a delivery fault, not an absence of intelligence.' },
    OFFLINE:      { sync: 'OFFLINE',      badge: 'NO NETWORK',            detail: 'Your browser reports no network connection.' },
  });

  /**
   * True when an HTTP status is an entitlement/quota denial rather than a
   * statement about the data. 429 is the gateway's quota + rate-limit code;
   * 401/403 are auth denials, which are equally not "the feed is empty".
   */
  function isEntitlementDenial(status) {
    return status === 429 || status === 401 || status === 403;
  }

  /**
   * Resolve the terminal state of the primary feed.
   *
   * @param {Object} outcome
   * @param {Array<{url:string, status:number|null, ok:boolean, authoritative:boolean, itemCount:number}>} outcome.attempts
   *        One entry per MANIFEST_URLS source actually tried, in order.
   *        `status` is the HTTP status, or null when the request never
   *        produced one (network error / timeout / abort).
   *        `authoritative` marks a first-party API source, as opposed to a
   *        third-party mirror.
   * @param {boolean} [outcome.online] navigator.onLine, when available.
   * @returns {{state:string, sync:string, badge:string, detail:string,
   *            httpStatus:number|null, sourceUrl:string|null, itemCount:number,
   *            isTerminalFailure:boolean, rateLimited:boolean}}
   */
  function resolveFeedTerminalState(outcome) {
    var o = outcome || {};
    var attempts = Array.isArray(o.attempts) ? o.attempts : [];
    var online = (o.online === undefined) ? true : !!o.online;

    // A source that answered with usable items wins, authoritative first.
    var authoritativeHit = null, fallbackHit = null, authoritativeEmpty = null;
    for (var i = 0; i < attempts.length; i++) {
      var a = attempts[i] || {};
      if (!a.ok) continue;
      var n = typeof a.itemCount === 'number' ? a.itemCount : 0;
      if (n > 0) {
        if (a.authoritative) { if (!authoritativeHit) authoritativeHit = a; }
        else if (!fallbackHit) fallbackHit = a;
      } else if (a.authoritative && !authoritativeEmpty) {
        authoritativeEmpty = a;
      }
    }

    if (authoritativeHit) return _build(STATES.LIVE, authoritativeHit);
    // A stale mirror is shown — but it is labelled STALE, never LIVE, and the
    // badge never claims verification. Serving it silently under a "LIVE /
    // MANIFEST VERIFIED" label was the second truth defect in this incident.
    if (fallbackHit) return _build(STATES.STALE, fallbackHit);
    // Only an authoritative source is allowed to assert that the feed is
    // genuinely empty. A fallback returning 0 items proves nothing.
    if (authoritativeEmpty) return _build(STATES.EMPTY, authoritativeEmpty);

    if (!online) return _build(STATES.OFFLINE, null);

    // Nothing usable came back. Distinguish an entitlement denial from a
    // generic failure — a quota error must never be reported as an empty feed.
    var denial = null;
    for (var j = 0; j < attempts.length; j++) {
      if (attempts[j] && isEntitlementDenial(attempts[j].status)) { denial = attempts[j]; break; }
    }
    if (denial) return _build(STATES.RATE_LIMITED, denial);

    var anyStatus = null;
    for (var k = 0; k < attempts.length; k++) {
      if (attempts[k] && attempts[k].status) { anyStatus = attempts[k]; break; }
    }
    return _build(STATES.ERROR, anyStatus);
  }

  function _build(state, attempt) {
    var copy = COPY[state] || COPY.ERROR;
    var terminalFailure = (state === STATES.RATE_LIMITED || state === STATES.ERROR || state === STATES.OFFLINE);
    return {
      state: state,
      sync: copy.sync,
      badge: copy.badge,
      detail: copy.detail,
      httpStatus: attempt && attempt.status != null ? attempt.status : null,
      sourceUrl: attempt && attempt.url ? attempt.url : null,
      itemCount: attempt && typeof attempt.itemCount === 'number' ? attempt.itemCount : 0,
      isTerminalFailure: terminalFailure,
      rateLimited: state === STATES.RATE_LIMITED,
    };
  }

  return {
    VERSION: VERSION,
    STATES: STATES,
    COPY: COPY,
    isEntitlementDenial: isEntitlementDenial,
    resolveFeedTerminalState: resolveFeedTerminalState,
  };
});
