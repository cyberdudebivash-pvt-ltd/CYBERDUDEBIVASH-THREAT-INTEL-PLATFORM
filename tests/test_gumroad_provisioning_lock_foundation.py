"""
Regression tests for issue #288: atomic Gumroad key-provisioning idempotency
via a Durable Object.

History: this file originally guarded a deliberate scope limit -- an owner
decision (AskUserQuestion, 2026-09-01) to ship the decision logic and
Durable Object class fully unit-tested, but NOT wire either into
wrangler.toml or handleWebhookGumroad until a human confirmed Durable
Objects are enabled for the Cloudflare account (a wrong migration would
fail every future deploy of this live payment gateway, and there was no
prior Durable Object anywhere in this codebase to pattern-match
wrangler.toml syntax against).

That confirmation happened (AskUserQuestion, 2026-09-01, same day): Durable
Objects are enabled for the account. This file now guards the wired state
instead -- the class is exported from index.js, bound in wrangler.toml
(both the top-level and [env.production] sections, matching every other
binding's duplication pattern there), and called from
handleWebhookGumroad() before the existing KV-based idempotency check.

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


def test_gumroad_provisioning_lock_is_reexported_from_index_js():
    text = GATEWAY_SRC.read_text(encoding="utf-8")
    assert "export { GumroadProvisioningLock } from './gumroad-provisioning-lock.js';" in text


def test_handle_webhook_gumroad_calls_the_lock_before_the_kv_idempotency_check():
    text = GATEWAY_SRC.read_text(encoding="utf-8")
    do_call_idx = text.find("env.GUMROAD_PROVISIONING_LOCK.idFromName(sale_id)")
    kv_check_idx = text.find('const idempKey = `gumroad_sale:${sale_id}`;')
    assert do_call_idx != -1, "handleWebhookGumroad no longer calls the Durable Object claim"
    assert kv_check_idx != -1, "the pre-existing KV idempotency check was removed -- it must stay as defense-in-depth"
    assert do_call_idx < kv_check_idx, (
        "the Durable Object claim must run BEFORE the KV idempotency check "
        "(it's the atomic guard; KV is now the fallback)"
    )


def test_handle_webhook_gumroad_short_circuits_on_an_already_claimed_sale():
    text = GATEWAY_SRC.read_text(encoding="utf-8")
    assert 'if (claimed.alreadyClaimed) return jsonResp({ status: "already_provisioned", sale_id });' in text


def test_wrangler_toml_has_the_durable_object_binding_and_migration():
    text = WRANGLER_TOML.read_text(encoding="utf-8")
    assert "[[durable_objects.bindings]]" in text
    assert "[[env.production.durable_objects.bindings]]" in text
    assert 'class_name = "GumroadProvisioningLock"' in text
    assert "[[migrations]]" in text
    assert 'new_sqlite_classes = ["GumroadProvisioningLock"]' in text


def test_wrangler_toml_migration_uses_sqlite_backed_classes_not_the_deprecated_kv_backed_type():
    """Production incident (2026-09-01, PR #296): `new_classes` (classic
    KV-backed Durable Object storage) failed to deploy with Cloudflare API
    error [code: 10099] -- this account only allows creating new namespaces
    via `new_sqlite_classes`. Regression guard against reintroducing the
    deprecated key."""
    text = WRANGLER_TOML.read_text(encoding="utf-8")
    # Checks the actual TOML key assignment, not just the word "new_classes"
    # -- the incident comment above the migration block legitimately mentions
    # it in prose to document what NOT to use.
    assert "new_classes =" not in text
    assert 'new_sqlite_classes = ["GumroadProvisioningLock"]' in text


def test_wrangler_toml_migrations_block_is_not_duplicated_per_environment():
    """Durable Object migrations are tracked once per Worker script, not per
    environment -- a duplicated [[migrations]] block under [env.production]
    would be a wrangler config error, unlike bindings/vars which ARE
    duplicated there (see every other binding in this file)."""
    text = WRANGLER_TOML.read_text(encoding="utf-8")
    assert "[[env.production.migrations]]" not in text
    assert text.count('new_sqlite_classes = ["GumroadProvisioningLock"]') == 1
