/**
 * Zero-blast-radius test for Stage 21's commercial-catalog/ directory, mirroring
 * product-platform/__tests__/zero-blast-radius.test.js's (Stage 19) exact pattern. Confirms this
 * stage's brand-new directory has not been wired into any production route, and that its
 * PRODUCTION code (excluding __tests__) never imports evidence-registry/ or intelligence-platform/
 * directly -- only enterprise-gateway/, knowledge-platform/, product-platform/, and
 * p39-handlers.js, per TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md Sec 3.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CC_DIR = dirname(HERE); // .../commercial-catalog
const WORKER_SRC_DIR = dirname(CC_DIR); // .../src
const CC_TESTS_DIR = join(CC_DIR, "__tests__");

const CC_PRODUCTION_FILES = Object.freeze([
  "feature-flags.js",
  "catalog.js",
  "commercial-adapters.js",
  "service-contracts.js",
  "commercial-metrics.js",
  "commercial-readiness.js",
  "platform.js",
]);

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
  assert.equal(isInside(join(CC_DIR, "platform.js"), CC_DIR), true);
  assert.equal(isInside(CC_DIR, CC_DIR), true);
  assert.equal(
    isInside(join(WORKER_SRC_DIR, "commercial-catalog-experimental", "x.js"), CC_DIR),
    false,
    "a sibling directory whose name extends CC_DIR's name must NOT be treated as inside it"
  );
});

test("index.js does not import any commercial-catalog/ file", () => {
  const indexJs = join(WORKER_SRC_DIR, "index.js");
  const text = readFileSync(indexJs, "utf-8");
  for (const file of CC_PRODUCTION_FILES) {
    assert.equal(text.includes(file), false, `index.js must not reference ${file}`);
  }
  assert.equal(text.includes("commercial-catalog"), false, "index.js must not reference commercial-catalog/ at all");
});

test("commercial-catalog/ production files never import a pNN-handlers.js file by relative path or index.js directly", () => {
  for (const file of listJsFiles(CC_DIR)) {
    if (isInside(file, CC_TESTS_DIR)) continue;
    const text = readFileSync(file, "utf-8");
    // p39-handlers.js is a deliberate, authorized exception (P39's own file header explicitly
    // authorizes "Integrate with Gateway composition layer only" -- see audit doc Sec 2.4). Every
    // OTHER pNN-handlers.js file remains forbidden.
    const importSpecifiers = [...text.matchAll(/from\s+["'](.+?)["']/g)].map((m) => m[1]);
    for (const specifier of importSpecifiers) {
      if (/\/p39-handlers\.js$/.test(specifier)) continue;
      assert.equal(/p\d+-handlers\.js$/.test(specifier), false, `${relative(WORKER_SRC_DIR, file)} must not import a pNN-handlers.js file other than p39-handlers.js (specifier: ${specifier})`);
      assert.equal(/\/index\.js$/.test(specifier), false, `${relative(WORKER_SRC_DIR, file)} must not import index.js (specifier: ${specifier})`);
    }
  }
});

test("commercial-catalog/ production files never import evidence-registry/ or intelligence-platform/ directly", () => {
  for (const file of listJsFiles(CC_DIR)) {
    if (isInside(file, CC_TESTS_DIR)) continue; // __tests__ is the established exception (test-helpers.js constructs fixtures directly)
    const text = readFileSync(file, "utf-8");
    const realImports = [...text.matchAll(/^import\s+.*?from\s+["'](.+?)["'];?\s*$/gm)].map((m) => m[1]);
    for (const specifier of realImports) {
      assert.equal(specifier.includes("evidence-registry"), false, `${relative(WORKER_SRC_DIR, file)} must not import evidence-registry/ directly (specifier: ${specifier})`);
      assert.equal(specifier.includes("intelligence-platform"), false, `${relative(WORKER_SRC_DIR, file)} must not import intelligence-platform/ directly (specifier: ${specifier})`);
    }
  }
});

test("commercial-catalog/ production files only import files that already exist in enterprise-gateway/, knowledge-platform/, and product-platform/ -- it does not modify any of them", () => {
  const enterpriseGatewayFiles = new Set(readdirSync(join(WORKER_SRC_DIR, "enterprise-gateway")).filter((f) => f.endsWith(".js")));
  const knowledgePlatformFiles = new Set(readdirSync(join(WORKER_SRC_DIR, "knowledge-platform")).filter((f) => f.endsWith(".js")));
  const productPlatformFiles = new Set(readdirSync(join(WORKER_SRC_DIR, "product-platform")).filter((f) => f.endsWith(".js")));
  for (const file of listJsFiles(CC_DIR)) {
    if (isInside(file, CC_TESTS_DIR)) continue;
    const text = readFileSync(file, "utf-8");
    for (const [, dirName, fileName] of text.matchAll(/from\s+["'].*?\/(enterprise-gateway|knowledge-platform|product-platform)\/([\w.-]+\.js)["']/g)) {
      const table = { "enterprise-gateway": enterpriseGatewayFiles, "knowledge-platform": knowledgePlatformFiles, "product-platform": productPlatformFiles }[dirName];
      assert.ok(table.has(fileName), `${relative(WORKER_SRC_DIR, file)} imports ${dirName}/${fileName}, which does not exist -- commercial-catalog/ must only import pre-existing files`);
    }
  }
});

test("gateway-service.js (enterprise-gateway/) does not import commercial-catalog/ -- wiring uses registerCapability()/annotateCapability() from a composition script, not a gateway-service.js change", () => {
  const gatewayServiceJs = join(WORKER_SRC_DIR, "enterprise-gateway", "gateway-service.js");
  const text = readFileSync(gatewayServiceJs, "utf-8");
  assert.equal(text.includes("commercial-catalog"), false);
});

test("knowledge-platform.js and product-platform.js do not import commercial-catalog/", () => {
  for (const [dir, file] of [
    ["knowledge-platform", "knowledge-platform.js"],
    ["product-platform", "product-platform.js"],
  ]) {
    const text = readFileSync(join(WORKER_SRC_DIR, dir, file), "utf-8");
    assert.equal(text.includes("commercial-catalog"), false, `${dir}/${file} must not reference commercial-catalog/`);
  }
});
