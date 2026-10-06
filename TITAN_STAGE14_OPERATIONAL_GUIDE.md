# Project TITAN Stage 14, Phase 1 — Enterprise Intelligence Gateway (EIG) Operational Guide

## What runs today

Nothing, in production. `enterprise-gateway/` is not imported by `index.js` or any `pNN-handlers.js` file, and `EIG_ENABLED`/`INTERNAL_ADOPTION_ENABLED` both default to `false` in `canary`/`production` (`true` in `development`/`testing`, mirroring `EIPS_FLAGS`'s identical pattern). The only thing that ever runs it is `scripts/enterprise_gateway_snapshot.mjs`, invoked manually or by CI, and its own test suite.

## Instantiation example

```js
import { createEnterpriseGateway } from "./workers/intel-gateway/src/enterprise-gateway/platform.js";

const { enabled, gateway, reason } = createEnterpriseGateway({ environment: "development" });
if (!enabled) {
  console.log(`Gateway disabled: ${reason}`);
} else {
  const result = await gateway.dispatch({
    capability: "evidence.lookup",
    method: "byCVE",
    args: ["CVE-2026-1234"],
    caller: { id: "my-script", kind: "script" },
    grantedCapabilities: ["evidence.lookup"], // least privilege — only what this call needs
  });
}
```

Or inject an already-constructed platform (e.g. from a caller that already has one, or from a test):

```js
import { createEnterpriseGateway } from ".../enterprise-gateway/platform.js";
import { createIntelligencePlatform } from ".../intelligence-platform/platform.js";

const intelligencePlatform = createIntelligencePlatform({ environment: "testing" });
const { gateway } = createEnterpriseGateway({ environment: "testing", deps: { intelligencePlatform } });
```

## Migration guidance for a future consumer

1. Confirm `EIG_ENABLED` for your target environment (`resolveEigFlags()`).
2. Construct via `createEnterpriseGateway()` (preferred) or inject `EnterpriseGateway` directly via DI (supported, used throughout this stage's own tests).
3. Call `gateway.dispatch({capability, method, args, caller, grantedCapabilities})` instead of importing `IntelligenceService`/`EvidenceService` directly.
4. Grant only the capabilities your caller actually needs — `grantedCapabilities` is checked against each capability's `requiredCapabilities` (defaults to `[capabilityName]`).
5. If you need per-request metrics/audit visibility, read `gateway.metrics.snapshot()` (shape: `{registry, service, gateway}`).

Wiring the gateway into a live `pNN-handlers.js` route or `index.js` is a separate, future, architecturally-significant step requiring its own authorization — not performed here (see the Completion Report §11).

## Rollback

Nothing to roll back in the usual sense. Stop invoking `scripts/enterprise_gateway_snapshot.mjs`, or leave `INTERNAL_ADOPTION_ENABLED`/`EIG_ENABLED` at their default `false` in canary/production. No persisted state exists anywhere (every `EnterpriseGateway`/`IntelligenceService` instance is in-memory only, constructed fresh per invocation).

## Observability

`gateway.healthCheck()` → `{state, ready, transitionedAt, capabilities, environment}`.
`gateway.metrics.snapshot()` → `{registry: {...Stage11}, service: {...shared Stage12/13/14 counters, including "gateway.<capability>" call_counts/latency}, gateway: {feature_flag_evaluations, capability_authorization_denials, middleware_validation_failures, recent_audit_entries}}`.
Every dispatch call also emits two `console.log` lines (`[Stage 14 gateway-trace]`) and one (`[Stage 14 gateway-audit]`), matching this platform's existing stdout-as-durable-record convention for local/CI runs.

## Support readiness

- All 8 capabilities are read-only in Phase 1 — no data-mutation risk from any gateway-mediated call.
- `evidence.relationships` remains pass-through-only pending ADR-0010 Acceptance; a caller invoking it gets exactly what `RelationshipResolutionService`'s `NullRelationshipProvider` already returns today (nothing new).
- If `dispatch()` throws `CapabilityAuthorizationError`, the error's `.missing` array names exactly which capability(ies) the caller needs to be granted — no guessing.
- If `dispatch()` throws `CapabilityNotRegisteredError`, the requested capability name doesn't exist; `gateway.listCapabilities()` returns the current live list.

## Performance baseline summary

See `TITAN_STAGE14_PERFORMANCE_BASELINE.md` for full methodology. Headline: gateway composition and dispatch overhead are both a small fraction of a millisecond to low tens of milliseconds even at 100-1000 sample volume — well under the platform's 50ms cold-start budget.
