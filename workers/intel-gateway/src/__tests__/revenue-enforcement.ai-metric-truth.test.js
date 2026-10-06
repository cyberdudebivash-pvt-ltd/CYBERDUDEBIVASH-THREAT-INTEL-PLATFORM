import assert from 'node:assert/strict';
import test from 'node:test';
import { applyTierGateV2 } from '../revenue-enforcement.js';

for (const tier of ['free', 'pro', 'enterprise', 'mssp']) {
  test(`${tier}: absent and invalid AI measurements stay unavailable`, () => {
    for (const value of [undefined, null, '0.5', -1, NaN, Infinity, -Infinity]) {
      const response = applyTierGateV2({ id: 'metric-fixture', risk_score: value, confidence: value }, tier, null);
      assert.equal(response.apex_ai.predictive_risk, null);
      assert.equal(response.apex_ai.ai_confidence, null);
    }
    const response = applyTierGateV2({ id: 'metric-fixture', risk_score: 11, confidence: 1.1 }, tier, null);
    assert.equal(response.apex_ai.predictive_risk, null);
    assert.equal(response.apex_ai.ai_confidence, null);
  });
  test(`${tier}: measured zero and valid boundaries survive without changing entitlement`, () => {
    for (const [risk, confidence] of [[0, 0], [10, 1], [7.5, 0.25]]) {
      const response = applyTierGateV2({ id: 'metric-fixture', risk_score: risk, confidence }, tier, null);
      assert.equal(response.apex_ai.predictive_risk, risk);
      assert.equal(response.apex_ai.ai_confidence, confidence * 100);
      assert.equal(response.apex_ai.locked, tier === 'free');
    }
  });
}
