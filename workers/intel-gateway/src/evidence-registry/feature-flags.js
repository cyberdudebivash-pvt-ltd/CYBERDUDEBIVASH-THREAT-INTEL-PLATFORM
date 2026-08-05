/**
 * Evidence Registry feature flags — Phase 9 scaffolding (Project TITAN Stage 8).
 * Not imported by index.js or any production route. See README.md.
 *
 * Nothing reads these flags yet, because nothing is wired up yet. This file
 * establishes the naming convention a future, authorized integration should
 * follow (Stage 8 Engineering Requirements: "Feature-flagged").
 */

export const EVIDENCE_REGISTRY_FLAGS = Object.freeze({
  // Master switch for wiring this scaffolding into any live code path.
  // Must remain false until ADR-0008 is formally Accepted and Migration
  // Roadmap Phase 3 has shipped - see TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md.
  SCAFFOLDING_ENABLED: false,

  // Sub-flags for future, separately-authorized capability - not active,
  // listed here only to reserve the naming convention.
  REGISTRY_SERVICE_ENABLED: false,
  EVIDENCE_API_ENABLED: false,
});
