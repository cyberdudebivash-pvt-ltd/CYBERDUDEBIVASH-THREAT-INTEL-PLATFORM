/**
 * Commercial Catalog (Project TITAN Stage 21 Phase 1) -- Canonical Commercial Service Catalog.
 * Not imported by index.js or any production route. See TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md
 * Sec 4 and COMMERCIAL_SERVICE_CATALOG.md for the full classification rationale.
 *
 * Documentation-as-data, mirroring enterprise-gateway/service-contracts.js's frozen-object
 * convention. Every entry here was derived from a currently-existing, verified method (file:line
 * cited in the audit doc) -- no aspirational entries, and no entry duplicates another under a
 * different name (e.g. `intelligence.query` and the `byVendor`/`byProduct`/`byMalware` dimensions
 * of `getThreatProfile` are deliberately NOT separate catalog entries; see audit Sec 4).
 *
 * `gatewayCapability` names an already-registered Gateway capability this entry classifies
 * in-place (registered via annotate(), not register() -- see gateway-registry.js). `newAdapter`
 * true means Stage 21 registers a brand-new capability for it (see commercial-adapters.js);
 * `sourceLayer` names which existing platform composition it reads from.
 */

export const CATALOG_VISIBILITY = Object.freeze(["internal", "commercial", "partner"]);
export const CATALOG_LIFECYCLE = Object.freeze(["ga", "beta", "blocked-pending-wiring", "internal-only"]);
export const CATALOG_SECURITY_CLASSIFICATION = Object.freeze(["standard", "restricted"]);

/**
 * @typedef {{
 *   id: string, name: string, description: string,
 *   gatewayCapability: string|null, newAdapter: boolean, sourceLayer: string,
 *   owner: string, classification: string[], visibility: string,
 *   securityClassification: string, lifecycle: string,
 *   commercialValue: string, internalConsumers: string[], expectedLatencyMs: number,
 *   documentationStatus: string, dependencies: string[]
 * }} CommercialCatalogEntry
 */

/** @type {CommercialCatalogEntry[]} */
export const COMMERCIAL_SERVICE_CATALOG = Object.freeze(
  [
    {
      id: "evidence.lookup",
      name: "Evidence Lookup",
      description:
        "Unified single/multi-entity evidence lookup (getEvidence/findEvidence and 9 of 12 " +
        "lookup dimensions -- byCVE/byThreatActor/byCampaign/byIOC/byReport/byAttackTechnique/" +
        "bySource/byConfidenceTier). byVendor/byProduct/byMalware are documented gaps (throw) " +
        "and are excluded from the commercial contract.",
      gatewayCapability: "evidence.lookup",
      newAdapter: false,
      sourceLayer: "intelligence-platform",
      owner: "Intelligence Platform (Stage 13)",
      classification: Object.freeze(["commercial", "partner", "ai-agent", "mcp"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "ga",
      commercialValue: "Core lookup primitive underlying most enterprise/API/MCP-tool consumption.",
      internalConsumers: Object.freeze(["commercial-catalog/commercial-adapters.js (Knowledge Object adapter)"]),
      expectedLatencyMs: 250,
      documentationStatus: "documented",
      dependencies: Object.freeze(["intelligence-platform/intelligence-service.js"]),
    },
    {
      id: "intelligence.threatProfile",
      name: "Threat & Entity Profile",
      description:
        "Single bounded call composing lookup + confidence aggregation + a 10-record provenance " +
        "sample for one dimension/value pair (CVE, threat actor, campaign, IOC, ...) into one " +
        "presentable business object.",
      gatewayCapability: "intelligence.threatProfile",
      newAdapter: false,
      sourceLayer: "intelligence-platform",
      owner: "Intelligence Platform (Stage 13)",
      classification: Object.freeze(["commercial", "partner", "soc", "ai-agent", "mcp"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "ga",
      commercialValue: "Best single-call commercial/partner product: one request, one bounded business object.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 400,
      documentationStatus: "documented",
      dependencies: Object.freeze(["intelligence-platform/intelligence-service.js"]),
    },
    {
      id: "intelligence.correlation",
      name: "Correlation Summary",
      description:
        "Cross-entity correlation and confidence/source aggregation (correlateEvidence, " +
        "aggregateConfidence, correlateBySource/Report/IOC/AttackTechnique, aggregateSources).",
      gatewayCapability: "intelligence.correlation",
      newAdapter: false,
      sourceLayer: "intelligence-platform",
      owner: "Intelligence Platform (Stage 13)",
      classification: Object.freeze(["commercial", "partner", "soc", "ai-agent", "mcp"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "ga",
      commercialValue: "Analyst pivoting/hunting primitive with direct partner-API applicability.",
      internalConsumers: Object.freeze(["knowledge-platform/knowledge-navigation.js (upstream, unmodified)"]),
      expectedLatencyMs: 400,
      documentationStatus: "documented",
      dependencies: Object.freeze(["intelligence-platform/intelligence-service.js"]),
    },
    {
      id: "evidence.relationships",
      name: "Relationship Summary",
      description:
        "Entity-to-related-entity graph edges. NullRelationshipProvider throws NOT_WIRED by " +
        "default -- real data requires composing with relationship-framework/ (ADR-0010 " +
        "Accepted, Stage 16). Not activatable as-is; catalogued for completeness, not marketed " +
        "as ready.",
      gatewayCapability: "evidence.relationships",
      newAdapter: false,
      sourceLayer: "evidence-registry",
      owner: "Evidence Registry (Stage 12) / Relationship Framework (Stage 16)",
      classification: Object.freeze(["commercial", "partner", "soc", "ai-agent", "mcp"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "blocked-pending-wiring",
      commercialValue: "Graph-shaped relationship data is a strong partner/API product once wired -- not yet.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 400,
      documentationStatus: "documented",
      dependencies: Object.freeze(["evidence-registry/relationship-resolution.js", "relationship-framework/"]),
    },
    {
      id: "intelligence.explainability",
      name: "Explainability Summary",
      description:
        "Deterministic Analyst Reasoning Object (summary, supporting/contradictory evidence, " +
        "provenance, collection gaps, confidenceAsRecorded surfaced verbatim, policy). No LLM.",
      gatewayCapability: "intelligence.explainability",
      newAdapter: false,
      sourceLayer: "intelligence-platform",
      owner: "Intelligence Platform (Stage 17)",
      classification: Object.freeze(["commercial", "partner", "soc", "ai-agent"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "ga",
      commercialValue: "Flagship trust/transparency product; deterministic and bounded, ideal for AI-agent tool use.",
      internalConsumers: Object.freeze(["knowledge-platform/knowledge-object.js (upstream, unmodified)"]),
      expectedLatencyMs: 400,
      documentationStatus: "documented",
      dependencies: Object.freeze(["intelligence-platform/explainability-engine.js"]),
    },
    {
      id: "evidence.provenance",
      name: "Evidence Provenance Summary",
      description:
        "5 of 6 lineage views (evidence/version/confidence/source/relationship lineage). " +
        "getAuditLineage is EXCLUDED -- it carries internal actor identity and stays " +
        "internal-only, enforced by the adapter (see commercial-adapters.js).",
      gatewayCapability: "evidence.provenance",
      newAdapter: false,
      sourceLayer: "evidence-registry",
      owner: "Evidence Registry (Stage 12)",
      classification: Object.freeze(["commercial", "partner"]),
      visibility: "commercial",
      securityClassification: "restricted",
      lifecycle: "ga",
      commercialValue: "Chain-of-custody / trust narrative for enterprise and partner consumption.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 300,
      documentationStatus: "documented",
      dependencies: Object.freeze(["evidence-registry/provenance-engine.js"]),
    },
    {
      id: "intelligence.validation",
      name: "Intelligence Validation Report",
      description: "Schema and referential-integrity validation (validateEvidence, validateBatch, validateIntelligenceBundle).",
      gatewayCapability: "intelligence.validation",
      newAdapter: false,
      sourceLayer: "intelligence-platform",
      owner: "Intelligence Platform (Stage 13)",
      classification: Object.freeze(["partner"]),
      visibility: "internal",
      securityClassification: "standard",
      lifecycle: "ga",
      commercialValue: "Fits a future MSSP/data-contribution partner 'submit intel, get a validation report' flow.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 300,
      documentationStatus: "partial",
      dependencies: Object.freeze(["intelligence-platform/intelligence-service.js"]),
    },
    {
      id: "commercial.knowledgeObject",
      name: "Knowledge Object Summary",
      description:
        "Reshapes evidence lookup + explainability into a 7-field Knowledge Object " +
        "(KnowledgeObjectService.build) -- deterministic, single-entity JSON in/out.",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "knowledge-platform",
      owner: "Knowledge Platform (Stage 18)",
      classification: Object.freeze(["ai-agent", "mcp"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "Ideal bounded tool-call shape for AI-agent/MCP consumption.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 500,
      documentationStatus: "documented",
      dependencies: Object.freeze(["knowledge-platform/knowledge-object.js"]),
    },
    {
      id: "commercial.knowledgeNavigation",
      name: "Knowledge Navigation",
      description:
        "Correlation/similarity/conflict/lineage/gap analyst pivoting primitives " +
        "(relatedIntelligence, supportingEvidence, similarIntelligence, contradictoryEvidence, " +
        "historicalIntelligence, collectionGaps).",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "knowledge-platform",
      owner: "Knowledge Platform (Stage 18)",
      classification: Object.freeze(["soc", "mcp"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "Analyst pivoting primitives, cleanly tool-shaped for SOC/MCP consumption.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 500,
      documentationStatus: "documented",
      dependencies: Object.freeze(["knowledge-platform/knowledge-navigation.js"]),
    },
    {
      id: "commercial.knowledgeExecutiveBriefing",
      name: "Knowledge Platform Executive Briefing",
      description:
        "Business/operational impact narrative composed from a Knowledge Object -- every " +
        "statement basis-tagged (evidence vs. analyst_recommendation), no computed score. " +
        "Deliberately named distinctly from the live p19/p20 'EXECUTIVE INTELLIGENCE BRIEF' " +
        "heading (see audit Sec 2.5) -- unrelated system, not a duplicate.",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "knowledge-platform",
      owner: "Knowledge Platform (Stage 18)",
      classification: Object.freeze(["commercial", "portal"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "Executive-framed trust narrative for enterprise portal/report consumption.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 600,
      documentationStatus: "documented",
      dependencies: Object.freeze(["knowledge-platform/executive-views.js"]),
    },
    {
      id: "commercial.productAssembly",
      name: "Product Assembly",
      description:
        "Bundles Knowledge Object + correlation view + executive briefing into one Product " +
        "Assembly per evidence record (ProductEngineService.assemble).",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "product-platform",
      owner: "Product Platform (Stage 19)",
      classification: Object.freeze(["commercial"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "Productization backbone -- the input every packaged commercial deliverable is built from.",
      internalConsumers: Object.freeze(["commercial-catalog/commercial-adapters.js (packaging + profile adapters)"]),
      expectedLatencyMs: 700,
      documentationStatus: "documented",
      dependencies: Object.freeze(["product-platform/product-engine.js"]),
    },
    {
      id: "commercial.productProfiledView",
      name: "Audience-Profiled Product View",
      description:
        "Selects one of 6 named audience profiles (soc_analyst, incident_response, " +
        "threat_intelligence_analyst, executive_leadership, mssp_operations, " +
        "vulnerability_management) over an already-assembled product -- pure field selection, " +
        "never recomputes.",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "product-platform",
      owner: "Product Platform (Stage 19)",
      classification: Object.freeze(["commercial", "soc"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "One product, six audience-shaped views -- direct tier/audience differentiation.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 700,
      documentationStatus: "documented",
      dependencies: Object.freeze(["product-platform/product-profiles.js"]),
    },
    {
      id: "commercial.productPackage",
      name: "Commercial Report Package",
      description:
        "Deterministic packaging envelope over an assembly + profiled view, one of 4 package " +
        "types (enterprise_threat_intelligence_report, tactical_dossier, " +
        "executive_intelligence_briefing, knowledge_summary). Evidentiary backbone always read " +
        "from the full assembly, never the narrowed profiled view.",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "product-platform",
      owner: "Product Platform (Stage 19)",
      classification: Object.freeze(["commercial", "partner"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "The literal packaged deliverable -- direct commercial report/API product.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 900,
      documentationStatus: "documented",
      dependencies: Object.freeze(["product-platform/product-packaging.js", "product-platform/product-profiles.js"]),
    },
    {
      id: "commercial.msspPartnerPackage",
      name: "MSSP Partner Package",
      description:
        "Commercial Report Package pinned to the mssp_operations audience profile -- " +
        "product-profiles.js's own description: 'for a managed service provider operating on " +
        "behalf of a client.'",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "product-platform",
      owner: "Product Platform (Stage 19)",
      classification: Object.freeze(["partner"]),
      visibility: "partner",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "Only catalog entry explicitly scoped to a reselling/managed-service partner.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 900,
      documentationStatus: "documented",
      dependencies: Object.freeze(["product-platform/product-packaging.js", "product-platform/product-profiles.js"]),
    },
    {
      id: "commercial.readinessSummary",
      name: "Commercial Readiness Summary",
      description:
        "P39 Commercial Quality Orchestrator's applicability + quality view + readiness summary " +
        "for one feed item (computeCommercialApplicability, buildCommercialQualityView, " +
        "buildCommercialReadinessSummary) -- the literal 'Commercial Readiness' example this " +
        "stage's own brief names.",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "commercial-quality-orchestrator",
      owner: "Commercial Quality Orchestrator (Stage 20A)",
      classification: Object.freeze(["commercial"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "Publication-grade quality signal, directly commercial (tier/pricing input).",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 200,
      documentationStatus: "documented",
      dependencies: Object.freeze(["p39-handlers.js"]),
    },
    {
      id: "commercial.explanationSummary",
      name: "Commercial Explanation",
      description:
        "P39's human-readable explanation and recommendation layer for a commercial quality view " +
        "(buildCommercialExplanation, buildCommercialRecommendationLayer).",
      gatewayCapability: null,
      newAdapter: true,
      sourceLayer: "commercial-quality-orchestrator",
      owner: "Commercial Quality Orchestrator (Stage 20A)",
      classification: Object.freeze(["commercial"]),
      visibility: "commercial",
      securityClassification: "standard",
      lifecycle: "beta",
      commercialValue: "Explains a commercial readiness decision -- supports sales/support transparency.",
      internalConsumers: Object.freeze([]),
      expectedLatencyMs: 200,
      documentationStatus: "documented",
      dependencies: Object.freeze(["p39-handlers.js"]),
    },
  ].map((entry) => Object.freeze(entry))
);

/** @param {string} id @returns {CommercialCatalogEntry|undefined} */
export function getCatalogEntry(id) {
  return COMMERCIAL_SERVICE_CATALOG.find((entry) => entry.id === id);
}

/** @returns {CommercialCatalogEntry[]} entries Stage 21 registers as brand-new Gateway capabilities */
export function listNewAdapterEntries() {
  return COMMERCIAL_SERVICE_CATALOG.filter((entry) => entry.newAdapter);
}

/** @returns {CommercialCatalogEntry[]} entries that classify an already-registered Gateway capability */
export function listExistingCapabilityEntries() {
  return COMMERCIAL_SERVICE_CATALOG.filter((entry) => !entry.newAdapter && entry.gatewayCapability);
}
