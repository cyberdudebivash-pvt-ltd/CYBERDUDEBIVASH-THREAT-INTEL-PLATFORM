"""
Regression tests for issue #288's deliberately-scoped foundation: atomic
Gumroad key-provisioning idempotency via a Durable Object.

Owner decision (AskUserQuestion, 2026-09-01): implement and fully unit-test
the decision logic and Durable Object class, but do NOT wire either into
wrangler.toml or handleWebhookGumroad yet. A Durable Object migration
applies unconditionally the next time `wrangler deploy` runs -- deploy-
worker.yml only fires on push to main, never validating a PR first -- and
there is no prior Durable Object anywhere in this codebase to pattern-match
wrangler.toml syntax against, nor any way to confirm the Cloudflare account
supports them from this session. A wrong migration wouldn't just leave a
feature inert; it would fail every future deploy of this live payment
gateway until someone fixes or reverts it.

This test file exists specifically to guard that scope limit: if someone
later wires GumroadProvisioningLock in without also completing the
wrangler.toml side (documented in gumroad-provisioning-lock.js's header
comment), these tests will fail loudly rather than let a half-wired state
ship silently.

Run with: pytest tests/test_gumroad_provisioning_lock_foundation.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_MODULE = REPO_ROOT / "workers" / "intel-gateway" / "src" / "gumroad-provisioning-lock.js"
LOCK_TEST = REPO_ROOT / "workers" / "intel-gateway" / "src" / "__tests__" / "gumroad-provisioning-lock.test.js"
GATEWAY_SRC = REPO_ROOT / "workers" / "intel-gateway" / "src" / "index.js"
WRANGLER_TOML = REPO_ROOT / "workers" / "intel-gateway" / "wrangler.toml"


def _node_available() -> bool:
    try:
        return subprocess.run(["node", "--version"], capture_output=True, timeout=5).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


needs_node = pytest.mark.skipif(not _node_available(), reason="node not available in this environment")


def test_lock_module_exists_with_expected_exports():
    assert LOCK_MODULE.exists()
    text = LOCK_MODULE.read_text(encoding="utf-8")
    assert "export function decideProvisioningClaim" in text
    assert "export class GumroadProvisioningLock" in text


@needs_node
def test_lock_module_node_unit_tests_pass():
    assert LOCK_TEST.exists()
    result = subprocess.run(
        ["node", "--test", str(LOCK_TEST)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"gumroad-provisioning-lock.test.js failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_lock_is_not_yet_wired_into_index_js():
    """Regression guard for the deliberate scope limit: index.js must not
    reference this class or its binding until the wrangler.toml side (below)
    is also done. If this starts failing because someone added the
    wiring, verify test_wrangler_toml_has_durable_object_binding also
    passes before treating that as progress rather than a half-wired state."""
    text = GATEWAY_SRC.read_text(encoding="utf-8")
    assert "GumroadProvisioningLock" not in text
    assert "GUMROAD_PROVISIONING_LOCK" not in text
    assert "gumroad-provisioning-lock" not in text


def test_wrangler_toml_does_not_yet_have_the_durable_object_binding():
    """Companion guard: wrangler.toml must not declare the binding/migration
    until someone has confirmed Durable Objects are available for this
    Cloudflare account and reviewed the exact migration syntax -- see
    gumroad-provisioning-lock.js's header comment for the activation steps."""
    text = WRANGLER_TOML.read_text(encoding="utf-8")
    assert "durable_objects" not in text
    assert "GumroadProvisioningLock" not in text
