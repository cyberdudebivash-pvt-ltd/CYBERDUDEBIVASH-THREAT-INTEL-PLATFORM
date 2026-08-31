#!/usr/bin/env node
// platform/frontend/scripts/generate-intel-data.mjs
//
// Regenerates src/lib/intel-data/cve-live.generated.json from the real,
// live Sentinel APEX API (the same domain/routes the rest of this
// platform serves from -- workers/intel-gateway/src/index.js) before
// `next build` runs. cve-data.ts imports this file and shapes it into
// CVE_RECORDS -- previously that array was ~28 entries of hand-written
// sample data with clearly-synthetic metrics (every HIGH-severity item
// shared the identical [T1190, T1059] MITRE tactic pair regardless of
// the actual CVE).
//
// Fields sourced live:
//   id/severity/cvss_score/published_at/kev_present -- GET /api/v1/cve/live
//   advisory_count -- how many times this CVE ID appears across the real
//     feed manifest's iocs_by_type.cve (GET /api/feed), fetched once and
//     reused for every CVE rather than one request per CVE
//   epss_score -- matched against GET /api/v1/intel/epss's top_cves list
//     when present; left null otherwise (that list only covers the top
//     10 by risk, so most CVEs legitimately have no EPSS match here)
//
// Fields NOT available from any live route and left honestly empty
// rather than invented: mitre_tactics (NVD data has no ATT&CK mapping;
// the old sample data's identical tactic pairs on every item were
// themselves decorative, not real per-CVE analysis). risk_score is
// explicitly derived (cvss_score * 10, documented as such below), not an
// independent CDB model output -- there is no live per-CVE risk-scoring
// route to source it from.
//
// Fails soft: a network error here must never break `next build` for a
// developer working offline -- falls back to whatever generated file
// (if any) already exists, or an empty list.

import { writeFile, readFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_PATH = join(__dirname, "..", "src", "lib", "intel-data", "cve-live.generated.json");
const API_BASE = "https://intel.cyberdudebivash.com";
const CVE_LIMIT = 60;

async function fetchJson(path) {
  const res = await fetch(`${API_BASE}${path}`, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

async function buildAdvisoryCountMap() {
  try {
    const feed = await fetchJson("/api/feed");
    const counts = new Map();
    for (const item of feed.items || []) {
      const cves = (item.iocs_by_type && item.iocs_by_type.cve) || [];
      for (const cveId of cves) {
        counts.set(cveId, (counts.get(cveId) || 0) + 1);
      }
    }
    return counts;
  } catch (err) {
    console.warn(`[generate-intel-data] advisory-count fetch failed, defaulting to 0: ${err.message}`);
    return new Map();
  }
}

async function buildEpssMap() {
  try {
    const epss = await fetchJson("/api/v1/intel/epss");
    const map = new Map();
    for (const c of epss.top_cves || []) {
      if (c.cve_id && c.epss_score != null) map.set(c.cve_id, c.epss_score);
    }
    return map;
  } catch (err) {
    console.warn(`[generate-intel-data] EPSS fetch failed, leaving epss_score null: ${err.message}`);
    return new Map();
  }
}

async function main() {
  let cveRecords = [];
  try {
    const [live, advisoryCounts, epssMap] = await Promise.all([
      fetchJson(`/api/v1/cve/live?limit=${CVE_LIMIT}`),
      buildAdvisoryCountMap(),
      buildEpssMap(),
    ]);

    cveRecords = (live.cves || []).map((c) => ({
      id: c.id,
      severity: c.severity || "MEDIUM",
      cvss_score: c.cvss_score != null ? c.cvss_score : null,
      // Derived, not an independent CDB risk model -- CVSS (0-10) scaled
      // to the 0-100 range the page displays. Documented so a future
      // reader doesn't mistake this for a separately-computed score.
      risk_score: c.cvss_score != null ? Math.round(c.cvss_score * 10) : 0,
      epss_score: epssMap.has(c.id) ? epssMap.get(c.id) : null,
      kev_present: !!c.kev,
      published_at: (c.published || "").slice(0, 10) || null,
      source_url: (c.references && c.references[0]) || `https://nvd.nist.gov/vuln/detail/${c.id}`,
      advisory_count: advisoryCounts.get(c.id) || 0,
      mitre_tactics: [], // honestly empty -- no live source maps CVEs to ATT&CK techniques
      description: c.description || "",
    }));

    console.log(`[generate-intel-data] fetched ${cveRecords.length} real CVE records from ${API_BASE}`);
  } catch (err) {
    console.warn(`[generate-intel-data] live fetch failed (${err.message}) -- keeping existing generated data if any`);
    try {
      const existing = JSON.parse(await readFile(OUT_PATH, "utf-8"));
      cveRecords = existing;
      console.log(`[generate-intel-data] reusing ${cveRecords.length} previously-generated records`);
    } catch {
      console.warn("[generate-intel-data] no previously-generated data either -- writing an empty list");
    }
  }

  await mkdir(dirname(OUT_PATH), { recursive: true });
  await writeFile(OUT_PATH, JSON.stringify(cveRecords, null, 2) + "\n", "utf-8");
  console.log(`[generate-intel-data] wrote ${cveRecords.length} records to ${OUT_PATH}`);
}

main();
