// CYBERDUDEBIVASH SENTINEL APEX — Revenue Engine production security entrypoint
// P0 control: the legacy manual-payment submission/approval workflow is retired.
//
// Why this wrapper exists instead of weakening the existing Revenue Engine internals:
// - payment-submission.html is already retired in favor of automated checkout;
// - the legacy public POST /api/payments/submit accepted caller-controlled commercial claims;
// - legacy pending records could still reach the admin approval -> entitlement path;
// - production must therefore fail closed BEFORE any persistence, notification, approval,
//   provisioning, email, API-key issuance, or entitlement side effect can occur.
//
// All non-retired routes are delegated unchanged to the existing Revenue Engine.
import revenueEngine from "./index.js";

export const MANUAL_PAYMENT_RETIRED_CODE = "MANUAL_PAYMENT_RETIRED";

function retiredManualPaymentResponse() {
  return new Response(JSON.stringify({
    success: false,
    code: MANUAL_PAYMENT_RETIRED_CODE,
    error: "Legacy manual payment processing is retired. Use verified Razorpay checkout.",
  }), {
    status: 410,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store, no-cache, must-revalidate, private",
      "pragma": "no-cache",
      "deprecation": "true",
      "sunset": "Sat, 05 Sep 2026 00:00:00 GMT",
    },
  });
}

function isRetiredManualPaymentMutation(path, method) {
  if (method !== "POST") return false;
  if (path === "/api/payments/submit") return true;
  // Existing records may include attacker-controlled amount/plan assertions from the retired
  // public workflow. Blocking approval closes the residual money -> entitlement trust boundary.
  if (path.startsWith("/api/payments/approve/")) return true;
  return false;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (isRetiredManualPaymentMutation(url.pathname, request.method)) {
      return retiredManualPaymentResponse();
    }
    return revenueEngine.fetch(request, env, ctx);
  },

  async scheduled(event, env, ctx) {
    return revenueEngine.scheduled(event, env, ctx);
  },
};

export { isRetiredManualPaymentMutation, retiredManualPaymentResponse };
