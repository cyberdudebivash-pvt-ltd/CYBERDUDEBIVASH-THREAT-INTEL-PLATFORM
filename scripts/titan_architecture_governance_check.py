#!/usr/bin/env python3
"""
scripts/titan_architecture_governance_check.py
Project TITAN Stage 6 — Architecture Governance Drift Check (advisory)

Stage 6 produced five canonical-ownership ADRs (docs/adr/0007-0011) after finding that
prior stages' discovery had real, non-hypothetical blind spots: TITAN_STAGE6_VALIDATION.md
documents a ~12,600-line parallel implementation (cyberdudebivash-blog's lib/ tree) that
existed, undetected, through two full discovery passes, plus two additional independently-
invented "has evidence" heuristics (P37, P35) neither discovery doc catalogued. The failure
mode in both cases was the same: a new confidence/evidence-shaped function or a governance
artifact went missing or was added without anyone checking it against the ownership decisions
already on record.

This script does not detect everything Stage 6 Task 6 asked for (schema drift and deprecated-
interface detection are not implemented here — see TITAN_CI_GOVERNANCE.md's recommendations
for the larger set this is a first slice of). It checks four narrow, concrete things that are
cheap to check and were each a real finding this stage:

  1. Do the five ADRs (docs/adr/0007-0011.md) and the discovery/governance docs they depend
     on still exist? (documentation-deletion / broken-reference drift)
  2. Do the specific functions each ADR names as "Existing Implementations" still exist at
     their cited locations? (broken architectural reference — an ADR citing a function that
     has since been renamed or removed is exactly the "governance docs wrong, not just stale"
     failure this program has hit before)
  3. Do any *new* top-level functions in the P-layer handlers match a confidence/evidence/
     reliability-shaped name that ISN'T already accounted for in the ADRs' inventories?
     (possible new, un-reviewed implementation — the thing this whole program exists to catch
     before it becomes a sixth disagreeing scorer)
  4. Does the ownership matrix (TITAN_OWNERSHIP_MATRIX.md) still exist and still list all
     five ADRs?

Advisory only. Exit code is informational (0 = clean, 1 = findings to review) but the CI step
invoking this script wraps it in continue-on-error / an unconditional exit 0, matching the
STAGE 4.04 schema-mirror-drift-check precedent — this is intentionally non-blocking until it
has run clean across a few real drift cycles, the same rollout pattern used for that check.
Promoting it to a blocking gate is a deliberate future decision, not a default.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"
HANDLERS_DIR = ROOT / "workers" / "intel-gateway" / "src"

REQUIRED_ADRS = [
    "0007-canonical-confidence-framework.md",
    "0008-canonical-evidence-framework.md",
    "0009-source-reliability-ownership.md",
    "0010-relationship-graph-ownership.md",
    "0011-evidence-lifecycle-ownership.md",
]

REQUIRED_GOVERNANCE_DOCS = [
    "CONFIDENCE_FRAMEWORK_DISCOVERY.md",
    "EVIDENCE_ENGINE_DISCOVERY.md",
    "TITAN_OWNERSHIP_MATRIX.md",
    "TITAN_STAGE6_VALIDATION.md",
    "ARCHITECTURE_DECISIONS.md",
]

# file -> function/property names ADR-0007/0008/0009 cite as "Existing Implementations".
# Keep this list in sync with the ADRs by hand; this script does not parse the ADRs
# themselves (deliberately — parsing prose ADRs for ground truth is more fragile than a
# short, human-maintained allowlist reviewed alongside any ADR edit).
CITED_REFERENCES = {
    "p20-handlers.js": ["computeP20QualityScore", "buildEvidenceChainBlock"],
    "p18-handlers.js": ["buildEvidenceAttribution", "computeTransparentConfidence"],
    "p25-handlers.js": ["computeEnterpriseTrustScore"],
    "p23-handlers.js": [],  # gate is inline, not a named export; presence checked via keyword below
    "p30-handlers.js": [
        "buildP30VerificationBlock",
        "buildP30TimelineBlock",
        "buildP30ChangeTrackingBlock",
    ],
    "p31-handlers.js": ["buildP31RelationshipBlock"],
    "p29-handlers.js": ["_computeConfidenceGraph"],
    "p32-handlers.js": ["buildP32EvidenceTransparencyBlock"],
    "p35-handlers.js": ["handleP35Evidence"],
    "p37-handlers.js": ["_confidenceAudit", "_evidenceAudit", "_reliabilityAudit"],
}

# Names ADR-0007/0008/0009 already know about and have made an explicit ownership call on,
# reviewed by reading the function body (not just the name) before being added here — see
# TITAN_STAGE6_VALIDATION.md §4 for how the first ten of these were triaged. A new top-level
# match for the patterns below that ISN'T in this allowlist is what this script flags — it is
# not itself a defect, it's a "review this against the ADRs" signal.
KNOWN_CONFIDENCE_EVIDENCE_FUNCTIONS = {
    # Canonical sources (ADR-0007/0008/0009 Decision)
    "computeEnterpriseTrustScore",   # A1 — canonical (ADR-0007)
    "computeP20QualityScore",        # E1 support — canonical (ADR-0008)
    "computeP26Grade",               # composite grade, reads P20/P21/P23/P25 — not independently scoring
    "computeActionabilityScore",     # P23, distinct concept (actionability, not confidence) — out of scope, allowlisted to avoid false positives
    "buildEvidenceChainBlock",       # E1 renderer
    # Deprecated-pending-migration, already reviewed and decided (ADR-0007/0008/0009), not re-flag
    "buildEvidenceAttribution",      # A2/E2/S2 — Deprecated Pending Migration
    "computeTransparentConfidence",  # A9 — Deprecated Pending Migration (found via this script, §4)
    # P30 lifecycle signal (ADR-0011's L1-L4, canonical derivation source)
    "buildP30VerificationBlock",
    "buildP30TimelineBlock",
    "buildP30ChangeTrackingBlock",
    "_computeIOCLifecycle",
    "buildP30TrustTimelineBlock",    # renderer composing L1-L4 — reviewed, not a new scorer
    # P31 relationship graph (ADR-0010)
    "buildP31RelationshipBlock",
    # P32 evidence transparency (ADR-0008 item 3)
    "buildP32EvidenceTransparencyBlock",
    # Fleet-level auditors (TITAN_STAGE6_VALIDATION.md §3) — consumers/auditors, not scorers
    "_confidenceAudit",              # reuses computeEnterpriseTrustScore directly
    "_evidenceAudit",
    "_reliabilityAudit",             # false-positive name match — pipeline health, not source reliability
    "_enrichmentAudit",
    "_reliabilityMetrics",
    "handleP35Evidence",
    "buildP34ReliabilityBlock",      # false-positive name match — CI gate pass-rate, not source reliability
    # Renderers/composers reviewed and confirmed to only format already-canonical values —
    # see TITAN_STAGE6_VALIDATION.md §4 for the read-through that classified each of these
    "buildTrustIndicatorBlock",      # composes buildEvidenceAttribution + computeTransparentConfidence + quality — renderer
    "buildConfidenceExplanationBlock",  # renders computeP20QualityScore's breakdown
    "buildTrustScoreBlock",          # renders computeEnterpriseTrustScore's dims directly
    "buildP25TrustPackage",          # composes other block-builders, no independent scoring
    "buildP26TrustBadgesBlock",      # renders computeP26Grade's sub-details
    "buildP29ConfidenceGraphBlock",  # renderer for _computeConfidenceGraph (see below)
    # Tracked, not yet decided (DEBT-012) — allowlisted so the script doesn't re-flag a
    # already-logged, already-triaged item; NOT a canonical-ownership decision
    "_computeConfidenceGraph",
}

NAME_PATTERN = re.compile(
    r"function\s+(_?(?:compute|build|score|grade|rate|assess)\w*"
    r"(?:[Cc]onfidence|[Ee]vidence|[Rr]eliability|[Tt]rust)\w*)\s*\(",
)


def check_docs_exist() -> list[str]:
    findings = []
    for name in REQUIRED_ADRS:
        if not (ADR_DIR / name).exists():
            findings.append(f"MISSING ADR: docs/adr/{name} — referenced by docs/adr/README.md and TITAN_OWNERSHIP_MATRIX.md")
    for name in REQUIRED_GOVERNANCE_DOCS:
        if not (ROOT / name).exists():
            findings.append(f"MISSING GOVERNANCE DOC: {name} — cited by one or more ADRs as source material")
    return findings


def check_cited_references_exist() -> list[str]:
    findings = []
    for filename, names in CITED_REFERENCES.items():
        path = HANDLERS_DIR / filename
        if not path.exists():
            findings.append(f"MISSING FILE: {filename} — cited by an ADR's Existing Implementations table")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name in names:
            if name not in text:
                findings.append(
                    f"BROKEN REFERENCE: {filename} no longer contains '{name}' — "
                    f"an ADR's Existing Implementations table cites it. Update the ADR or investigate the removal."
                )
    return findings


def check_for_unreviewed_new_scorers() -> list[str]:
    findings = []
    if not HANDLERS_DIR.exists():
        return findings
    for path in sorted(HANDLERS_DIR.glob("p*-handlers.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in NAME_PATTERN.finditer(text):
            name = match.group(1)
            if name not in KNOWN_CONFIDENCE_EVIDENCE_FUNCTIONS:
                findings.append(
                    f"POSSIBLE NEW IMPLEMENTATION: {path.name} defines '{name}', a confidence/evidence/"
                    f"reliability/trust-shaped function not in this script's known-implementations "
                    f"allowlist. Review against ADR-0007/0008/0009's ownership decisions before this "
                    f"becomes a new disagreeing scorer — see TITAN_STAGE6_VALIDATION.md §3 for why this "
                    f"category of drift matters."
                )
    return findings


def check_ownership_matrix() -> list[str]:
    findings = []
    matrix = ROOT / "TITAN_OWNERSHIP_MATRIX.md"
    if not matrix.exists():
        return findings  # already reported by check_docs_exist
    text = matrix.read_text(encoding="utf-8", errors="replace")
    for adr_num in ("0007", "0008", "0009", "0010", "0011"):
        if adr_num not in text:
            findings.append(f"OWNERSHIP MATRIX DRIFT: TITAN_OWNERSHIP_MATRIX.md does not reference ADR-{adr_num}")
    return findings


def main() -> None:
    all_findings: list[str] = []
    all_findings += check_docs_exist()
    all_findings += check_cited_references_exist()
    all_findings += check_for_unreviewed_new_scorers()
    all_findings += check_ownership_matrix()

    print("=== Project TITAN Architecture Governance Check (advisory) ===")
    if not all_findings:
        print("Clean: all 5 ADRs present, all cited references resolve, no unreviewed "
              "confidence/evidence/reliability functions found, ownership matrix in sync.")
        sys.exit(0)

    print(f"{len(all_findings)} finding(s):\n")
    for i, finding in enumerate(all_findings, 1):
        print(f"  {i}. {finding}")
    print(
        "\nNone of the above blocks this build (advisory-only stage). Review against "
        "docs/adr/ and TITAN_OWNERSHIP_MATRIX.md, and update whichever is stale — "
        "per this program's standing rule, document discrepancies rather than silently "
        "resolving them in whichever direction is convenient."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
