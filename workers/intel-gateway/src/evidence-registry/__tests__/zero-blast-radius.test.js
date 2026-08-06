/**
 * Zero-blast-radius test  -  mirrors scripts/titan_architecture_governance_check.py's
 * check_evidence_registry_scaffolding_boundary() as an explicit, independently-runnable Node
 * test, so this property is verifiable from either toolchain (Python CI check or `node --test`)
 * without depending on the other. Confirms Stage 10's expansion of this directory has not
 * changed the one property Stage 8's authorization actually depends on: nothing outside this
 * directory references it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCAFFOLD_DIR = dirname(HERE); // .../evidence-registry
const WORKER_SRC_DIR = dirname(SCAFFOLD_DIR); // .../src

/**
 * Stage 13 (Project TITAN): intelligence-platform/ is the first explicitly-authorized consumer
 * of this directory -- its own brief requires composing EvidenceService/EvidenceQueryEngine/
 * EvidenceProvenanceEngine/RelationshipResolutionService (see
 * TITAN_STAGE13_SERVICE_ARCHITECTURE.md). This does not weaken what this test actually
 * protects: evidence-registry/ still must not be reachable from index.js or any pNN-handlers.js
 * file -- see the "index.js does not import..." test below, and
 * intelligence-platform/__tests__/zero-blast-radius.test.js's own independent boundary tests,
 * which confirm both that index.js does not import intelligence-platform/ and that
 * intelligence-platform/ never imports a pNN-handlers.js file or index.js itself. Exempting
 * this one named, documented directory -- rather than relaxing the check generally -- keeps
 * this test able to catch any OTHER, unauthorized reference.
 */
const AUTHORIZED_CONSUMER_DIRS = [join(WORKER_SRC_DIR, "intelligence-platform")];

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

test("nothing outside evidence-registry/ references 'evidence-registry' (Stage 8 boundary, unchanged by Stage 10)", () => {
  const violations = [];
  for (const file of listJsFiles(WORKER_SRC_DIR)) {
    if (file.startsWith(SCAFFOLD_DIR)) continue; // files inside the scaffolding are exempt
    if (AUTHORIZED_CONSUMER_DIRS.some((dir) => file.startsWith(dir))) continue; // Stage 13, see above
    const text = readFileSync(file, "utf-8");
    if (text.includes("evidence-registry")) {
      violations.push(relative(WORKER_SRC_DIR, file));
    }
  }
  assert.deepEqual(violations, [], `boundary violation(s) found: ${violations.join(", ")}`);
});

test("index.js does not import any Stage 10 Canonical Evidence Core file", () => {
  const indexJs = join(WORKER_SRC_DIR, "index.js");
  const text = readFileSync(indexJs, "utf-8");
  for (const newFile of [
    "entity.js",
    "validation.js",
    "interfaces.js",
    "serialization.js",
    "migration-adapters.js",
    "schema.js",
    "feature-flags.js",
  ]) {
    assert.equal(text.includes(newFile), false, `index.js must not reference ${newFile}`);
  }
});

test("SCAFFOLDING_ENABLED remains hardcoded false in source (not read from an env var that could be flipped without a code review)", () => {
  const text = readFileSync(join(SCAFFOLD_DIR, "feature-flags.js"), "utf-8");
  assert.match(text, /SCAFFOLDING_ENABLED:\s*false/);
});
