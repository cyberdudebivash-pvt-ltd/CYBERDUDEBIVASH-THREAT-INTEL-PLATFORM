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

test("nothing outside enterprise-gateway/ references 'enterprise-gateway' -- zero authorized consumers in Phase 1", () => {
  // __tests__ directories are exempt from this sweep: both intelligence-platform's AND
  // evidence-registry's own zero-blast-radius tests legitimately document this directory BY
  // NAME in their own authorized-exception comments/AUTHORIZED_CONSUMER_DIRS arrays (the mirror
  // image of what this file does for them below) -- that is boundary documentation, not
  // production coupling. Production reachability is what actually matters and is covered
  // precisely by the two tests below (index.js, and pNN-handlers.js/index.js imports from
  // inside this directory).
  const violations = [];
  const intelligencePlatformTestsDir = join(INTELLIGENCE_PLATFORM_DIR, "__tests__");
  const evidenceRegistryTestsDir = join(EVIDENCE_REGISTRY_DIR, "__tests__");
  for (const file of listJsFiles(WORKER_SRC_DIR)) {
    if (isInside(file, EIG_DIR)) continue; // files inside this directory are exempt
    if (isInside(file, intelligencePlatformTestsDir)) continue; // see above
    if (isInside(file, evidenceRegistryTestsDir)) continue; // see above
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

test("intelligence-platform/__tests__/zero-blast-radius.test.js's authorized exception names exactly this directory, nothing broader (the one exempted test file itself stays honest)", () => {
  const text = readFileSync(join(INTELLIGENCE_PLATFORM_DIR, "__tests__", "zero-blast-radius.test.js"), "utf-8");
  assert.match(text, /AUTHORIZED_CONSUMER_DIRS\s*=\s*\[join\(WORKER_SRC_DIR,\s*"enterprise-gateway"\)\]/);
});
