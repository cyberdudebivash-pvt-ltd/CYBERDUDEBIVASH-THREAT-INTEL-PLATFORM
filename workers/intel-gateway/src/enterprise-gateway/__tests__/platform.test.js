import assert from "node:assert/strict";
import { test } from "node:test";
import { createEnterpriseGateway } from "../platform.js";
import { EnterpriseGateway } from "../gateway-service.js";
import { createIntelligencePlatform } from "../../intelligence-platform/platform.js";

test("disabled by default for production and canary (default environment is production)", () => {
  const result = createEnterpriseGateway();
  assert.equal(result.enabled, false);
  assert.equal(result.gateway, null);
  assert.match(result.reason, /EIG_ENABLED is false/);

  const canary = createEnterpriseGateway({ environment: "canary" });
  assert.equal(canary.enabled, false);
});

test("enabled for development and testing, returning a real, ready EnterpriseGateway", () => {
  for (const environment of ["development", "testing"]) {
    const result = createEnterpriseGateway({ environment });
    assert.equal(result.enabled, true);
    assert.ok(result.gateway instanceof EnterpriseGateway);
    assert.equal(result.environment, environment);
  }
});

test("an unrecognized environment string falls back to the disabled production state", () => {
  const result = createEnterpriseGateway({ environment: "staging-typo" });
  assert.equal(result.enabled, false);
});

test("an injected deps.intelligencePlatform is honored instead of constructing a new one", () => {
  const injected = createIntelligencePlatform({ environment: "testing" });
  const result = createEnterpriseGateway({ environment: "testing", deps: { intelligencePlatform: injected } });
  assert.equal(result.enabled, true);
  assert.equal(result.gateway.platform, injected.platform);
});

test("propagates a disabled underlying intelligence platform (defense in depth against an inconsistent injected result)", () => {
  const result = createEnterpriseGateway({
    environment: "testing",
    deps: {
      intelligencePlatform: { enabled: false, platform: null, environment: "testing", reason: "forced disabled for this test" },
    },
  });
  assert.equal(result.enabled, false);
  assert.match(result.reason, /Underlying intelligence platform is disabled/);
});
