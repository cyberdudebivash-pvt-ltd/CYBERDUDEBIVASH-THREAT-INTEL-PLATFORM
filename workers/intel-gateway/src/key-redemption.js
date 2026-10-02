/**
 * One-time API key redemption (F22, 2026-10-02).
 *
 * Owner decision: a raw API key is never put in an email. An email carries
 * only a one-time link; the key is revealed once, over POST, to whoever
 * opens that link and asks for it.
 *
 *   issue:  32 random bytes -> base64url token. Only SHA-256(token) is
 *           stored: API_KEYS_KV "key_redeem:<hex>" -> { key, tier, ... },
 *           expiring after REDEMPTION_TTL_SECONDS. The link carries the
 *           token in the URL fragment, which browsers never send to a
 *           server, so it stays out of access logs and Referer headers.
 *   redeem: the token arrives in a POST body. The record must exist and be
 *           unexpired, the key must still authenticate (the caller passes
 *           the gateway's own access decision), and the one-time claim is
 *           taken atomically (the gateway passes its Durable Object claim)
 *           before the key is returned. A replay, an unknown or expired
 *           token, and a revoked key are all refused with the same answer.
 *
 * Pure apart from the injected store and claim, so the decision table is
 * unit-testable. The revenue engine writes the same record shape for keys
 * it provisions (issueActivationLink in workers/revenue-engine/src/index.js);
 * workers/revenue-engine/src/__tests__/activation-link.test.js redeems such a
 * link here, pinning the two to one contract.
 */

export const REDEMPTION_PREFIX = "key_redeem:";
export const REDEMPTION_TTL_SECONDS = 72 * 3600;
export const REDEMPTION_PAGE = "https://intel.cyberdudebivash.com/customer/api-keys.html";

const TOKEN_RE = /^[A-Za-z0-9_-]{43}$/;

export function isRedemptionToken(token) {
  return typeof token === "string" && TOKEN_RE.test(token);
}

function base64url(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function hashRedemptionToken(token) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function redemptionUrl(token) {
  return `${REDEMPTION_PAGE}#redeem=${token}`;
}

/**
 * Stores a one-time redemption for apiKey. Returns the token (for the email
 * link only; never log it) and a short, non-secret reference for audit.
 */
export async function issueKeyRedemption(kv, apiKey, { tier = null, source = null, nowMs = Date.now(), ttlSeconds = REDEMPTION_TTL_SECONDS } = {}) {
  if (!kv || typeof apiKey !== "string" || !apiKey) throw new Error("redemption store or key missing");
  const token = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const hash = await hashRedemptionToken(token);
  const expiresAt = new Date(nowMs + ttlSeconds * 1000).toISOString();
  await kv.put(REDEMPTION_PREFIX + hash, JSON.stringify({
    v: 1, key: apiKey, tier, source, issued_at: new Date(nowMs).toISOString(), expires_at: expiresAt,
  }), { expirationTtl: ttlSeconds });
  return { token, url: redemptionUrl(token), expires_at: expiresAt, ref: hash.slice(0, 12) };
}

/**
 * deps.kv        the store issueKeyRedemption wrote to
 * deps.claim     (hash) -> "claimed" | "replay" | "unavailable"; atomic, once per hash
 * deps.keyAccess (apiKey) -> { ok: true, record } | { ok: false, reason }, reason
 *                "unavailable" when the decision could not be made
 *
 * Returns { status, outcome, ref, api_key?, tier?, expires_at? }. Only a 200
 * carries the key. 503 means nothing was spent: the same link works later.
 */
export async function redeemKeyToken(token, deps, nowMs = Date.now()) {
  if (!isRedemptionToken(token)) return { status: 400, outcome: "malformed", ref: null };
  const hash = await hashRedemptionToken(token);
  const ref = hash.slice(0, 12);
  let rec;
  try {
    rec = await deps.kv.get(REDEMPTION_PREFIX + hash, "json");
  } catch (_) {
    return { status: 503, outcome: "unavailable", ref };
  }
  if (!rec || typeof rec.key !== "string" || !rec.key) return { status: 410, outcome: "unknown_or_used", ref };
  if (!(Date.parse(rec.expires_at) > nowMs)) return { status: 410, outcome: "expired", ref };

  // The key must still authenticate before the one-time claim is spent, so
  // a transient authority outage never burns a customer's only link.
  const access = await deps.keyAccess(rec.key);
  if (!access.ok && access.reason === "unavailable") return { status: 503, outcome: "unavailable", ref };
  if (!access.ok) {
    try { await deps.kv.delete(REDEMPTION_PREFIX + hash); } catch (_) { /* expires anyway */ }
    return { status: 410, outcome: "key_not_active", ref, reason: access.reason || "denied" };
  }

  const claim = await deps.claim(hash);
  if (claim === "unavailable") return { status: 503, outcome: "unavailable", ref };
  if (claim !== "claimed") return { status: 410, outcome: "replay", ref };

  try { await deps.kv.delete(REDEMPTION_PREFIX + hash); } catch (_) { /* the claim already blocks reuse */ }
  return {
    status: 200, outcome: "redeemed", ref,
    api_key: rec.key, tier: access.record?.tier || rec.tier || null, expires_at: access.record?.expires_at || null,
  };
}
