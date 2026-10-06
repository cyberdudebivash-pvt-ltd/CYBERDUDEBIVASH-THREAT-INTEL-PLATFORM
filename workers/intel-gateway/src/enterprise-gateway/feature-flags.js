/**
 * Enterprise Intelligence Gateway (EIG) feature flags -- Stage 14 Phase 1 (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Mirrors intelligence-platform/feature-flags.js's exact per-environment shape, defaults
 * (development/testing enabled, canary/production disabled), and Object.hasOwn() resolution --
 * intelligence-platform's own PR #120 fix over evidence-registry/feature-flags.js's older
 * `EER_FLAGS[env] || EER_FLAGS.production` pattern (left as-is there, a known follow-up, not
 * backported by this file). Re-exports DEPLOYMENT_ENVIRONMENTS from intelligence-platform/
 * (which itself re-exports evidence-registry's) rather than redefining it a third time --
 * imported from intelligence-platform/, not evidence-registry/ directly, keeping this
 * directory's dependency to the one authorized hop (see zero-blast-radius.test.js).
 *
 * EIG_ENABLED: governs whether createEnterpriseGateway() may construct a live gateway.
 * INTERNAL_ADOPTION_ENABLED: a separate, narrower gate for the one authorized internal consumer
 * (scripts/enterprise_gateway_snapshot.mjs), mirroring EIPS_FLAGS's identical two-flag shape for
 * the identical reason: the property that matters is zero blast radius in canary/production,
 * not a flag that's never true anywhere (which couldn't be regression-tested at all).
 */

import { DEPLOYMENT_ENVIRONMENTS } from "../intelligence-platform/feature-flags.js";

export { DEPLOYMENT_ENVIRONMENTS };

export const EIG_FLAGS = Object.freeze({
  development: Object.freeze({ EIG_ENABLED: true, INTERNAL_ADOPTION_ENABLED: true }),
  testing: Object.freeze({ EIG_ENABLED: true, INTERNAL_ADOPTION_ENABLED: true }),
  canary: Object.freeze({ EIG_ENABLED: false, INTERNAL_ADOPTION_ENABLED: false }),
  production: Object.freeze({ EIG_ENABLED: false, INTERNAL_ADOPTION_ENABLED: false }),
});

/**
 * Unrecognized/missing environment strings resolve to "production" (all-disabled) -- secure by
 * default, never fails open. Object.hasOwn(), not a bare `EIG_FLAGS[environment] || ...` lookup,
 * for the same reason intelligence-platform/feature-flags.js's resolveEipsFlags() does: avoids
 * resolving an inherited Object.prototype member for a string like "constructor"/"toString".
 * @param {string} [environment]
 * @returns {{EIG_ENABLED: boolean, INTERNAL_ADOPTION_ENABLED: boolean}}
 */
export function resolveEigFlags(environment) {
  return Object.hasOwn(EIG_FLAGS, environment) ? EIG_FLAGS[environment] : EIG_FLAGS.production;
}

/** Rollback: forces the safest (all-disabled) flag state regardless of environment. */
export function rollbackEigFlags() {
  return EIG_FLAGS.production;
}
