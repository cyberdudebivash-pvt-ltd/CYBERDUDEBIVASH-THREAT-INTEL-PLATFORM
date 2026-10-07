/**
 * Ephemeral owner-controlled webhook certification sink.
 *
 * Purpose: let the production Cyber Watchdog canary prove verification
 * challenges, signed delivery, delivery persistence and Retry-After handling
 * without depending on a third-party capture service or a long-lived operator
 * secret. State lives only in the already-bound SECURITY_HUB_KV and expires
 * automatically. No new Cloudflare binding, trigger, bucket or database.
 *
 * Security invariants:
 * - sink identifiers are 128-bit random capabilities and expire after 15 min;
 * - inspection/mode changes require an independent 256-bit bearer token;
 * - only bounded Watchdog headers + bounded raw JSON are retained;
 * - request bodies are capped at 64 KiB;
 * - inspection responses are no-store and never CORS-enabled here;
 * - cleanup is explicit and TTL-backed.
 */

export const CERTIFICATION_SINK_PREFIX = "/api/certification/webhook-sink/";
export const CERTIFICATION_SINK_TTL_SEC = 15 * 60;
export const CERTIFICATION_SINK_MAX_BODY_BYTES = 64 * 1024;
export const CERTIFICATION_SINK_MAX_RECORDS = 32;
export const CERTIFICATION_SINK_KV_SETTLE_MS = 65_000;

const STATE_PREFIX = "cert:webhook-sink:";
const RECORD_MARKER = ":record:";

function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...headers,
    },
  });
}

function randomHex(bytes) {
  const buf = crypto.getRandomValues(new Uint8Array(bytes));
  return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(String(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function constantTimeHexEqual(a, b) {
  const x = String(a || "");
  const y = String(b || "");
  const len = Math.max(x.length, y.length);
  let diff = x.length ^ y.length;
  for (let i = 0; i < len; i += 1) diff |= (x.charCodeAt(i) || 0) ^ (y.charCodeAt(i) || 0);
  return diff === 0;
}

function stateKey(id) {
  return STATE_PREFIX + id;
}

function recordPrefix(id) {
  return STATE_PREFIX + id + RECORD_MARKER;
}

function parsePath(path) {
  const escaped = CERTIFICATION_SINK_PREFIX.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
  const match = new RegExp("^" + escaped + "([0-9a-f]{32})(/__inspect(?:/mode)?)?$").exec(path);
  if (!match) return null;
  return { id: match[1], suffix: match[2] || "" };
}

async function readState(env, id) {
  if (!env?.SECURITY_HUB_KV || typeof env.SECURITY_HUB_KV.get !== "function") return null;
  try {
    const raw = await env.SECURITY_HUB_KV.get(stateKey(id));
    if (!raw) return null;
    return typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch (_) {
    return null;
  }
}

async function writeState(env, id, state) {
  await env.SECURITY_HUB_KV.put(stateKey(id), JSON.stringify(state), {
    expirationTtl: CERTIFICATION_SINK_TTL_SEC,
  });
}

async function inspectAuthorized(request, state) {
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  const got = await sha256Hex(auth.slice("Bearer ".length));
  return constantTimeHexEqual(got, state.inspect_token_hash);
}

function capturedHeaders(request) {
  const allowed = [
    "content-type",
    "user-agent",
    "x-cdb-watchdog-event-id",
    "x-cdb-watchdog-delivery-id",
    "x-cdb-watchdog-timestamp",
    "x-cdb-watchdog-signature",
  ];
  const out = {};
  for (const name of allowed) {
    const value = request.headers.get(name);
    if (value !== null) out[name] = value;
  }
  return out;
}

async function listRecords(env, id) {
  const prefix = recordPrefix(id);
  const listed = await env.SECURITY_HUB_KV.list({ prefix, limit: CERTIFICATION_SINK_MAX_RECORDS });
  const rows = [];
  for (const key of listed.keys || []) {
    const raw = await env.SECURITY_HUB_KV.get(key.name);
    if (!raw) continue;
    try { rows.push(typeof raw === "string" ? JSON.parse(raw) : raw); } catch (_) {}
  }
  rows.sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
  return rows.slice(0, CERTIFICATION_SINK_MAX_RECORDS);
}

export function isCertificationWebhookSinkPath(path) {
  return parsePath(path) !== null;
}

/**
 * Cloudflare Worker-to-self HTTPS subrequests do not reliably re-enter the
 * same Worker route; on the production custom domain they can fall through
 * to the underlying origin and return method-level responses such as 405.
 *
 * This adapter keeps ONLY an admin-provisioned certification sink inside the
 * Worker. It first proves that the capability id exists in SECURITY_HUB_KV
 * and that the stored origin exactly matches the requested origin. Any other
 * URL -- including every real customer webhook destination -- is delegated
 * unchanged to fallbackFetch and therefore retains the normal DNS/SSRF and
 * network-delivery path.
 */
export function certificationWebhookSinkFetch(env, fallbackFetch = fetch) {
  return async (input, init) => {
    const request = input instanceof Request ? new Request(input, init) : new Request(input, init);
    const url = new URL(request.url);
    const parsed = parsePath(url.pathname);
    if (!parsed) return fallbackFetch(input, init);

    const state = await readState(env, parsed.id);
    if (!state || typeof state.origin !== "string" || state.origin !== url.origin) {
      return fallbackFetch(input, init);
    }
    return routeCertificationWebhookSink(request, env, url.pathname);
  };
}

export async function createCertificationWebhookSink(request, env) {
  if (!env?.SECURITY_HUB_KV || typeof env.SECURITY_HUB_KV.put !== "function") {
    return json({ error: "certification_sink_storage_unavailable" }, 503);
  }
  const id = randomHex(16);
  const inspectToken = randomHex(32);
  const now = Date.now();
  const origin = new URL(request.url).origin;
  const state = {
    schema_version: 2,
    origin,
    inspect_token_hash: await sha256Hex(inspectToken),
    mode: { status: 204, retry_after: null },
    created_at: new Date(now).toISOString(),
    expires_at: new Date(now + CERTIFICATION_SINK_TTL_SEC * 1000).toISOString(),
  };
  try {
    await writeState(env, id, state);
  } catch (_) {
    return json({ error: "certification_sink_storage_unavailable" }, 503);
  }
  const sinkUrl = origin + CERTIFICATION_SINK_PREFIX + id;
  return json({
    status: "created",
    sink_id: id,
    sink_url: sinkUrl,
    inspect_url: sinkUrl + "/__inspect",
    inspect_token: inspectToken,
    expires_at: state.expires_at,
    storage: "SECURITY_HUB_KV",
    ttl_seconds: CERTIFICATION_SINK_TTL_SEC,
    // The first webhook may arrive through a different Cloudflare location.
    // Expose the same conservative KV settle bound used for mode changes so
    // the certification workflow never races initial capability propagation.
    settle_ms: CERTIFICATION_SINK_KV_SETTLE_MS,
  }, 201);
}

export async function deleteCertificationWebhookSink(env, id) {
  if (!/^[0-9a-f]{32}$/.test(String(id || ""))) return json({ error: "invalid_sink_id" }, 400);
  if (!env?.SECURITY_HUB_KV) return json({ error: "certification_sink_storage_unavailable" }, 503);
  try {
    await env.SECURITY_HUB_KV.delete(stateKey(id));
    let cursor;
    do {
      const listed = await env.SECURITY_HUB_KV.list({ prefix: recordPrefix(id), cursor, limit: 1000 });
      await Promise.all((listed.keys || []).map((k) => env.SECURITY_HUB_KV.delete(k.name)));
      cursor = listed.list_complete ? undefined : listed.cursor;
    } while (cursor);
    return json({ status: "deleted", sink_id: id });
  } catch (_) {
    return json({ error: "certification_sink_cleanup_failed" }, 503);
  }
}

export async function routeCertificationWebhookSink(request, env, path) {
  const parsed = parsePath(path);
  if (!parsed) return null;
  const state = await readState(env, parsed.id);
  if (!state) return json({ error: "certification_sink_not_found_or_expired" }, 404);

  if (parsed.suffix.startsWith("/__inspect")) {
    if (!(await inspectAuthorized(request, state))) return json({ error: "unauthorized" }, 401);

    if (parsed.suffix === "/__inspect/mode") {
      if (request.method === "GET") {
        return json({ mode: state.mode, expires_at: state.expires_at });
      }
      if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405, { Allow: "GET, POST" });
      let body;
      try { body = await request.json(); } catch (_) { return json({ error: "invalid_json" }, 400); }
      const status = Number(body?.status);
      if (status !== 204 && status !== 503) {
        return json({ error: "invalid_mode", allowed_statuses: [204, 503] }, 400);
      }
      const retryAfter = body?.retry_after == null ? null : Number(body.retry_after);
      if (retryAfter !== null && (!Number.isInteger(retryAfter) || retryAfter < 1 || retryAfter > 3600)) {
        return json({ error: "invalid_retry_after" }, 400);
      }
      const changed = state.mode?.status !== status || state.mode?.retry_after !== retryAfter;
      const next = { ...state, mode: { status, retry_after: retryAfter } };
      try { await writeState(env, parsed.id, next); } catch (_) {
        return json({ error: "certification_sink_storage_unavailable" }, 503);
      }
      return json({
        status,
        retry_after: retryAfter,
        settle_ms: changed ? CERTIFICATION_SINK_KV_SETTLE_MS : 0,
      });
    }

    if (request.method !== "GET") return json({ error: "method_not_allowed" }, 405, { Allow: "GET" });
    try {
      return json({ records: await listRecords(env, parsed.id), expires_at: state.expires_at });
    } catch (_) {
      return json({ error: "certification_sink_storage_unavailable" }, 503);
    }
  }

  if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405, { Allow: "POST" });
  const contentLength = Number(request.headers.get("Content-Length") || 0);
  if (Number.isFinite(contentLength) && contentLength > CERTIFICATION_SINK_MAX_BODY_BYTES) {
    return json({ error: "payload_too_large" }, 413);
  }

  let raw;
  try { raw = await request.text(); } catch (_) { return json({ error: "unreadable_body" }, 400); }
  if (new TextEncoder().encode(raw).byteLength > CERTIFICATION_SINK_MAX_BODY_BYTES) {
    return json({ error: "payload_too_large" }, 413);
  }
  let body;
  try { body = JSON.parse(raw); } catch (_) { return json({ error: "invalid_json" }, 400); }

  const record = {
    at: new Date().toISOString(),
    headers: capturedHeaders(request),
    raw,
  };
  try {
    const key = recordPrefix(parsed.id) + Date.now().toString(36) + "-" + randomHex(8);
    await env.SECURITY_HUB_KV.put(key, JSON.stringify(record), {
      expirationTtl: CERTIFICATION_SINK_TTL_SEC,
    });
  } catch (_) {
    return json({ error: "certification_sink_storage_unavailable" }, 503);
  }

  if (body?.type === "watchdog.verification" && typeof body.challenge === "string") {
    return json({ challenge: body.challenge }, 200);
  }

  const status = state.mode?.status === 503 ? 503 : 204;
  const headers = { "Cache-Control": "no-store" };
  if (status === 503 && state.mode?.retry_after) headers["Retry-After"] = String(state.mode.retry_after);
  return new Response(null, { status, headers });
}
