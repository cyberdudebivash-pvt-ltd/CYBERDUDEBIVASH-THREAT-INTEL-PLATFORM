const assert = require('node:assert/strict');
const { test } = require('node:test');
const FeedState = require('../feed-state.js');

const { STATES, resolveFeedTerminalState, isEntitlementDenial } = FeedState;

// ---------------------------------------------------------------------------
// P0 incident 2026-09-03. index.html's loadGOCIntel() walked MANIFEST_URLS and,
// when every source failed, painted "SYNC: LOADING / NO DATA" and stopped --
// a terminal failure wearing a transient label, which is why the customer
// dashboard sat on LOADING indefinitely while /api/health reported 500
// healthy advisories. These tests pin the two guarantees that fix it:
//
//   1. No failure path may ever resolve to LOADING.
//   2. An entitlement denial (429) may never resolve to "the feed is empty".
//
// Attempt-record shape mirrors what index.html now pushes into _feedAttempts:
//   { url, status, ok, authoritative, itemCount }
// ---------------------------------------------------------------------------

const AUTH_OK    = (n = 500) => ({ url: 'api/feed.json', status: 200, ok: true,  authoritative: true,  itemCount: n });
const AUTH_429   = (u = 'api/feed.json') => ({ url: u, status: 429, ok: false, authoritative: true, itemCount: 0 });
const AUTH_500   = { url: 'api/feed.json', status: 500, ok: false, authoritative: true,  itemCount: 0 };
const AUTH_404   = { url: 'api/feed.json', status: 404, ok: false, authoritative: true,  itemCount: 0 };
const AUTH_NET   = { url: 'api/feed.json', status: null, ok: false, authoritative: true,  itemCount: 0 };
const MIRROR_OK  = (n = 109) => ({ url: 'https://raw.githubusercontent.com/x/y/main/api/feed.json', status: 200, ok: true, authoritative: false, itemCount: n });
const MIRROR_429 = { url: 'https://raw.githubusercontent.com/x/y/main/api/feed.json', status: 429, ok: false, authoritative: false, itemCount: 0 };
const MIRROR_NET = { url: 'https://raw.githubusercontent.com/x/y/main/api/feed.json', status: null, ok: false, authoritative: false, itemCount: 0 };

// The exact production shape: 4 same-origin API sources, then the mirror.
const ALL_QUOTA_DENIED = [
  AUTH_429('api/feed.json'),
  AUTH_429('api/v1/intel/latest.json'),
  AUTH_429('api/v1/intel/apex.json'),
  AUTH_429('https://intel.cyberdudebivash.com/api/preview/'),
];

// ===========================================================================
// GUARANTEE 1 -- no path may end on LOADING
// ===========================================================================

test('CRITICAL: no terminal state is ever LOADING, for any combination of outcomes', () => {
  const pool = [AUTH_OK(500), AUTH_OK(0), AUTH_429(), AUTH_500, AUTH_404, AUTH_NET,
                MIRROR_OK(109), MIRROR_OK(0), MIRROR_429, MIRROR_NET];
  const cases = [{ attempts: [] }, { attempts: [], online: false }];
  for (const a of pool) {
    cases.push({ attempts: [a] });
    for (const b of pool) cases.push({ attempts: [a, b] });
  }
  const seen = new Set();
  for (const c of cases) {
    const r = resolveFeedTerminalState(c);
    seen.add(r.state);
    assert.ok(r.state && r.state !== 'LOADING' && r.state !== 'BOOTING',
      `resolved to a non-terminal state for ${JSON.stringify(c)}`);
    assert.ok(/^(LIVE|STALE|EMPTY|RATE_LIMITED|ERROR|OFFLINE)$/.test(r.state), `unknown state ${r.state}`);
    assert.ok(!/loading/i.test(r.sync), `sync label must never say LOADING (got "${r.sync}")`);
    assert.ok(typeof r.sync === 'string' && r.sync.length > 0);
    assert.ok(typeof r.badge === 'string' && r.badge.length > 0);
  }
  assert.ok(seen.size >= 5, 'the matrix should exercise most states, got: ' + [...seen].join(','));
});

test('an empty attempt list is still terminal, never LOADING', () => {
  const r = resolveFeedTerminalState({ attempts: [] });
  assert.equal(r.state, STATES.ERROR);
  assert.equal(r.isTerminalFailure, true);
});

test('malformed input degrades to a terminal ERROR rather than throwing', () => {
  for (const bad of [undefined, null, {}, { attempts: null }, { attempts: 'nope' }, { attempts: [null, undefined] }]) {
    const r = resolveFeedTerminalState(bad);
    assert.equal(r.state, STATES.ERROR);
    assert.ok(!/loading/i.test(r.sync));
  }
});

// ===========================================================================
// GUARANTEE 2 -- a quota denial is never a false EMPTY
// ===========================================================================

test('CRITICAL: the exact production quota-exhaustion case resolves to RATE_LIMITED, not EMPTY', () => {
  // All four same-origin API sources denied by the entitlement gate, and the
  // third-party mirror unreachable. This is the reproduced customer state.
  const r = resolveFeedTerminalState({ attempts: [...ALL_QUOTA_DENIED, MIRROR_NET], online: true });
  assert.equal(r.state, STATES.RATE_LIMITED);
  assert.equal(r.rateLimited, true);
  assert.equal(r.httpStatus, 429);
  assert.notEqual(r.state, STATES.EMPTY, 'a quota denial must never present as an empty feed');
  assert.ok(!/no (current )?threat intelligence|no advisories/i.test(r.detail),
    'RATE_LIMITED copy must not assert an absence of intelligence, got: ' + r.detail);
  assert.match(r.detail, /throttled/i);
});

test('401 and 403 are entitlement denials too, not empty feeds', () => {
  assert.equal(isEntitlementDenial(429), true);
  assert.equal(isEntitlementDenial(401), true);
  assert.equal(isEntitlementDenial(403), true);
  assert.equal(isEntitlementDenial(404), false);
  assert.equal(isEntitlementDenial(500), false);
  assert.equal(isEntitlementDenial(200), false);
  for (const s of [401, 403]) {
    const r = resolveFeedTerminalState({ attempts: [{ url: 'api/feed.json', status: s, ok: false, authoritative: true, itemCount: 0 }] });
    assert.equal(r.state, STATES.RATE_LIMITED, `HTTP ${s} must not be reported as an empty feed`);
  }
});

test('a rate limit anywhere in the chain wins over a generic failure', () => {
  const r = resolveFeedTerminalState({ attempts: [AUTH_500, AUTH_NET, AUTH_429(), MIRROR_NET] });
  assert.equal(r.state, STATES.RATE_LIMITED, 'the most actionable cause must surface');
});

test('non-entitlement failures resolve to ERROR, with honest copy', () => {
  for (const attempts of [[AUTH_500], [AUTH_404], [AUTH_NET], [AUTH_500, MIRROR_NET]]) {
    const r = resolveFeedTerminalState({ attempts });
    assert.equal(r.state, STATES.ERROR);
    assert.equal(r.isTerminalFailure, true);
    assert.match(r.detail, /delivery fault, not an absence of intelligence/i);
  }
});

test('OFFLINE takes precedence when the browser reports no network', () => {
  const r = resolveFeedTerminalState({ attempts: [AUTH_NET, MIRROR_NET], online: false });
  assert.equal(r.state, STATES.OFFLINE);
  assert.equal(r.isTerminalFailure, true);
});

// ===========================================================================
// TRUTH LABELLING -- LIVE / STALE / EMPTY
// ===========================================================================

test('CRITICAL: authority > 0 items resolves to LIVE with the real count', () => {
  // The mandated regression: when the delivery authority has data, the
  // dashboard must reach a rendering state with a non-zero count.
  const r = resolveFeedTerminalState({ attempts: [AUTH_OK(500)] });
  assert.equal(r.state, STATES.LIVE);
  assert.equal(r.itemCount, 500);
  assert.equal(r.isTerminalFailure, false);
  assert.equal(r.badge, 'MANIFEST VERIFIED');
});

test('CRITICAL: a non-authoritative mirror is labelled STALE, never LIVE/VERIFIED', () => {
  // The second truth defect: with the API quota-denied, the stale 109-item
  // GitHub mirror answered and the page still displayed "LIVE / MANIFEST
  // VERIFIED" over it. Reproduced in a real Chromium against production.
  const r = resolveFeedTerminalState({ attempts: [...ALL_QUOTA_DENIED, MIRROR_OK(109)] });
  assert.equal(r.state, STATES.STALE);
  assert.equal(r.itemCount, 109);
  assert.notEqual(r.sync, 'LIVE');
  assert.notEqual(r.badge, 'MANIFEST VERIFIED');
  assert.match(r.detail, /cached mirror/i);
});

test('an authoritative source always outranks a mirror, whatever the order', () => {
  const a = resolveFeedTerminalState({ attempts: [MIRROR_OK(109), AUTH_OK(500)] });
  const b = resolveFeedTerminalState({ attempts: [AUTH_OK(500), MIRROR_OK(109)] });
  assert.equal(a.state, STATES.LIVE);
  assert.equal(b.state, STATES.LIVE);
  assert.equal(a.itemCount, 500);
});

test('only an authoritative source may declare the feed genuinely EMPTY', () => {
  const authEmpty = resolveFeedTerminalState({ attempts: [AUTH_OK(0)] });
  assert.equal(authEmpty.state, STATES.EMPTY, 'a reachable authority with 0 items is a real empty feed');
  assert.equal(authEmpty.isTerminalFailure, false);

  const mirrorEmpty = resolveFeedTerminalState({ attempts: [...ALL_QUOTA_DENIED, MIRROR_OK(0)] });
  assert.equal(mirrorEmpty.state, STATES.RATE_LIMITED,
    'a mirror returning 0 items proves nothing about the feed -- the 429 is the real cause');
});

test('a quota denial followed by an authoritative recovery is LIVE, not RATE_LIMITED', () => {
  const r = resolveFeedTerminalState({ attempts: [AUTH_429(), AUTH_OK(500)] });
  assert.equal(r.state, STATES.LIVE, 'usable data always wins over an earlier failed attempt');
});

// ===========================================================================
// SCHEMA / CONTRACT
// ===========================================================================

test('every resolution returns the full contract shape', () => {
  for (const attempts of [[AUTH_OK(500)], [MIRROR_OK(109)], [AUTH_OK(0)], ALL_QUOTA_DENIED, [AUTH_500], []]) {
    const r = resolveFeedTerminalState({ attempts });
    for (const k of ['state', 'sync', 'badge', 'detail', 'httpStatus', 'sourceUrl', 'itemCount', 'isTerminalFailure', 'rateLimited']) {
      assert.ok(Object.prototype.hasOwnProperty.call(r, k), `missing key ${k}`);
    }
    assert.equal(typeof r.isTerminalFailure, 'boolean');
    assert.equal(typeof r.rateLimited, 'boolean');
    assert.equal(typeof r.itemCount, 'number');
  }
});

test('STATES deliberately contains no LOADING member', () => {
  assert.ok(!('LOADING' in STATES), 'LOADING is not a terminal state and must not be resolvable');
  assert.ok(!('BOOTING' in STATES));
  assert.deepEqual(Object.keys(STATES).sort(), ['EMPTY', 'ERROR', 'LIVE', 'OFFLINE', 'RATE_LIMITED', 'STALE']);
});
