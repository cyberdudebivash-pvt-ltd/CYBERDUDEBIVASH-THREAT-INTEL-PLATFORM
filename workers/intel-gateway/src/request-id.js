/**
 * Canonical request-correlation helper for the intel-gateway.
 *
 * Accept a caller-supplied X-Request-ID only when it is short and safe to
 * log/reflect. Otherwise mint a new opaque identifier. This module is kept
 * dependency-free so it can be unit-tested with plain node --test.
 */
const REQUEST_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function generateRequestId() {
  const uuid = globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
  return `sentinel-apex-${uuid}`;
}

export function resolveRequestId(request) {
  const supplied = String(request?.headers?.get?.('X-Request-ID') || '').trim();
  return REQUEST_ID_RE.test(supplied) ? supplied : generateRequestId();
}

export function withRequestId(response, requestId) {
  const headers = new Headers(response.headers);
  headers.set('X-Request-ID', requestId);
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export function withoutRequestId(response) {
  const headers = new Headers(response.headers);
  headers.delete('X-Request-ID');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export { REQUEST_ID_RE };
