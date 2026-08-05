# Project TITAN — Contract Governance Specification (Task 6)

**Status:** Design specification only. Per this stage's explicit instruction ("No production
changes yet"), nothing in this document is implemented — unlike Stage 6's Task 6, which shipped
one small advisory script, this document contains no code and wires nothing into CI. It
specifies what a future implementation should do, sequenced as Stage 8+ candidate work
(`TITAN_STAGE8_PLAN.md`).

---

## Scope

Contract governance covers seven capabilities, per Task 6's explicit list. For each: current
state (does anything like this exist today?), gap, and design sketch.

### 1. Schema Validation

**Current state:** P38's `SCHEMA_REGISTRY` (`scripts/p38_shared_validators.py`) is the strongest
existing precedent — a canonical, versioned field registry with a documented mirror-drift check
(`scripts/p38_schema_mirror_check.py`, STAGE 4.04) already catching real drift on its first run.
No equivalent exists for any other route family's response shape, and nothing validates
request/response bodies against a schema at request time (runtime validation) anywhere in
either repository.

**Gap:** ~150 intel-platform routes and ~25 blog routes have no machine-checkable response
schema beyond what P38 already covers (which is item-field-level, not per-route response-shape
level).

**Design sketch:** Extend P38's `SCHEMA_REGISTRY` pattern to a per-route response-shape
registry (not a new validation engine — the same JSON-Schema-adjacent approach P38 already
uses, applied to route outputs instead of item fields). Recommended starting scope: the routes
named Canonical in `TITAN_INTERFACE_REGISTRY.md`, not all ~175 routes at once.

### 2. Version Compatibility

**Current state:** No automated check exists anywhere that a route's response still matches
its documented `v1` contract.

**Gap:** ADR-0012's Compatibility Rules table (field removal, type change, etc.) is currently
enforced by human review only.

**Design sketch:** A snapshot-diff check — capture a route's response shape (field names,
types, presence) on a known-good sample, store it, and diff future responses against the
snapshot in CI, flagging (not blocking, initially) any Compatibility-Rules violation. Modeled
directly on `scripts/p38_schema_mirror_check.py`'s diff-and-report pattern.

### 3. Breaking Change Detection

**Current state:** None, beyond the general regression suite (21/21), which tests specific
named behaviors, not exhaustive response-shape stability.

**Gap:** A genuinely breaking change (field removed, type changed) to an uncovered route would
not be caught by anything today short of a human noticing.

**Design sketch:** Subsumed by #2 above — version-compatibility snapshot-diffing *is* breaking-
change detection when the diff is interpreted against ADR-0012's Compatibility Rules table
(some diffs are compatible per that table — e.g. a new field — and shouldn't flag; others
should).

### 4. API Drift Detection

**Current state:** `scripts/titan_architecture_governance_check.py` (Stage 6, STAGE 5.9.4)
already does a narrow version of this for confidence/evidence/reliability-named *functions*,
not routes. `reports/public_api_sanitization_audit.json` (existing, pre-TITAN infrastructure,
`scripts/public_api_sanitizer.py`) already does a real, running form of drift detection for a
different concern — PII/internal-field leakage in public responses, currently PASS.

**Gap:** No check confirms the *documented* route list (index.js's header comment, this
document's own interface registry) matches the *actual* route list the router recognizes.

**Design sketch:** Parse index.js's header-comment route list and its live `if (path === ...)`
/`path.startsWith(...)` conditions; diff the two. This is cheap (both are in the same file,
static analysis, no runtime dependency) and directly protects against the exact kind of
documentation drift this stage found in `enterprise-endpoints.js` (comment: "previously
unreachable — now wired"), just running continuously instead of being caught by a one-off audit.

### 5. Documentation Drift

**Current state:** Stage 6's `titan_architecture_governance_check.py` covers ADR/governance-doc
existence and cross-referencing. Nothing covers whether `TITAN_INTERFACE_REGISTRY.md` (this
stage) stays in sync with the actual route table.

**Gap:** This stage's own interface registry could go stale the same way Stage 6's discovery
docs initially had blind spots.

**Design sketch:** Extend Stage 6's existing advisory script (do not create a second, separate
script — Reuse Before Build) with a new check function that counts routes matched by #4's
route-list parser and compares the count against `TITAN_INTERFACE_REGISTRY.md`'s row count per
surface, flagging a material mismatch (not an exact-match requirement, since the registry is
intentionally grouped at route-family grain, not one row per exact path).

### 6. Interface Completeness

**Current state:** No check verifies every route in the Interface Registry has an assigned
Owner, Status, and Category (per Tasks 3–5's required columns).

**Gap:** A future route could be added to the registry with an incomplete row and nothing would
catch it.

**Design sketch:** A simple registry-linter — parse `TITAN_INTERFACE_REGISTRY.md`'s tables,
confirm every row has non-empty Owner/Status/Category columns. Cheapest of the seven checks to
build; recommended as the first one implemented if Stage 8 picks this up, since it validates
this stage's own deliverable stays accurate over time.

### 7. CI Integration

**Current state:** STAGE 5.9.4 (Stage 6) is the only existing hook point for this class of
check — advisory, non-blocking, `if: always()`, at the true end of `sentinel-blogger.yml`.

**Design sketch:** All six checks above (#1–#6), when implemented, should extend
`scripts/titan_architecture_governance_check.py` as new check functions within the same script
and the same STAGE 5.9.4 step — not new scripts, not new CI stages — per Reuse Before Build and
to avoid the CI-stage-numbering confusion already found and logged as DEBT-011. Each new check
function follows the same pattern as the existing four: read-only, returns a list of findings,
contributes to the same advisory (non-blocking) exit behavior until individually proven stable
enough to consider promoting to blocking — the same maturation path Stage 6 already established
for STAGE 4.04 and STAGE 5.9.4.

---

## What this specification deliberately does not do

- Does not implement any of the seven checks — Task 6 explicitly says no production changes
  this stage.
- Does not modify `titan_architecture_governance_check.py` — extension is recommended for
  Stage 8, not performed now.
- Does not propose a new CI stage number — explicitly reuses STAGE 5.9.4's existing slot for
  all future contract-governance checks, avoiding repeating DEBT-011's numbering-confusion
  pattern.
- Does not specify exact schemas for #1 (Schema Validation) — that requires ADR-0008's Evidence
  schema and ADR-0012's approval first; this document specifies the *mechanism*, not the
  *content* of what gets validated.

---

## Priority ordering for Stage 8+ implementation

1. **#6 Interface Completeness** — cheapest, validates this stage's own deliverable, no
   dependency on anything else.
2. **#4 API Drift Detection** — cheap (static analysis, same file), high value (already found
   one real historical case — the enterprise-endpoints.js wiring fix — that this check would
   have caught earlier had it existed then).
3. **#5 Documentation Drift** — depends on #4's route-list parser as a building block.
4. **#1 Schema Validation** — higher effort, depends on ADR-0008 shipping a real schema to
   validate against for the Evidence-specific case, though the mechanism could start with P38's
   existing `SCHEMA_REGISTRY` first.
5. **#2 Version Compatibility / #3 Breaking Change Detection** — highest effort (snapshot
   infrastructure, sample capture), most valuable long-term, correctly sequenced last.
