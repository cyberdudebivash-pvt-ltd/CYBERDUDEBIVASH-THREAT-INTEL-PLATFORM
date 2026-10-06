/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) -- Project TITAN Stage 19 Phase 4,
 * Product Packaging. Not imported by index.js or any production route. See README.md.
 *
 * Deterministic packaging over an already-assembled product (ProductEngineService.assemble())
 * and an already-profiled view (ProductProfileService.applyProfile()) -- no new correlation,
 * provenance, or explanation logic. Every package preserves metadata, evidence references,
 * provenance, a correlation summary, explainability, and intelligence gaps regardless of
 * audience profile, so a narrow profile (e.g. executive_leadership, which surfaces only the
 * briefing section) never loses the underlying evidentiary backbone -- it is read from `assembly`
 * directly, not from the (possibly narrower) `profiledView`.
 *
 * "tactical_dossier" here is a structured JSON packaging shape over Knowledge Platform output --
 * NOT the pre-existing, CI-wired Python HTML Tactical Dossier generator script (a completely
 * separate, unmodified system; see TITAN_STAGE19_READINESS_REPORT.md Sec 2.3 for its exact
 * path). The two are not merged, and this file does not import, invoke, or produce output
 * compatible with the Python pipeline's format.
 */

export const PRODUCT_PACKAGE_TYPES = Object.freeze([
  "enterprise_threat_intelligence_report",
  "tactical_dossier",
  "executive_intelligence_briefing",
  "knowledge_summary",
]);

export class ProductPackagingService {
  /** @param {{metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} [deps] */
  constructor(deps = {}) {
    this._metrics = deps.metrics || null;
  }

  async _timed(name, fn) {
    if (this._metrics) return this._metrics.timed(`product.packaging.${name}`, fn);
    return fn();
  }

  /** @param {string} packageType */
  validatePackageType(packageType) {
    if (!PRODUCT_PACKAGE_TYPES.includes(packageType)) {
      throw new Error(`Unknown package type "${packageType}". Known types: ${PRODUCT_PACKAGE_TYPES.join(", ")}`);
    }
  }

  /** Subject plus every supporting record, tagged by role -- the evidence-reference envelope every package carries. */
  _evidenceReferences(assembly) {
    const subject = assembly.knowledgeObject.subject;
    const supporting = assembly.knowledgeObject.supportingEvidence || [];
    return [
      { evidence_uuid: subject.evidence_uuid, evidence_id: subject.evidence_id, role: "subject" },
      ...supporting.map((record) => ({ evidence_uuid: record.evidence_uuid, evidence_id: record.evidence_id, role: "supporting" })),
    ];
  }

  /** Counts only -- the full lists already live in `content` when a profile includes `correlation`. */
  _correlationSummary(assembly) {
    const correlation = assembly.correlation || {};
    return {
      relatedCount: (correlation.relatedIntelligence || []).length,
      similarCount: (correlation.similarIntelligence || []).length,
      contradictoryCount: (correlation.contradictoryEvidence || []).length,
      statusDisagreement: correlation.statusDisagreement || false,
    };
  }

  /** Verbatim passthrough of the Knowledge Object's own explanation fields -- nothing computed here. */
  _explainability(assembly) {
    const knowledgeObject = assembly.knowledgeObject;
    return {
      summary: knowledgeObject.summary,
      confidenceAsRecorded: knowledgeObject.confidenceAsRecorded,
      policy: knowledgeObject.policy,
    };
  }

  _intelligenceGaps(assembly) {
    const knowledgeObject = assembly.knowledgeObject;
    return { gaps: knowledgeObject.intelligenceGaps || [], recommendations: knowledgeObject.collectionRecommendations || [] };
  }

  /**
   * @param {object} assembly - ProductEngineService.assemble()'s output (the evidentiary backbone)
   * @param {object} profiledView - ProductProfileService.applyProfile()'s output (the audience-shaped content)
   * @param {string} packageType - one of PRODUCT_PACKAGE_TYPES
   * @returns {Promise<object>}
   */
  async package(assembly, profiledView, packageType) {
    return this._timed("package", async () => {
      this.validatePackageType(packageType);
      const packageId = `PKG-${packageType}-${assembly.evidenceUuid}`;

      if (!assembly.found) {
        return { packageId, packageType, evidenceUuid: assembly.evidenceUuid, found: false, reason: assembly.reason };
      }

      return {
        packageId,
        packageType,
        evidenceUuid: assembly.evidenceUuid,
        found: true,
        metadata: {
          generatedAt: new Date().toISOString(),
          packageType,
          profile: profiledView.profileName || null,
          evidenceUuid: assembly.evidenceUuid,
        },
        evidenceReferences: this._evidenceReferences(assembly),
        provenance: assembly.knowledgeObject.provenance,
        correlationSummary: this._correlationSummary(assembly),
        explainability: this._explainability(assembly),
        intelligenceGaps: this._intelligenceGaps(assembly),
        content: profiledView,
      };
    });
  }
}
