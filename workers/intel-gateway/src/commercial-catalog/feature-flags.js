/**
 * Commercial Catalog (Project TITAN Stage 21, Gateway Commercial Activation) feature flags.
 * Not imported by index.js or any production route. See TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md.
 *
 * Mirrors enterprise-gateway/feature-flags.js's exact per-environment shape, defaults
 * (development/testing enabled, canary/production disabled), and Object.hasOwn() resolution.
 * Re-exports DEPLOYMENT_ENVIRONMENTS from enterprise-gateway/ rather than redefining it a sixth
 * time. Unlike every prior single-hop stage, this directory is a deliberate cross-cutting layer
 * over enterprise-gateway/, knowledge-platform/, product-platform/, and p39-handlers.js
 * simultaneously (Stage 21's own charter -- see the audit doc Sec 3), so "the one authorized hop"
 * does not apply in the strict single-parent sense; enterprise-gateway/ is chosen as the
 * re-export source because this layer is Gateway-centric (it exists to register capabilities on
 * an EnterpriseGateway instance).
 *
 * CC_ENABLED: governs whether wireCommercialCapabilities()/createCommercialGateway() may run.
 * INTERNAL_ADOPTION_ENABLED: a separate, narrower gate for the one authorized internal consumer
 * (a future scripts/commercial_gateway_snapshot.mjs, mirroring
 * scripts/enterprise_gateway_snapshot.mjs's identical precedent), gated independently of
 * CC_ENABLED for the same "zero blast radius in canary/production, but still regression-testable"
 * reason EIG_FLAGS/KP_FLAGS already establish.
 */

import { DEPLOYMENT_ENVIRONMENTS } from "../enterprise-gateway/feature-flags.js";

export { DEPLOYMENT_ENVIRONMENTS };

export const CC_FLAGS = Object.freeze({
  development: Object.freeze({ CC_ENABLED: true, INTERNAL_ADOPTION_ENABLED: true }),
  testing: Object.freeze({ CC_ENABLED: true, INTERNAL_ADOPTION_ENABLED: true }),
  canary: Object.freeze({ CC_ENABLED: false, INTERNAL_ADOPTION_ENABLED: false }),
  production: Object.freeze({ CC_ENABLED: false, INTERNAL_ADOPTION_ENABLED: false }),
});

/**
 * Unrecognized/missing environment strings resolve to "production" (all-disabled) -- secure by
 * default, never fails open. Object.hasOwn(), not a bare `CC_FLAGS[environment] || ...` lookup,
 * for the same reason every lower layer's resolve*Flags() does: avoids resolving an inherited
 * Object.prototype member for a string like "constructor"/"toString".
 * @param {string} [environment]
 * @returns {{CC_ENABLED: boolean, INTERNAL_ADOPTION_ENABLED: boolean}}
 */
export function resolveCcFlags(environment) {
  return Object.hasOwn(CC_FLAGS, environment) ? CC_FLAGS[environment] : CC_FLAGS.production;
}

/** Rollback: forces the safest (all-disabled) flag state regardless of environment. */
export function rollbackCcFlags() {
  return CC_FLAGS.production;
}
