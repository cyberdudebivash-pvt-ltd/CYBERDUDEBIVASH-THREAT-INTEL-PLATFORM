/**
 * Zero-blast-radius test for Stage 13's intelligence-platform/ directory, mirroring
 * evidence-registry/__tests__/zero-blast-radius.test.js's exact pattern (Stage 8-12 precedent).
 * Confirms this stage's brand-new directory has not been wired into any production route, and
 * confirms it did not have to modify evidence-registry/ (a Stage 8-12 file set) to compose it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const EIPS_DIR = dirname(HERE); // .../intelligence-platform
const WORKER_SRC_DIR = dirname(EIPS_DIR); // .../src
const EVIDENCE_REGISTRY_DIR = join(WORKER_SRC_DIR, "evidence-registry");

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

test("nothing outside intelligence-platform/ references 'intelligence-platform'", () => {
  // __tests__ directories are exempt from this sweep: this test's own counterpart in
  // evidence-registry/__tests__/zero-blast-radius.test.js legitimately documents this
  // directory BY NAME in its own authorized-exception comment (the mirror image of what this
  // file does for evidence-registry below) -- that is boundary documentation, not production
  // coupling. Production reachability is what actually matters and is covered precisely by the
  // two tests below (index.js, and pNN-handlers.js/index.js imports from inside this directory).
  const violations = [];
  for (const file of listJsFiles(WORKER_SRC_DIR)) {
    if (file.startsWith(EIPS_DIR)) continue; // files inside this directory are exempt
    if (file.includes(`${WORKER_SRC_DIR}/evidence-registry/__tests__/`)) continue; // see above
    const text = readFileSync(file, "utf-8");
    if (text.includes("intelligence-platform")) {
      violations.push(relative(WORKER_SRC_DIR, file));
    }
  }
  assert.deepEqual(violations, [], `boundary violation(s) found: ${violations.join(", ")}`);
});

test("index.js does not import any intelligence-platform/ file", () => {
  const indexJs = join(WORKER_SRC_DIR, "index.js");
  const text = readFileSync(indexJs, "utf-8");
  for (const newFile of [
    "intelligence-service.js",
    "query-service.js",
    "correlation-engine.js",
    "platform.js",
    "service-contracts.js",
  ]) {
    assert.equal(text.includes(newFile), false, `index.js must not reference ${newFile}`);
  }
});

test("intelligence-platform/ never imports a pNN-handlers.js file or index.js directly (same boundary rule evidence-registry/README.md documents for itself)", () => {
  for (const file of listJsFiles(EIPS_DIR)) {
    if (file.includes(`${EIPS_DIR}/__tests__`)) continue;
    const text = readFileSync(file, "utf-8");
    assert.equal(/from\s+["'].*p\d+-handlers\.js["']/.test(text), false, `${relative(WORKER_SRC_DIR, file)} must not import a pNN-handlers.js file`);
    assert.equal(/from\s+["'].*\/index\.js["']/.test(text), false, `${relative(WORKER_SRC_DIR, file)} must not import index.js`);
  }
});

test("intelligence-platform/ only imports evidence-registry/ files that already exist -- it does not modify evidence-registry/ itself", () => {
  const evidenceRegistryFiles = new Set(readdirSync(EVIDENCE_REGISTRY_DIR).filter((f) => f.endsWith(".js")));
  for (const file of listJsFiles(EIPS_DIR)) {
    if (file.includes(`${EIPS_DIR}/__tests__`)) continue;
    const text = readFileSync(file, "utf-8");
    const importMatches = [...text.matchAll(/from\s+["']\.\.\/evidence-registry\/([\w-]+\.js)["']/g)];
    for (const match of importMatches) {
      assert.ok(evidenceRegistryFiles.has(match[1]), `${match[1]} imported from evidence-registry/ must be a pre-existing Stage 8-12 file`);
    }
  }
});

test("no evidence-registry/ PRODUCTION file references intelligence-platform/ (one-directional dependency, matching P-layer import direction)", () => {
  // evidence-registry/__tests__/zero-blast-radius.test.js is exempt: it legitimately documents
  // this directory BY NAME in its own authorized-exception comment (see that file). What this
  // test actually protects -- evidence-registry's PRODUCTION code never importing "upward" into
  // its one authorized consumer -- is unaffected by a test file's own boundary documentation.
  for (const file of listJsFiles(EVIDENCE_REGISTRY_DIR)) {
    if (file.includes(`${EVIDENCE_REGISTRY_DIR}/__tests__/`)) continue;
    const text = readFileSync(file, "utf-8");
    assert.equal(text.includes("intelligence-platform"), false, `${relative(WORKER_SRC_DIR, file)} must not reference intelligence-platform/`);
  }
});

test("evidence-registry/__tests__/zero-blast-radius.test.js's authorized exception names exactly this directory, nothing broader (the one exempted test file itself stays honest)", () => {
  const text = readFileSync(join(EVIDENCE_REGISTRY_DIR, "__tests__", "zero-blast-radius.test.js"), "utf-8");
  assert.match(text, /AUTHORIZED_CONSUMER_DIRS\s*=\s*\[join\(WORKER_SRC_DIR,\s*"intelligence-platform"\)\]/);
});
