/**
 * Unit-level adapter tests using fakes, isolated from a real Gateway/IntelligenceService stack --
 * complements gateway-integration.test.js's real end-to-end coverage. Focuses on each adapter's
 * own validation/mapping/translation responsibility (Phase 2's actual charter), independent of
 * whether the real underlying platforms are wired correctly.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CommercialAdapterValidationError,
  createKnowledgeObjectAdapter,
  createKnowledgeNavigationAdapter,
  createKnowledgeExecutiveBriefingAdapter,
  createProductAssemblyAdapter,
  createProductProfiledViewAdapter,
  createProductPackageAdapter,
  createMsspPartnerPackageAdapter,
  createCommercialReadinessSummaryAdapter,
  createCommercialExplanationAdapter,
} from "../commercial-adapters.js";
import { feedItem } from "./test-helpers.js";

const CALLER_CONTEXT = { correlationId: "test" };

test("every DI-based adapter factory throws when its required platform dependency is missing", () => {
  assert.throws(() => createKnowledgeObjectAdapter({}), /requires a knowledgePlatform dependency/);
  assert.throws(() => createKnowledgeNavigationAdapter({}), /requires a knowledgePlatform dependency/);
  assert.throws(() => createKnowledgeExecutiveBriefingAdapter({}), /requires a knowledgePlatform dependency/);
  assert.throws(() => createProductAssemblyAdapter({}), /requires a productPlatform dependency/);
  assert.throws(() => createProductProfiledViewAdapter({}), /requires a productPlatform dependency/);
  assert.throws(() => createProductPackageAdapter({}), /requires a productPlatform dependency/);
  assert.throws(() => createMsspPartnerPackageAdapter({}), /requires a productPlatform dependency/);
});

test("commercial.knowledgeObject rejects an unknown method before ever touching knowledgePlatform", async () => {
  const adapter = createKnowledgeObjectAdapter({ knowledgePlatform: { object: { build: () => { throw new Error("must not be called"); } } } });
  await assert.rejects(() => adapter(CALLER_CONTEXT, "delete", "uuid-1"), CommercialAdapterValidationError);
});

test("commercial.knowledgeObject rejects a non-string evidenceUuid", async () => {
  const adapter = createKnowledgeObjectAdapter({ knowledgePlatform: { object: { build: async () => ({}) } } });
  await assert.rejects(() => adapter(CALLER_CONTEXT, "build", 12345), /"evidenceUuid" must be a non-empty string/);
  await assert.rejects(() => adapter(CALLER_CONTEXT, "build", ""), /"evidenceUuid" must be a non-empty string/);
});

test("commercial.knowledgeObject returns a versioned envelope wrapping the platform's real return value", async () => {
  const fakeKnowledgePlatform = { object: { build: async (uuid) => ({ found: true, evidenceUuid: uuid }) } };
  const adapter = createKnowledgeObjectAdapter({ knowledgePlatform: fakeKnowledgePlatform });
  const envelope = await adapter(CALLER_CONTEXT, "build", "uuid-1");
  assert.equal(envelope.capabilityId, "commercial.knowledgeObject");
  assert.equal(envelope.namespace, "internal/v1");
  assert.equal(typeof envelope.contractVersion, "string");
  assert.equal(typeof envelope.generatedAt, "string");
  assert.deepEqual(envelope.data, { found: true, evidenceUuid: "uuid-1" });
});

test("commercial.knowledgeNavigation allows all 6 navigation methods and dispatches to the matching one", async () => {
  const calls = [];
  const fakeKnowledgePlatform = {
    navigation: Object.fromEntries(
      ["relatedIntelligence", "supportingEvidence", "similarIntelligence", "contradictoryEvidence", "historicalIntelligence", "collectionGaps"].map(
        (method) => [method, async (uuid) => { calls.push([method, uuid]); return { method, uuid }; }]
      )
    ),
  };
  const adapter = createKnowledgeNavigationAdapter({ knowledgePlatform: fakeKnowledgePlatform });
  const envelope = await adapter(CALLER_CONTEXT, "contradictoryEvidence", "uuid-1");
  assert.deepEqual(envelope.data, { method: "contradictoryEvidence", uuid: "uuid-1" });
  assert.deepEqual(calls, [["contradictoryEvidence", "uuid-1"]]);
});

test("commercial.knowledgeNavigation rejects a method that is not one of the 6 named navigation methods", async () => {
  const adapter = createKnowledgeNavigationAdapter({ knowledgePlatform: { navigation: {} } });
  await assert.rejects(() => adapter(CALLER_CONTEXT, "deleteEverything", "uuid-1"), CommercialAdapterValidationError);
});

test("commercial.productProfiledView returns only the profiled view -- the full assembly is never present in the envelope", async () => {
  const fakeProductPlatform = {
    engine: { assemble: async (uuid) => ({ found: true, evidenceUuid: uuid, knowledgeObject: { secret: "full-backbone" } }) },
    profiles: { applyProfile: (assembly, profileKey) => ({ profileName: profileKey, sections: {} }) }, // synchronous, matches the real signature
  };
  const adapter = createProductProfiledViewAdapter({ productPlatform: fakeProductPlatform });
  const envelope = await adapter(CALLER_CONTEXT, "applyProfile", "uuid-1", "soc_analyst");
  assert.equal("assembly" in envelope.data, false);
  assert.equal("knowledgeObject" in envelope.data, false);
  assert.equal(envelope.data.profileName, "soc_analyst");
});

test("commercial.productPackage awaits the async package() call -- data is the resolved object, not a Promise", async () => {
  const fakeProductPlatform = {
    engine: { assemble: async (uuid) => ({ found: true, evidenceUuid: uuid }) },
    profiles: { applyProfile: (assembly, profileKey) => ({ profileName: profileKey }) },
    packaging: { package: async (assembly, profiledView, packageType) => ({ found: true, packageType, profile: profiledView.profileName }) },
  };
  const adapter = createProductPackageAdapter({ productPlatform: fakeProductPlatform });
  const envelope = await adapter(CALLER_CONTEXT, "package", "uuid-1", "soc_analyst", "tactical_dossier");
  assert.equal(envelope.data instanceof Promise, false, "data must be the resolved value, not a pending Promise");
  assert.equal(envelope.data.packageType, "tactical_dossier");
  assert.equal(envelope.data.profile, "soc_analyst");
});

test("commercial.msspPartnerPackage always calls applyProfile with 'mssp_operations', ignoring any profile the caller might try to pass", async () => {
  const appliedProfileKeys = [];
  const fakeProductPlatform = {
    engine: { assemble: async (uuid) => ({ found: true, evidenceUuid: uuid }) },
    profiles: { applyProfile: (assembly, profileKey) => { appliedProfileKeys.push(profileKey); return { profileName: profileKey }; } },
    packaging: { package: async (assembly, profiledView, packageType) => ({ found: true, packageType, profile: profiledView.profileName }) },
  };
  const adapter = createMsspPartnerPackageAdapter({ productPlatform: fakeProductPlatform });
  // Only evidenceUuid and packageType are accepted positionally -- there is no way for a caller
  // to smuggle a different profileKey through this adapter's signature.
  await adapter(CALLER_CONTEXT, "package", "uuid-1", "knowledge_summary");
  assert.deepEqual(appliedProfileKeys, ["mssp_operations"]);
});

test("commercial.readinessSummary and commercial.explanationSummary reject a non-object item", async () => {
  const readinessAdapter = createCommercialReadinessSummaryAdapter();
  await assert.rejects(() => readinessAdapter(CALLER_CONTEXT, "summarize", "not-an-object"), CommercialAdapterValidationError);
  await assert.rejects(() => readinessAdapter(CALLER_CONTEXT, "summarize", null), CommercialAdapterValidationError);
  await assert.rejects(() => readinessAdapter(CALLER_CONTEXT, "summarize", ["array", "not", "object"]), CommercialAdapterValidationError);

  const explanationAdapter = createCommercialExplanationAdapter();
  await assert.rejects(() => explanationAdapter(CALLER_CONTEXT, "explain", 42), CommercialAdapterValidationError);
});

test("commercial.readinessSummary and commercial.explanationSummary require no platform DI -- P39's functions are pure", async () => {
  const readinessAdapter = createCommercialReadinessSummaryAdapter();
  const readinessEnvelope = await readinessAdapter(CALLER_CONTEXT, "summarize", feedItem());
  assert.ok(readinessEnvelope.data.view);
  assert.ok(readinessEnvelope.data.summary);

  const explanationAdapter = createCommercialExplanationAdapter();
  const explanationEnvelope = await explanationAdapter(CALLER_CONTEXT, "explain", feedItem());
  assert.ok(explanationEnvelope.data.explanation);
  assert.ok(explanationEnvelope.data.recommendation);
});

test("CommercialAdapterValidationError carries the capabilityId it was raised for", () => {
  const error = new CommercialAdapterValidationError("commercial.productPackage", "bad input");
  assert.equal(error.capabilityId, "commercial.productPackage");
  assert.equal(error.name, "CommercialAdapterValidationError");
  assert.match(error.message, /commercial\.productPackage/);
});
