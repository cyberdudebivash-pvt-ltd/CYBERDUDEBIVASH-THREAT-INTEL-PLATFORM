/**
 * Zero-blast-radius test for Stage 14's enterprise-gateway/ directory, mirroring
 * intelligence-platform/__tests__/zero-blast-radius.test.js's exact pattern (Stage 8-13
 * precedent). Confirms this stage's brand-new directory has not been wired into any production
 * route, and that it composes intelligence-platform/ through the one authorized hop without
 * modifying it or reaching past it into evidence-registry/ directly.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const EIG_DIR = dirname(HERE); // .../enterprise-gateway
const WORKER_SRC_DIR = dirname(EIG_DIR); // .../src
const INTELLIGENCE_PLATFORM_DIR = join(WORKER_SRC_DIR, "intelligence-platform");
const EVIDENCE_REGISTRY_DIR = join(WORKER_SRC_DIR, "evidence-registry");
const RELATIONSHIP_FRAMEWORK_DIR = join(WORKER_SRC_DIR, "relationship-framework");
const KNOWLEDGE_PLATFORM_DIR = join(WORKER_SRC_DIR, "knowledge-platform");
const PRODUCT_PLATFORM_DIR = join(WORKER_SRC_DIR, "product-platform");
const COMMERCIAL_CATALOG_DIR = join(WORKER_SRC_DIR, "commercial-catalog");

/**
 * Stage 16 (Project TITAN): relationship-framework/ is the first explicitly-authorized consumer
 * of enterprise-gateway/, added once ADR-0010 was Accepted. Its integration test
 * (relationship-framework/__tests__/integration.test.js) legitimately imports EnterpriseGateway
 * to prove real relationship data flows through the Gateway end-to-end -- the actual Phase 5
 * acceptance criterion. Its own zero-blast-radius test also names "enterprise-gateway" in prose
 * throughout. Exempting the whole directory mirrors exactly how this file already exempts
 * intelligence-platform's and evidence-registry's own __tests__ directories for the identical
 * boundary-documentation reason.
 *
 * Stage 18: knowledge-platform/ is added because its feature-flags.js docstring names
 * "enterprise-gateway" in prose (documenting that it mirrors EIG_FLAGS's shape) and its
 * __tests__/gateway-integration.test.js legitimately imports EnterpriseGateway and
 * createServiceMethodHandler to demonstrate Phase 7's registerCapability()-based wiring end to
 * end -- the same "composition-script consumer" pattern relationship-framework/'s own
 * integration test already established, not a new production dependency in either direction
 * (enterprise-gateway/ does not import knowledge-platform/ -- see
 * knowledge-platform/__tests__/zero-blast-radius.test.js's own independent confirmation).
 *
 * Stage 19: product-platform/ is added for the identical reason as knowledge-platform above --
 * its feature-flags.js docstring names "enterprise-gateway" in prose, and its own
 * __tests__/gateway-integration.test.js legitimately imports EnterpriseGateway and
 * createServiceMethodHandler to demonstrate Phase 6's registerCapability()-based wiring end to
 * end, the same composition-script-consumer pattern. Not a new production dependency in either
 * direction (enterprise-gateway/ does not import product-platform/ -- see
 * product-platform/__tests__/zero-blast-radius.test.js's own independent confirmation).
 *
 * Stage 21: commercial-catalog/ is added for a related but distinct reason. Unlike
 * knowledge-platform/product-platform (each composing exactly one thing one hop below
 * themselves), commercial-catalog/ is a deliberate cross-cutting layer over enterprise-gateway/,
 * knowledge-platform/, product-platform/, and p39-handlers.js simultaneously (Stage 21's own
 * charter -- see TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md Sec 3), so its feature-flags.js
 * genuinely imports DEPLOYMENT_ENVIRONMENTS from enterprise-gateway/feature-flags.js (a real,
 * constants-only import -- not just a prose mention), on the reasoning that EnterpriseGateway is
 * the instance every new commercial capability is ultimately registered onto. The Gateway
 * *instance* itself still reaches commercial-catalog/'s production files only via dependency
 * injection (platform.js/commercial-adapters.js take an already-constructed EnterpriseGateway as
 * a parameter, mirroring knowledge-platform/product-platform's identical DI pattern for their own
 * upstream dependency) -- only feature-flags.js's constants re-export, and
 * __tests__/gateway-integration.test.js proving Stage 21's registerCapability()/
 * annotateCapability()-based wiring end to end, are real imports. See
 * commercial-catalog/__tests__/zero-blast-radius.test.js's own independent confirmation that
 * enterprise-gateway/ does not import commercial-catalog/ back.
 */
const AUTHORIZED_CONSUMER_DIRS = [
  RELATIONSHIP_FRAMEWORK_DIR,
  KNOWLEDGE_PLATFORM_DIR,
  PRODUCT_PLATFORM_DIR,
  COMMERCIAL_CATALOG_DIR,
];

/**
 * True only if `file` IS `dir`, or is a path strictly inside it. Mirrors
 * intelligence-platform/__tests__/zero-blast-radius.test.js's identical helper.
 */
function isInside(file, dir) {
  return file === dir || file.startsWith(dir + sep);
}

function listJsFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      if (name === "node_modules") continue;
      out.push(...listJsFiles(full));
    } else if (name.endsWith(".js")) {
      out.push(full);
    }
  }
  return out;
}

test("isInside does not treat a sibling directory whose name merely extends dir's name as being inside it", () => {
  assert.equal(isInside(join(EIG_DIR, "gateway-service.js"), EIG_DIR), true, "a real child file must still match");
  assert.equal(isInside(EIG_DIR, EIG_DIR), true, "the directory itself must match");
  assert.equal(
    isInside(join(WORKER_SRC_DIR, "enterprise-gateway-experimental", "x.js"), EIG_DIR),
    false,
    "a sibling directory whose name extends EIG_DIR's name must NOT be treated as inside it"
  );
});

test("nothing outside enterprise-gateway/ references 'enterprise-gateway' except relationship-framework/ (Stage 16, the first authorized consumer) and documented test-fixture directories", () => {
  // __tests__ directories are exempt from this sweep: both intelligence-platform's AND
  // evidence-registry's own zero-blast-radius tests legitimately document this directory BY
  // NAME in their own authorized-exception comments/AUTHORIZED_CONSUMER_DIRS arrays (the mirror
  // image of what this file does for them below) -- that is boundary documentation, not
  // production coupling. Production reachability is what actually matters and is covered
  // precisely by the two tests below (index.js, and pNN-handlers.js/index.js imports from
  // inside this directory). AUTHORIZED_CONSUMER_DIRS (Stage 16, above) covers
  // relationship-framework/'s real import plus its own boundary-documentation prose.
  const violations = [];
  const intelligencePlatformTestsDir = join(INTELLIGENCE_PLATFORM_DIR, "__tests__");
  const evidenceRegistryTestsDir = join(EVIDENCE_REGISTRY_DIR, "__tests__");
  for (const file of listJsFiles(WORKER_SRC_DIR)) {
    if (isInside(file, EIG_DIR)) continue; // files inside this directory are exempt
    if (isInside(file, intelligencePlatformTestsDir)) continue; // see above
    if (isInside(file, evidenceRegistryTestsDir)) continue; // see above
    if (AUTHORIZED_CONSUMER_DIRS.some((dir) => isInside(file, dir))) continue; // Stage 16, see above
    const text = readFileSync(file, "utf-8");
    if (text.includes("enterprise-gateway")) {
      violations.push(relative(WORKER_SRC_DIR, file));
    }
  }
  assert.deepEqual(violations, [], `boundary violation(s) found: ${violations.join(", ")}`);
});

test("index.js does not import any enterprise-gateway file", () => {
  const indexJs = join(WORKER_SRC_DIR, "index.js");
  const text = readFileSync(indexJs, "utf-8");
  for (const newFile of [
    "gateway-context.js",
    "gateway-registry.js",
    "gateway-dispatcher.js",
    "gateway-lifecycle.js",
    "gateway-middleware.js",
    "gateway-metrics.js",
    "gateway-service.js",
  ]) {
    assert.equal(text.includes(newFile), false, `index.js must not reference ${newFile}`);
  }
});

test("enterprise-gateway/ production files never import a pNN-handlers.js file or index.js directly", () => {
  const eigTestsDir = join(EIG_DIR, "__tests__");
  for (const file of listJsFiles(EIG_DIR)) {
    if (isInside(file, eigTestsDir)) continue;
    const text = readFileSync(file, "utf-8");
    assert.equal(/from\s+["'].*p\d+-handlers\.js["']/.test(text), false, `${relative(WORKER_SRC_DIR, file)} must not import a pNN-handlers.js file`);
    assert.equal(/from\s+["'].*\/index\.js["']/.test(text), false, `${relative(WORKER_SRC_DIR, file)} must not import index.js`);
  }
});

test("enterprise-gateway/ production files only import pre-existing intelligence-platform/ files, and never import evidence-registry/ directly (the one-hop boundary this stage deliberately holds itself to)", () => {
  const intelligencePlatformFiles = new Set(readdirSync(INTELLIGENCE_PLATFORM_DIR).filter((f) => f.endsWith(".js")));
  const eigTestsDir = join(EIG_DIR, "__tests__");
  for (const file of listJsFiles(EIG_DIR)) {
    if (isInside(file, eigTestsDir)) continue; // test fixtures are the established, precedented exception -- see test-helpers.js
    const text = readFileSync(file, "utf-8");
    const intelligencePlatformImports = [...text.matchAll(/from\s+["']\.\.\/intelligence-platform\/([\w-]+\.js)["']/g)];
    for (const match of intelligencePlatformImports) {
      assert.ok(intelligencePlatformFiles.has(match[1]), `${match[1]} imported from intelligence-platform/ must be a pre-existing Stage 13 file`);
    }
    const evidenceRegistryImports = [...text.matchAll(/from\s+["']\.\.\/evidence-registry\//g)];
    assert.deepEqual(
      evidenceRegistryImports,
      [],
      `${relative(WORKER_SRC_DIR, file)} must not import evidence-registry/ directly -- reach it only via intelligence-platform/'s platform.evidenceService`
    );
  }
});

test("neither evidence-registry/ nor intelligence-platform/ PRODUCTION code references 'enterprise-gateway' (one-directional dependency, matching P-layer import direction)", () => {
  for (const dir of [EVIDENCE_REGISTRY_DIR, INTELLIGENCE_PLATFORM_DIR]) {
    const testsDir = join(dir, "__tests__");
    for (const file of listJsFiles(dir)) {
      if (isInside(file, testsDir)) continue;
      const text = readFileSync(file, "utf-8");
      assert.equal(text.includes("enterprise-gateway"), false, `${relative(WORKER_SRC_DIR, file)} must not reference enterprise-gateway/`);
    }
  }
});

test("intelligence-platform/__tests__/zero-blast-radius.test.js's authorized exceptions name exactly these four directories, nothing broader (the exempted test file itself stays honest)", () => {
  // Stage 16: intelligence-platform's own array grew a second entry (relationship-framework)
  // alongside its pre-existing enterprise-gateway entry -- see that file's own updated doc
  // comment for why. Stage 18 added a third (knowledge-platform). Stage 19 added a fourth
  // (product-platform). This assertion is updated in lockstep.
  const text = readFileSync(join(INTELLIGENCE_PLATFORM_DIR, "__tests__", "zero-blast-radius.test.js"), "utf-8");
  assert.match(
    text,
    /AUTHORIZED_CONSUMER_DIRS\s*=\s*\[\s*join\(WORKER_SRC_DIR,\s*"enterprise-gateway"\),\s*join\(WORKER_SRC_DIR,\s*"relationship-framework"\),\s*join\(WORKER_SRC_DIR,\s*"knowledge-platform"\),\s*join\(WORKER_SRC_DIR,\s*"product-platform"\),?\s*\]/
  );
});
