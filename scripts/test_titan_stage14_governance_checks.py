#!/usr/bin/env python3
"""
scripts/test_titan_stage14_governance_checks.py
Project TITAN Stage 14/15 — positive/negative fixture tests for the Stage 14/15 governance check
functions in titan_architecture_governance_check.py: the 12 added in Stage 14 Phase 1, Phase 2's
check_gateway_registry_describe_omits_handler(), and Stage 15's check_gateway_bypass_new_direct_
composition_consumers() (14 check_* functions total, plus Stage 15's compute_gateway_adoption_
metrics(), which returns counts rather than findings; not all share the check_eig_* naming
prefix, e.g. check_no_duplicate_enterprise_gateway() and check_gateway_capability_authorization_
present() -- see that file's own docstring for the full naming list). Filename kept as Stage 14's
original -- Stage 15 extends the same fixture suite rather than starting a parallel one.

titan_architecture_governance_check.py's existing check_* functions have no fixture-directory
mechanism anywhere in this codebase (confirmed by grep before writing this file in Phase 1) --
each one reads real production files from disk directly. Rather than inventing an inconsistent
parallel fixture convention for only some checks, this file takes the narrower path: only the
Stage 14/15 functions listed above (and no pre-existing function -- their signatures are
otherwise untouched) accept an optional directory-override parameter defaulting to the real path,
so main()'s own call sites stay zero-argument while this file can point them at temp-directory
good/bad content instead.

stdlib only (unittest + tempfile), matching the governance script's own zero-dependency ethos.
Run: python3 scripts/test_titan_stage14_governance_checks.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import titan_architecture_governance_check as governance  # noqa: E402


def write_tree(root: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


# A minimal, otherwise-clean gateway-service.js body reused as the "good" baseline by several
# tests below, then selectively mutated per test to introduce exactly one bad condition.
GOOD_GATEWAY_SERVICE_JS = """
export class EnterpriseGateway {
  constructor(deps = {}) {
    this._platform = deps.platform;
    const serviceMetrics = deps.serviceMetrics || this._platform.metrics.sharedServiceMetrics;
    if (this._platform.metrics.sharedServiceMetrics !== serviceMetrics) {
      throw new Error("mismatch");
    }
    this.metrics = new GatewayMetrics(this._platform.metrics);
    this._dispatcher = new GatewayDispatcher({
      registry: this._registry,
      serviceMetrics,
      gatewayMetrics: this.metrics,
    });
  }
  _registerDefaultCapabilities() {
    this._registry.register("evidence.lookup", createServiceMethodHandler(platform.lookup));
    this._registry.register("intelligence.query", createServiceMethodHandler(platform.enterpriseQuery));
    this._registry.register("intelligence.correlation", createServiceMethodHandler(platform.correlation));
    this._registry.register("intelligence.validation", createServiceMethodHandler(platform.validation));
    this._registry.register("intelligence.threatProfile", createServiceMethodHandler(platform.threatIntelligence));
    this._registry.register("evidence.provenance", createServiceMethodHandler(platform.provenance));
    // ADR-0010: pass-through only
    this._registry.register("evidence.relationships", createServiceMethodHandler(platform.relationshipResolution));
    this._registry.register("platform.metrics", createServiceMethodHandler(platform.metrics));
    this._registry.register("intelligence.explainability", createServiceMethodHandler(platform.explainability));
  }
}
"""

GOOD_GATEWAY_METRICS_JS = """
export class GatewayMetrics {
  constructor(intelligenceMetrics) {
    this._intelligenceMetrics = intelligenceMetrics;
    this._featureFlagEvaluations = {};
  }
}
"""

GOOD_GATEWAY_DISPATCHER_JS = """
export class CapabilityAuthorizationError extends Error {}
export class GatewayDispatcher {
  async dispatch(request) {
    const missing = entry.requiredCapabilities.filter((r) => !grantedCapabilities.includes(r));
    if (missing.length > 0) throw new CapabilityAuthorizationError();
  }
}
"""

GOOD_GATEWAY_MIDDLEWARE_JS = """
export function capabilityValidationMiddleware() { return async (context, next) => next(); }
"""

def _contract_block(name: str, version: str = "1.0.0", history_version: str = "1.0.0") -> str:
    return f"""
export const {name} = Object.freeze({{
  name: "{name}",
  version: "{version}",
  source: "gateway-service.js",
  methods: Object.freeze(["EnterpriseGateway.dispatch"]),
  history: Object.freeze([
    Object.freeze({{ version: "{history_version}", change: "Initial", backwardCompatibleWithPrevious: null }}),
  ]),
}});
"""


# All 4 real EIG contract names, each individually version-consistent -- check_eig_contract_
# version_drift() iterates all 4 by name, so a "clean" fixture must define every one of them,
# not just the one under direct test.
GOOD_SERVICE_CONTRACTS_JS = "".join(
    _contract_block(name)
    for name in ["GatewayServiceContract", "MiddlewareContract", "CapabilityRegistryContract", "GatewayMetricsContract"]
)


class CheckEigFilesPresentAndIsolatedTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(gateway_dir, {name: "export const x = 1;\n" for name in governance.EIG_CORE_FILES})
            findings = governance.check_eig_files_present_and_isolated(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_missing_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            files = {name: "export const x = 1;\n" for name in governance.EIG_CORE_FILES}
            del files["platform.js"]
            write_tree(gateway_dir, files)
            findings = governance.check_eig_files_present_and_isolated(gateway_dir=gateway_dir)
            self.assertTrue(any("MISSING EIG FILE" in f and "platform.js" in f for f in findings))

    def test_pNN_handlers_import_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            files = {name: "export const x = 1;\n" for name in governance.EIG_CORE_FILES}
            files["gateway-service.js"] = 'import { x } from "../p99-handlers.js";\n'
            write_tree(gateway_dir, files)
            findings = governance.check_eig_files_present_and_isolated(gateway_dir=gateway_dir)
            self.assertTrue(any("ARCHITECTURE VIOLATION" in f for f in findings))


class CheckNoDuplicateEnterpriseGatewayTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            handlers_dir = Path(tmp)
            gateway_dir = handlers_dir / "enterprise-gateway"
            write_tree(
                handlers_dir,
                {
                    "enterprise-gateway/gateway-service.js": "export class EnterpriseGateway {}\n",
                    "index.js": "// no gateway class here\n",
                },
            )
            findings = governance.check_no_duplicate_enterprise_gateway(handlers_dir=handlers_dir, gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_duplicate_class_outside_canonical_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            handlers_dir = Path(tmp)
            gateway_dir = handlers_dir / "enterprise-gateway"
            write_tree(
                handlers_dir,
                {
                    "enterprise-gateway/gateway-service.js": "export class EnterpriseGateway {}\n",
                    "some-other-file.js": "export class EnterpriseGateway {}\n",
                },
            )
            findings = governance.check_no_duplicate_enterprise_gateway(handlers_dir=handlers_dir, gateway_dir=gateway_dir)
            self.assertTrue(any("DUPLICATE ENGINE" in f and "EnterpriseGateway" in f for f in findings))


class CheckGatewayCapabilitiesDelegateTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(gateway_dir, {"gateway-service.js": GOOD_GATEWAY_SERVICE_JS})
            findings = governance.check_gateway_capabilities_delegate_not_reimplement(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_missing_capability_target_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            # "platformX.provenanceY" does not contain "platform.provenance" as a substring --
            # unlike e.g. "platform.provenanceRENAMED", which still would (a real mistake this
            # test caught on its first run: extending the string left the original substring
            # intact, so the check correctly found nothing wrong).
            bad = GOOD_GATEWAY_SERVICE_JS.replace("platform.provenance", "platformX.provenanceY")
            write_tree(gateway_dir, {"gateway-service.js": bad})
            findings = governance.check_gateway_capabilities_delegate_not_reimplement(gateway_dir=gateway_dir)
            self.assertTrue(any("REUSE BYPASS" in f and "platform.provenance" in f for f in findings))


class CheckEigContractVersionDriftTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(gateway_dir, {"service-contracts.js": GOOD_SERVICE_CONTRACTS_JS})
            findings = governance.check_eig_contract_version_drift(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_mismatched_version_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            # Only GatewayServiceContract's own top-level version drifts from its history --
            # its name+version combination is unique in the fixture, so this can't accidentally
            # also mutate one of the other 3 contracts.
            bad = GOOD_SERVICE_CONTRACTS_JS.replace(
                'export const GatewayServiceContract = Object.freeze({\n  name: "GatewayServiceContract",\n  version: "1.0.0"',
                'export const GatewayServiceContract = Object.freeze({\n  name: "GatewayServiceContract",\n  version: "2.0.0"',
            )
            write_tree(gateway_dir, {"service-contracts.js": bad})
            findings = governance.check_eig_contract_version_drift(gateway_dir=gateway_dir)
            self.assertTrue(any("CONTRACT VERSION DRIFT" in f and "GatewayServiceContract" in f for f in findings))


class CheckNoDuplicateEigContractsTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            handlers_dir = Path(tmp)
            gateway_dir = handlers_dir / "enterprise-gateway"
            write_tree(handlers_dir, {"enterprise-gateway/service-contracts.js": GOOD_SERVICE_CONTRACTS_JS})
            findings = governance.check_no_duplicate_eig_contracts(handlers_dir=handlers_dir, gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_duplicate_contract_export_elsewhere_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            handlers_dir = Path(tmp)
            gateway_dir = handlers_dir / "enterprise-gateway"
            write_tree(
                handlers_dir,
                {
                    "enterprise-gateway/service-contracts.js": GOOD_SERVICE_CONTRACTS_JS,
                    "rogue.js": "export const GatewayServiceContract = {};\n",
                },
            )
            findings = governance.check_no_duplicate_eig_contracts(handlers_dir=handlers_dir, gateway_dir=gateway_dir)
            self.assertTrue(any("DUPLICATE CONTRACT" in f for f in findings))


class CheckNoEigRegistryPrivateFieldBypassTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(
                gateway_dir,
                {
                    "gateway-registry.js": "export class GatewayRegistry { constructor() { this._entries = new Map(); } }\n",
                    "gateway-service.js": "export class EnterpriseGateway {}\n",
                },
            )
            findings = governance.check_no_eig_registry_private_field_bypass(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_bypass_from_outside_canonical_files_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(
                gateway_dir,
                {
                    "gateway-registry.js": "export class GatewayRegistry { constructor() { this._entries = new Map(); } }\n",
                    "gateway-service.js": "export class EnterpriseGateway { peek() { return this._registry._entries; } }\n",
                },
            )
            findings = governance.check_no_eig_registry_private_field_bypass(gateway_dir=gateway_dir)
            self.assertTrue(any("REGISTRY BYPASS" in f and "_entries" in f for f in findings))


GOOD_GATEWAY_REGISTRY_JS = """
export class GatewayRegistry {
  constructor() {
    this._entries = new Map();
  }

  get(name) {
    const entry = this._entries.get(name);
    if (!entry) throw new CapabilityNotRegisteredError(name);
    return entry;
  }

  list() {
    return [...this._entries.keys()];
  }

  describe(name) {
    const entry = this.get(name);
    return {
      name: entry.name,
      version: entry.version,
      description: entry.description,
      requiredCapabilities: entry.requiredCapabilities,
    };
  }

  describeAll() {
    return this.list().map((name) => this.describe(name));
  }
}
"""


class CheckGatewayRegistryDescribeOmitsHandlerTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(gateway_dir, {"gateway-registry.js": GOOD_GATEWAY_REGISTRY_JS})
            findings = governance.check_gateway_registry_describe_omits_handler(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_describe_leaking_handler_via_spread_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad = GOOD_GATEWAY_REGISTRY_JS.replace(
                "  describe(name) {\n    const entry = this.get(name);\n    return {\n"
                "      name: entry.name,\n      version: entry.version,\n"
                "      description: entry.description,\n"
                "      requiredCapabilities: entry.requiredCapabilities,\n    };\n  }\n",
                "  describe(name) {\n    const entry = this.get(name);\n    return { ...entry };\n  }\n",
            )
            self.assertIn("...entry", bad)
            write_tree(gateway_dir, {"gateway-registry.js": bad})
            findings = governance.check_gateway_registry_describe_omits_handler(gateway_dir=gateway_dir)
            self.assertTrue(any("REGISTRY BYPASS" in f and "describe()" in f for f in findings))

    def test_describe_leaking_handler_directly_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad = GOOD_GATEWAY_REGISTRY_JS.replace(
                "requiredCapabilities: entry.requiredCapabilities,\n    };\n  }\n",
                "requiredCapabilities: entry.requiredCapabilities,\n      handler: entry.handler,\n    };\n  }\n",
            )
            write_tree(gateway_dir, {"gateway-registry.js": bad})
            findings = governance.check_gateway_registry_describe_omits_handler(gateway_dir=gateway_dir)
            self.assertTrue(any("REGISTRY BYPASS" in f and "describe()" in f for f in findings))

    def test_missing_describe_method_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad = GOOD_GATEWAY_REGISTRY_JS.replace(
                "  describe(name) {\n    const entry = this.get(name);\n    return {\n"
                "      name: entry.name,\n      version: entry.version,\n"
                "      description: entry.description,\n"
                "      requiredCapabilities: entry.requiredCapabilities,\n    };\n  }\n\n",
                "",
            )
            # describeAll()'s own body still legitimately calls `this.describe(name)` -- assert the
            # DEFINITION is gone (the " {" opening), not the substring, which remains at that call site.
            self.assertNotIn("describe(name) {", bad)
            write_tree(gateway_dir, {"gateway-registry.js": bad})
            findings = governance.check_gateway_registry_describe_omits_handler(gateway_dir=gateway_dir)
            self.assertTrue(any("GOVERNANCE" in f and "'describe()'" in f for f in findings))

    def test_missing_file_yields_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            gateway_dir.mkdir(parents=True)
            findings = governance.check_gateway_registry_describe_omits_handler(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])


class CheckGatewayRelationshipCapabilityStillPassthroughTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(gateway_dir, {"gateway-service.js": GOOD_GATEWAY_SERVICE_JS})
            findings = governance.check_gateway_relationship_capability_still_passthrough(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_missing_adr_0010_documentation_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad = GOOD_GATEWAY_SERVICE_JS.replace("// ADR-0010: pass-through only\n", "")
            write_tree(gateway_dir, {"gateway-service.js": bad})
            findings = governance.check_gateway_relationship_capability_still_passthrough(gateway_dir=gateway_dir)
            self.assertTrue(any("ADR-0010 GOVERNANCE" in f for f in findings))


class CheckGatewayValidationMiddlewareTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(
                gateway_dir,
                {"gateway-service.js": GOOD_GATEWAY_SERVICE_JS, "gateway-middleware.js": GOOD_GATEWAY_MIDDLEWARE_JS},
            )
            findings = governance.check_gateway_validation_middleware_delegates_not_reimplements(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_data_validation_smell_in_middleware_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad_middleware = GOOD_GATEWAY_MIDDLEWARE_JS + '\nconst check = (e) => e.reliability_code === "A";\n'
            write_tree(gateway_dir, {"gateway-service.js": GOOD_GATEWAY_SERVICE_JS, "gateway-middleware.js": bad_middleware})
            findings = governance.check_gateway_validation_middleware_delegates_not_reimplements(gateway_dir=gateway_dir)
            self.assertTrue(any("VALIDATION BYPASS" in f and "reliability_code" in f for f in findings))


class CheckEigMetricsNoDuplicateInstanceTests(unittest.TestCase):
    """The check the brief calls out by name -- this is the exact bug class Stage 13's own
    prior, interrupted session found and lost before committing a fix."""

    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(
                gateway_dir, {"gateway-service.js": GOOD_GATEWAY_SERVICE_JS, "gateway-metrics.js": GOOD_GATEWAY_METRICS_JS}
            )
            findings = governance.check_eig_metrics_no_duplicate_instance(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_missing_mismatch_guard_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad = GOOD_GATEWAY_SERVICE_JS.replace(
                'if (this._platform.metrics.sharedServiceMetrics !== serviceMetrics) {\n      throw new Error("mismatch");\n    }\n',
                "",
            )
            write_tree(gateway_dir, {"gateway-service.js": bad, "gateway-metrics.js": GOOD_GATEWAY_METRICS_JS})
            findings = governance.check_eig_metrics_no_duplicate_instance(gateway_dir=gateway_dir)
            self.assertTrue(any("no longer guards against a mismatched" in f for f in findings))

    def test_second_counter_set_in_gateway_metrics_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad_metrics = GOOD_GATEWAY_METRICS_JS.replace(
                "this._featureFlagEvaluations = {};", "this._featureFlagEvaluations = {};\n    this._callCounts = {};"
            )
            write_tree(gateway_dir, {"gateway-service.js": GOOD_GATEWAY_SERVICE_JS, "gateway-metrics.js": bad_metrics})
            findings = governance.check_eig_metrics_no_duplicate_instance(gateway_dir=gateway_dir)
            self.assertTrue(any("_callCounts" in f and "already owned by ServicePlatformMetrics" in f for f in findings))


class CheckNoCircularDependencyTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(
                root,
                {
                    "enterprise-gateway/gateway-service.js": "export class EnterpriseGateway {}\n",
                    "intelligence-platform/intelligence-service.js": "export class IntelligenceService {}\n",
                    "evidence-registry/evidence-service.js": "export class EvidenceService {}\n",
                },
            )
            findings = governance.check_no_circular_dependency_gateway_intelligence_platform(
                gateway_dir=root / "enterprise-gateway",
                intelligence_platform_dir=root / "intelligence-platform",
                evidence_registry_dir=root / "evidence-registry",
            )
            self.assertEqual(findings, [])

    def test_upward_reference_from_intelligence_platform_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(
                root,
                {
                    "enterprise-gateway/gateway-service.js": "export class EnterpriseGateway {}\n",
                    "intelligence-platform/intelligence-service.js": "// see enterprise-gateway for the consumer\n",
                    "evidence-registry/evidence-service.js": "export class EvidenceService {}\n",
                },
            )
            findings = governance.check_no_circular_dependency_gateway_intelligence_platform(
                gateway_dir=root / "enterprise-gateway",
                intelligence_platform_dir=root / "intelligence-platform",
                evidence_registry_dir=root / "evidence-registry",
            )
            self.assertTrue(any("CIRCULAR DEPENDENCY" in f for f in findings))


class CheckGatewayCapabilityAuthorizationPresentTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(gateway_dir, {"gateway-dispatcher.js": GOOD_GATEWAY_DISPATCHER_JS})
            findings = governance.check_gateway_capability_authorization_present(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_missing_authorization_error_class_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad = GOOD_GATEWAY_DISPATCHER_JS.replace("CapabilityAuthorizationError", "SomeOtherError")
            write_tree(gateway_dir, {"gateway-dispatcher.js": bad})
            findings = governance.check_gateway_capability_authorization_present(gateway_dir=gateway_dir)
            self.assertTrue(any("GOVERNANCE" in f and "CapabilityAuthorizationError" in f for f in findings))


class CheckGatewayNoNetworkAuthScopeCreepTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            write_tree(gateway_dir, {"gateway-service.js": GOOD_GATEWAY_SERVICE_JS})
            findings = governance.check_gateway_no_network_auth_scope_creep(gateway_dir=gateway_dir)
            self.assertEqual(findings, [])

    def test_admin_secret_reference_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad = GOOD_GATEWAY_SERVICE_JS + "\nconst secret = env.ADMIN_SECRET;\n"
            write_tree(gateway_dir, {"gateway-service.js": bad})
            findings = governance.check_gateway_no_network_auth_scope_creep(gateway_dir=gateway_dir)
            # The finding's description prose doesn't echo the literal matched token (unlike the
            # "fetch" case below, where it happens to) -- assert against what the message
            # actually says, not what the matched pattern was.
            self.assertTrue(any("SCOPE CREEP" in f and "shared-secret" in f for f in findings))

    def test_fetch_handler_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway_dir = Path(tmp) / "enterprise-gateway"
            bad = 'addEventListener("fetch", (event) => {});\n'
            write_tree(gateway_dir, {"gateway-service.js": bad})
            findings = governance.check_gateway_no_network_auth_scope_creep(gateway_dir=gateway_dir)
            self.assertTrue(any("SCOPE CREEP" in f and "fetch" in f for f in findings))


def _write_gateway_consumer_fixture(tmp: str) -> tuple[Path, Path]:
    """Shared fixture builder for the Stage 15 tests below: a scripts_dir with the two REAL,
    known consumers (one legacy/authorized, one Gateway-backed) plus a handlers_dir whose mere
    existence satisfies _classify_scripts_gateway_consumers()'s gate check (its own contents are
    never read by that function)."""
    scripts_dir = Path(tmp) / "scripts"
    handlers_dir = Path(tmp) / "handlers"
    write_tree(
        scripts_dir,
        {
            "intelligence_platform_snapshot.mjs": (
                'import { createIntelligencePlatform } from "../handlers/intelligence-platform/platform.js";\n'
            ),
            "enterprise_gateway_snapshot.mjs": (
                'import { createEnterpriseGateway } from "../handlers/enterprise-gateway/platform.js";\n'
            ),
        },
    )
    (handlers_dir / "intelligence-platform").mkdir(parents=True, exist_ok=True)
    return scripts_dir, handlers_dir


class CheckGatewayBypassNewDirectCompositionConsumersTests(unittest.TestCase):
    def test_known_legacy_and_gateway_backed_consumers_are_both_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir, handlers_dir = _write_gateway_consumer_fixture(tmp)
            findings = governance.check_gateway_bypass_new_direct_composition_consumers(
                scripts_dir=scripts_dir, handlers_dir=handlers_dir
            )
            self.assertEqual(findings, [])

    def test_new_unauthorized_direct_composition_consumer_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir, handlers_dir = _write_gateway_consumer_fixture(tmp)
            write_tree(
                scripts_dir,
                {
                    "some_new_script.mjs": (
                        'import { createIntelligencePlatform } from "../handlers/intelligence-platform/platform.js";\n'
                    )
                },
            )
            findings = governance.check_gateway_bypass_new_direct_composition_consumers(
                scripts_dir=scripts_dir, handlers_dir=handlers_dir
            )
            self.assertTrue(any("GATEWAY BYPASS" in f and "some_new_script.mjs" in f for f in findings))

    def test_missing_scripts_dir_yields_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = governance.check_gateway_bypass_new_direct_composition_consumers(
                scripts_dir=Path(tmp) / "nonexistent", handlers_dir=Path(tmp) / "handlers"
            )
            self.assertEqual(findings, [])

    def test_missing_intelligence_platform_dir_yields_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir, _ = _write_gateway_consumer_fixture(tmp)
            findings = governance.check_gateway_bypass_new_direct_composition_consumers(
                scripts_dir=scripts_dir, handlers_dir=Path(tmp) / "no-handlers-here"
            )
            self.assertEqual(findings, [])


class ComputeGatewayAdoptionMetricsTests(unittest.TestCase):
    def test_metrics_match_the_known_two_consumer_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir, handlers_dir = _write_gateway_consumer_fixture(tmp)
            metrics = governance.compute_gateway_adoption_metrics(scripts_dir=scripts_dir, handlers_dir=handlers_dir)
            self.assertEqual(metrics["total_known_consumers"], 2)
            self.assertEqual(metrics["gateway_backed"], 1)
            self.assertEqual(metrics["direct_composition_legacy"], 1)
            self.assertEqual(metrics["adoption_percentage"], 50.0)
            self.assertEqual(len(metrics["consumers"]), 2)

    def test_empty_scripts_dir_yields_none_percentage_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir = Path(tmp) / "scripts"
            handlers_dir = Path(tmp) / "handlers"
            scripts_dir.mkdir()
            (handlers_dir / "intelligence-platform").mkdir(parents=True)
            metrics = governance.compute_gateway_adoption_metrics(scripts_dir=scripts_dir, handlers_dir=handlers_dir)
            self.assertEqual(metrics["total_known_consumers"], 0)
            self.assertIsNone(metrics["adoption_percentage"])

    def test_a_third_gateway_backed_consumer_shifts_the_percentage(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir, handlers_dir = _write_gateway_consumer_fixture(tmp)
            write_tree(
                scripts_dir,
                {
                    "another_gateway_consumer.mjs": (
                        'import { createEnterpriseGateway } from "../handlers/enterprise-gateway/platform.js";\n'
                    )
                },
            )
            metrics = governance.compute_gateway_adoption_metrics(scripts_dir=scripts_dir, handlers_dir=handlers_dir)
            self.assertEqual(metrics["total_known_consumers"], 3)
            self.assertEqual(metrics["gateway_backed"], 2)
            self.assertAlmostEqual(metrics["adoption_percentage"], 66.7)


# -- Stage 16: Relationship Framework governance check fixture tests -----------------------------

GOOD_RELATIONSHIP_SERVICE_JS = """
import { RelationshipResolutionService } from "../evidence-registry/relationship-resolution.js";
import { P31RelationshipProvider } from "./relationship-provider.js";

export class RelationshipService {
  constructor(deps = {}) {
    this._provider = new P31RelationshipProvider({ repository: this._repository });
    this.resolution = new RelationshipResolutionService({ provider: this._provider });
  }
}
"""

GOOD_RELATIONSHIP_PROVIDER_JS = """
import { RelationshipProviderInterface } from "../evidence-registry/relationship-resolution.js";
export class P31RelationshipProvider extends RelationshipProviderInterface {}
"""


class CheckRelationshipFrameworkFilesPresentAndIsolatedTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            rf_dir = Path(tmp) / "relationship-framework"
            write_tree(rf_dir, {name: "export const x = 1;\n" for name in governance.RELATIONSHIP_FRAMEWORK_CORE_FILES})
            findings = governance.check_relationship_framework_files_present_and_isolated(rf_dir=rf_dir)
            self.assertEqual(findings, [])

    def test_missing_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            rf_dir = Path(tmp) / "relationship-framework"
            files = {name: "export const x = 1;\n" for name in governance.RELATIONSHIP_FRAMEWORK_CORE_FILES}
            del files["relationship-service.js"]
            write_tree(rf_dir, files)
            findings = governance.check_relationship_framework_files_present_and_isolated(rf_dir=rf_dir)
            self.assertTrue(any("MISSING RELATIONSHIP FRAMEWORK FILE" in f and "relationship-service.js" in f for f in findings))

    def test_pNN_handlers_import_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            rf_dir = Path(tmp) / "relationship-framework"
            files = {name: "export const x = 1;\n" for name in governance.RELATIONSHIP_FRAMEWORK_CORE_FILES}
            files["relationship-provider.js"] = 'import { x } from "../p31-handlers.js";\n'
            write_tree(rf_dir, files)
            findings = governance.check_relationship_framework_files_present_and_isolated(rf_dir=rf_dir)
            self.assertTrue(any("ARCHITECTURE VIOLATION" in f for f in findings))

    def test_missing_directory_yields_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            rf_dir = Path(tmp) / "relationship-framework"  # never created
            findings = governance.check_relationship_framework_files_present_and_isolated(rf_dir=rf_dir)
            self.assertEqual(findings, [])


class CheckNoDuplicateRelationshipEngineTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            handlers_dir = Path(tmp)
            rf_dir = handlers_dir / "relationship-framework"
            write_tree(
                handlers_dir,
                {
                    "relationship-framework/relationship-service.js": "export class RelationshipService {}\n",
                    "index.js": "// no relationship class here\n",
                },
            )
            findings = governance.check_no_duplicate_relationship_engine(handlers_dir=handlers_dir, rf_dir=rf_dir)
            self.assertEqual(findings, [])

    def test_duplicate_class_outside_canonical_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            handlers_dir = Path(tmp)
            rf_dir = handlers_dir / "relationship-framework"
            write_tree(
                handlers_dir,
                {
                    "relationship-framework/relationship-traversal.js": "export class RelationshipTraversalService {}\n",
                    "some-other-file.js": "export class RelationshipTraversalService {}\n",
                },
            )
            findings = governance.check_no_duplicate_relationship_engine(handlers_dir=handlers_dir, rf_dir=rf_dir)
            self.assertTrue(any("DUPLICATE ENGINE" in f and "RelationshipTraversalService" in f for f in findings))

    def test_missing_directory_yields_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            handlers_dir = Path(tmp)
            rf_dir = handlers_dir / "relationship-framework"  # never created
            findings = governance.check_no_duplicate_relationship_engine(handlers_dir=handlers_dir, rf_dir=rf_dir)
            self.assertEqual(findings, [])


class CheckRelationshipFrameworkProviderWiringIntactTests(unittest.TestCase):
    def test_good_fixture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            rf_dir = Path(tmp) / "relationship-framework"
            write_tree(
                rf_dir,
                {
                    "relationship-service.js": GOOD_RELATIONSHIP_SERVICE_JS,
                    "relationship-provider.js": GOOD_RELATIONSHIP_PROVIDER_JS,
                },
            )
            findings = governance.check_relationship_framework_provider_wiring_intact(rf_dir=rf_dir)
            self.assertEqual(findings, [])

    def test_regression_to_unwired_default_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            rf_dir = Path(tmp) / "relationship-framework"
            bad = GOOD_RELATIONSHIP_SERVICE_JS.replace(
                "this.resolution = new RelationshipResolutionService({ provider: this._provider });",
                "this.resolution = new RelationshipResolutionService();",
            ).replace("P31RelationshipProvider", "SomethingElse")
            write_tree(rf_dir, {"relationship-service.js": bad, "relationship-provider.js": GOOD_RELATIONSHIP_PROVIDER_JS})
            findings = governance.check_relationship_framework_provider_wiring_intact(rf_dir=rf_dir)
            self.assertTrue(any("RELATIONSHIP WIRING DRIFT" in f and "provider" in f for f in findings))
            self.assertTrue(any("RELATIONSHIP WIRING DRIFT" in f and "P31RelationshipProvider" in f for f in findings))

    def test_direct_p31_handlers_import_in_provider_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            rf_dir = Path(tmp) / "relationship-framework"
            bad_provider = 'import { buildP31RelationshipBlock } from "../p31-handlers.js";\n' + GOOD_RELATIONSHIP_PROVIDER_JS
            write_tree(rf_dir, {"relationship-service.js": GOOD_RELATIONSHIP_SERVICE_JS, "relationship-provider.js": bad_provider})
            findings = governance.check_relationship_framework_provider_wiring_intact(rf_dir=rf_dir)
            self.assertTrue(any("ARCHITECTURE VIOLATION" in f for f in findings))

    def test_missing_service_file_yields_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            rf_dir = Path(tmp) / "relationship-framework"  # never created
            findings = governance.check_relationship_framework_provider_wiring_intact(rf_dir=rf_dir)
            self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
