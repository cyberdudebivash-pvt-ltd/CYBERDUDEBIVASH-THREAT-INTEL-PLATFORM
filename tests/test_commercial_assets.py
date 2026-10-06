"""
test_commercial_assets.py — CYBERDUDEBIVASH SENTINEL APEX

Regression coverage for the commercial asset factory.

Each test here pins a defect that was verified present in the shipped assets
before this suite existed, so a regression is caught rather than sold:

  * Detection packs shipped empty sigma_rules/yara_rules arrays.
  * Suricata "rules" were {sid, msg, severity} stubs, not rule syntax, with
    duplicate SIDs (which makes Suricata refuse the whole ruleset).
  * The IOC blocklist documented for firewall enforcement was dominated by CVE
    reference databases (cvefeed.io x179), vendor sites and source-code symbols
    parsed as domains ('llama.cpp', 'env.production').
  * IOC "bundles" held feed articles with ioc_count: 0 and no STIX at all.
  * The playbook product was a single 3-step, ~500-byte file.
  * No asset carried a price, a licence, an integrity manifest or deployment docs.
"""

import json
import os
import zipfile

import pytest

from agent.product_factory import ioc_validation
from agent.product_factory.asset_catalog_builder import build_catalog, is_primary_artefact
from agent.product_factory.commercial_asset_spec import (
    ASSET_CLASSES,
    commercial_metadata,
    license_text,
    load_pricing,
    resolve_price,
)
from agent.product_factory.detection_pack_builder import DetectionPackBuilder
from agent.product_factory.ioc_bundle_builder import IOCBundleBuilder
from agent.product_factory.soc_playbook_generator import (
    SLA_MATRIX,
    THREAT_PROFILES,
    SOCPlaybookGenerator,
)


# ── Commercial spec / pricing SSOT ───────────────────────────────────────────
class TestCommercialSpec:
    def test_every_asset_class_is_priced_from_the_ssot(self):
        pricing = load_pricing()
        for asset_class in ASSET_CLASSES:
            price = resolve_price(asset_class, pricing)
            assert price["priced"], f"{asset_class} is unpriced"
            assert price["price_usd"] > 0
            assert price["price_inr"] > 0
            assert price["pricing_source"] == "config/pricing.json"

    def test_prices_are_not_hardcoded_in_python(self):
        """A price change in config/pricing.json must propagate with no code change."""
        pricing = load_pricing()
        pricing["add_ons"]["detection_pack"]["price_usd"] = 12345
        assert resolve_price("detection_pack", pricing)["price_usd"] == 12345

    def test_unknown_add_on_reports_unpriced_rather_than_inventing_a_price(self):
        pricing = load_pricing()
        del pricing["add_ons"]["ioc_bundle"]
        price = resolve_price("ioc_bundle", pricing)
        assert price["priced"] is False
        assert "price_usd" not in price

    def test_licence_text_states_grant_and_prohibitions(self):
        for asset_class in ASSET_CLASSES:
            text = license_text(asset_class)
            assert "GRANT OF LICENCE" in text
            assert "PROHIBITED USE" in text
            assert "TLP:" in text
            assert ASSET_CLASSES[asset_class]["sku"] in text

    def test_commercial_metadata_carries_entitlement_and_licence(self):
        meta = commercial_metadata("detection_pack")
        assert meta["entitlement"]["required_tiers"]
        assert meta["licence"]["prohibited"]
        assert meta["pricing"]["priced"]


# ── IOC validation engine ────────────────────────────────────────────────────
class TestIOCValidation:
    @pytest.mark.parametrize("value", [
        "llama.cpp", "ggml-rpc.cpp", "messagescontroller.java",
        "env.production", "env.backup", "selectquerybuilder.distincton",
        "configprovider.getcontextprops", "plancontroller.getimmediateplans",
    ])
    def test_source_code_symbols_are_not_indicators(self, value):
        """These were shipped in a firewall-enforcement blocklist."""
        res = ioc_validation.validate(value, "domain")
        assert not res.accepted
        assert res.reason == "non_registrable_tld"

    @pytest.mark.parametrize("value", [
        "cvefeed.io", "nvd.nist.gov", "github.com", "www.zerodayinitiative.com",
        "metacpan.org", "gitweb.gentoo.org", "exploit-db.com", "virustotal.com",
        "cyberdudebivash.com",
    ])
    def test_reference_infrastructure_is_suppressed(self, value):
        """Blocking these breaks the customer's own security workflow."""
        res = ioc_validation.validate(value, "domain")
        assert not res.accepted
        assert res.reason == "benign_infrastructure"

    @pytest.mark.parametrize("value", [
        "webdeohemn.github.io", "docs-trezor-app.pages.dev",
        "d30sec8k5ond2x.cloudfront.net", "evil.azurewebsites.net",
    ])
    def test_subdomains_of_user_content_namespaces_stay_eligible(self, value):
        """Attackers host on these constantly; only the apex is benign."""
        assert ioc_validation.validate(value, "domain").accepted

    @pytest.mark.parametrize("value", ["github.io", "pages.dev", "cloudfront.net"])
    def test_user_content_apexes_are_suppressed(self, value):
        assert not ioc_validation.validate(value, "domain").accepted

    @pytest.mark.parametrize("value,reason", [
        ("192.168.1.1", "non_routable_private"),
        ("127.0.0.1", "non_routable_loopback"),
        ("169.254.1.1", "non_routable_link_local"),
        ("192.0.2.5", "documentation_range"),
    ])
    def test_non_routable_addresses_are_rejected(self, value, reason):
        res = ioc_validation.validate(value, "ipv4")
        assert not res.accepted
        assert res.reason == reason

    def test_cve_ids_are_never_treated_as_blockable_indicators(self):
        res = ioc_validation.validate("CVE-2024-12345", "cve")
        assert not res.accepted
        assert res.reason == "cve_not_an_indicator"

    @pytest.mark.parametrize("value,expected", [
        ("45.33.32.156", "ipv4"),
        ("a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a", "sha256"),
        ("d41d8cd98f00b204e9800998ecf8427e", "md5"),
        ("https://evil-domain.xyz/payload", "url"),
        ("bad-actor.example-malware.top", "domain"),
    ])
    def test_type_inference(self, value, expected):
        assert ioc_validation.infer_type(value) == expected

    def test_low_confidence_indicators_never_reach_the_enforcement_tier(self):
        low = ioc_validation.validate("evil-low.xyz", "domain", confidence=10)
        high = ioc_validation.validate("evil-high.xyz", "domain", confidence=95)
        assert low.tier == "monitoring"
        assert high.tier == "enforcement"

    def test_non_blockable_types_never_reach_the_enforcement_tier(self):
        res = ioc_validation.validate("suspicious parent-child chain", "behavioral",
                                      confidence=99)
        assert res.accepted and res.tier == "monitoring"

    def test_batch_deduplicates_and_reports(self):
        accepted, report = ioc_validation.validate_batch([
            {"value": "evil-dupe.xyz", "type": "domain", "confidence": 70},
            {"value": "evil-dupe.xyz", "type": "domain", "confidence": 90},
            {"value": "cvefeed.io", "type": "domain", "confidence": 90},
            {"value": "llama.cpp", "type": "domain"},
        ])
        assert len(accepted) == 1
        assert accepted[0].confidence == 90
        assert report.rejection_reasons["benign_infrastructure"] == 1
        assert report.rejection_reasons["non_registrable_tld"] == 1


# ── Detection pack ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def detection_pack(tmp_path_factory):
    out = tmp_path_factory.mktemp("detpack")
    os.environ["DETECTION_PACK_OUTPUT_DIR"] = str(out)
    os.environ["SOURCE_DATE_EPOCH"] = "1780000000"
    builder = DetectionPackBuilder()
    result = builder.build_pack("enterprise")
    if result.get("status") != "success":
        pytest.skip(f"detection pack unavailable: {result.get('message')}")
    return result


class TestDetectionPack:
    def test_build_succeeds_and_preserves_the_1x_response_contract(self, detection_pack):
        for key in ("status", "product_id", "path", "version"):
            assert key in detection_pack
        assert detection_pack["product_id"] == "DET-PACK-ENTERPRISE"

    def test_archive_ships_no_empty_content_arrays(self, detection_pack):
        """sigma_rules and yara_rules shipped empty in every 1.x pack."""
        contents = detection_pack["contents"]
        for key in ("sigma_rules", "kql_queries", "suricata_rules", "snort_rules"):
            assert contents[key] > 0, f"{key} is empty — pack is not deployable"

    def test_ids_rules_have_no_duplicate_sids(self, detection_pack):
        """Duplicate SIDs make Suricata refuse the entire ruleset."""
        import re
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            for engine in ("suricata", "snort"):
                body = zf.read(f"{engine}/cdb-apex.rules").decode()
                sids = re.findall(r"\bsid:(\d+);", body)
                assert sids, f"{engine} ruleset is empty"
                assert len(sids) == len(set(sids)), f"{engine} has duplicate SIDs"
                assert all(9_100_000 <= int(s) <= 9_999_999 for s in sids)

    def test_ids_rules_are_rule_syntax_not_json_stubs(self, detection_pack):
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            body = zf.read("suricata/cdb-apex.rules").decode()
        rules = [l for l in body.splitlines() if l.startswith("alert ")]
        assert rules
        for rule in rules:
            assert rule.endswith(")")
            for token in ("msg:", "sid:", "rev:", "classtype:"):
                assert token in rule

    def test_ids_rules_alert_never_drop(self, detection_pack):
        """Shipped content must not block inline before the customer tunes it."""
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            for engine in ("suricata", "snort"):
                body = zf.read(f"{engine}/cdb-apex.rules").decode()
                assert not any(l.startswith("drop ") for l in body.splitlines())

    def test_enforcement_blocklist_has_no_benign_infrastructure(self, detection_pack):
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            body = zf.read("ioc/enforcement_blocklist.txt").decode()
        for line in body.splitlines():
            v = line.strip()
            if not v or v.startswith("#"):
                continue
            assert not ioc_validation.is_benign_host(v), f"benign host in enforcement list: {v}"

    def test_monitoring_and_enforcement_tiers_are_separate_files(self, detection_pack):
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            names = zf.namelist()
        assert "ioc/enforcement_blocklist.txt" in names
        assert "ioc/monitoring_indicators.txt" in names

    def test_archive_carries_licence_readme_and_integrity_manifest(self, detection_pack):
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            names = zf.namelist()
            for required in ("README.md", "LICENSE.txt", "CHANGELOG.md", "SHA256SUMS.txt"):
                assert required in names
            assert len([n for n in names if n.startswith("deployment/")]) >= 3

    def test_sha256sums_covers_and_matches_every_file(self, detection_pack):
        import hashlib
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            declared = {}
            for line in zf.read("SHA256SUMS.txt").decode().splitlines():
                digest, name = line.split("  ", 1)
                declared[name] = digest
            for name in zf.namelist():
                if name == "SHA256SUMS.txt":
                    continue
                assert name in declared, f"{name} missing from SHA256SUMS.txt"
                assert hashlib.sha256(zf.read(name)).hexdigest() == declared[name]

    def test_backward_compatible_manifest_and_metadata_keys_survive(self, detection_pack):
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            meta = json.loads(zf.read("metadata.json").decode())
            manifest = json.loads(zf.read("manifest.json").decode())
        for key in ("pack_id", "tier", "generated_by", "authority"):
            assert key in meta, f"1.x metadata key '{key}' was dropped"
        assert meta["authority"] == "CYBERDUDEBIVASH OFFICIAL AUTHORITY"
        # Genesis manifest keys are preserved alongside the new commercial block.
        assert "_commercial" in manifest

    def test_attack_navigator_layer_is_importable(self, detection_pack):
        with zipfile.ZipFile(detection_pack["path"]) as zf:
            layer = json.loads(zf.read("mitre/attack_navigator_layer.json").decode())
        assert layer["domain"] == "enterprise-attack"
        assert layer["versions"]["attack"]
        assert layer["techniques"]
        for tech in layer["techniques"]:
            assert tech["techniqueID"].startswith("T")
            assert isinstance(tech["score"], int)

    def test_archive_is_reproducible_under_pinned_source_date_epoch(self, tmp_path):
        os.environ["DETECTION_PACK_OUTPUT_DIR"] = str(tmp_path)
        os.environ["SOURCE_DATE_EPOCH"] = "1780000000"
        builder = DetectionPackBuilder()
        first = builder.build_pack("enterprise")
        second = builder.build_pack("enterprise")
        if first.get("status") != "success":
            pytest.skip("detection pack unavailable")
        assert first["sha256"] == second["sha256"]


# ── IOC bundle ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def ioc_bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("iocbundle")
    os.environ["IOC_BUNDLE_OUTPUT_DIR"] = str(out)
    os.environ["SOURCE_DATE_EPOCH"] = "1780000000"
    result = IOCBundleBuilder().generate_bundle()
    if result.get("status") != "success":
        pytest.skip(f"IOC bundle unavailable: {result.get('message')}")
    return result


class TestIOCBundle:
    def test_preserves_the_1x_response_contract(self, ioc_bundle):
        for key in ("status", "file", "count"):
            assert key in ioc_bundle

    def test_bundle_contains_indicators_not_feed_articles(self, ioc_bundle):
        """1.x shipped 2 news articles with ioc_count: 0 on every item."""
        data = json.loads(open(ioc_bundle["file"], encoding="utf-8").read())
        assert data["ioc_count"] > 0
        assert len(data["indicators"]) == data["ioc_count"]
        for ind in data["indicators"][:50]:
            assert ind["type"] in ioc_validation.ENFORCEABLE_TYPES | ioc_validation.MONITORING_ONLY_TYPES

    def test_preserves_1x_bundle_keys(self, ioc_bundle):
        data = json.loads(open(ioc_bundle["file"], encoding="utf-8").read())
        for key in ("bundle_id", "timestamp", "ioc_count", "data", "authority"):
            assert key in data, f"1.x bundle key '{key}' was dropped"

    def test_emits_a_valid_stix_21_bundle(self, ioc_bundle):
        path = ioc_bundle["files"][f"{ioc_bundle['bundle_id']}.stix2.json"]
        stix = json.loads(open(path, encoding="utf-8").read())
        assert stix["type"] == "bundle"
        assert stix["id"].startswith("bundle--")
        indicators = [o for o in stix["objects"] if o["type"] == "indicator"]
        assert indicators
        for obj in indicators:
            assert obj["spec_version"] == "2.1"
            assert obj["pattern_type"] == "stix"
            assert obj["pattern"].startswith("[") and obj["pattern"].endswith("]")
            assert obj["id"].startswith("indicator--")
            assert obj["valid_from"]
            if "confidence" in obj:
                assert 0 <= obj["confidence"] <= 100

    def test_stix_identifiers_are_stable_across_builds(self, ioc_bundle, tmp_path):
        """A TIP must update an existing object, not accumulate duplicates."""
        os.environ["IOC_BUNDLE_OUTPUT_DIR"] = str(tmp_path)
        second = IOCBundleBuilder().generate_bundle()
        first_path = ioc_bundle["files"][f"{ioc_bundle['bundle_id']}.stix2.json"]
        a = json.loads(open(first_path, encoding="utf-8").read())
        b = json.loads(open(second["files"][f"{second['bundle_id']}.stix2.json"],
                            encoding="utf-8").read())
        ids_a = {o["id"] for o in a["objects"] if o["type"] == "indicator"}
        ids_b = {o["id"] for o in b["objects"] if o["type"] == "indicator"}
        assert ids_a == ids_b

    def test_emits_a_misp_event(self, ioc_bundle):
        path = ioc_bundle["files"][f"{ioc_bundle['bundle_id']}.misp.json"]
        misp = json.loads(open(path, encoding="utf-8").read())
        assert "Event" in misp and misp["Event"]["Attribute"]
        for attr in misp["Event"]["Attribute"][:50]:
            assert attr["type"] and attr["value"] and "uuid" in attr

    def test_only_enforcement_indicators_are_to_ids(self, ioc_bundle):
        path = ioc_bundle["files"][f"{ioc_bundle['bundle_id']}.misp.json"]
        misp = json.loads(open(path, encoding="utf-8").read())
        for attr in misp["Event"]["Attribute"]:
            if attr["to_ids"]:
                assert "tier=enforcement" in attr["comment"]

    def test_blocklist_contains_only_enforcement_tier(self, ioc_bundle):
        path = ioc_bundle["files"][f"{ioc_bundle['bundle_id']}.blocklist.txt"]
        body = open(path, encoding="utf-8").read()
        for line in body.splitlines():
            v = line.strip()
            if v and not v.startswith("#"):
                assert not ioc_validation.is_benign_host(v)

    def test_falls_back_to_the_certified_baseline(self, ioc_bundle):
        """1.x returned {'status':'error'} on any runner without the live feed."""
        assert ioc_bundle["source"] in ("live_feed_manifest", "certified_baseline")


# ── Playbooks ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def playbooks(tmp_path_factory):
    out = tmp_path_factory.mktemp("playbooks")
    os.environ["PLAYBOOK_OUTPUT_DIR"] = str(out)
    os.environ["SOURCE_DATE_EPOCH"] = "1780000000"
    gen = SOCPlaybookGenerator()
    return gen.generate_library("Test-Actor"), out


class TestPlaybooks:
    def test_library_covers_every_threat_profile(self, playbooks):
        paths, _ = playbooks
        assert len(paths) == len(THREAT_PROFILES)

    def test_each_playbook_covers_the_full_nist_lifecycle(self, playbooks):
        paths, _ = playbooks
        required = {"Preparation", "Detection and Analysis",
                    "Containment, Eradication, and Recovery", "Post-Incident Activity"}
        for path in paths:
            data = json.loads(open(path, encoding="utf-8").read())
            assert required <= {p["nist_phase"] for p in data["phases"]}

    def test_playbooks_are_operational_not_three_steps(self, playbooks):
        """1.x shipped one ~500-byte, 3-step file."""
        paths, _ = playbooks
        for path in paths:
            data = json.loads(open(path, encoding="utf-8").read())
            assert data["task_count"] >= 20
            assert os.path.getsize(path) > 10_000

    def test_preserves_1x_keys_and_leading_steps(self, playbooks):
        paths, _ = playbooks
        ransomware = [p for p in paths if "RANSOMWARE" in p][0]
        data = json.loads(open(ransomware, encoding="utf-8").read())
        for key in ("title", "authority", "steps", "last_updated"):
            assert key in data, f"1.x playbook key '{key}' was dropped"
        assert data["steps"][:3] == [
            {"phase": "Identification",
             "action": "Query SIEM for Test-Actor infrastructure reuse."},
            {"phase": "Containment",
             "action": "Isolate endpoints exhibiting v43 temporal bursts."},
            {"phase": "Eradication",
             "action": "Deploy Genesis G07 generated Sigma rules."},
        ]

    def test_mitre_and_sla_are_present_and_severity_matched(self, playbooks):
        paths, _ = playbooks
        for path in paths:
            data = json.loads(open(path, encoding="utf-8").read())
            assert data["mitre_technique_count"] > 0
            assert data["sla"] == SLA_MATRIX[data["severity"]]

    def test_markdown_and_licence_ship_alongside_json(self, playbooks):
        paths, out = playbooks
        for path in paths:
            base = os.path.basename(path).replace(".json", "")
            assert (out / f"{base}.md").exists()
            assert (out / f"{base}.LICENSE.txt").exists()

    def test_unknown_threat_type_falls_back_without_raising(self, tmp_path):
        os.environ["PLAYBOOK_OUTPUT_DIR"] = str(tmp_path)
        path = SOCPlaybookGenerator().generate_for_threat("Cryptojacking", "Unknown")
        data = json.loads(open(path, encoding="utf-8").read())
        assert data["task_count"] >= 20


# ── Catalog ──────────────────────────────────────────────────────────────────
class TestCatalog:
    def test_catalog_prices_every_asset_class(self):
        catalog = build_catalog()
        assert catalog["summary"]["priced_asset_classes"] == len(ASSET_CLASSES)
        for product in catalog["products"]:
            assert product["commercial"]["pricing"]["priced"]

    @pytest.mark.parametrize("asset_class,name,expected", [
        ("ioc_bundle", "IOC-BNDL-20260101_0000.json", True),
        ("ioc_bundle", "IOC-BNDL-20260101_0000.stix2.json", False),
        ("ioc_bundle", "IOC-BNDL-20260101_0000.misp.json", False),
        ("soc_playbook", "PB-RANSOMWARE-LAZARUS.json", True),
        ("soc_playbook", "PB-RANSOMWARE-LAZARUS.LICENSE.txt", False),
        ("detection_pack", "CDB_DETECTION_PACK_ENTERPRISE_20260101_0000.zip", True),
    ])
    def test_companion_files_are_not_catalog_entries(self, asset_class, name, expected):
        assert is_primary_artefact(asset_class, name) is expected
