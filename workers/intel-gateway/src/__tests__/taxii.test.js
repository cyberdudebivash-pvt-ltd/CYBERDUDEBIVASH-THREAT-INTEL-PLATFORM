import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  TAXII_COLLECTIONS,
  tierMeetsCollection,
  findCollection,
  filterItemsForCollection,
  tagC2Eligibility,
  encodeCursor,
  decodeCursor,
  paginateFeedItems,
  buildTaxiiUpgradeBody,
} from '../taxii.js';

const ITEMS = [
  { id: 'a', threat_type: 'Ransomware', actor_tag: 'CDB-RAN-01', kev_present: false, published: '2026-01-01T00:00:00Z' },
  { id: 'b', threat_type: 'APT', actor_tag: 'CDB-APT-28', kev_present: true, published: '2026-06-01T00:00:00Z' },
  { id: 'c', threat_type: 'Vulnerability', actor_tag: 'CDB-CVE-GEN', kev_present: false, published: '2026-07-01T00:00:00Z' },
  { id: 'd', threat_type: 'Threat Intel', actor_tag: 'CDB-APT-GEN', kev_present: false, published: '2026-08-01T00:00:00Z' },
];

describe('TAXII_COLLECTIONS registry', () => {
  test('contains exactly the 5 expected collection ids, main/kev first (backward-compat order)', () => {
    const ids = TAXII_COLLECTIONS.map((c) => c.id);
    assert.deepEqual(ids, ['sentinel-apex-main', 'sentinel-apex-kev', 'c2-indicators', 'active-ransomware', 'apt-attribution']);
  });

  test('kev and apt-attribution require ENTERPRISE; the rest require PRO', () => {
    const byId = Object.fromEntries(TAXII_COLLECTIONS.map((c) => [c.id, c.minTier]));
    assert.equal(byId['sentinel-apex-kev'], 'ENTERPRISE');
    assert.equal(byId['apt-attribution'], 'ENTERPRISE');
    assert.equal(byId['sentinel-apex-main'], 'PRO');
    assert.equal(byId['c2-indicators'], 'PRO');
    assert.equal(byId['active-ransomware'], 'PRO');
  });
});

describe('tierMeetsCollection', () => {
  test('FREE never meets any collection', () => {
    for (const c of TAXII_COLLECTIONS) assert.equal(tierMeetsCollection('FREE', c), false);
  });
  test('PRO meets PRO-gated collections but not ENTERPRISE-gated ones', () => {
    assert.equal(tierMeetsCollection('PRO', findCollection('sentinel-apex-main')), true);
    assert.equal(tierMeetsCollection('PRO', findCollection('sentinel-apex-kev')), false);
    assert.equal(tierMeetsCollection('PRO', findCollection('apt-attribution')), false);
  });
  test('ENTERPRISE and MSSP meet every collection', () => {
    for (const c of TAXII_COLLECTIONS) {
      assert.equal(tierMeetsCollection('ENTERPRISE', c), true);
      assert.equal(tierMeetsCollection('MSSP', c), true);
    }
  });
});

describe('findCollection', () => {
  test('returns null for an unknown id', () => {
    assert.equal(findCollection('does-not-exist'), null);
  });
});

describe('filterItemsForCollection', () => {
  test('sentinel-apex-main returns every item unchanged (exact pre-existing behavior)', () => {
    assert.deepEqual(filterItemsForCollection(ITEMS, 'sentinel-apex-main'), ITEMS);
  });
  test('sentinel-apex-kev filters to kev_present only (exact pre-existing behavior)', () => {
    assert.deepEqual(filterItemsForCollection(ITEMS, 'sentinel-apex-kev').map((i) => i.id), ['b']);
  });
  test('active-ransomware matches threat_type Ransomware OR a CDB-RAN- actor tag', () => {
    assert.deepEqual(filterItemsForCollection(ITEMS, 'active-ransomware').map((i) => i.id), ['a']);
  });
  test('apt-attribution matches threat_type APT OR a CDB-APT- actor tag', () => {
    assert.deepEqual(filterItemsForCollection(ITEMS, 'apt-attribution').map((i) => i.id), ['b', 'd']);
  });
  test('an unknown collection id falls through to the "all items" default', () => {
    assert.deepEqual(filterItemsForCollection(ITEMS, 'nonsense'), ITEMS);
  });
});

describe('tagC2Eligibility + c2-indicators filter', () => {
  test('tags items whose threat_type is in the supplied set, leaves originals unmodified', () => {
    const tagged = tagC2Eligibility(ITEMS, new Set(['Ransomware', 'APT']));
    assert.deepEqual(tagged.map((i) => i._c2Eligible), [true, true, false, false]);
    assert.equal(ITEMS[0]._c2Eligible, undefined, 'original items must not be mutated');
  });
  test('c2-indicators collection returns only tagged-eligible items', () => {
    const tagged = tagC2Eligibility(ITEMS, new Set(['Ransomware', 'APT']));
    assert.deepEqual(filterItemsForCollection(tagged, 'c2-indicators').map((i) => i.id), ['a', 'b']);
  });
});

describe('cursor encode/decode', () => {
  test('round-trips an offset', () => {
    for (const n of [0, 1, 42, 999, 123456]) assert.equal(decodeCursor(encodeCursor(n)), n);
  });
  test('decodeCursor is defensive against garbage input', () => {
    assert.equal(decodeCursor(''), 0);
    assert.equal(decodeCursor(null), 0);
    assert.equal(decodeCursor('!!!not-base64!!!'), 0);
    assert.equal(decodeCursor('abcXYZ=='), 0); // decodes to non-numeric text
  });
  test('a cursor is URL-safe (no +, /, or = padding)', () => {
    const token = encodeCursor(999999);
    assert.equal(/^[A-Za-z0-9_-]+$/.test(token), true);
  });
});

describe('paginateFeedItems', () => {
  test('defaults to a 100-item page with no cursor', () => {
    const { page, more, next } = paginateFeedItems(ITEMS);
    assert.equal(page.length, 4);
    assert.equal(more, false);
    assert.equal(next, null);
  });
  test('honors a smaller limit and returns a next cursor when more remain', () => {
    const { page, more, next } = paginateFeedItems(ITEMS, { limit: 2 });
    assert.deepEqual(page.map((i) => i.id), ['a', 'b']);
    assert.equal(more, true);
    assert.ok(next);
  });
  test('a cursor from page 1 correctly resumes at page 2', () => {
    const page1 = paginateFeedItems(ITEMS, { limit: 2 });
    const page2 = paginateFeedItems(ITEMS, { limit: 2, cursor: page1.next });
    assert.deepEqual(page2.page.map((i) => i.id), ['c', 'd']);
    assert.equal(page2.more, false);
  });
  test('limit is clamped to the [1, 500] range', () => {
    assert.equal(paginateFeedItems(ITEMS, { limit: 0 }).page.length, 1); // explicit 0 clamps up to 1, not "unset"
    assert.equal(paginateFeedItems(ITEMS, { limit: -5 }).page.length, 1); // negative clamps up to 1
    assert.equal(paginateFeedItems(ITEMS, { limit: 99999 }).page.length, 4); // clamped down to 500, still only 4 items exist
  });
  test('an unset/unparseable limit falls back to the 100-item default', () => {
    assert.equal(paginateFeedItems(ITEMS, {}).page.length, 4);
    assert.equal(paginateFeedItems(ITEMS, { limit: 'not-a-number' }).page.length, 4);
  });
  test('added_after filters out items published at or before the cutoff', () => {
    const { page } = paginateFeedItems(ITEMS, { addedAfter: '2026-03-01T00:00:00Z' });
    assert.deepEqual(page.map((i) => i.id), ['b', 'c', 'd']);
  });
  test('an unparseable added_after is ignored rather than throwing or emptying the result', () => {
    const { page } = paginateFeedItems(ITEMS, { addedAfter: 'not-a-date' });
    assert.equal(page.length, 4);
  });
  test('total reflects the added_after-filtered pool, not the pre-filter item count', () => {
    const { total } = paginateFeedItems(ITEMS, { addedAfter: '2026-03-01T00:00:00Z', limit: 1 });
    assert.equal(total, 3);
  });
});

describe('buildTaxiiUpgradeBody', () => {
  test('a null collection (bare /taxii access denial) produces a generic PRO-tier message', () => {
    const body = buildTaxiiUpgradeBody(null, 'https://x/upgrade?tier=pro');
    assert.equal(body.required_tier, 'PRO');
    assert.equal(body.upgrade_url, 'https://x/upgrade?tier=pro');
    assert.match(body.description, /PRO or ENTERPRISE/);
  });
  test('a specific collection names its own minTier requirement', () => {
    const body = buildTaxiiUpgradeBody(findCollection('apt-attribution'), 'https://x/upgrade?tier=enterprise');
    assert.equal(body.required_tier, 'ENTERPRISE');
    assert.match(body.description, /apt-attribution/);
    assert.match(body.description, /ENTERPRISE/);
  });
});
