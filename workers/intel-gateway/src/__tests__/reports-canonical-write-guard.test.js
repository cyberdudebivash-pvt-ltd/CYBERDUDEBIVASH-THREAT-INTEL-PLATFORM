/**
 * RX-PUB-A0 regression guard: ordinary customer/crawler traffic must never
 * be able to write into the canonical reports/*.html R2 keyspace.
 *
 * index.js previously had two request-handling branches (the legacy-slug
 * fallback and the canonical-URL fallback) that, on an R2 miss for an
 * otherwise-resolvable, publication-gate-approved item, rendered a report
 * with a Worker-local JS implementation (generateIntelReport -- a distinct,
 * independent rendering path from the authoritative Python generator,
 * scripts/generate_intel_reports.py, with no engine marker and no
 * certification tie-in) and then persisted it directly into the same R2 key
 * the certified pipeline owns via `env.REPORTS_R2.put(...)`, triggered by
 * nothing more than an ordinary GET request. See
 * docs/REPORT_WRITER_OWNERSHIP_MATRIX.md ("Writer C") and
 * docs/RX_PUB_A0_INCIDENT_ROOT_CAUSE.md for the full incident this closes.
 *
 * index.js is a single ~4000+ line request handler, not a set of
 * independently importable functions -- unlike publication-gate.js /
 * certification-registry.js (which this same __tests__/ directory unit-
 * tests by direct import), there is no clean seam to import just this
 * branch. A static source-invariant check is the honest, low-risk way to
 * lock this in: it directly enforces "this call must never exist in this
 * file again" without constructing a fake Request/env/R2 binding for a
 * handler this large, and mirrors the same-shape guard already used for
 * the equivalent Python-side invariant
 * (tests/test_safe_git_commit_artifact_recovery.py::TestReportsRegistryInGeneratedArtifactGuard).
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const INDEX_JS_PATH = join(HERE, "..", "index.js");

test("index.js never writes into the canonical R2 reports keyspace from a live request handler", () => {
  const source = readFileSync(INDEX_JS_PATH, "utf-8");
  const matches = source.match(/REPORTS_R2\s*\.\s*put\s*\(/g) || [];
  assert.equal(
    matches.length, 0,
    `Found ${matches.length} call(s) to REPORTS_R2.put(...) in index.js. Ordinary customer/crawler ` +
    `traffic must never write into the canonical reports/*.html keyspace -- only ` +
    `scripts/generate_intel_reports.py may. If a legitimate new write path is being added, it must ` +
    `not be reachable from an unauthenticated GET request; update this guard's justification, not ` +
    `just the count.`
  );
});

test("the Worker-local fallback renderer still exists and still serves a live response (customer-facing behavior preserved)", () => {
  const source = readFileSync(INDEX_JS_PATH, "utf-8");
  assert.match(
    source, /function generateIntelReport\(/,
    "generateIntelReport must still exist -- this fix removes its write-through to R2, not the " +
    "fallback rendering itself. An approved item missing its canonical artifact must still get a " +
    "live-rendered response, not a hard 404."
  );
  const noStoreCount = (source.match(/"Cache-Control":\s*"no-store"/g) || []).length;
  assert.ok(
    noStoreCount >= 2,
    "the two synthesis-fallback response paths should mark their response no-store (it is generated " +
    "on the fly and never persisted, so it must not be cached as if it were the canonical artifact)."
  );
});
