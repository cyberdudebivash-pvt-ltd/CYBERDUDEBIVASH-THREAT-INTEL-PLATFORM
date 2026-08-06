/**
 * Enterprise Intelligence Platform Services (EIPS) -- Stage 13 Phase 6, Platform Orchestration
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Composition root. Resolves EIPS_FLAGS for `environment` and, if enabled, builds one
 * fully-wired IntelligenceService graph -- single EvidenceRegistry, single shared
 * ServicePlatformMetrics instance across both Stage 12 (EvidenceService/EvidenceQueryEngine/
 * EvidenceProvenanceEngine) and Stage 13's own services, so "no duplicate metrics instances"
 * holds by construction, not by convention (see intelligence-service.js's
 * IntelligenceMetricsService docstring, and metrics-sharing.test.js, for the identity proof).
 *
 * No circular dependencies: this file imports FROM intelligence-service.js and feature-flags.js
 * only; nothing in evidence-registry/ or intelligence-service.js imports this file.
 */

import { IntelligenceService } from "./intelligence-service.js";
import { resolveEipsFlags } from "./feature-flags.js";

/**
 * @param {{environment?: string, deps?: object}} [options]
 * @returns {{enabled: boolean, platform: IntelligenceService | null, environment: string, reason?: string}}
 */
export function createIntelligencePlatform(options = {}) {
  const environment = options.environment || "production";
  const flags = resolveEipsFlags(environment);

  if (!flags.EIPS_ENABLED) {
    return {
      enabled: false,
      platform: null,
      environment,
      reason: `EIPS_ENABLED is false for environment "${environment}"`,
    };
  }

  const platform = new IntelligenceService(options.deps || {});
  return { enabled: true, platform, environment };
}
