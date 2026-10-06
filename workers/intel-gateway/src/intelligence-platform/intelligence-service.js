/**
 * Enterprise Intelligence Platform Services (EIPS) -- Stage 13 Phase 1, Intelligence Service
 * Layer (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Composes Stage 12's Enterprise Evidence Service Platform (evidence-registry/) -- EvidenceService,
 * EvidenceQueryEngine, EvidenceProvenanceEngine, RelationshipResolutionService -- into a broader
 * intelligence-operations layer. Every method here delegates to an already-existing public
 * method; none of these classes hold their own storage or reimplement evidence-registry logic.
 */

import { EvidenceService } from "../evidence-registry/evidence-service.js";
import { EvidenceQueryEngine } from "../evidence-registry/query-engine.js";
import { EvidenceProvenanceEngine } from "../evidence-registry/provenance-engine.js";
import { RelationshipResolutionService } from "../evidence-registry/relationship-resolution.js";
import { ServicePlatformMetrics } from "../evidence-registry/service-metrics.js";
import { EnterpriseQueryService } from "./query-service.js";
import { IntelligenceCorrelationService } from "./correlation-engine.js";
import { IntelligenceExplainabilityService } from "./explainability-engine.js";

/**
 * Unifies EvidenceService.lookup (Stage 12's 9 evidence-registry-native method names) with
 * EnterpriseQueryService (Stage 13 Phase 2's 12-dimension enterprise vocabulary) behind one
 * Stage-13-level lookup surface. Distinct from both: EvidenceLookupService is scoped to
 * evidence-registry's own naming, EnterpriseQueryService is scoped to the 12-dimension brief
 * vocabulary (and documents the 3 it cannot serve) -- this class is the one place a Stage 13
 * consumer looks up "the current lookup surface" without needing to know which of those two
 * it maps to internally. No independent logic: every method is a one-line delegation.
 */
export class IntelligenceLookupService {
  /**
   * @param {{evidenceLookup: import('../evidence-registry/evidence-service.js').EvidenceLookupService,
   *   enterpriseQuery: EnterpriseQueryService}} deps
   */
  constructor(deps = {}) {
    this._evidenceLookup = deps.evidenceLookup;
    this._enterpriseQuery = deps.enterpriseQuery;
    if (!this._evidenceLookup || !this._enterpriseQuery) {
      throw new Error("IntelligenceLookupService requires evidenceLookup and enterpriseQuery dependencies");
    }
  }

  async getEvidence(evidenceUuid) { return this._evidenceLookup.getEvidence(evidenceUuid); }
  async findEvidence(criteria) { return this._evidenceLookup.findEvidence(criteria); }
  async byCVE(cve) { return this._enterpriseQuery.queryByCVE(cve); }
  async byThreatActor(actor) { return this._enterpriseQuery.queryByThreatActor(actor); }
  async byCampaign(campaign) { return this._enterpriseQuery.queryByCampaign(campaign); }
  async byIOC(ioc) { return this._enterpriseQuery.queryByIOC(ioc); }
  async byReport(reportId) { return this._enterpriseQuery.queryByReport(reportId); }
  async byAttackTechnique(technique) { return this._enterpriseQuery.queryByAttackTechnique(technique); }
  async bySource(sourceId) { return this._enterpriseQuery.queryBySource(sourceId); }
  async byConfidenceTier(tier) { return this._enterpriseQuery.queryByConfidence(tier); }
  /** @throws documents a platform gap -- see query-service.js */
  async byVendor(vendor) { return this._enterpriseQuery.queryByVendor(vendor); }
  /** @throws documents a platform gap -- see query-service.js */
  async byProduct(product) { return this._enterpriseQuery.queryByProduct(product); }
  /** @throws documents a platform gap -- see query-service.js */
  async byMalware(malware) { return this._enterpriseQuery.queryByMalware(malware); }
}

/**
 * Composed validation: single/batch evidence validation delegates verbatim to Stage 12's
 * EvidenceValidationService (validation.js's validateCanonicalEvidence, unchanged). The one
 * genuinely new method, validateIntelligenceBundle(), composes that with IntelligenceLookupService
 * to check cross-entity referential integrity (e.g. a claimed source_id actually resolves to
 * registered evidence) -- a Stage-13-level, multi-entity concern Stage 12's per-evidence
 * validator was never scoped to cover, not a re-implementation of what it already does.
 */
export class IntelligenceValidationService {
  /**
   * @param {{evidenceValidation: import('../evidence-registry/evidence-service.js').EvidenceValidationService,
   *   lookup: IntelligenceLookupService}} deps
   */
  constructor(deps = {}) {
    this._evidenceValidation = deps.evidenceValidation;
    this._lookup = deps.lookup;
    if (!this._evidenceValidation || !this._lookup) {
      throw new Error("IntelligenceValidationService requires evidenceValidation and lookup dependencies");
    }
  }

  validateEvidence(evidence, options) { return this._evidenceValidation.validateEvidence(evidence, options); }
  validateBatch(entities) { return this._evidenceValidation.validateBatch(entities); }

  /**
   * @param {{evidence: import('../evidence-registry/entity.js').CanonicalEvidence, sourceId?: string}} bundle
   * @returns {Promise<{valid: boolean, errors: string[]}>}
   */
  async validateIntelligenceBundle(bundle) {
    const errors = [];
    const evidenceResult = this.validateEvidence(bundle.evidence);
    if (!evidenceResult.valid) errors.push(...evidenceResult.errors);

    if (bundle.sourceId) {
      const sourceEvidence = await this._lookup.bySource(bundle.sourceId);
      if (!sourceEvidence || sourceEvidence.length === 0) {
        errors.push(`sourceId "${bundle.sourceId}" has no registered evidence -- cannot confirm it is a known source`);
      }
    }
    return { valid: errors.length === 0, errors };
  }
}

/**
 * Merges Stage 12's registry+service metrics (EvidenceService.metrics.snapshot()) into a
 * Stage-13-labelled view. Because every Stage 13 component shares the SAME ServicePlatformMetrics
 * instance EvidenceService itself was constructed with (see platform.js's
 * createIntelligencePlatform()), evidenceService.metrics.snapshot().service ALREADY reflects
 * every Stage 13 call recorded through that shared instance -- there is exactly one
 * ServicePlatformMetrics instance for the whole platform, not one per stage. This class adds no
 * second counter set; it is a read-only view of the same merged snapshot.
 */
export class IntelligenceMetricsService {
  /** @param {{evidenceMetrics: import('../evidence-registry/evidence-service.js').EvidenceMetricsService}} deps */
  constructor(deps = {}) {
    this._evidenceMetrics = deps.evidenceMetrics;
    if (!this._evidenceMetrics) {
      throw new Error("IntelligenceMetricsService requires an evidenceMetrics dependency");
    }
  }

  /**
   * @returns {import('../evidence-registry/service-metrics.js').ServicePlatformMetrics} the
   *   single shared instance -- exposed so "no duplicate metrics instances" can be asserted by
   *   identity in tests, not just claimed in a comment.
   */
  get sharedServiceMetrics() { return this._evidenceMetrics.serviceMetrics; }

  /** Merged point-in-time snapshot: registry counters (Stage 11) + shared service counters (Stage 12 + 13). */
  snapshot() {
    return this._evidenceMetrics.snapshot();
  }
}

/**
 * Composes lookup + correlation + provenance for one entity into a single "threat profile" --
 * genuinely new orchestration value (the brief's Phase 1 mandate), not a rename of an existing
 * method: no single Stage 12 method already returns this composed shape.
 */
export class ThreatIntelligenceService {
  /**
   * @param {{lookup: IntelligenceLookupService, correlation: IntelligenceCorrelationService,
   *   provenanceEngine?: import('../evidence-registry/provenance-engine.js').EvidenceProvenanceEngine}} deps
   */
  constructor(deps = {}) {
    this._lookup = deps.lookup;
    this._correlation = deps.correlation;
    this._provenanceEngine = deps.provenanceEngine || null;
    if (!this._lookup || !this._correlation) {
      throw new Error("ThreatIntelligenceService requires lookup and correlation dependencies");
    }
  }

  /**
   * @param {"cve"|"threatActor"|"campaign"|"ioc"|"attackTechnique"} dimension
   * @param {string} value
   */
  async getThreatProfile(dimension, value) {
    const lookupMethod = {
      cve: "byCVE",
      threatActor: "byThreatActor",
      campaign: "byCampaign",
      ioc: "byIOC",
      attackTechnique: "byAttackTechnique",
    }[dimension];
    if (!lookupMethod) {
      throw new Error(
        `getThreatProfile: unknown dimension "${dimension}" -- expected one of cve, threatActor, ` +
          "campaign, ioc, attackTechnique"
      );
    }

    const evidence = await this._lookup[lookupMethod](value);
    const confidence = await this._correlation.aggregateConfidence(evidence);

    let provenanceSample = [];
    if (this._provenanceEngine && evidence.length > 0) {
      provenanceSample = await Promise.all(
        evidence.slice(0, 10).map((record) => this._provenanceEngine.getConfidenceLineage(record.evidence_uuid))
      );
    }

    return { dimension, value, evidenceCount: evidence.length, evidence, confidence, provenanceSample };
  }
}

/**
 * "One Intelligence Service" -- the single aggregating facade Phase 1 names as this stage's
 * primary deliverable, mirroring Stage 12's own EvidenceService pattern one layer up. Composes
 * every Stage 13 service plus a direct reference to Stage 12's EvidenceProvenanceEngine for
 * provenance (Phase 4 -- see this class's `provenance` property docs below for why no Stage 13
 * wrapper class was needed there).
 */
export class IntelligenceService {
  /**
   * @param {{evidenceService?: EvidenceService, queryEngine?: EvidenceQueryEngine,
   *   provenanceEngine?: EvidenceProvenanceEngine, relationshipResolution?: RelationshipResolutionService,
   *   serviceMetrics?: ServicePlatformMetrics}} [deps]
   */
  constructor(deps = {}) {
    // Must derive the shared serviceMetrics AFTER resolving _evidenceService, not before: an
    // injected deps.evidenceService already owns its own ServicePlatformMetrics instance, and
    // building a fresh one here first (the original Stage 13 bug) would silently split
    // observability in two -- every component below would share a DIFFERENT instance than the
    // injected EvidenceService actually uses, and IntelligenceMetricsService.snapshot() (which
    // reads through _evidenceService.metrics) would never see Stage 13's own recorded calls.
    // If both an evidenceService AND an explicit, different serviceMetrics are injected, that
    // is a caller error -- fail loudly rather than silently using either instance.
    this._evidenceService =
      deps.evidenceService || new EvidenceService({ serviceMetrics: deps.serviceMetrics || new ServicePlatformMetrics() });
    const serviceMetrics = deps.serviceMetrics || this._evidenceService.metrics.serviceMetrics;
    if (this._evidenceService.metrics.serviceMetrics !== serviceMetrics) {
      throw new Error(
        "IntelligenceService: deps.serviceMetrics does not match the injected deps.evidenceService's " +
          "own metrics instance -- inject one or the other, not two different ones."
      );
    }
    this._queryEngine = deps.queryEngine || new EvidenceQueryEngine(this._evidenceService.registry, serviceMetrics);

    /**
     * Phase 4 "Provenance Services" (evidence/version/source/confidence/audit lineage):
     * EvidenceProvenanceEngine's 6 lineage kinds (Stage 12 Phase 3) already cover all 5
     * brief-named kinds, verbatim -- exposed directly, zero new provenance code. See
     * TITAN_STAGE13_SERVICE_ARCHITECTURE.md's "Phase 4 disposition" for the full reasoning.
     * @type {EvidenceProvenanceEngine}
     */
    this.provenance = deps.provenanceEngine || new EvidenceProvenanceEngine(this._evidenceService.registry, serviceMetrics);

    this._relationshipResolution = deps.relationshipResolution || new RelationshipResolutionService({ metrics: serviceMetrics });

    this.enterpriseQuery = new EnterpriseQueryService({ queryEngine: this._queryEngine });
    this.lookup = new IntelligenceLookupService({
      evidenceLookup: this._evidenceService.lookup,
      enterpriseQuery: this.enterpriseQuery,
    });
    this.correlation = new IntelligenceCorrelationService({
      evidenceService: this._evidenceService,
      queryEngine: this._queryEngine,
      relationshipResolution: this._relationshipResolution,
      metrics: serviceMetrics,
    });
    this.validation = new IntelligenceValidationService({
      evidenceValidation: this._evidenceService.validation,
      lookup: this.lookup,
    });
    this.metrics = new IntelligenceMetricsService({ evidenceMetrics: this._evidenceService.metrics });
    this.threatIntelligence = new ThreatIntelligenceService({
      lookup: this.lookup,
      correlation: this.correlation,
      provenanceEngine: this.provenance,
    });

    /**
     * Project TITAN Stage 17 (Track A) addition: composes lookup + correlation + provenance
     * (all three already public above) into the Explainable Intelligence Engine / Analyst
     * Reasoning Object. See explainability-engine.js's module docstring for the full ADR-0007
     * boundary. Added last, after every dependency it needs already exists -- no reordering of
     * anything above.
     * @type {IntelligenceExplainabilityService}
     */
    this.explainability = new IntelligenceExplainabilityService({
      lookup: this.lookup,
      correlation: this.correlation,
      provenance: this.provenance,
      metrics: serviceMetrics,
    });
  }

  /** @returns {EvidenceService} the underlying Stage 12 facade, for components that need it directly */
  get evidenceService() { return this._evidenceService; }

  /** @returns {RelationshipResolutionService} the shared, ADR-0010-gated pass-through instance */
  get relationshipResolution() { return this._relationshipResolution; }
}
