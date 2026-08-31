import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  ORG_ROLES,
  ORG_PLANS,
  SEAT_ADDON_PRICE_USD_PER_MONTH,
  isValidEmail,
  isValidRole,
  isValidPlan,
  buildOrgId,
  buildInviteToken,
  hashApiKey,
  buildOrgRecord,
  buildOrgMemberRecord,
  buildInviteRecord,
  isInviteExpired,
  computeSeatUsage,
  aggregateOrgUsage,
  buildOrgInviteEmailHtml,
  resolveSeatAddonContactUrl,
  buildGstInvoiceRecord,
  renderInvoiceHtml,
} from '../teams.js';

describe('validators', () => {
  test('isValidEmail accepts well-formed addresses, rejects garbage', () => {
    assert.equal(isValidEmail('a@b.com'), true);
    assert.equal(isValidEmail('a.b+c@sub.domain.co'), true);
    assert.equal(isValidEmail('not-an-email'), false);
    assert.equal(isValidEmail(''), false);
    assert.equal(isValidEmail(null), false);
    assert.equal(isValidEmail('a'.repeat(260) + '@b.com'), false);
  });
  test('isValidRole matches ORG_ROLES exactly', () => {
    for (const r of ORG_ROLES) assert.equal(isValidRole(r), true);
    assert.equal(isValidRole('SUPERUSER'), false);
    assert.equal(isValidRole(''), false);
  });
  test('isValidPlan matches ORG_PLANS exactly', () => {
    for (const p of Object.keys(ORG_PLANS)) assert.equal(isValidPlan(p), true);
    assert.equal(isValidPlan('FREE_FOREVER'), false);
  });
});

describe('id/token generation', () => {
  test('buildOrgId/buildInviteToken produce distinct, prefixed, reasonably long ids', () => {
    const a = buildOrgId(), b = buildOrgId();
    assert.notEqual(a, b);
    assert.match(a, /^org_[0-9a-f]{24}$/);
    const t1 = buildInviteToken(), t2 = buildInviteToken();
    assert.notEqual(t1, t2);
    assert.match(t1, /^orginv_[0-9a-f]{48}$/);
  });
});

describe('hashApiKey', () => {
  test('is deterministic and produces a 64-char hex SHA-256 digest', async () => {
    const h1 = await hashApiKey('cdb_pro_abc123');
    const h2 = await hashApiKey('cdb_pro_abc123');
    assert.equal(h1, h2);
    assert.match(h1, /^[0-9a-f]{64}$/);
  });
  test('different keys hash differently', async () => {
    assert.notEqual(await hashApiKey('key-a'), await hashApiKey('key-b'));
  });
});

describe('buildOrgRecord', () => {
  test('applies TEAM_PRO default max_seats when not given', () => {
    const org = buildOrgRecord({ orgId: 'org_1', name: 'Acme', ownerUserId: 'o@acme.com', plan: 'TEAM_PRO', billingEmail: 'b@acme.com' });
    assert.equal(org.max_seats, ORG_PLANS.TEAM_PRO.maxSeats);
    assert.equal(org.plan, 'TEAM_PRO');
  });
  test('applies ENTERPRISE default max_seats', () => {
    const org = buildOrgRecord({ orgId: 'org_1', name: 'Acme', ownerUserId: 'o@acme.com', plan: 'ENTERPRISE', billingEmail: 'b@acme.com' });
    assert.equal(org.max_seats, ORG_PLANS.ENTERPRISE.maxSeats);
  });
  test('an explicit max_seats overrides the plan default', () => {
    const org = buildOrgRecord({ orgId: 'org_1', name: 'Acme', ownerUserId: 'o@acme.com', plan: 'TEAM_PRO', billingEmail: 'b@acme.com', maxSeats: 12 });
    assert.equal(org.max_seats, 12);
  });
  test('an invalid plan falls back to TEAM_PRO rather than throwing', () => {
    const org = buildOrgRecord({ orgId: 'org_1', name: 'Acme', ownerUserId: 'o@acme.com', plan: 'BOGUS', billingEmail: 'b@acme.com' });
    assert.equal(org.plan, 'TEAM_PRO');
  });
  test('name is truncated to 200 chars', () => {
    const org = buildOrgRecord({ orgId: 'org_1', name: 'x'.repeat(500), ownerUserId: 'o@acme.com', plan: 'TEAM_PRO', billingEmail: 'b@acme.com' });
    assert.equal(org.name.length, 200);
  });
});

describe('buildOrgMemberRecord', () => {
  test('an invalid role falls back to ANALYST rather than throwing', () => {
    const m = buildOrgMemberRecord({ orgId: 'org_1', email: 'x@acme.com', role: 'BOGUS', apiKeyHash: 'h' });
    assert.equal(m.role, 'ANALYST');
  });
  test('status defaults to active', () => {
    const m = buildOrgMemberRecord({ orgId: 'org_1', email: 'x@acme.com', role: 'ADMIN', apiKeyHash: 'h' });
    assert.equal(m.status, 'active');
    assert.equal(m.id, 'org_1:x@acme.com');
  });
});

describe('invite records', () => {
  test('buildInviteRecord defaults to a 7-day expiry', () => {
    const at = new Date('2026-01-01T00:00:00Z');
    const invite = buildInviteRecord({ orgId: 'org_1', email: 'x@acme.com', role: 'ANALYST', invitedBy: 'a@acme.com' }, at);
    assert.equal(invite.expires_at, '2026-01-08T00:00:00.000Z');
  });
  test('isInviteExpired is false before expiry, true after', () => {
    const at = new Date('2026-01-01T00:00:00Z');
    const invite = buildInviteRecord({ orgId: 'org_1', email: 'x@acme.com', role: 'ANALYST', invitedBy: 'a@acme.com' }, at);
    assert.equal(isInviteExpired(invite, new Date('2026-01-05T00:00:00Z')), false);
    assert.equal(isInviteExpired(invite, new Date('2026-01-09T00:00:00Z')), true);
  });
  test('isInviteExpired treats a missing/malformed invite as expired (fail closed)', () => {
    assert.equal(isInviteExpired(null), true);
    assert.equal(isInviteExpired({}), true);
  });
});

describe('computeSeatUsage', () => {
  test('reports seats_available and at_capacity correctly below, at, and over capacity', () => {
    const org = { max_seats: 5 };
    assert.deepEqual(computeSeatUsage(org, 3), { max_seats: 5, seats_used: 3, seats_available: 2, at_capacity: false });
    assert.deepEqual(computeSeatUsage(org, 5), { max_seats: 5, seats_used: 5, seats_available: 0, at_capacity: true });
    assert.deepEqual(computeSeatUsage(org, 7), { max_seats: 5, seats_used: 7, seats_available: 0, at_capacity: true });
  });
  test('handles a missing/zero max_seats without throwing', () => {
    assert.deepEqual(computeSeatUsage({}, 1), { max_seats: 0, seats_used: 1, seats_available: 0, at_capacity: true });
  });
});

describe('aggregateOrgUsage', () => {
  test('sums requests/credits across members and merges endpoint_usage', () => {
    const result = aggregateOrgUsage([
      { user_id: 'a@x.com', requests_count: 100, credits_consumed: 50, endpoint_usage: { feed: 80, search: 20 } },
      { user_id: 'b@x.com', requests_count: 40, credits_consumed: 10, endpoint_usage: { feed: 40 } },
    ], '2026-08-31');
    assert.equal(result.members_counted, 2);
    assert.equal(result.total_requests, 140);
    assert.equal(result.total_credits_consumed, 60);
    assert.deepEqual(result.endpoint_usage, { feed: 120, search: 20 });
  });
  test('skips null entries (a member with no usage-meter data yet) without throwing', () => {
    const result = aggregateOrgUsage([null, { user_id: 'a@x.com', requests_count: 5, credits_consumed: 1, endpoint_usage: {} }, null], '2026-08-31');
    assert.equal(result.members_counted, 1);
    assert.equal(result.total_requests, 5);
  });
  test('an empty/undefined member list produces an all-zero total, not a throw', () => {
    const result = aggregateOrgUsage(undefined, '2026-08-31');
    assert.equal(result.members_counted, 0);
    assert.equal(result.total_requests, 0);
    assert.deepEqual(result.endpoint_usage, {});
  });
});

describe('buildOrgInviteEmailHtml', () => {
  test('includes the org name, role, and invite URL, and escapes HTML in user-controlled fields', () => {
    const html = buildOrgInviteEmailHtml({ orgName: '<script>alert(1)</script>', inviterEmail: 'a@x.com', role: 'ADMIN', inviteUrl: 'https://x/accept?token=abc' });
    assert.equal(html.includes('<script>alert(1)</script>'), false);
    assert.match(html, /&lt;script&gt;/);
    assert.match(html, /ADMIN/);
    assert.match(html, /https:\/\/x\/accept\?token=abc/);
  });
});

describe('resolveSeatAddonContactUrl', () => {
  test('builds a mailto: link carrying org id, seat count, and price', () => {
    const url = resolveSeatAddonContactUrl({ orgId: 'org_1', orgName: 'Acme', seatsRequested: 10, billingEmail: 'b@acme.com' });
    assert.match(url, /^mailto:enterprise@cyberdudebivash\.com\?/);
    const decoded = decodeURIComponent(url);
    assert.match(decoded, /org_1/);
    assert.match(decoded, /Seats requested: 10/);
    assert.match(decoded, /\$30\/analyst\/mo/);
  });
});

describe('GST invoice', () => {
  const org = buildOrgRecord({ orgId: 'org_1', name: 'Acme SOC', ownerUserId: 'o@acme.com', plan: 'TEAM_PRO', billingEmail: 'billing@acme.com' });

  test('computes subtotal, 18% GST, and total correctly', () => {
    const inv = buildGstInvoiceRecord({ invoiceId: 'inv_1', org, seatsBilled: 3, periodStart: '2026-09-01', periodEnd: '2026-09-30' });
    assert.equal(inv.subtotal_usd, 3 * SEAT_ADDON_PRICE_USD_PER_MONTH);
    assert.equal(inv.gst_rate, 0.18);
    assert.equal(inv.gst_amount_usd, Math.round(inv.subtotal_usd * 0.18 * 100) / 100);
    assert.equal(inv.total_usd, Math.round((inv.subtotal_usd + inv.gst_amount_usd) * 100) / 100);
  });
  test('carries the real seller GSTIN used consistently across the site', () => {
    const inv = buildGstInvoiceRecord({ invoiceId: 'inv_1', org, seatsBilled: 1, periodStart: '2026-09-01', periodEnd: '2026-09-30' });
    assert.equal(inv.seller_gstin, '21ARKPN8270G1ZP');
  });
  test('buyer_gstin defaults to null when not supplied', () => {
    const inv = buildGstInvoiceRecord({ invoiceId: 'inv_1', org, seatsBilled: 1, periodStart: '2026-09-01', periodEnd: '2026-09-30' });
    assert.equal(inv.buyer_gstin, null);
  });

  test('renderInvoiceHtml produces a printable page containing the total, GSTIN, and org name, with HTML-escaped org name', () => {
    const dangerousOrg = { ...org, name: '<b>Acme</b> & Co' };
    const inv = buildGstInvoiceRecord({ invoiceId: 'inv_1', org: dangerousOrg, seatsBilled: 2, periodStart: '2026-09-01', periodEnd: '2026-09-30' });
    const html = renderInvoiceHtml(inv);
    assert.match(html, /21ARKPN8270G1ZP/);
    assert.match(html, /\$60\.00/); // 2 seats * 30 subtotal
    assert.equal(html.includes('<b>Acme</b>'), false);
    assert.match(html, /&lt;b&gt;Acme&lt;\/b&gt;/);
  });
});
