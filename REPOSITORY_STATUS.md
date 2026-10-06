# Repository Status

**Last updated:** 2026-07-28 · **Maintained as of:** Enterprise Production Transformation Program (EPTP), Phase 8 Batch 2

## Purpose

CYBERDUDEBIVASH® SENTINEL APEX is a threat intelligence platform: automated collection, enrichment, and publication of threat advisories, IOCs, and MITRE-mapped detections, served through a commercial API with tiered access (FREE/PRO/ENTERPRISE/MSSP).

## Current Production Runtime

Cloudflare Workers. See [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md) for the full architecture and [`production_manifest.yaml`](production_manifest.yaml) for the machine-readable definition.

## Current Deployment Model

`.github/workflows/deploy-worker.yml` deploys `workers/intel-gateway` to Cloudflare on push/dispatch. This is the repository's only confirmed live continuous-deployment path.

## Current Transformation Status

The repository is mid-way through a multi-phase rationalization program:

- Legacy and dead-code identification: complete.
- Business-decision reconciliation (retired infrastructure vs. active systems): complete.
- First controlled cleanup batch (dead code removal, tooling gap closed): complete.
- Canonical production documentation (this file and its siblings): in progress, this phase.

See [`TRANSFORMATION_STATUS.md`](TRANSFORMATION_STATUS.md) for the itemized breakdown.

## Current Modernization Phase

**Production Canonicalization** — establishing a single, documented source of truth for what is and is not part of the production system, ahead of further consolidation work.

## Current Production Version

`184.0` (Cloudflare gateway `GATEWAY_VERSION`, `wrangler.toml`).

## Repository Health

The live production system (Cloudflare Workers, its KV/R2/D1 storage, and the report-generation pipeline) is healthy and internally consistent. The surrounding repository carries substantial accumulated complexity: multiple historical architecture attempts that were never deployed to production, version-generation sprawl in several directories, and a large volume of point-in-time historical documentation. This is a repository-organization characteristic, not a statement about the production system's own reliability. See [`LEGACY_COMPONENTS.md`](LEGACY_COMPONENTS.md) and [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json) for the classification detail.
