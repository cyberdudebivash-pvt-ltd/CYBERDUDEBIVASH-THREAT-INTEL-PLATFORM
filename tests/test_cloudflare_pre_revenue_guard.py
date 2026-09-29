import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRANGLER = ROOT / "workers" / "intel-gateway" / "wrangler.toml"
POLICY = ROOT / "config" / "cloudflare_pre_revenue_guard.json"


def _binding_names(text: str, section: str):
    # Restrict parsing to a TOML array-of-table section family and collect
    # the name/binding fields that follow until the next top-level table.
    names = []
    lines = text.splitlines()
    active = False
    for line in lines:
        stripped = line.strip()
        if stripped == section:
            active = True
            continue
        if active and stripped.startswith("[[") and stripped != section:
            active = False
        if active:
            m = re.match(r'(?:name|binding)\s*=\s*"([^"]+)"', stripped)
            if m:
                names.append(m.group(1))
    return names


def _all_array_table_bindings(text: str, prefix: str):
    names = []
    current = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[[") and s.endswith("]]"):
            current = s
            continue
        if current == prefix:
            m = re.match(r'(?:name|binding)\s*=\s*"([^"]+)"', s)
            if m:
                names.append(m.group(1))
    return names


def _crons(text: str):
    m = re.search(r'^crons\s*=\s*\[(.*?)\]$', text, re.M)
    if not m:
        return []
    return re.findall(r'"([^"]+)"', m.group(1))


def test_pre_revenue_cost_mode_keeps_strong_consistency_disabled_everywhere():
    text = WRANGLER.read_text(encoding="utf-8")
    values = re.findall(r'^AUTH_STRONG_CONSISTENCY_ENABLED\s*=\s*"([^"]+)"', text, re.M)
    assert values, "strong-consistency flag missing"
    assert all(v == "false" for v in values), values


def test_pre_revenue_cost_mode_keeps_strong_consistency_canary_disabled_everywhere():
    text = WRANGLER.read_text(encoding="utf-8")
    values = re.findall(r'^AUTH_STRONG_CONSISTENCY_CANARY_ENABLED\s*=\s*"([^"]+)"', text, re.M)
    assert values, "strong-consistency canary flag missing"
    assert all(v == "false" for v in values), values


def test_no_unapproved_durable_object_bindings_are_added():
    text = WRANGLER.read_text(encoding="utf-8")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    allowed = set(policy["approved_durable_object_bindings"])
    actual = set(_all_array_table_bindings(text, "[[durable_objects.bindings]]"))
    actual |= set(_all_array_table_bindings(text, "[[env.production.durable_objects.bindings]]"))
    assert actual == allowed


def test_no_unapproved_r2_bindings_are_added():
    text = WRANGLER.read_text(encoding="utf-8")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    allowed = set(policy["approved_r2_bindings"])
    actual = set(_all_array_table_bindings(text, "[[r2_buckets]]"))
    actual |= set(_all_array_table_bindings(text, "[[env.production.r2_buckets]]"))
    assert actual == allowed


def test_no_unapproved_kv_bindings_are_added():
    text = WRANGLER.read_text(encoding="utf-8")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    allowed = set(policy["approved_kv_bindings"])
    actual = set(_all_array_table_bindings(text, "[[kv_namespaces]]"))
    actual |= set(_all_array_table_bindings(text, "[[env.production.kv_namespaces]]"))
    assert actual == allowed


def test_scheduled_cloudflare_triggers_do_not_expand_silently():
    text = WRANGLER.read_text(encoding="utf-8")
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert set(_crons(text)) == set(policy["approved_crons"])


def test_policy_explicitly_requires_separate_approval_for_cloudflare_expansion():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["mode"] == "pre_revenue_cost_guard"
    assert policy["production_strong_consistency_must_remain_disabled"] is True
    assert "explicit founder approval" in policy["policy"].lower()
    assert "usage/cost impact" in policy["policy"].lower()
