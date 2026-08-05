# ADR-0009: Source Reliability Ownership

**Date:** 2026-08-05
**Status:** Proposed — pending executive/architecture-review approval. Not Accepted.
**Deciders (proposed reviewers):** Platform Governance Lead, Chief Threat Intelligence
Architect, Intelligence Engineering (P18/P20 owner)
**Program:** Project TITAN, Stage 6
**Depends on:** ADR-0008 (Canonical Evidence Framework) — source reliability is a field within
the canonical Evidence record, not a freestanding concept.

---

## Context

`EVIDENCE_ENGINE_DISCOVERY.md` §3 documents the concrete case this ADR exists to resolve: the
same item can carry a P20 reliability grade of "B," an independently-computed P18 attribution
string of "D — Unknown," and a separate P25 trust percentage — three signals, three
computations, zero cross-checks. This is narrower than ADR-0007 (overall confidence) and
ADR-0008 (the evidence record as a whole): this ADR is specifically about **"how trustworthy
is this source"**, a single dimension that multiple systems currently compute independently.

---

## Problem Statement

**Which system's source-reliability grade is authoritative, what is its canonical scale, and
how do the other systems' differently-scaled grades map onto it without silently changing
what analysts and customers see?**

---

## Existing Implementations

| ID | System | Scale | Computation | Consumers |
|---|---|---|---|---|
| S1 | P20 `evidence_chain.reliability_code` | **A–F** (6 grades) | Upstream-populated during ingestion, not computed in `p20-handlers.js` itself | `computeP20QualityScore` (25/22/18/12/6/0 pts), `buildEvidenceChainBlock` |
| S2 | P18 `buildEvidenceAttribution()` | **A–E** (5 grades) | Computed at render time via substring match on `item.source`/`item.feed_source` against hardcoded strings (`"nvd"`, `"cisa"`, `"github"`, `"vendor"`, `"rss"`, `"api_ingest"`) | `p19-handlers.js:561,651,700` (SOC/executive narrative) |
| S3 | P25 `computeEnterpriseTrustScore()`, one dimension of twelve | **0–100** ("Source Authenticity") | Reads `item.source_quality` — a third, independent input field, not S1 or S2 | 13 files (see ADR-0007) |
| S4 (audit, not a scorer) | P37 `_confidenceAudit`, `_evidenceAudit` | N/A | Reads whatever `.confidence`/evidence fields already exist; does not compute source reliability itself | Fleet-level reporting only |
| S5 (audit, not a scorer) | P35 `handleP35Evidence` | N/A | Same category as S4 | Fleet-level reporting only |

S1 and S2 use **different letter ranges** (six grades vs. five) for what is nominally the same
concept — this mismatch has never been reconciled and is a real compatibility hazard for
whichever direction migration goes.

---

## Decision

**S1 (P20 `reliability_code`, A–F) is designated the canonical source-reliability grade.**

1. **S1 is canonical**, on the strength of using an external, industry-recognizable convention
   (NATO/Admiralty-System-style, not a CDB-invented scale — directly serves this platform's
   enterprise-trust positioning, since analysts and customers with intelligence backgrounds
   already know how to read it) and being the most narrowly-scoped-to-"source" of the three
   candidates (S3 measures the item, not the source).
2. **S2 (P18) is marked Deprecated — Pending Migration**, consistent with ADR-0008's decision.
   It migrates to a formatting/consumption role: read S1's `reliability_code` and translate it
   to P19's existing five-letter display format using the explicit mapping table below, rather
   than independently deriving a grade via substring matching.
3. **S3's "Source Authenticity" dimension is retained as-is inside P25's composite**, but its
   input is extended (per ADR-0007 Phase 1) to also read S1's `reliability_code` where present,
   rather than relying solely on `item.source_quality`. This is the concrete mechanism ADR-0007
   refers to as "A2 becomes an input dimension to A1."
4. **A–F → A–E mapping (S1 → S2's display format), proposed for review, not silently decided:**

   | S1 (A–F) | S2 display (A–E) | Rationale |
   |---|---|---|
   | A | A | Direct |
   | B | B | Direct |
   | C | C | Direct |
   | D | D | Direct |
   | E | E | Direct |
   | F | E | No S2 equivalent for "F" exists today; collapsing F into E is the conservative choice (does not invent a new bottom grade in a customer-facing display) but is flagged explicitly below as a compatibility risk requiring sign-off, not asserted as obviously correct. |

5. **S4, S5 are unaffected** — they are consumers/auditors of whatever field already exists,
   not scorers; once S1 becomes more consistently populated (per the coverage tracking in
   ADR-0008), their read-throughs improve automatically with no code change required in this
   ADR's scope.

---

## Rationale

- **External-convention alignment (S1) is a genuine enterprise-trust asset**, not just a
  technical tiebreaker — this directly serves the "Enterprise Trust Enforcement Layer" both
  repos' CLAUDE.md files mandate, since an Admiralty-style A–F code is independently
  verifiable/interpretable by customers with an intelligence background, unlike an ad hoc
  scale.
- **S2's substring-matching computation is the weakest of the three technically** — hardcoded
  string matches against six literal values is more brittle and more likely to silently
  misclassify a new source type than S1's upstream-populated field, and is the one most in need
  of replacement.
- **Choosing the narrowest-scoped candidate (S1) as canonical, rather than the broadest (S3),
  avoids scope creep** — S3 stays what it already is (a composite that *reads* source
  reliability among eleven other things), rather than being redefined as "the" source
  reliability grade, which would be a much larger behavior change for its 13 consumers.

---

## Alternatives Considered

1. **Make S3's "Source Authenticity" sub-score canonical, expose it standalone.** Rejected: it
   is currently computed from `item.source_quality`, a field with no documented provenance or
   population process (unlike S1's explicit A–F convention), and extracting one dimension of a
   12-dimension composite as a new standalone public signal is a larger, riskier surface change
   than reusing S1 as-is.
2. **Preserve both S1 and S2's independent scales permanently, document the mismatch instead of
   resolving it.** Rejected: this is the status quo, and it is the status quo this ADR exists to
   change — `EVIDENCE_ENGINE_DISCOVERY.md` §3 names it as a live, concrete defect, not a stable
   equilibrium.
3. **Map F to a new "E-minus" or six-grade extension of S2's scale instead of collapsing to E.**
   Considered — technically cleaner (no information loss) — but rejected as the ADR's default
   recommendation because it changes P19's narrative rendering contract (a new possible grade
   value) rather than reusing the existing five values, a larger compatibility footprint for a
   marginal precision gain. Listed as the primary open question for reviewer sign-off rather
   than foreclosed.

---

## Migration Strategy

See `TITAN_MIGRATION_ROADMAP.md` Phase 1, 4 (shared with ADR-0008 — this is the same migration,
viewed from the source-reliability angle specifically).

1. Ship ADR-0008 Phase 1 (Evidence schema extension) first — no dependency the other direction.
2. Implement the A–F → A–E mapping as a small, isolated, named function (e.g.,
   `mapReliabilityCodeToDisplayGrade()`), unit-testable in isolation before P18 is touched.
3. Migrate P18's `buildEvidenceAttribution()` to call the mapping function against S1's value
   when `evidence_chain.reliability_code` is present, falling back to today's substring-match
   behavior when it is absent (which, per the current ~0% Evidence Chain coverage cited in
   ADR-0007, is most live items at cutover time — meaning **Phase 4 initially changes almost
   nothing visible**, and its visible impact grows only as Evidence Chain coverage grows, giving
   this migration a naturally gradual rollout without a feature flag being strictly required,
   though one is still recommended per `TITAN_MIGRATION_ROADMAP.md`'s standard practice).
4. Only after the fallback path is confirmed working does S2's substring-matching code get
   marked `@deprecated` (not removed) per the Deprecation Instead of Deletion policy.

---

## Compatibility Impact

- **P19's narrative rendering contract is preserved** — same five-letter output shape.
  Individual displayed grades may change for items where S1 is populated and disagrees with
  what S2's substring match would have produced; this is a data-accuracy improvement, not a
  contract break, but is a real, user-visible change and is called out explicitly rather than
  minimized.
- **No API route or response schema changes.**
- **S1's own consumers (`computeP20QualityScore`, `buildEvidenceChainBlock`) are unaffected** —
  S1 is not modified, only read from a new call site.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A–F→A–E mapping's F→E collapse understates severity for the worst-graded sources in customer-facing narrative | Medium | Medium (could read as reputational softening of a real weakness) | Explicit reviewer sign-off requested on this specific point (see Approval); alternative (six-grade S2 display) documented as a live option, not foreclosed |
| Fallback logic (S1-present vs. S1-absent) becomes permanent because Evidence Chain coverage never improves | Medium | Low–Medium (dual-path code persists indefinitely) | Same coverage-tracking mechanism as ADR-0008's rollback risk; owned jointly |
| P19 narrative output changes trigger customer questions about why a source's grade changed | Low–Medium | Low | Recommend a changelog note in customer-facing release notes at Phase 4 cutover, coordinated with commercial/CS teams — outside engineering's authority to decide unilaterally, flagged here for that reason |

---

## Rollback Strategy

The mapping function is pure and isolated — reverting P18's call site to its prior
substring-match implementation (retained in version control, not deleted) is a single-commit
rollback with no data migration to undo, since S1 itself is never written to by this change.

---

## Future Considerations

- If Evidence Chain (S1) coverage grows significantly, revisit whether the F→E collapse should
  become a genuine six-grade S2 display instead, once real usage data shows how often F-graded
  sources actually occur.
- S4/S5's independent "has evidence" heuristics are not source-reliability scorers and are not
  in this ADR's scope — tracked instead under ADR-0008's Future Considerations and the tech
  debt register.

---

## Approval

**Proposed**, not Accepted. Required sign-offs before Migration Strategy begins, with the
F→E mapping choice specifically flagged for explicit reviewer attention rather than
rubber-stamped:

- [ ] Platform Governance Lead
- [ ] Chief Threat Intelligence Architect / P-layer stack owner (P18, P20 owner)
- [ ] Explicit sign-off on the A–F→A–E mapping table (or the six-grade alternative)

No code implementing this decision exists yet.
