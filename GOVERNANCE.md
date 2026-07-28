# Repository Governance

**Last updated:** 2026-07-28. This document describes how the repository's canonical production documentation is maintained and validated. It does not cover security-incident response, which is tracked separately and confidentially.

## Validation Purpose

This repository's architecture is documented in a small set of canonical files (below). Left unchecked, documentation like this drifts from reality: a new deploy pipeline gets added and never recorded, a file gets renamed, a component gets removed but its registry entry doesn't. The purpose of the validation described here is prevention — catching that drift automatically, rather than relying on every future contributor remembering to update every document by hand.

## Repository Source of Truth

In order of precedence:

1. [`production_manifest.yaml`](production_manifest.yaml) — machine-readable definition of the production surface.
2. [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json) — per-component classification, confidence, and provenance.
3. [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md), [`REPOSITORY_STATUS.md`](REPOSITORY_STATUS.md), [`LEGACY_COMPONENTS.md`](LEGACY_COMPONENTS.md), [`TRANSFORMATION_STATUS.md`](TRANSFORMATION_STATUS.md), [`ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md) — narrative documentation, each cross-linked to the two files above.

Where any other document in this repository (a README, a comment, an older audit report) disagrees with the five files above, these five take precedence. If you find a real disagreement, fix the canonical file, not the other way around — unless the canonical file is what's actually wrong, in which case fix that instead. Either way, keep them in agreement.

## Validation Tooling

Two scripts, both read-only:

- `scripts/validate_canonical_docs.py` — enforces consistency: every path/workflow/Worker referenced in the manifest and registry must exist, no duplicate registry entries, every internal markdown link must resolve. Exits non-zero on any failure.
- `scripts/detect_repository_drift.py` — reports, never enforces: scans for production-shaped things (Worker directories, `wrangler deploy`-running workflows, Cloudflare bindings, deployment-asset files) not yet reflected in the canonical documents. Always exits 0 — a finding here is a prompt for review, not a build failure, and this script never assigns a classification on its own.

Both run in `.github/workflows/repository-integrity-check.yml`, a workflow deliberately isolated from every deployment pipeline: it does not build, test, or deploy anything, and it is not a required status check. A failure there means documentation has drifted, not that production is broken.

## Update Responsibilities

Whoever makes a change that affects the production surface — adding a Worker, a deploy pipeline, a KV/R2/D1 binding, or retiring one of the legacy/experimental items already catalogued — is responsible for updating `production_manifest.yaml` and/or `COMPONENT_REGISTRY.json` in the same change. This isn't a separate follow-up task; it's part of the change itself.

## Documentation Maintenance Rules

- New production component → add it to `production_manifest.yaml` and give it a `COMPONENT_REGISTRY.json` entry in the same commit.
- Component reclassified (e.g. an experimental system gets formally adopted, or a legacy system gets confirmed dead) → update its `COMPONENT_REGISTRY.json` entry's `classification`, `confidence`, and `last_verified_phase`, and update the relevant narrative document (`LEGACY_COMPONENTS.md` or `ARCHITECTURE_DECISIONS.md`).
- Never leave a `COMPONENT_REGISTRY.json` `path` field as a description or a glob pattern — it must be a real, checkable path. `validate_canonical_docs.py` will not catch this class of error consistently, and `detect_repository_drift.py` depends on registry paths being literal.
- Run `python3 scripts/validate_canonical_docs.py` locally before committing a change to any canonical file.

## Classification Update Process

Matches the standard this program has used throughout: **evidence before classification.** A component only moves to `production` when there's a confirmed deployment path (a workflow that actually runs `wrangler deploy` or equivalent, not just a Dockerfile that could theoretically be built). A component only moves to `archived` once it's actually been removed and confirmed to have zero remaining references. Confidence should read `low` honestly when the evidence is thin — a wrong `high` confidence is more dangerous than an honest `low` one.

## Review Expectations

- `repository-integrity-check.yml` runs on every push touching a canonical file, `workers/**/wrangler.toml`, or `.github/workflows/**`, on manual dispatch, and on a weekly schedule as a safety net for drift introduced through paths the trigger doesn't cover.
- A drift-detection finding does not need to be resolved immediately — it needs to be looked at and either incorporated into the canonical documentation or explicitly deferred with a reason, the same discipline this program has applied to every other open item it has produced.
