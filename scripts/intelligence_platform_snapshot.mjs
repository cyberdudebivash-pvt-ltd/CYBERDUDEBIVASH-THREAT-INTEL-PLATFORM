#!/usr/bin/env node
/**
 * scripts/intelligence_platform_snapshot.mjs
 * Project TITAN Stage 13 Phase 10 — Internal Adoption (first real, non-test consumer)
 *
 * @deprecated Stage 15 Phase 3 (Gateway migration). This script calls IntelligenceService
 * directly, bypassing EnterpriseGateway (Stage 14) — the exact "direct composition consumer"
 * pattern Stage 15 migrates away from. Replacement: scripts/enterprise_gateway_snapshot.mjs,
 * which performs a strict superset of this script's operations (evidence registration, the same
 * byCVE lookup, the same metrics snapshot) routed through EnterpriseGateway.dispatch() instead.
 * Per this repository's Deprecation Instead of Deletion policy: kept fully functional (not
 * removed, not behavior-changed), confirmed zero known consumers (not CI-wired — see
 * TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md §1 — and not referenced by any package.json/workflow,
 * grep-confirmed before this notice was added). Eligible for removal at Stage 16 or later, once
 * zero-consumer status has held for a full stage cycle after this notice. See
 * TITAN_STAGE15_MIGRATION_RUNBOOK.md for the full migration record.
 *
 * This is the one, deliberately low-risk internal consumer this stage's Phase 10 authorizes.
 * It is a standalone internal script — invoked manually or by CI, never by a live HTTP request —
 * NOT a change to workers/intel-gateway/src/index.js or any pNN-handlers.js file. That boundary
 * stays exactly as every prior stage (8, 10, 11, 12) and this stage's own Phases 1-9 left it:
 * intelligence-platform/ (and the evidence-registry/ it composes) remains unreachable from any
 * live Cloudflare Worker request path, verified by this stage's own zero-blast-radius tests and
 * governance checks, none of which this script's existence changes or weakens.
 *
 * Why a script, not a wired-in P-layer handler: Phase 10's brief asks for "one low-risk
 * consumer" with "no customer-visible behavior changes." Wiring IntelligenceService into a live
 * route would be the single highest-risk, most architecturally significant change available in
 * this stage — the first time in the entire evidence/intelligence line (Stage 8-13) any of this
 * infrastructure would touch a request path — and Stage 14's own preview explicitly reserves
 * "Internal REST layer... Service gateway... API version negotiation" for itself, not this
 * stage. Per this repository's Architecture Preservation Rule ("architectural changes require
 * substantially stronger evidence than feature additions... when in doubt, add, don't replace"),
 * that step is out of scope here and is documented as required follow-up below, not taken
 * silently or without separate authorization.
 *
 * Gating: reads EIPS_FLAGS.INTERNAL_ADOPTION_ENABLED for the given environment
 * (feature-flags.js) — hardcoded false in canary and production, and true in development and
 * testing so the integration point stays regression-testable (see feature-flags.test.js's own
 * regression guard for the canary/production values). Running this script in canary or
 * production is a documented, intentional no-op — proof the integration point exists and is
 * off where real traffic is, not evidence it does nothing useful when turned on.
 *
 * Rollback: there is nothing to roll back in the usual sense — this script holds no state
 * between runs (a fresh in-memory EvidenceRegistry every invocation) and touches no persisted
 * storage, D1, KV, or R2. Reverting is: stop invoking this script, or leave
 * INTERNAL_ADOPTION_ENABLED at its default false. No code change is required to "roll back."
 *
 * Usage:
 *   node scripts/intelligence_platform_snapshot.mjs [environment]
 *   EIPS_ENVIRONMENT=development node scripts/intelligence_platform_snapshot.mjs
 */

import { createIntelligencePlatform } from "../workers/intel-gateway/src/intelligence-platform/platform.js";
import { resolveEipsFlags } from "../workers/intel-gateway/src/intelligence-platform/feature-flags.js";
import { ALL_EIPS_CONTRACTS } from "../workers/intel-gateway/src/intelligence-platform/service-contracts.js";
import { createEvidenceEntity, createCanonicalEvidence } from "../workers/intel-gateway/src/evidence-registry/entity.js";
import { generateEvidenceUuid } from "../workers/intel-gateway/src/evidence-registry/identifiers.js";

const environment = process.argv[2] || process.env.EIPS_ENVIRONMENT || "production";
const flags = resolveEipsFlags(environment);

console.log(`=== Project TITAN Stage 13 -- Intelligence Platform Snapshot (environment: ${environment}) ===`);
console.log(
  "[DEPRECATED, Stage 15] This script bypasses EnterpriseGateway. Prefer " +
    "scripts/enterprise_gateway_snapshot.mjs, a strict superset routed through the Gateway. " +
    "Still fully functional -- see this file's own header comment for the deprecation record."
);
console.log(`EIPS_ENABLED=${flags.EIPS_ENABLED} INTERNAL_ADOPTION_ENABLED=${flags.INTERNAL_ADOPTION_ENABLED}`);

if (!flags.INTERNAL_ADOPTION_ENABLED) {
  console.log(
    `INTERNAL_ADOPTION_ENABLED is false for environment "${environment}" (true only in development/testing) -- ` +
      "documented no-op. This confirms the integration point exists and is correctly gated off, " +
      "per Phase 10's 'no customer-visible behavior changes' requirement. To exercise it, run " +
      "with an environment where this flag has been deliberately (and separately) flipped."
  );
  process.exit(0);
}

const { enabled, platform, reason } = createIntelligencePlatform({ environment });
if (!enabled) {
  console.error(`Unexpected: INTERNAL_ADOPTION_ENABLED was true but the platform itself is disabled: ${reason}`);
  process.exit(1);
}

// Self-contained, ephemeral, in-memory-only exercise -- no external I/O, no persisted storage,
// no read of any real feed/customer data. Registers one sample record so the snapshot below
// reflects a platform that has actually done something, not just booted.
const sample = createCanonicalEvidence(
  createEvidenceEntity(
    { evidence_id: "EC-snapshot-sample", reliability_code: "B" },
    { evidence_uuid: generateEvidenceUuid() }
  ),
  { related_cves: ["CVE-0000-0000"], source_id: "SRC-internal-snapshot" }
);
await platform.evidenceService.registerEvidence(sample, { skipReuseCheck: true });
await platform.lookup.byCVE("CVE-0000-0000");

const snapshot = {
  environment,
  flags,
  contracts: ALL_EIPS_CONTRACTS.map((c) => ({ name: c.name, version: c.version })),
  metrics: platform.metrics.snapshot(),
};

console.log(JSON.stringify(snapshot, null, 2));
console.log(
  "\nRequired follow-up (documented, not performed here): wiring IntelligenceService into a " +
    "live pNN-handlers.js route or index.js is a separate, future, architecturally-significant " +
    "step requiring its own authorization -- see Stage 14's preview scope in the Stage 13 brief " +
    "and TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md's process for how that authorization has been " +
    "obtained for every prior ADR in this program."
);
