// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- B2B Organization & Team Seats (pure module)
//
// ARCHITECTURE NOTE (this is a genuine additive architectural event, not a
// routine feature -- see this repo's CLAUDE.md "Architecture Preservation
// Rule"): the platform's real, live data model (confirmed by direct
// investigation of workers/intel-gateway/src/index.js's resolveAuth() /
// provisionApiKey()) is 1 API key : 1 customer via API_KEYS_KV. There is no
// D1 or Postgres database anywhere in this deployment (wrangler.toml has
// only kv_namespaces + r2_buckets); a from-scratch relational Organization/
// TeamMember schema would need infrastructure this repo does not have
// provisioned and this session cannot provision.
//
// Current architecture: 1:1 key:customer, API_KEYS_KV authoritative,
//   REVENUE_CRM_KV an additive read-mirror for the customer portal
//   (provisionApiKey() already writes both -- see index.js:3011+).
// Proposed architecture: an additive Organization/TeamMember layer stored
//   in REVENUE_CRM_KV (the existing binding already used for this exact
//   purpose -- customer-facing account data -- zero new infrastructure to
//   provision) that GROUPS N individually-real API_KEYS_KV keys under one
//   org. Every team member still gets a real, independently-valid key via
//   the existing provisionApiKey() -- nothing about core auth/entitlement
//   resolution changes. The org layer only adds invite/seat-limit/usage-
//   rollup bookkeeping on top.
// Reason current architecture is insufficient: no way to group keys,
//   enforce a seat cap, or roll up usage across a company's several
//   analysts -- each key today is billed/tracked in total isolation.
// Expected benefits: $249-$999/mo team/enterprise seat revenue tier this
//   task exists to unlock; SOC teams no longer share one key across
//   analysts (today's only workaround, which defeats per-user audit trails).
// Compatibility: 100% -- every existing single-key customer is simply an
//   org-less key, completely unaffected; this reads/writes only new key
//   prefixes (org:, orgmember:, org_owner:, org_member_index:, org_invite:,
//   org_invoice:) inside REVENUE_CRM_KV, nothing else.
// Migration: none required -- opt-in only (POST /api/org/create).
// Rollback: delete the new routes in index.js; the new KV keys are inert
//   (nothing else in the codebase reads them) and can be left or purged.
//
// KV keys (all in REVENUE_CRM_KV):
//   org:<org_id>                    -- Organization record
//   orgmember:<org_id>:<email>      -- TeamMember record
//   org_owner:<customer_id>         -- customer_id -> org_id (one org per owner)
//   org_member_index:<key_hash>     -- SHA-256(api key) -> {org_id, email}
//                                       (lets a member's OWN presented key
//                                       resolve their org/role without a
//                                       KV list/scan -- REVENUE_CRM_KV has
//                                       no query-by-field capability)
//   org_invite:<token>              -- pending invite, TTL-bound
//   org_invoice:<invoice_id>        -- GST invoice record
//
// Extracted as a pure module (same pattern as daily-quota.js/feeds.js/
// taxii.js) for `node --test` unit testing outside index.js's pricing.js
// import chain. All KV I/O and email-sending stays in index.js's route
// handlers; this file only builds records and does math.
// =============================================================================

export const ORG_ROLES = new Set(["ADMIN", "ANALYST", "AUDITOR"]);

export const ORG_PLANS = {
  TEAM_PRO: { label: "Team Pro", maxSeats: 5, includedTier: "PRO" },
  ENTERPRISE: { label: "Enterprise", maxSeats: 25, includedTier: "ENTERPRISE" },
};

export const SEAT_ADDON_PRICE_USD_PER_MONTH = 30;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(email) {
  return typeof email === "string" && EMAIL_RE.test(email) && email.length <= 254;
}

export function isValidRole(role) {
  return ORG_ROLES.has(role);
}

export function isValidPlan(plan) {
  return Object.prototype.hasOwnProperty.call(ORG_PLANS, plan);
}

function randHex(bytes) {
  return Array.from(crypto.getRandomValues(new Uint8Array(bytes))).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function buildOrgId() {
  return `org_${randHex(12)}`;
}

export function buildInviteToken() {
  return `orginv_${randHex(24)}`;
}

/** SHA-256 hex digest of a raw API key -- org_member_index never stores the plaintext key. */
export async function hashApiKey(rawKey) {
  const data = new TextEncoder().encode(rawKey || "");
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * @param {{orgId:string, name:string, ownerUserId:string, plan:string, billingEmail:string, maxSeats?:number, customRateLimit?:number|null}} p
 */
export function buildOrgRecord({ orgId, name, ownerUserId, plan, billingEmail, maxSeats, customRateLimit }, at = new Date()) {
  const planDef = ORG_PLANS[plan] || ORG_PLANS.TEAM_PRO;
  return {
    id: orgId,
    name: (name || "").slice(0, 200),
    owner_user_id: ownerUserId,
    plan: isValidPlan(plan) ? plan : "TEAM_PRO",
    billing_email: billingEmail,
    max_seats: Number.isFinite(maxSeats) && maxSeats > 0 ? maxSeats : planDef.maxSeats,
    custom_rate_limit: Number.isFinite(customRateLimit) ? customRateLimit : null,
    created_at: at.toISOString(),
  };
}

/** @param {{orgId:string, email:string, role:string, apiKeyHash:string, invitedBy?:string}} p */
export function buildOrgMemberRecord({ orgId, email, role, apiKeyHash, invitedBy }, at = new Date()) {
  return {
    id: `${orgId}:${email}`,
    org_id: orgId,
    email,
    role: isValidRole(role) ? role : "ANALYST",
    api_key_hash: apiKeyHash,
    invited_by: invitedBy || null,
    invited_at: at.toISOString(),
    joined_at: at.toISOString(),
    status: "active",
  };
}

/** @param {{orgId:string, email:string, role:string, invitedBy:string}} p */
export function buildInviteRecord({ orgId, email, role, invitedBy }, at = new Date(), ttlDays = 7) {
  const expires = new Date(at.getTime() + ttlDays * 86400000);
  return {
    token: null, // set by caller as the KV key, kept off the value on purpose (redundant)
    org_id: orgId,
    email,
    role: isValidRole(role) ? role : "ANALYST",
    invited_by: invitedBy,
    invited_at: at.toISOString(),
    expires_at: expires.toISOString(),
  };
}

export function isInviteExpired(invite, at = new Date()) {
  if (!invite?.expires_at) return true;
  return new Date(invite.expires_at).getTime() < at.getTime();
}

/**
 * Seat math -- pure, no KV. index.js counts active orgmember: records for
 * an org and passes the count in.
 */
export function computeSeatUsage(org, activeMemberCount) {
  const maxSeats = org?.max_seats || 0;
  const used = Math.max(0, activeMemberCount || 0);
  return {
    max_seats: maxSeats,
    seats_used: used,
    seats_available: Math.max(0, maxSeats - used),
    at_capacity: used >= maxSeats,
  };
}

/**
 * Combines usage-meter.js's getUsageSummary() results (one per org member,
 * fetched by index.js -- this function does no I/O) into one org-wide
 * total. Reuses that module's real, already-live-but-previously-unwired
 * per-user usage tracking rather than re-deriving usage from scratch.
 * @param {Array<{user_id:string, requests_count:number, credits_consumed:number, endpoint_usage:Record<string,number>}|null>} memberSummaries
 */
export function aggregateOrgUsage(memberSummaries, date) {
  const perMember = [];
  let totalRequests = 0;
  let totalCredits = 0;
  const endpointTotals = {};

  for (const s of memberSummaries || []) {
    if (!s) continue;
    perMember.push({
      user_id: s.user_id,
      requests_count: s.requests_count || 0,
      credits_consumed: s.credits_consumed || 0,
    });
    totalRequests += s.requests_count || 0;
    totalCredits += s.credits_consumed || 0;
    for (const [ep, count] of Object.entries(s.endpoint_usage || {})) {
      endpointTotals[ep] = (endpointTotals[ep] || 0) + count;
    }
  }

  return {
    date,
    members_counted: perMember.length,
    total_requests: totalRequests,
    total_credits_consumed: totalCredits,
    endpoint_usage: endpointTotals,
    per_member: perMember,
  };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/**
 * Invite email body -- same Resend-compatible inline-styled HTML pattern
 * index.js's sendActivationEmail() already uses (not reusing that function
 * itself: its content is activation-specific, but the same fetch call
 * shape index.js already has, just with this HTML).
 */
export function buildOrgInviteEmailHtml({ orgName, inviterEmail, role, inviteUrl }) {
  return `<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;background:#050c18;color:#e2e8f0;padding:32px;">
  <div style="max-width:480px;margin:0 auto;background:#0b1422;border:1px solid #162030;border-radius:14px;padding:32px;">
    <div style="font-family:monospace;font-weight:900;color:#00ffc6;letter-spacing:2px;margin-bottom:20px;">SENTINEL APEX</div>
    <h2 style="margin:0 0 12px;">You're invited to ${escapeHtml(orgName)}</h2>
    <p style="color:#94a3b8;font-size:14px;">${escapeHtml(inviterEmail)} invited you to join their CYBERDUDEBIVASH(R) SENTINEL APEX team as <strong>${escapeHtml(role)}</strong>. Accept below to get your own API key.</p>
    <a href="${escapeHtml(inviteUrl)}" style="display:inline-block;margin-top:16px;padding:12px 24px;background:#00ffc6;color:#000;font-weight:800;border-radius:8px;text-decoration:none;">Accept Invite</a>
    <p style="color:#475569;font-size:12px;margin-top:24px;">This invite expires in 7 days. If you weren't expecting it, you can ignore this email.</p>
  </div>
  </body></html>`;
}

/**
 * Seat add-on checkout: NO self-serve product exists for a variable-
 * quantity seat purchase (billing-checkout.js's Gumroad links are fixed
 * single-seat products; Razorpay order-amount math in upgrade.html has no
 * seat-count dimension). Same honest precedent billing-checkout.js already
 * set for MSSP ("no Gumroad product... routed to a mailto instead of a
 * dead link") rather than fabricating a checkout flow for a product that
 * doesn't exist.
 */
export function resolveSeatAddonContactUrl({ orgId, orgName, seatsRequested, billingEmail }) {
  const subject = encodeURIComponent(`Team seat add-on request -- ${orgName || orgId}`);
  const body = encodeURIComponent(
    `Organization: ${orgName || "(unnamed)"} (${orgId})\n` +
    `Seats requested: ${seatsRequested}\n` +
    `Billing email: ${billingEmail || "(not provided)"}\n` +
    `Price: $${SEAT_ADDON_PRICE_USD_PER_MONTH}/analyst/mo\n\n` +
    `(Sent from the Sentinel APEX customer portal's seat add-on request form.)`
  );
  return `mailto:enterprise@cyberdudebivash.com?subject=${subject}&body=${body}`;
}

// -- GST invoice ----------------------------------------------------------
// No PDF-generation capability exists anywhere in this deployment
// (premium-reports.js's own header: "PDF generation metadata (served as
// downloadable JSON until PDF render service wired)" -- confirmed, not
// assumed). Rather than fabricate a fake PDF binary, this produces a real,
// correct, GST-compliant invoice as structured JSON plus a printable HTML
// rendering (browser print-to-PDF covers the "hand me a PDF" need without
// claiming a binary-PDF capability that doesn't exist) -- the exact same
// honesty precedent premium-reports.js already set.

const SELLER_GSTIN = "21ARKPN8270G1ZP"; // real, already used consistently across compare.html/security-compliance.html/payment-confirmation.html/SECURITY.md
const SEAT_HSN_SAC = "998319"; // SAC 998319: "Other information technology services" (India GST) -- SaaS/API-access services

/**
 * @param {{invoiceId:string, org:object, seatsBilled:number, periodStart:string, periodEnd:string, buyerGstin?:string}} p
 */
export function buildGstInvoiceRecord({ invoiceId, org, seatsBilled, periodStart, periodEnd, buyerGstin }, at = new Date()) {
  const unitPrice = SEAT_ADDON_PRICE_USD_PER_MONTH;
  const subtotal = unitPrice * seatsBilled;
  // 18% IGST for a cross-state/export B2B SaaS supply is the standard India
  // GST rate for this SAC code; buyer-state-specific CGST+SGST split is a
  // billing-desk decision outside this function's scope (documented, not
  // silently assumed) -- the record carries a single igst_amount so a
  // human can re-split it if the buyer is intra-state.
  const gstRate = 0.18;
  const gstAmount = Math.round(subtotal * gstRate * 100) / 100;
  const total = Math.round((subtotal + gstAmount) * 100) / 100;

  return {
    invoice_id: invoiceId,
    org_id: org.id,
    org_name: org.name,
    billing_email: org.billing_email,
    buyer_gstin: buyerGstin || null,
    seller_gstin: SELLER_GSTIN,
    seller_name: "CyberDudeBivash Pvt. Ltd.",
    line_items: [{
      description: `Sentinel APEX ${ORG_PLANS[org.plan]?.label || org.plan} -- seat add-ons`,
      hsn_sac: SEAT_HSN_SAC,
      quantity: seatsBilled,
      unit_price_usd: unitPrice,
      period_start: periodStart,
      period_end: periodEnd,
    }],
    subtotal_usd: subtotal,
    gst_rate: gstRate,
    gst_amount_usd: gstAmount,
    total_usd: total,
    currency: "USD",
    issued_at: at.toISOString(),
    _gst_note: "IGST rate shown; re-split into CGST+SGST manually if the buyer is intra-state with the seller.",
  };
}

export function renderInvoiceHtml(inv) {
  const rows = inv.line_items.map((li) => `
    <tr>
      <td style="padding:8px;border:1px solid #ddd;">${escapeHtml(li.description)}</td>
      <td style="padding:8px;border:1px solid #ddd;">${escapeHtml(li.hsn_sac)}</td>
      <td style="padding:8px;border:1px solid #ddd;text-align:right;">${li.quantity}</td>
      <td style="padding:8px;border:1px solid #ddd;text-align:right;">$${li.unit_price_usd.toFixed(2)}</td>
    </tr>`).join("");

  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Invoice ${escapeHtml(inv.invoice_id)}</title></head>
  <body style="font-family:system-ui,sans-serif;color:#111;max-width:720px;margin:40px auto;padding:0 20px;">
    <div style="display:flex;justify-content:space-between;border-bottom:2px solid #111;padding-bottom:16px;margin-bottom:20px;">
      <div><h1 style="margin:0;">TAX INVOICE</h1><p style="color:#555;">Invoice #${escapeHtml(inv.invoice_id)}</p></div>
      <div style="text-align:right;font-size:13px;">
        <strong>${escapeHtml(inv.seller_name)}</strong><br>GSTIN: ${escapeHtml(inv.seller_gstin)}<br>Issued: ${escapeHtml(inv.issued_at.slice(0, 10))}
      </div>
    </div>
    <div style="margin-bottom:20px;font-size:13px;">
      <strong>Bill To:</strong> ${escapeHtml(inv.org_name)}<br>
      ${escapeHtml(inv.billing_email)}<br>
      ${inv.buyer_gstin ? `GSTIN: ${escapeHtml(inv.buyer_gstin)}` : "GSTIN: (not provided)"}
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead><tr style="background:#f3f4f6;">
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Description</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">HSN/SAC</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:right;">Qty</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:right;">Unit ($)</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div style="margin-top:16px;text-align:right;font-size:13px;">
      <p>Subtotal: $${inv.subtotal_usd.toFixed(2)}</p>
      <p>GST (${(inv.gst_rate * 100).toFixed(0)}%): $${inv.gst_amount_usd.toFixed(2)}</p>
      <p style="font-size:16px;font-weight:800;">Total: $${inv.total_usd.toFixed(2)}</p>
    </div>
    <p style="color:#888;font-size:11px;margin-top:32px;">${escapeHtml(inv._gst_note)} &middot; Print this page to PDF for your records.</p>
  </body></html>`;
}
