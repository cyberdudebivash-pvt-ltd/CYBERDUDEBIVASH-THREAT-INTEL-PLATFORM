/**
 * Enterprise Intelligence Platform Services (EIPS) feature flags -- Stage 13 Phase 6/10
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Mirrors evidence-registry/feature-flags.js's exact per-environment shape and defaults
 * (development/testing enabled, canary/production disabled) -- reuses that file's
 * DEPLOYMENT_ENVIRONMENTS constant rather than redefining the environment list (Single Source
 * of Truth). Same "zero production blast radius regardless of value" property as
 * CEC_FLAGS/EER_FLAGS: nothing outside this directory reads EIPS_ENABLED, and
 * INTERNAL_ADOPTION_ENABLED's own one documented call site (Phase 10) checks it explicitly
 * before doing anything observable.
 */

import { DEPLOYMENT_ENVIRONMENTS } from "../evidence-registry/feature-flags.js";

export { DEPLOYMENT_ENVIRONMENTS };

/**
 * Per-environment EIPS flag table.
 *
 * EIPS_ENABLED: governs whether this directory's own service graph may be constructed/exercised
 * (tests, local dev) -- same shape/defaults as CEC_FLAGS/EER_FLAGS.
 *
 * INTERNAL_ADOPTION_ENABLED (Phase 10): a SEPARATE, narrower gate for the one authorized
 * internal consumer (scripts/intelligence_platform_snapshot.mjs). Mirrors EIPS_ENABLED's own
 * shape -- development/testing enabled, canary/production disabled -- for the same reason
 * EER_FLAGS/CEC_FLAGS already established this pattern: the property that actually matters is
 * zero blast radius in canary/production (where real customers/traffic are), not zero blast
 * radius everywhere. A flag that could never be true in any environment couldn't be
 * regression-tested or compatibility-verified at all, which Phase 10 explicitly requires; a
 * flag that's off in canary/production has the same real-world safety guarantee as
 * EIPS_ENABLED already provides for this entire directory, satisfying "no customer-visible
 * behavior changes" the same way.
 */
export const EIPS_FLAGS = Object.freeze({
  development: Object.freeze({ EIPS_ENABLED: true, INTERNAL_ADOPTION_ENABLED: true }),
  testing: Object.freeze({ EIPS_ENABLED: true, INTERNAL_ADOPTION_ENABLED: true }),
  canary: Object.freeze({ EIPS_ENABLED: false, INTERNAL_ADOPTION_ENABLED: false }),
  production: Object.freeze({ EIPS_ENABLED: false, INTERNAL_ADOPTION_ENABLED: false }),
});

/**
 * Resolves EIPS flag state for an environment. Unrecognized/missing environment strings resolve
 * to "production" (the all-disabled state) -- secure by default, never fails open. Mirrors
 * resolveCecFlags()/resolveEerFlags() exactly.
 * @param {string} [environment]
 * @returns {{EIPS_ENABLED: boolean, INTERNAL_ADOPTION_ENABLED: boolean}}
 */
export function resolveEipsFlags(environment) {
  return EIPS_FLAGS[environment] || EIPS_FLAGS.production;
}

/**
 * Rollback: forces the safest (all-disabled) flag state regardless of environment. Mirrors
 * rollbackCecFlags()/rollbackEerFlags() exactly.
 * @returns {{EIPS_ENABLED: boolean, INTERNAL_ADOPTION_ENABLED: boolean}}
 */
export function rollbackEipsFlags() {
  return EIPS_FLAGS.production;
}
