#!/usr/bin/env python3
"""
scripts/entitlement_resource_drift_gate.py
SENTINEL APEX v185.4 -- Entitlement Resource Drift Gate

MISSION: SENTINEL APEX v185.0 Phase 8's own requirement: "Any newly
introduced paid route without an entitlement resource classification must
fail CI." This is the smallest, safest version of that guard that can ship
without a full canonical-entitlement migration (tracked separately, see
docs/ENTITLEMENT_RESOURCE_INVENTORY_V185.md).

WHAT THIS CATCHES (real, demonstrated risk):
revenue-enforcement.js's enforceTierGate() has a `default: return { allowed:
true }` fail-open branch (by design, so an unrecognized resource name never
hard-blocks a real customer). That means if wrangler.toml's
ENTITLEMENT_ENFORCEMENT_RESOURCES ever names a resource that is NOT a case
in enforceTierGate()'s switch -- a typo, a rename that missed one side, a
copy-paste error -- the engine silently falls through to "allowed: true" for
that resource. Since resolveEntitlement() only takes the engine's decision
when isEntitlementEnforced() is true for that exact resource, this is a
silent fail-OPEN on a resource an operator explicitly believed was being
enforced. That is the highest-severity class of entitlement bug there is
(a customer entitlement gate that looks configured but does nothing), so
this gate hard-fails CI on it.

WHAT THIS DOES NOT (YET) CATCH: a genuinely new paid route added to
index.js/enterprise-endpoints.js/etc. with an ad-hoc tier check but never
wired to resolveEntitlement() at all. Detecting that reliably (vs. e.g. a
free-tier-gated route, or an internal-only route) requires a canonical list
of what "paid route" means structurally, which this repo does not yet have
in a machine-checkable form -- doing this precisely is future work, tracked
in docs/ENTITLEMENT_RESOURCE_INVENTORY_V185.md's migration backlog rather
than papered over with a guard that would either miss real cases or false-
positive on legitimate free/internal routes. This gate exists now, narrowly
scoped to what it can check with certainty, rather than not existing at all.

Exit code: 1 (hard fail) on drift. 0 otherwise.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRANGLER_TOML = REPO_ROOT / "workers" / "intel-gateway" / "wrangler.toml"
REVENUE_ENFORCEMENT_JS = REPO_ROOT / "workers" / "intel-gateway" / "src" / "revenue-enforcement.js"
# Every file that is allowed to call resolveEntitlement() -- v185.9 Wave A
# Phase 16 extended this gate to also check that a resource actually
# *enforced* via wrangler.toml has a live resolveEntitlement() callsite
# somewhere in the codebase. Without this, a resource could be removed from
# every route (refactor, accidental deletion) while remaining in
# ENTITLEMENT_ENFORCEMENT_RESOURCES -- the flag would still read as "on" to
# an operator, but nothing would actually be gated by it. Two files today;
# add a new one here if a future P-layer starts calling resolveEntitlement()
# directly.
RESOLVE_ENTITLEMENT_CALLSITE_FILES = [
    REPO_ROOT / "workers" / "intel-gateway" / "src" / "index.js",
    REPO_ROOT / "workers" / "intel-gateway" / "src" / "enterprise-endpoints.js",
]

CASE_RE = re.compile(r'case\s+"([a-zA-Z0-9_]+)"\s*:')
ENFORCEMENT_RESOURCES_RE = re.compile(r'ENTITLEMENT_ENFORCEMENT_RESOURCES\s*=\s*"([^"]*)"')
RESOLVE_ENTITLEMENT_CALL_RE = re.compile(r'resolveEntitlement\([^,]+,\s*[^,]+,\s*"([a-zA-Z0-9_]+)"')


NEXT_FN_RE = re.compile(r'^(?:export\s+)?function\s', re.MULTILINE)


def _defined_resources() -> set:
    text = REVENUE_ENFORCEMENT_JS.read_text(encoding="utf-8")
    # Only scan inside enforceTierGate() -- stop at the next top-level
    # function declaration after it (export or not -- revenue-enforcement.js
    # mixes both, e.g. the very next function after enforceTierGate() is
    # `export function buildUpgradeTrigger`, which a bare "\nfunction "
    # search would skip right past) so an unrelated function's case labels
    # can't silently feed into the "defined" set. That would only ever make
    # this gate more permissive than intended, the opposite of its purpose.
    start = text.find("function enforceTierGate")
    if start == -1:
        print("[entitlement-drift-gate] FATAL: enforceTierGate() not found in revenue-enforcement.js")
        sys.exit(1)
    m = NEXT_FN_RE.search(text, start + 1)
    body = text[start: m.start() if m else len(text)]
    return set(CASE_RE.findall(body))


def _enforced_resources(section_label: str, section_text: str) -> set:
    m = ENFORCEMENT_RESOURCES_RE.search(section_text)
    if not m:
        return set()
    return {r.strip() for r in m.group(1).split(",") if r.strip()}


def _live_callsite_resources() -> set:
    """Resources with at least one resolveEntitlement(ctx, env, "resource", ...)
    call site across every file allowed to call it."""
    found = set()
    for path in RESOLVE_ENTITLEMENT_CALLSITE_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        found.update(RESOLVE_ENTITLEMENT_CALL_RE.findall(text))
    return found


def _wrangler_sections() -> dict:
    """Split wrangler.toml into [vars] and [env.production.vars] blocks."""
    text = WRANGLER_TOML.read_text(encoding="utf-8")
    sections = {}
    pattern = re.compile(r'^\[([^\]]+)\]\s*$', re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        name = m.group(1)
        if name not in ("vars", "env.production.vars"):
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[m.end():end]
    return sections


def main() -> int:
    if not REVENUE_ENFORCEMENT_JS.exists() or not WRANGLER_TOML.exists():
        print("[entitlement-drift-gate] Required files not found -- skipping (non-fatal)")
        return 0

    defined = _defined_resources()
    print(f"[entitlement-drift-gate] {len(defined)} resource(s) defined in enforceTierGate(): "
          f"{', '.join(sorted(defined))}")

    live_callsites = _live_callsite_resources()
    print(f"[entitlement-drift-gate] {len(live_callsites)} resource(s) have a live "
          f"resolveEntitlement() callsite: {', '.join(sorted(live_callsites))}")

    sections = _wrangler_sections()
    undefined_failures = []
    no_callsite_failures = []
    for section_name, section_text in sections.items():
        enforced = _enforced_resources(section_name, section_text)
        undefined = enforced - defined
        if undefined:
            undefined_failures.append((section_name, sorted(undefined)))
        # v185.9 Wave A Phase 16: a resource can be defined in
        # enforceTierGate() (so the drift check above passes) yet have every
        # call site removed elsewhere -- ENTITLEMENT_ENFORCEMENT_RESOURCES
        # would then be "enforcing" a rule no route ever asks the engine
        # about, which is a silent no-op, not protection.
        no_callsite = enforced - live_callsites
        if no_callsite:
            no_callsite_failures.append((section_name, sorted(no_callsite)))
        print(f"[entitlement-drift-gate] [{section_name}] "
              f"ENTITLEMENT_ENFORCEMENT_RESOURCES = {sorted(enforced) or '(empty)'}")

    if undefined_failures:
        print("\n[entitlement-drift-gate] FAIL -- resource(s) enforced in wrangler.toml but "
              "UNDEFINED in enforceTierGate() (silent fail-open via the default case):")
        for section_name, undefined in undefined_failures:
            print(f"  [{section_name}]: {', '.join(undefined)}")

    if no_callsite_failures:
        print("\n[entitlement-drift-gate] FAIL -- resource(s) enforced in wrangler.toml but "
              "with NO live resolveEntitlement() callsite in index.js/enterprise-endpoints.js "
              "(the enforcement flag is a no-op -- no route ever asks the engine about this "
              "resource):")
        for section_name, no_callsite in no_callsite_failures:
            print(f"  [{section_name}]: {', '.join(no_callsite)}")

    if undefined_failures or no_callsite_failures:
        return 1

    print("[entitlement-drift-gate] PASS -- no drift between wrangler.toml enforcement list, "
          "enforceTierGate()'s defined resources, and live resolveEntitlement() call sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
