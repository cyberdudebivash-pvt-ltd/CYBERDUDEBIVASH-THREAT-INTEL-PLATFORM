// SENTINEL APEX P0 #596 -- strong-consistency authority adapter.
//
// This module deliberately reuses the already-bound GUMROAD_PROVISIONING_LOCK
// Durable Object namespace/class as a transport for additional keyed,
 // serialized state. No new Durable Object binding, namespace, migration, or
// billing product is introduced.
//
// IMPORTANT: production use is feature-flagged OFF by default through
// AUTH_STRONG_CONSISTENCY_ENABLED. This keeps the no-new-spend/no-surprise-
// traffic mandate intact until an operator explicitly enables the extra
// Durable Object request path after reviewing its usage impact.

export function strongConsistencyEnabled(env) {
  return env?.AUTH_STRONG_CONSISTENCY_ENABLED === "true";
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(String(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function authorityStub(env, namespace, identity) {
  if (!env?.GUMROAD_PROVISIONING_LOCK) throw new Error("strong_consistency_binding_unavailable");
  const hash = await sha256Hex(identity);
  const id = env.GUMROAD_PROVISIONING_LOCK.idFromName(`${namespace}:${hash}`);
  return env.GUMROAD_PROVISIONING_LOCK.get(id);
}

async function postJson(stub, body) {
  const response = await stub.fetch("https://authority.internal/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try { data = await response.json(); } catch (_) {}
  if (!response.ok || !data?.ok) {
    throw new Error(data?.error || `strong_consistency_http_${response.status}`);
  }
  return data;
}

export async function putStrongAuthState(env, identity, state) {
  const stub = await authorityStub(env, "auth", identity);
  return postJson(stub, { action: "auth_state_put", state });
}

export async function getStrongAuthState(env, identity) {
  const stub = await authorityStub(env, "auth", identity);
  const data = await postJson(stub, { action: "auth_state_get" });
  return data.state || null;
}

export async function incrementStrongRate(env, identity, limit, resetAt) {
  const stub = await authorityStub(env, "rate", identity);
  return postJson(stub, { action: "rate_increment", limit, resetAt });
}

export function authStateDenies(state) {
  return new Set(["cancelled", "expired", "refunded", "suspended", "revoked"]).has(
    String(state?.status || "").toLowerCase()
  );
}


export function strongConsistencyCanaryEnabled(env) {
  return env?.AUTH_STRONG_CONSISTENCY_CANARY_ENABLED === "true";
}

// Admin-only, explicitly invoked production canary. It does nothing unless
// the dedicated canary flag is enabled. It reuses two fixed logical identities
// so repeated canaries do not create unbounded Durable Object instances.
export async function runStrongConsistencyCanary(env) {
  if (!strongConsistencyCanaryEnabled(env)) {
    return { ok: false, disabled: true, error: "strong_consistency_canary_disabled" };
  }

  const authIdentity = "canary:auth";
  const rateIdentity = "canary:rate";
  const now = Date.now();

  await putStrongAuthState(env, authIdentity, {
    status: "suspended",
    version: now,
    updatedAt: now,
  });
  const suspended = await getStrongAuthState(env, authIdentity);
  if (!authStateDenies(suspended)) {
    throw new Error("canary_auth_suspend_read_after_write_failed");
  }

  await putStrongAuthState(env, authIdentity, {
    status: "active",
    version: now + 1,
    updatedAt: now + 1,
  });
  const active = await getStrongAuthState(env, authIdentity);
  if (authStateDenies(active) || active?.status !== "active") {
    throw new Error("canary_auth_reactivation_read_after_write_failed");
  }

  const resetAt = now + 60000;
  let firstDenied = 0;
  let final = null;
  for (let i = 1; i <= 31; i += 1) {
    final = await incrementStrongRate(env, rateIdentity, 30, resetAt);
    if (!final.allowed && firstDenied === 0) firstDenied = i;
  }
  if (firstDenied !== 31 || final?.count !== 31) {
    throw new Error("canary_rate_boundary_failed");
  }

  return {
    ok: true,
    auth_suspend_read_after_write: true,
    auth_reactivate_read_after_write: true,
    rate_limit: 30,
    first_denied_request: firstDenied,
    final_count: final.count,
    canary_identities_reused: true,
  };
}
