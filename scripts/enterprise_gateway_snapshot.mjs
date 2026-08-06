#!/usr/bin/env node
/**
 * scripts/enterprise_gateway_snapshot.mjs
 * Project TITAN Stage 14 Phase 1 — Internal Adoption (first real, non-test consumer)
 *
 * This is the one, deliberately low-risk internal consumer this stage's brief authorizes
 * ("Adopt the Gateway for one low-risk internal workflow... No customer-visible behavior").
 * Standalone internal script — invoked manually or by CI, never by a live HTTP request — NOT a
 * change to workers/intel-gateway/src/index.js or any pNN-handlers.js file. That boundary stays
 * exactly as every prior stage (8, 10, 11, 12, 13) left it, and as this stage's own
 * zero-blast-radius tests and governance checks independently verify.
 *
 * Unlike scripts/intelligence_platform_snapshot.mjs (Stage 13, which calls platform.lookup
 * directly), this script dispatches every operation THROUGH EnterpriseGateway.dispatch() — the
 * thing this stage actually adds. It demonstrates capability routing, authorization
 * (grantedCapabilities), the middleware pipeline, and gateway-owned metrics, not just that the
 * underlying platform still works underneath it.
 *
 * Gating: reads EIG_FLAGS.INTERNAL_ADOPTION_ENABLED for the given environment
 * (enterprise-gateway/feature-flags.js) — hardcoded false in canary and production, true in
 * development and testing, mirroring EIPS_FLAGS's identical rollout pattern exactly.
 *
 * Rollback: nothing to roll back in the usual sense — this script holds no state between runs
 * (a fresh in-memory gateway every invocation) and touches no persisted storage, D1, KV, or R2.
 * Reverting is: stop invoking this script, or leave INTERNAL_ADOPTION_ENABLED at its default
 * false. No code change is required to "roll back."
 *
 * Usage:
 *   node scripts/enterprise_gateway_snapshot.mjs [environment]
 *   EIG_ENVIRONMENT=development node scripts/enterprise_gateway_snapshot.mjs
 */

import { createEnterpriseGateway } from "../workers/intel-gateway/src/enterprise-gateway/platform.js";
import { resolveEigFlags } from "../workers/intel-gateway/src/enterprise-gateway/feature-flags.js";
import { ALL_EIG_CONTRACTS } from "../workers/intel-gateway/src/enterprise-gateway/service-contracts.js";
import { createEvidenceEntity, createCanonicalEvidence } from "../workers/intel-gateway/src/evidence-registry/entity.js";
import { generateEvidenceUuid } from "../workers/intel-gateway/src/evidence-registry/identifiers.js";

const environment = process.argv[2] || process.env.EIG_ENVIRONMENT || "production";
const flags = resolveEigFlags(environment);

console.log(`=== Project TITAN Stage 14 -- Enterprise Intelligence Gateway Snapshot (environment: ${environment}) ===`);
console.log(`EIG_ENABLED=${flags.EIG_ENABLED} INTERNAL_ADOPTION_ENABLED=${flags.INTERNAL_ADOPTION_ENABLED}`);

if (!flags.INTERNAL_ADOPTION_ENABLED) {
  console.log(
    `INTERNAL_ADOPTION_ENABLED is false for environment "${environment}" (true only in development/testing) -- ` +
      "documented no-op. This confirms the integration point exists and is correctly gated off, " +
      "per this stage's 'no customer-visible behavior changes' requirement. To exercise it, run " +
      "with an environment where this flag has been deliberately (and separately) flipped."
  );
  process.exit(0);
}

const { enabled, gateway, reason } = createEnterpriseGateway({ environment });
if (!enabled) {
  console.error(`Unexpected: INTERNAL_ADOPTION_ENABLED was true but the gateway itself is disabled: ${reason}`);
  process.exit(1);
}

// Self-contained, ephemeral, in-memory-only exercise -- no external I/O, no persisted storage,
// no read of any real feed/customer data. Registers one sample record so the snapshot below
// reflects a gateway that has actually dispatched something, not just booted.
const sample = createCanonicalEvidence(
  createEvidenceEntity(
    { evidence_id: "EC-gateway-snapshot-sample", reliability_code: "B" },
    { evidence_uuid: generateEvidenceUuid() }
  ),
  { related_cves: ["CVE-0000-0001"], source_id: "SRC-internal-gateway-snapshot" }
);
await gateway.platform.evidenceService.registerEvidence(sample, { skipReuseCheck: true });

const caller = { id: "enterprise_gateway_snapshot.mjs", kind: "script" };

// Trusted internal script: full capability grant for the demonstration lookup.
await gateway.dispatch({
  capability: "evidence.lookup",
  method: "byCVE",
  args: ["CVE-0000-0001"],
  caller,
  grantedCapabilities: gateway.listCapabilities(),
});

// Least-privilege example, for contrast: grants ONLY the one capability this call needs.
const platformMetricsViaDispatch = await gateway.dispatch({
  capability: "platform.metrics",
  method: "snapshot",
  args: [],
  caller,
  grantedCapabilities: ["platform.metrics"],
});

const snapshot = {
  environment,
  flags,
  capabilities: gateway.listCapabilities(),
  contracts: ALL_EIG_CONTRACTS.map((c) => ({ name: c.name, version: c.version })),
  health: gateway.healthCheck(),
  gatewayMetrics: gateway.metrics.snapshot(),
  platformMetricsViaDispatch,
};

console.log(JSON.stringify(snapshot, null, 2));
console.log(
  "\nRequired follow-up (documented, not performed here -- Phase 1 scope): wiring " +
    "EnterpriseGateway into a live pNN-handlers.js route or index.js, a real network-facing " +
    "internal service-identity system, and any HTTP/REST/GraphQL/SDK/rate-limiting surface are " +
    "the broader scope Stage 13's own completion docs originally previewed for 'Stage 14' -- " +
    "deliberately deferred by this Phase 1 slice as separate, future, architecturally-" +
    "significant steps requiring their own authorization. See " +
    "TITAN_STAGE14_SERVICE_ARCHITECTURE.md's 'Deferred, not built' scope note and " +
    "TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md's process for how that authorization has been " +
    "obtained for every prior ADR in this program."
);
