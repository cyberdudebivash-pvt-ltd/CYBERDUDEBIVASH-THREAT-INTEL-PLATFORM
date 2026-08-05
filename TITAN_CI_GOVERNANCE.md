# Project TITAN — CI Governance (Task 6)

**Status:** One check implemented and shipped this stage (advisory, non-blocking). The
remaining checks below are recommendations, not implemented — Stage 6's own instruction was to
extend CI validation, not to build every category of detector in one pass, and this task's
ENGINEERING RULES prohibit speculative work beyond what's justified. What's shipped is
justified by a concrete need this stage hit directly (Task 1's discrepancies); the rest is
scoped and estimated for whoever picks this up next.

---

## What's implemented: `scripts/titan_architecture_governance_check.py`

**STAGE 5.9.4** in `sentinel-blogger.yml` (`.github/workflows/sentinel-blogger.yml`), advisory
only (`continue-on-error: true`, unconditional `exit 0` in the CI step), `if: always()` so it
still reports when an upstream hard gate has already failed the job — matching the STAGE 4.04
schema-mirror-drift-check rollout pattern exactly (ship non-blocking, prove stability across
real cycles, consider promoting to blocking later).

It checks:

1. **Duplicate ownership / multiple confidence implementations (partial)** — scans
   `workers/intel-gateway/src/p*-handlers.js` for new top-level functions matching a
   confidence/evidence/reliability/trust-shaped name pattern, flags any not already in a
   reviewed allowlist. This is the check that found A9 (`computeTransparentConfidence`) and
   `_computeConfidenceGraph` live, on its first run, before this document was even finished —
   direct evidence the check works, not a hypothetical capability.
2. **Multiple evidence implementations** — same mechanism, same pattern (the regex covers both
   `confidence` and `evidence` name fragments).
3. **Broken architectural references** — verifies every function/property an ADR's Existing
   Implementations table cites by name still exists in its cited file.
4. **Documentation drift (partial)** — verifies the five ADRs and the governance docs they
   depend on (discovery docs, ownership matrix, `ARCHITECTURE_DECISIONS.md`) still exist as
   files, and that the ownership matrix still references all five ADR numbers.

It does not (see "Not implemented" below): validate schema drift, detect deprecated interfaces
still being called, or check the blog repository (a single repo's CI cannot cheaply check a
sibling repo's files without an extra checkout step, which was judged too large an addition for
this stage — see Alternatives below).

**Maintenance model:** the allowlist (`KNOWN_CONFIDENCE_EVIDENCE_FUNCTIONS`) and cited-reference
map (`CITED_REFERENCES`) are hand-maintained Python dicts, deliberately not auto-derived from
parsing the ADRs' prose. Anyone adding a new confidence/evidence-shaped function should expect
this check to flag it — that's it working as intended, not a false positive to silence by
reflex. Triage per the same standard this stage used (read the function body, decide if it's a
genuine new scorer needing an ADR addendum or a reviewed consumer/renderer, add to the
allowlist only after that read, with a comment explaining which).

---

## Recommended, not implemented

### Duplicate ownership detection beyond confidence/evidence

The current regex is scoped to confidence/evidence/reliability/trust-named functions because
that's this stage's subject matter. Extending it to other capability classes (e.g., severity
scoring, actor attribution) is straightforward — same mechanism, a new named pattern and
allowlist — but should wait until a concrete need arises, per this program's own "don't build
speculative capability" rule. Estimated effort: 1–2 hours per additional capability class, once
that class has its own ownership decision to protect.

### Schema drift detection

Stage 6 Phase 8 (source material) asks for validation of "evidence serialization" and similar.
This repository already has a working example of exactly this check for a different pair of
sources: `scripts/p38_schema_mirror_check.py` (STAGE 4.04), which diffs
`p38_shared_validators.py`'s `SCHEMA_REGISTRY` against its hand-mirrored JS copy. Once ADR-0008's
`evidence_uuid`/`content_hash`/`schema_version` fields ship (Migration Roadmap Phase 3), the
same pattern should be applied: a canonical Python-side (or JSON Schema) definition of the
Evidence record shape, diffed against every place that shape is read or written. Not built now
because the shape doesn't exist yet — building a drift checker for a schema that isn't decided
would be checking against a moving target. Estimated effort: 1 day, modeled directly on the
existing P38 script.

### Deprecated-interface-still-called detection

Once ADR-0007/0008/0009's `@deprecated`-marked functions (A4, A9, P18's `buildEvidenceAttribution`)
are actually marked in code (Migration Roadmap Phase 2/4, not yet shipped), a CI check that
greps for calls to any `@deprecated`-tagged export outside its own migration-approved call site
would close the loop on the Deprecation Instead of Deletion policy actually being honored, not
just documented. Estimated effort: half a day — the pattern-matching is simpler than the
schema-drift case, mostly a grep for `@deprecated` JSDoc tags plus a call-site search. Sequenced
behind Migration Roadmap Phase 2 actually shipping the annotations.

### Cross-repository checks (blog repo's `lib/` drift specifically)

DEBT-001/002 (the `lib/` disposition and its false CI-enforcement claim) would ideally be
checked continuously rather than caught once, manually, this stage. Doing so from
intel-platform's CI would require either (a) a cross-repo checkout step (adds a new external
dependency and secret/token surface to a CI job that currently has none — a real security-
surface increase, not a free addition) or (b) the check living in the blog repo's own CI
instead. Recommended: **(b)**, once DEBT-001 is resolved and there's a decided state to check
against — checking "does `lib/` still have zero consumers" continuously only has a clear
pass/fail meaning after someone decides whether that's the intended state (shelved) or a
problem to fix (integrate). Not implemented in either repo this stage.

### Documentation drift — broader form

The current check only verifies files exist and are cross-referenced by number. A stronger
version would diff each ADR's "Existing Implementations" table against a fresh grep of the
codebase, flagging when a table's row *count* looks stale (e.g., a new letter-grade computation
appears that isn't A2/S2/A9). This is a generalization of the "unreviewed new scorer" check
already implemented, not a new category — deferred because the current name-pattern approach
already covers the concrete cases found this stage, and a fully generalized version risks a much
higher false-positive rate without a clear net benefit yet demonstrated. Revisit if the current
check's false-positive rate (tracked informally via how often the allowlist needs updating)
turns out to be low enough to justify broadening.

---

## Alternatives considered

1. **Make the new check a blocking gate immediately.** Rejected: this stage's own
   `_computeConfidenceGraph`/`computeTransparentConfidence` findings prove the check surfaces
   real, previously-unknown items on a codebase that is otherwise CI-green — a blocking gate on
   day one would have failed every subsequent unrelated PR until those items were fully
   triaged, which is disproportionate to what this check is for (surfacing drift, not stopping
   unrelated work). STAGE 4.04's own precedent (ship non-blocking, prove stability, consider
   promoting later) is followed deliberately, not by default.
2. **Parse the ADRs' Markdown directly instead of a hand-maintained allowlist.** Rejected for
   now: more code, more fragility (a prose edit that doesn't change meaning could still break a
   parser), for a benefit (avoiding allowlist drift) that a simple review discipline handles
   adequately at this stage's scale (five ADRs, ~30 named functions). Revisit if the allowlist
   grows large enough that hand maintenance becomes the bottleneck.
3. **Skip implementing anything this stage, only write recommendations.** Rejected: the
   task's own Task 6 asks to "extend CI validation," and a recommendations-only document
   without a working example would have been a weaker deliverable than one concrete,
   demonstrated-useful check plus honestly-scoped recommendations for the rest.

---

## Where "architectural violations should fail CI where appropriate" stands today

Per this task's Task 6 language, violations "should fail CI where appropriate" — this stage's
judgment is that *none* of the four checks implemented are appropriate to fail CI on yet,
because none have run clean across multiple real cycles (the standard this repo's own STAGE
4.04 precedent sets). Promoting STAGE 5.9.4 from advisory to blocking is a future decision,
recommended once it has run without a false positive for a reasonable number of pipeline
cycles — a specific number is not fixed here since that itself would be a speculative
commitment; whoever owns CI should make that call with real data once it exists.
