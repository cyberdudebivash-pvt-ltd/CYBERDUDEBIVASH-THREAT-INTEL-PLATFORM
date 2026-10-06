/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Composition Root (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Resolves EIG_FLAGS for `environment` and, if enabled, builds one fully-wired EnterpriseGateway
 * -- composing createIntelligencePlatform() (Stage 13's own composition root) for the underlying
 * platform unless one is injected via options.deps.intelligencePlatform, so "no duplicate
 * ServicePlatformMetrics instance" holds by construction all the way down to Stage 11, not just
 * at this stage's own boundary. Mirrors intelligence-platform/platform.js's exact shape and
 * return contract.
 *
 * No circular dependencies: this file imports FROM gateway-service.js, feature-flags.js, and
 * intelligence-platform/platform.js only; nothing in evidence-registry/ or intelligence-platform/
 * imports this file (see __tests__/zero-blast-radius.test.js).
 */

import { EnterpriseGateway } from "./gateway-service.js";
import { resolveEigFlags } from "./feature-flags.js";
import { createIntelligencePlatform } from "../intelligence-platform/platform.js";

/**
 * @param {{environment?: string, deps?: {intelligencePlatform?: {enabled: boolean, platform: object, reason?: string},
 *   platformDeps?: object, serviceMetrics?: object}}} [options]
 * @returns {{enabled: boolean, gateway: EnterpriseGateway | null, environment: string, reason?: string}}
 */
export function createEnterpriseGateway(options = {}) {
  const environment = options.environment || "production";
  const flags = resolveEigFlags(environment);

  if (!flags.EIG_ENABLED) {
    return {
      enabled: false,
      gateway: null,
      environment,
      reason: `EIG_ENABLED is false for environment "${environment}"`,
    };
  }

  const deps = options.deps || {};
  const intelligencePlatformResult =
    deps.intelligencePlatform || createIntelligencePlatform({ environment, deps: deps.platformDeps });

  if (!intelligencePlatformResult.enabled) {
    return {
      enabled: false,
      gateway: null,
      environment,
      reason: `Underlying intelligence platform is disabled: ${intelligencePlatformResult.reason}`,
    };
  }

  const gateway = new EnterpriseGateway({
    platform: intelligencePlatformResult.platform,
    serviceMetrics: deps.serviceMetrics,
    environment,
  });
  return { enabled: true, gateway, environment };
}
