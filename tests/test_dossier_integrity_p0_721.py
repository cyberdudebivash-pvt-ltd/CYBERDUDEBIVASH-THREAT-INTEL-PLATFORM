"""P0 #721 -- enterprise dossier intelligence integrity.

Regression + negative-control tests for the evidence rules in scripts/dossier_integrity.py and
scripts/tlp_policy.py and their wiring into the live dossier renderers / publishers
(scripts/generate_intel_reports.py, scripts/report_enhancer.py, scripts/commercial_readiness_governor.py),
the ATT&CK mapping engine and the Navigator exporters.

Fixtures
  * tests/fixtures/dossier_p0_721_real_records.json -- verbatim production feed records (NOT the eight
    issue-#721 dossiers: those originals are not in the repository and, being TLP-restricted, must never
    be committed). They carry NO tlp label (that is itself the point of the fail-closed policy), so the
    rendering tests label them TLP:CLEAR explicitly via _clear(); the denial of the unlabelled originals
    is tested separately in TestTlpPublicationPolicy.
  * tests/fixtures/golden_721/*.json -- authorized, sanitized feed records for the eight dossiers; the
    golden tests start enforcing them when present and stay SKIPPED (a release blocker) otherwise.
"""
from __future__ import annotations

import copy
import html as _html
import importlib.util
import json
import logging
import re
import sys
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import dossier_integrity as di  # noqa: E402
import tlp_policy as tlp  # noqa: E402
import apex_mitre_attack_engine as mae  # noqa: E402
import generate_intel_reports as gen  # noqa: E402
import report_enhancer as enh  # noqa: E402
import commercial_readiness_governor as gov  # noqa: E402
import verify_commercial_contract as vcc  # noqa: E402

# A byte-for-byte duplicate of this module also sits at the repo root (no importers; flagged MERGE in the
# #721 register) -- load the canonical scripts/ copy explicitly, never by name.
_spec = importlib.util.spec_from_file_location("scripts_apex_sigma_templates", ROOT / "scripts" / "apex_sigma_templates.py")
sigma = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sigma)


@pytest.fixture(autouse=True, scope="module")
def _quiet_logs_for_this_module_only():
    """Renderers are chatty; silence them here but RESTORE afterwards -- a module-level
    logging.disable() would silently break later tests that assert on log output."""
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


FIXTURE = ROOT / "tests" / "fixtures" / "dossier_p0_721_real_records.json"
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden_721"
MANIFEST = ROOT / "data" / "apex_enriched_manifest.json"
PREFIX = "https://intel.cyberdudebivash.com"


def _clear(rec):
    """Explicitly label a fixture TLP:CLEAR (the production records carry no label)."""
    rec = copy.deepcopy(rec)
    rec["tlp"] = "TLP:CLEAR"
    return rec


def _records():
    return {r["id"]: _clear(r) for r in json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]}


def _by_suffix(sfx):
    return copy.deepcopy(next(r for i, r in _records().items() if i.endswith(sfx)))


def render(item, tier="free"):
    page = gen.render_report(copy.deepcopy(item), PREFIX)
    return enh.enhance_report_html(page, copy.deepcopy(item), tier)


def visible_text(page):
    page = re.sub(r"<(style|script).*?</\1>", " ", page, flags=re.S | re.I)
    return _html.unescape(re.sub(r"<[^>]+>", " ", page))


def ioc_numbers_in(page):
    """(observable counts, validated counts) a customer can see anywhere on the page."""
    t = re.sub(r"\s+", " ", visible_text(page))
    obs, val = [], []
    for p in (r"IOC observables?:\s*(\d+)", r"IOC Observables (\d+) ", r"IOC Observables / Validated (\d+) /",
              r"(\d+) IOC observables?\b", r"IOC obs\. / valid\. / KEV (\d+) /", r"(\d+) / \d+ IOC OBSERVABLES / VALIDATED",
              r"(\d+) IOC obs\. \(\d+ validated\)", r"IOC Observables / Validated \d+ / \d+"):
        obs += [int(x) for x in re.findall(p, t) if str(x).isdigit()]
    for p in (r"validated as malicious:\s*(\d+)", r"Validated IOCs:? (\d+)", r"(\d+) validated as malicious",
              r"IOC Observables / Validated \d+ / (\d+)", r"IOC obs\. / valid\. / KEV \d+ / (\d+)",
              r"\d+ / (\d+) IOC OBSERVABLES / VALIDATED", r"\d+ IOC obs\. \((\d+) validated\)"):
        val += [int(x) for x in re.findall(p, t)]
    return obs, val


# phrases the old fixed templates emitted for EVERY advisory
FORBIDDEN_FABRICATIONS = [
    "beacon interval 60s", "Implant beacons to C2", "Backdoor/RAT installed", "OSINT collection on target",
    "re-generated C2 infrastructure", "No IOCs in current data feed", "T1190.001",
    "Breach notification obligations may apply", "FAIR-aligned", "500-advisory rolling baseline",
    "within 4–6 hours of exploitation", "THREAT ACTIVE", "7-Day Trial",
]


def assert_dossier_invariants(item, tier="free"):
    page = render(item, tier)
    text = visible_text(page)
    # 1. one observable count and one validated count, everywhere
    obs, val = ioc_numbers_in(page)
    q = di.qualify_iocs(item.get("iocs"), item)
    assert len(set(obs)) <= 1, f"IOC observable count mismatch across sections: {sorted(set(obs))}"
    assert len(set(val)) <= 1, f"validated IOC count mismatch across sections: {sorted(set(val))}"
    if obs:
        assert set(obs) == {q["count"]}, f"page shows {set(obs)}, qualified observables = {q['count']}"
    if val:
        assert set(val) == {q["validated_count"]}, f"page shows {set(val)}, validated = {q['validated_count']}"
    # 2. no fabricated template claims, no trial promise (commercial contract), no active-threat claim
    for bad in FORBIDDEN_FABRICATIONS:
        assert bad not in text and bad not in page, f"fabricated claim present: {bad!r}"
    for label, rx in vcc.FORBIDDEN_PRICE_PATTERNS:
        assert not rx.search(text) and not rx.search(page), f"commercial-contract violation in generated page: {label}"
    assert not re.search(r"\bAPPLIES\b", text)
    # 3. no invalid / retired ATT&CK id anywhere in the page (incl. Navigator data-URI layer)
    for tid in set(re.findall(r"\bT\d{4}(?:\.\d{3})?\b", text + urllib.parse.unquote(page))):
        assert di.validate_technique(tid)["status"] == "VALID", f"non-current ATT&CK id rendered: {tid}"
    # 4. an internal key is never presented as a STIX id
    assert not re.search(r"STIX ID\s*(?:intel--|intrusion-set--)", text)
    # 5. an unrated, un-prioritized vulnerability record is told to triage
    cvss = item.get("cvss_score")
    kev = gen._kev_confirmed_check(item)
    if di.is_vulnerability_record(item) and cvss is None and not kev:
        assert "UNRATED" in text and "TRIAGE REQUIRED" in text
    # 6. displayed severity and the displayed action can never contradict each other
    m_sev = re.search(r"Severity:\s*(CRITICAL|HIGH|MEDIUM|LOW|UNRATED|UNKNOWN|INFO)", text)
    m_act = re.search(r"WHAT TO DO TODAY\?\s*(.+?)\s{2,}", text)
    if m_sev and m_act:
        sev_shown, action = m_sev.group(1), m_act.group(1)
        if sev_shown in ("CRITICAL", "HIGH") and re.search(r"routine cycle|INFORMATIONAL|STANDARD PATCH", action):
            raise AssertionError(f"{sev_shown} shown with routine action: {action}")
        if sev_shown in ("LOW", "UNRATED") and re.search(r"IMMEDIATE|WITHIN 7 DAYS", action) and not kev:
            raise AssertionError(f"{sev_shown} shown with emergency action: {action}")
    # 7. a CVSS-scored vulnerability is never displayed below its own CVSS band
    if cvss not in (None, "", 0) and di.is_vulnerability_record(item):
        band = di._ste.cvss_rating(float(cvss))
        assert re.search(rf"Severity:\s*{band}\b", text), f"CVSS {cvss} should display as {band}"
    return page


# ─────────────────────────────────────────────────────────────────────────────
# 1. IOC qualification -- observables vs validated actionable (negative controls)
# ─────────────────────────────────────────────────────────────────────────────
CTX = {"source": "abuse.ch", "feed_source": "threatfox"}


class TestIocQualification:
    def test_empty_none_and_non_list_are_zero(self):
        for raw in ([], None, "", 0, {}, "not-a-list"):
            q = di.qualify_iocs(raw)
            assert q["count"] == 0 and q["validated_count"] == 0 and q["observables"] == [] and q["rejected"] == []

    def test_cve_ids_and_advisory_urls_are_references_not_iocs(self):
        q = di.qualify_iocs(["CVE-2026-3300", "cve-2026-0001", "https://nvd.nist.gov/vuln/detail/CVE-2026-3300",
                             "https://www.cisa.gov/notification"])
        assert q["count"] == 0
        assert {r["reason_class"] for r in q["rejected"]} <= {"cve_reference", "contextual_reference"}

    def test_filenames_software_names_and_platform_domains_not_counted(self):
        q = di.qualify_iocs(["composer.js", "RegSvcs.exe", "worddecoder.decodeheader", "alf.io",
                             "cyberdudebivash.com", "api.cyberdudebivash.com", "x.cyberdudebivash.in"])
        assert q["count"] == 0 and len(q["rejected"]) == 7
        assert {r["value"]: r["reason_class"] for r in q["rejected"]}["api.cyberdudebivash.com"] == "platform_infrastructure"

    def test_private_malformed_and_version_strings_rejected(self):
        q = di.qualify_iocs(["192.168.1.10", "10.0.0.1", "999.1.1.1", "12.01.01.37", "", "   ", None, {"value": ""}])
        assert q["count"] == 0

    def test_valid_indicators_counted_and_original_shape_preserved(self):
        raw = ["45.153.204.118", {"type": "domain", "value": "update.microsoft-cdn.net", "source": "feedX"}, "a" * 64]
        q = di.qualify_iocs(raw)
        assert q["count"] == 3
        assert q["observables"][0] == "45.153.204.118"          # legacy bare string stays a string
        assert isinstance(q["observables"][1], dict)

    def test_duplicates_collapse_across_case_defang_and_root_dot(self):
        q = di.qualify_iocs(["45.153.204.118", "45.153.204[.]118", "Evil-Login.example.com",
                             "evil-login.example.com.", "EVIL-LOGIN.EXAMPLE.COM"])
        assert q["count"] == 2 and q["duplicates"] == 3

    def test_generated_candidates_are_never_counted(self):
        q = di.qualify_iocs([{"type": "ipv4", "value": "45.153.204.118", "generated": True},
                             {"type": "ipv4", "value": "45.153.204.119"}])
        assert q["count"] == 1 and len(q["generated"]) == 1 and q["validated_count"] == 0

    # ---- provenance-aware domain handling (review point 3) ------------------------------------
    def test_no_source_bare_domain_is_preserved_as_observable_never_validated(self):
        q = di.qualify_iocs(["badsite.com", "c2.evil.ru"], CTX)
        assert q["count"] == 2 and q["validated_count"] == 0
        assert all(di.ioc_evidence_state(o, CTX) == "UNVERIFIED" for o in q["observables"])

    def test_non_tld_dotted_strings_are_still_rejected(self):
        # 'decodeheader' / 'js' / 'phar' are not IANA TLDs: method refs and filenames are not domains
        q = di.qualify_iocs(["worddecoder.decodeheader", "node.js", "composer.phar", "com.example.ClassName"])
        assert q["count"] == 0

    def test_valid_benign_domain_with_corroborated_source_is_observable_not_actionable(self):
        ioc = {"value": "cdn.benign-example.com", "source": "abuse.ch"}
        q = di.qualify_iocs([ioc], CTX)
        assert q["count"] == 1 and q["validated_count"] == 0
        assert di.ioc_evidence_state(ioc, CTX) == "SOURCE_REPORTED"

    def test_confirmed_malicious_domain_with_corroborated_source_is_validated(self):
        ioc = {"value": "c2.evil.ru", "source": "abuse.ch", "verdict": "malicious"}
        q = di.qualify_iocs([ioc], CTX)
        assert q["count"] == 1 and q["validated_count"] == 1
        assert di.is_validated_actionable(ioc, CTX)

    def test_spoofed_source_is_claimed_not_corroborated_and_never_validated(self):
        ioc = {"value": "spoofed.example.org", "source": "CISA KEV", "verdict": "malicious"}
        assert di.ioc_evidence_state(ioc, CTX) == "SOURCE_CLAIMED"
        assert not di.is_validated_actionable(ioc, CTX)
        assert di.qualify_iocs([ioc], CTX)["validated_count"] == 0
        # and with NO context at all a source claim can never be corroborated
        assert di.qualify_iocs([dict(ioc, source="abuse.ch")])["validated_count"] == 0

    def test_duplicate_reference_across_sources_counts_once(self):
        a = {"value": "c2.evil.ru", "source": "abuse.ch", "verdict": "malicious"}
        b = {"value": "C2.EVIL.RU.", "source": "threatfox", "malicious": True}
        q = di.qualify_iocs([a, b], CTX)
        assert q["count"] == 1 and q["duplicates"] == 1 and q["validated_count"] == 1

    def test_observed_marker_without_a_source_stays_unverified(self):
        ioc = {"value": "x.example.com", "observed_in_wild": True}
        assert di.ioc_evidence_state(ioc, CTX) == "UNVERIFIED" and not di.is_validated_actionable(ioc, CTX)
        ok = {"value": "45.153.204.118", "observed_in_wild": True, "source": "abuse.ch"}
        assert di.ioc_evidence_state(ok, CTX) == "OBSERVED" and di.is_validated_actionable(ok, CTX)

    def test_known_product_and_advisory_hosts_are_not_promoted_by_the_domain_rule(self):
        assert di.qualify_iocs(["alf.io", "dask.org", "www.cisa.gov", "nvd.nist.gov"], CTX)["count"] == 0

    def test_fail_closed_without_the_iana_tld_reference(self, monkeypatch):
        monkeypatch.setattr(di, "IANA_TLD_PATH", ROOT / "does-not-exist.txt")
        di._iana_tlds.cache_clear()
        try:
            assert di.qualify_iocs(["badsite.com"], CTX)["count"] == 0       # no TLD list -> no promotion
        finally:
            monkeypatch.undo()
            di._iana_tlds.cache_clear()
        assert di.qualify_iocs(["badsite.com"], CTX)["count"] == 1

    def test_counts_are_consistent_for_every_fixture(self):
        for item in _records().values():
            q = di.qualify_iocs(item.get("iocs"), item)
            assert q["count"] == len(q["observables"]) and q["validated_count"] == len(q["validated"])
            assert q["validated_count"] <= q["count"] and sum(q["by_state"].values()) == q["count"]

    def test_qualification_is_idempotent_so_generator_and_enhancer_agree(self):
        for item in _records().values():
            q1 = di.qualify_iocs(item.get("iocs"), item)
            q2 = di.qualify_iocs(q1["observables"], item)
            assert (q1["count"], q1["validated_count"]) == (q2["count"], q2["validated_count"])


# ─────────────────────────────────────────────────────────────────────────────
# 2. ATT&CK authority -- official, release-pinned, fail-closed
# ─────────────────────────────────────────────────────────────────────────────
class TestAttack:
    def test_release_pin_identifies_the_official_release_and_its_hashes(self):
        pin = di.attack_dataset_pin()
        assert pin["available"] and pin["attack_release"] == "19.2" and pin["release_major"] == "19"
        assert re.fullmatch(r"[0-9a-f]{64}", pin["official_file_sha256"]) and pin["content_hash"]
        assert pin["technique_count"] == 697 and pin["retired_count"] > 100
        assert di.navigator_attack_version() == "19"

    def test_t1190_has_no_subtechniques_and_only_the_approved_alias_is_rewritten(self):
        assert di.validate_technique("T1190")["status"] == "VALID"
        r = di.validate_technique("T1190.001")
        assert r["status"] == "APPROVED_LEGACY_ALIAS" and r["maps_to"] == "T1190"
        assert di.canonical_technique_id("T1190.001") == "T1190"

    @pytest.mark.parametrize("unknown", ["T1059.999", "T1190.002", "T1566.099", "T1078.777"])
    def test_unknown_subtechniques_are_suppressed_never_mapped_to_their_parent(self, unknown):
        r = di.validate_technique(unknown)
        assert r["status"] == "UNKNOWN_TECHNIQUE"
        assert di.canonical_technique_id(unknown) is None
        out, rej = di.filter_valid_techniques([unknown])
        assert out == [] and rej and rej[0]["status"] == "UNKNOWN_TECHNIQUE"
        assert rej[0]["suggested_parent"] == unknown.split(".")[0]          # reviewer hint only, never applied

    @pytest.mark.parametrize("retired,replacement", [("T1574.002", "T1574.001"), ("T1562", "T1685"), ("T1562.001", "T1685")])
    def test_genuine_but_retired_ids_are_suppressed_with_the_official_replacement_reported(self, retired, replacement):
        r = di.validate_technique(retired)
        assert r["status"] == "RETIRED" and replacement in r["revoked_by"]
        assert di.canonical_technique_id(retired) is None and di.technique_name(retired) is None
        out, rej = di.filter_valid_techniques([retired, {"technique_id": retired}])
        assert out == [] and len(rej) == 2

    @pytest.mark.parametrize("bad", ["", "foo", "T12", "T1190.1", "T9999", "TA0001", None, 1190, "t1190 ", "T1190\n"])
    def test_malformed_ids_are_never_publishable(self, bad):
        if isinstance(bad, str) and bad.strip().upper() == "T1190":
            assert di.canonical_technique_id(bad) == "T1190"                # whitespace-only variance is normalised
        else:
            assert di.canonical_technique_id(bad) is None

    def test_names_must_resolve_to_an_official_current_technique(self):
        out, rej = di.filter_valid_techniques(
            ["Active Scanning", "Pre-OS Boot: Firmware Corruption", "Registry Run Keys", "free text", "<script>x</script>",
             "x" * 500, "Exploit Public-Facing Application", "active scanning"])
        assert out == ["Active Scanning", "Exploit Public-Facing Application"]
        assert {r["status"] for r in rej} == {"UNVERIFIED_NAME"} and len(rej) == 5
        assert di.resolve_technique_name("Phishing: Spearphishing Attachment")["ids"] == ["T1566.001"]

    def test_official_names_not_invented(self):
        assert di.technique_name("T1190") == "Exploit Public-Facing Application"
        assert di.technique_name("T9999") is None
        assert enh._mitre_name("T9999").startswith("Unvalidated")

    def test_fail_closed_when_the_dataset_is_missing(self, monkeypatch):
        monkeypatch.setattr(di, "ATTACK_DATASET_PATH", ROOT / "missing-attack.json")
        di._attack_state.cache_clear(); di.attack_dataset_pin.cache_clear()
        try:
            assert di.validate_technique("T1190")["status"] == "DATASET_UNAVAILABLE"
            assert di.canonical_technique_id("T1190") is None and di.canonical_technique_id("T1190.001") is None
            out, rej = di.filter_valid_techniques(["Active Scanning", "T1190", "T1190.001"])
            assert out == [] and len(rej) == 3
            assert di.navigator_attack_version() == "unpinned" and not di.attack_dataset_pin()["available"]
        finally:
            monkeypatch.undo(); di._attack_state.cache_clear(); di.attack_dataset_pin.cache_clear()
        assert di.validate_technique("T1190")["status"] == "VALID"

    def test_fail_closed_when_the_release_pin_is_missing_or_the_snapshot_drifted(self, monkeypatch, tmp_path):
        monkeypatch.setattr(di, "ATTACK_PIN_PATH", ROOT / "missing-pin.json")
        di._attack_state.cache_clear(); di.attack_dataset_pin.cache_clear()
        try:
            assert di.validate_technique("T1190")["status"] == "DATASET_UNAVAILABLE"
            pin = json.loads((ROOT / "data" / "attck" / "attack_release_pin.json").read_text(encoding="utf-8"))
            pin["snapshot_content_hash"] = "0" * 64                          # snapshot no longer matches the verified release
            drift = tmp_path / "pin.json"
            drift.write_text(json.dumps(pin), encoding="utf-8")
            monkeypatch.setattr(di, "ATTACK_PIN_PATH", drift)
            di._attack_state.cache_clear(); di.attack_dataset_pin.cache_clear()
            assert di.validate_technique("T1190")["status"] == "DATASET_UNAVAILABLE"
        finally:
            monkeypatch.undo(); di._attack_state.cache_clear(); di.attack_dataset_pin.cache_clear()
        assert di.validate_technique("T1190")["status"] == "VALID"

    def test_the_repo_snapshot_is_exactly_the_pinned_official_release(self):
        pin = json.loads((ROOT / "data" / "attck" / "attack_release_pin.json").read_text(encoding="utf-8"))
        snap = json.loads((ROOT / "data" / "attck" / "enterprise-attack.json").read_text(encoding="utf-8"))
        assert pin["snapshot_verified_equal_to_official"] is True
        assert pin["snapshot_content_hash"] == snap["content_hash"]
        assert pin["current_technique_count"] == len(snap["techniques"]) == 697
        assert set(pin["retired_techniques"]).isdisjoint({t["attck_id"] for t in snap["techniques"]})
        assert set(pin["approved_legacy_aliases"]) == {"T1190.001"}

    def test_engine_publishes_only_current_ids_for_every_library_keyword_and_cwe(self):
        issues = []
        texts = [kw for t in mae.TECHNIQUE_LIBRARY.values() for kw in t["applies_to"]]
        items = [{"title": f"vuln {kw}", "description": f"{kw} in product"} for kw in texts]
        items += [{"title": "x", "description": "y", "cwe_id": c} for c in mae.CWE_TO_ATTACK]
        for it in items:
            out = mae.enrich_attack_mapping(it)
            for tid in out["attck_technique_ids"]:
                if di.validate_technique(tid)["status"] != "VALID":
                    issues.append((it["title"], tid))
            assert len(set(out["attck_technique_ids"])) == len(out["attck_technique_ids"])
        assert not issues, issues[:5]

    def test_sqli_maps_to_real_parent_via_the_approved_alias_and_is_marked_inference(self):
        out = mae.enrich_attack_mapping({"title": "SQL injection in X", "description": "UNION SELECT via filter",
                                         "cwe_id": "CWE-89"})
        assert "T1190" in out["attck_technique_ids"] and "T1190.001" not in out["attck_technique_ids"]
        for t in out["ttps"]:
            assert t["evidence_state"] == "ANALYST_INFERENCE" and t["behavior_status"] == "HYPOTHESIS_NOT_OBSERVED"
            assert t["observed_behavior"].startswith("NOT OBSERVED") and "v16" not in json.dumps(t)
        assert out["attack_dataset"]["content_hash"]

    def test_sigma_tags_keep_subtechnique_dot_and_drop_unknown_and_retired_ids(self):
        r = sigma.APEXSigmaGenerator().generate("t", "CVE-2026-1", "sqli",
                                                ["T1190", "T1059.001", "T1190.001", "T9999", "T1574.002", "T1059.999"], [], "high")
        assert "attack.t1059.001" in r.tags and "attack.t1059001" not in r.tags
        assert not {"attack.t9999", "attack.t1574.002", "attack.t1059.999", "attack.t1059"} & set(r.tags)
        assert r.tags.count("attack.t1190") == 1

    def test_report_navigator_layer_contains_only_current_ids_and_the_pinned_version(self):
        item = _by_suffix("ffbf724f0ac1")
        item["ttps"] = ["T1190.001", "T1059", "Active Scanning", "T9999", "T1574.002", "T1059.999"]
        page = gen.render_report(item, PREFIX)
        m = re.search(r"href='data:application/json;charset=utf-8,([^']+)'", page)
        assert m, "navigator layer expected for valid techniques"
        layer = json.loads(urllib.parse.unquote(m.group(1)))
        ids = [t["techniqueID"] for t in layer["techniques"]]
        assert set(ids) == {"T1190", "T1059"}
        assert layer["versions"]["attack"] == "19"
        meta = {md["name"]: md["value"] for md in layer["metadata"]}
        assert meta["attack_release"] == "19.2" and len(meta["attack_dataset_sha256"]) == 64

    def test_coverage_navigator_layer_filters_ids_and_uses_the_pinned_version(self):
        from collections import Counter
        import attack_coverage_analytics as cov
        layer = cov.build_navigator_layer(Counter({"T1190": 3, "T1190.001": 2, "T1574.002": 1, "T1059.999": 1, "T1059": 1}), 10)
        assert [t["techniqueID"] for t in layer["techniques"]] == ["T1190", "T1059"]
        assert layer["versions"]["attack"] == "19"

    def test_no_navigator_exporter_hardcodes_an_attack_version_any_more(self):
        for rel in ("scripts/generate_intel_reports.py", "scripts/attack_coverage_analytics.py", "scripts/coverage_gap_analyzer.py",
                    "scripts/enterprise_validation_fabric.py", "agent/integrations/apex_detection_core.py",
                    "agent/product_factory/detection_pack_builder.py"):
            src = (ROOT / rel).read_text(encoding="utf-8")
            assert not re.search(r'"attack"\s*:\s*"\d+"', src), rel

    def test_defensive_matrix_has_no_default_techniques_and_no_blanket_high(self):
        html0 = enh.build_defensive_matrix_section({"mitre_techniques": []})
        assert "T1566" not in html0 and "T1078" not in html0 and "HIGH" not in html0
        html1 = enh.build_defensive_matrix_section({"ttps": ["T1190.001", "T9999", "T1574.002", "T1059.999"]})
        assert "T1190" in html1 and not re.search(r"T9999|T1574|T1059\.999|T1190\.001", html1) and ">HIGH<" not in html1


# ─────────────────────────────────────────────────────────────────────────────
# 3. TLP -- fail-closed anonymous publication (FIRST TLP v2)
# ─────────────────────────────────────────────────────────────────────────────
NO_POLICY = {"legacy_white_treated_as_clear": False, "first_party_public_sources": []}


class TestTlpPublicationPolicy:
    @pytest.mark.parametrize("label", ["TLP:CLEAR", "tlp:clear", " TLP:CLEAR ", "TLP-CLEAR"])
    def test_only_explicit_clear_is_publishable(self, label):
        d = tlp.publication_decision({"tlp": label}, NO_POLICY)
        assert d["allowed"] and d["label"] == "TLP:CLEAR" and d["assignment"] == "explicit"

    @pytest.mark.parametrize("label", ["TLP:GREEN", "TLP:AMBER", "TLP:AMBER+STRICT", "TLP:RED", "tlp:amber+strict"])
    def test_restricted_labels_are_quarantined(self, label):
        d = tlp.publication_decision({"tlp": label}, NO_POLICY)
        assert not d["allowed"] and d["state"] == "QUARANTINE" and d["reason_code"] == "RESTRICTED_LABEL"

    @pytest.mark.parametrize("missing", [None, "", "   ", {}])
    def test_missing_label_is_quarantined(self, missing):
        item = {} if missing == {} else {"tlp": missing}
        assert tlp.publication_decision(item, NO_POLICY)["reason_code"] == "MISSING_LABEL"
        assert tlp.publication_decision("not-a-dict", NO_POLICY)["reason_code"] == "MISSING_LABEL"

    @pytest.mark.parametrize("bad", ["TLP:PURPLE", "CLEAR", "TLP:AMBER STRICT", "TLP:", 5, ["TLP:CLEAR"], {"x": 1}, "TLP:CLEAR; TLP:RED"])
    def test_invalid_label_is_quarantined(self, bad):
        assert tlp.publication_decision({"tlp": bad}, NO_POLICY)["reason_code"] == "INVALID_LABEL"

    def test_legacy_white_is_quarantined_until_the_operator_migrates_it(self):
        assert tlp.publication_decision({"tlp": "TLP:WHITE"}, NO_POLICY)["reason_code"] == "LEGACY_LABEL_UNMIGRATED"
        d = tlp.publication_decision({"tlp": "TLP:WHITE"}, dict(NO_POLICY, legacy_white_treated_as_clear=True))
        assert d["allowed"] and d["assignment"] == "legacy_white_operator_migration"

    APPROVED = [{"source": "cisa-kev", "hosts": ["cisa.gov"]}]

    def test_policy_assignment_only_for_unlabelled_items_of_an_approved_collector(self):
        pol = dict(NO_POLICY, first_party_public_sources=self.APPROVED)
        good = {"source": "CISA-KEV", "source_url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"}
        ok = tlp.publication_decision(good, pol)
        assert ok["allowed"] and ok["assignment"] == "policy_first_party_public_source" and ok["label"] == "TLP:CLEAR"
        assert not tlp.publication_decision({"source": "someone-else", "source_url": "https://www.cisa.gov/x"}, pol)["allowed"]
        # an explicit label always wins over source approval -- third-party content is never relabelled
        for lab in ("TLP:GREEN", "TLP:PURPLE", "TLP:AMBER"):
            assert not tlp.publication_decision(dict(good, tlp=lab), pol)["allowed"], lab

    def test_feed_supplied_source_string_alone_cannot_self_approve(self):
        pol = dict(NO_POLICY, first_party_public_sources=self.APPROVED)
        # spoofed name, no URL / wrong host / look-alike host / userinfo trick / legacy string entry
        for item in ({"source": "cisa-kev"},
                     {"source": "cisa-kev", "source_url": "https://evil.example/cisa.gov"},
                     {"source": "cisa-kev", "source_url": "https://cisa.gov.evil.example/x"},
                     {"source": "cisa-kev", "source_url": "https://notcisa.gov/x"},
                     {"source": "cisa-kev", "source_url": "https://cisa.gov@evil.example/x"},
                     {"source": "cisa-kev", "source_url": "not a url"}):
            d = tlp.publication_decision(item, pol)
            assert not d["allowed"] and d["reason_code"] == "MISSING_LABEL", item
        legacy = dict(NO_POLICY, first_party_public_sources=["cisa-kev"])  # bare-string entries are not an approval
        assert not tlp.publication_decision({"source": "cisa-kev", "source_url": "https://www.cisa.gov/x"}, legacy)["allowed"]

    def test_restricted_upstream_label_is_never_laundered_into_a_clear_dossier(self):
        base = {"id": "agg", "tlp": "TLP:CLEAR"}
        cases = {
            "tlp_label": dict(base, tlp_label="TLP:AMBER"),
            "evidence_chain": dict(base, evidence_chain=[{"source_name": "a", "tlp": "TLP:CLEAR"}, {"source_name": "b", "tlp": "TLP:GREEN"}]),
            "sources": dict(base, sources=[{"name": "x", "tlp_label": "TLP:RED"}]),
            "merged_from": dict(base, merged_from=[{"tlp": "TLP:AMBER+STRICT"}]),
            "invalid_component": dict(base, evidence_chain=[{"tlp": "TLP:BLUE"}]),
            "legacy_component": dict(base, corroborating_sources=[{"tlp": "TLP:WHITE"}]),
        }
        for name, item in cases.items():
            d = tlp.publication_decision(item, NO_POLICY)
            assert not d["allowed"], name
        assert tlp.publication_decision(cases["tlp_label"], NO_POLICY)["reason_code"] == "RESTRICTED_UPSTREAM_LABEL"
        # unlabelled components cannot be proven restricted; an all-CLEAR aggregate still publishes
        ok = dict(base, tlp_label="TLP:CLEAR", evidence_chain=[{"source_name": "a"}, {"tlp": "TLP:CLEAR"}])
        assert tlp.publication_decision(ok, NO_POLICY)["allowed"]
        # an upstream label can only restrict: it never grants publication to an otherwise-quarantined item
        assert not tlp.publication_decision({"id": "u", "evidence_chain": [{"tlp": "TLP:CLEAR"}]}, NO_POLICY)["allowed"]

    def test_decision_never_rewrites_the_item(self):
        item = {"id": "x", "tlp": "TLP:GREEN", "source": "cisa-kev"}
        before = copy.deepcopy(item)
        tlp.publication_decision(item, dict(NO_POLICY, first_party_public_sources=self.APPROVED))
        assert item == before

    def test_policy_file_is_default_deny_and_unreadable_policy_fails_closed(self, tmp_path):
        pol = tlp.load_policy()
        assert pol["first_party_public_sources"] == [] and pol["legacy_white_treated_as_clear"] is False
        raw = json.loads((ROOT / "config" / "tlp_publication_policy.json").read_text(encoding="utf-8"))
        assert raw["default"] == "deny" and raw["rules"]["only_tlp_clear_is_anonymously_publishable"] is True
        for name, body in (("absent.json", None), ("garbage.json", "{not json"), ("wrong.json", '{"first_party_public_sources": "all"}'),
                           ("mixed.json", '{"first_party_public_sources": [1, 2]}'),
                           ("strings.json", '{"first_party_public_sources": ["cisa-kev"]}'),
                           ("nohosts.json", '{"first_party_public_sources": [{"source": "cisa-kev", "hosts": []}]}')):
            p = tmp_path / name
            if body is not None:
                p.write_text(body, encoding="utf-8")
            loaded = tlp.load_policy(p)
            assert loaded == {"legacy_white_treated_as_clear": False, "first_party_public_sources": []}, name

    def test_legacy_helpers_in_dossier_integrity_are_now_fail_closed(self):
        assert di.tlp_public_conflict(None) and di.tlp_public_conflict("TLP:WHITE") and di.tlp_public_conflict("TLP:GREEN")
        assert not di.tlp_public_conflict("TLP:CLEAR")
        assert di.normalize_tlp(None) == "TLP:UNLABELLED" and di.normalize_tlp("junk") == "TLP:INVALID"

    # ---- producer ---------------------------------------------------------------------------------
    @pytest.mark.parametrize("label", [None, "", "TLP:GREEN", "TLP:AMBER", "TLP:AMBER+STRICT", "TLP:RED", "TLP:WHITE", "TLP:PURPLE"])
    def test_producer_refuses_to_render_a_denied_item(self, label):
        item = _by_suffix("ffbf724f0ac1")
        item["tlp"] = label
        with pytest.raises(tlp.PublicationDenied):
            gen.render_report(item, PREFIX)
        with pytest.raises(tlp.PublicationDenied):
            gen.build_report_sections(copy.deepcopy(item))
        with pytest.raises(tlp.PublicationDenied):
            enh.enhance_report_html("<html><body></body></html>", item, "pro")
        assert enh.generate_pdf_report(item, "<html></html>", ROOT / "should-never-be-written.pdf") is False
        assert not (ROOT / "should-never-be-written.pdf").exists()

    def test_published_page_shows_the_decision_label_not_a_silent_clear_default(self):
        item = _by_suffix("ffbf724f0ac1")
        assert "TLP:CLEAR" in visible_text(render(item))
        item.pop("tlp")
        with pytest.raises(tlp.PublicationDenied):
            gen.render_report(item, PREFIX)

    # ---- publisher: the real main() on an isolated tree ---------------------------------------
    def test_publisher_main_writes_only_clear_items_and_flags_existing_restricted_artifacts(self, tmp_path, monkeypatch):
        base = _by_suffix("ffbf724f0ac1")

        def mk(i, label):
            it = copy.deepcopy(base)
            it.update(id=f"intel--{i:024x}", title=f"CVE-2026-{1000+i} Example Product Flaw", timestamp="2026-10-07T10:00:00+00:00",
                      processed_at="2026-10-07T10:00:00+00:00", report_url="")
            it.pop("tlp", None)
            if label is not None:
                it["tlp"] = label
            return it

        items = [mk(1, "TLP:CLEAR"), mk(2, "TLP:GREEN"), mk(3, "TLP:RED"), mk(4, None), mk(5, "TLP:WHITE"), mk(6, "TLP:BOGUS")]
        manifest = tmp_path / "feed.json"
        manifest.write_text(json.dumps(items), encoding="utf-8")
        reports = tmp_path / "reports"
        # a restricted item that is ALREADY public on disk (direct-object access): must be flagged, not silently deleted
        pre = reports / "2026" / "10" / items[1]["id"] / ".." / f"{items[1]['id']}.html"
        (reports / "2026" / "10").mkdir(parents=True)
        (reports / "2026" / "10" / f"{items[1]['id']}.html").write_text("<html>previously published</html>", encoding="utf-8")
        monkeypatch.setattr(gen, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(gen, "REPORTS_ROOT", reports)
        rc = gen.main(["--manifest", str(manifest), "--public-prefix", PREFIX])
        assert rc in (0, None)
        written = {p.name for p in reports.rglob("*.html")}
        assert f"{items[0]['id']}.html" in written                              # CLEAR published
        for denied in items[2:]:
            assert f"{denied['id']}.html" not in written                        # nothing emitted for denied items
        assert (reports / "2026" / "10" / f"{items[1]['id']}.html").read_text(encoding="utf-8") == "<html>previously published</html>"
        saved = {i["id"]: i for i in json.loads(manifest.read_text(encoding="utf-8"))}
        assert items[0]["id"] in saved and saved[items[0]["id"]]["report_url"].startswith("/reports/")
        for denied in items[1:]:                                                # quarantined: not in the published feed at all
            assert denied["id"] not in saved
        q = json.loads((tmp_path / "data" / "quality" / "tlp_quarantine_report.json").read_text(encoding="utf-8"))
        assert q["quarantined"] == 5
        assert {x["id"] for x in q["needing_retraction_review"]} == {items[1]["id"]}
        assert {x["reason_code"] for x in q["items"]} == {"RESTRICTED_LABEL", "MISSING_LABEL", "LEGACY_LABEL_UNMIGRATED", "INVALID_LABEL"}
        assert pre is not None

    def test_enhancer_publisher_skips_denied_items_and_makes_no_pdf(self, tmp_path, monkeypatch):
        base = _by_suffix("ffbf724f0ac1")
        reports = tmp_path / "reports"
        (reports / "2026" / "10").mkdir(parents=True)
        items = []
        for i, label in enumerate(["TLP:CLEAR", "TLP:AMBER", None], 1):
            it = copy.deepcopy(base)
            it.update(id=f"intel--{i:024x}", report_url=f"/reports/2026/10/intel--{i:024x}.html")
            it.pop("tlp", None)
            if label:
                it["tlp"] = label
            (reports / "2026" / "10" / f"intel--{i:024x}.html").write_text("<html><body>ORIGINAL</body></html>", encoding="utf-8")
            items.append(it)
        mpath = tmp_path / "m.json"
        mpath.write_text(json.dumps({"advisories": items}), encoding="utf-8")
        monkeypatch.setattr(enh, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(enh, "REPORTS_ROOT", reports)
        stats = enh.run_enhancement(mpath, "free")
        assert stats["tlp_skipped"] == 2 and stats["enhanced"] == 1
        for i in (2, 3):
            assert (reports / "2026" / "10" / f"intel--{i:024x}.html").read_text(encoding="utf-8") == "<html><body>ORIGINAL</body></html>"
            assert not (reports / "pdf" / f"intel--{i:024x}.pdf").exists()

    # ---- feed writers ---------------------------------------------------------------------------
    def test_governor_keeps_restricted_and_unlabelled_items_out_of_every_static_feed(self, monkeypatch):
        monkeypatch.setattr(gov, "enforce_publication_decision", lambda item: (True, {}))
        items = [{"id": f"i{n}", "title": "t", "tlp": lab, "intelligence_grade": "A"}
                 for n, lab in enumerate(["TLP:CLEAR", "TLP:GREEN", "TLP:AMBER", "TLP:RED", None, "TLP:WHITE"])]
        res = gov.process_feed(items)
        assert [i["id"] for i in res["published"]] == ["i0"]
        for feed in ("feed_public", "feed_mssp", "feed_enterprise"):
            assert all(i["tlp"] == "TLP:CLEAR" for i in res[feed])
        held = [q for q in res["quarantine"] if "TLP" in q["mandates_triggered"]]
        assert {q["id"] for q in held} == {"i1", "i2", "i3", "i4", "i5"}
        assert all(q["block_reasons"].startswith("TLP:") for q in held)

    def test_partition_publishable_for_exports(self):
        ok, held = tlp.partition_publishable([{"id": 1, "tlp": "TLP:CLEAR"}, {"id": 2, "tlp": "TLP:AMBER"}, {"id": 3}], NO_POLICY)
        assert [i["id"] for i in ok] == [1] and {h["id"]: h["reason_code"] for h in held} == {2: "RESTRICTED_LABEL", 3: "MISSING_LABEL"}

    def test_audit_measures_restricted_entries_in_the_static_feeds(self):
        import p0_721_dossier_integrity_audit as audit
        res = audit.audit_tlp()
        assert res["status"] == "MEASURED" and res["total_entries_that_must_not_be_anonymous"] >= 0
        assert set(res["files"]) <= {"feed.json", "feed_public.json", "feed_mssp.json", "feed_enterprise.json"}


# ─────────────────────────────────────────────────────────────────────────────
# 4. STIX ids, severity / KEV / priority attribution
# ─────────────────────────────────────────────────────────────────────────────
class TestIdentifiersSeverityKev:
    @pytest.mark.parametrize("val,ok", [
        ("intel--0a1b2c3d4e5f60718293a4b5", False),
        ("intel--", False), ("", False), (None, False), (123, False),
        ("bundle--911f92e0-2983-4dc3-acac-035709e76d26", True),
        ("vulnerability--911f92e0-2983-4dc3-acac-035709e76d26", True),
        ("Vulnerability--911f92e0-2983-4dc3-acac-035709e76d26", False),
        ("vulnerability--911F92E0-2983-4DC3-ACAC-035709E76D26", False),
        ("vulnerability--911f92e0-2983-6dc3-acac-035709e76d26", False),
    ])
    def test_valid_stix_id(self, val, ok):
        assert di.valid_stix_id(val) is ok

    def test_internal_report_key_never_rendered_as_stix_id(self):
        item = _by_suffix("4336641f-c816-41e7-9fbe-f50ab0c2c056")
        item["id"] = "intel--0a1b2c3d4e5f60718293a4b5"
        t = visible_text(render(item))
        assert "Report ID" in t and "intel--0a1b2c3d4e5f60718293a4b5" in t
        assert re.search(r"STIX 2\.1 ID\s+Not assigned", t)
        item["stix_id"] = "vulnerability--911f92e0-2983-4dc3-acac-035709e76d26"
        assert re.search(r"STIX 2\.1 ID\s+vulnerability--911f92e0", visible_text(render(item)))

    VULN = {"title": "CVE-2026-1 unauthenticated RCE", "description": "d", "severity": "LOW"}

    def test_severity_comes_only_from_cvss_and_never_from_kev_or_the_apex_heuristic(self):
        v = self.VULN
        un = di.severity_basis(v, None, False)
        assert (un["display"], un["rated"], un["kev"], un["prioritized"], un["authoritative"]) == ("UNRATED", False, False, False, False)
        assert un["composite"] == "LOW" and "not a rating" in un["note"] and un["severity_source"] == "none"
        for missing in (0, 0.0, "", "n/a", None, float("nan")):
            assert di.severity_basis(v, missing, False)["display"] == "UNRATED"
        hi = di.severity_basis(v, 9.8, False)
        assert (hi["display"], hi["rated"], hi["composite"], hi["conflict"]) == ("CRITICAL", True, "LOW", True)
        assert hi["severity_source"] == "cvss_reported" and "vector unavailable" in hi["basis"] and "superseded" in hi["note"]
        for score, band in ((0.1, "LOW"), (3.9, "LOW"), (4.0, "MEDIUM"), (6.9, "MEDIUM"), (7.0, "HIGH"), (8.9, "HIGH"), (9.0, "CRITICAL")):
            assert di.severity_basis(v, score, False)["display"] == band

    def test_kev_without_cvss_is_exploitation_evidence_not_a_severity(self):
        b = di.severity_basis(dict(self.VULN, severity="CRITICAL"), None, True)      # pipeline's KEV-policy label CRITICAL
        assert b["display"] == "UNRATED" and b["rated"] is False and b["kev"] is True and b["prioritized"] is True
        assert b["composite"] == "CRITICAL" and "not a severity rating" in b["note"] and "proprietary heuristic" in b["note"]
        assert b["severity_source"] == "none"

    def test_kev_with_cvss_keeps_both_facts_independently_attributable(self):
        b = di.severity_basis(dict(self.VULN, severity="HIGH"), 5.0, True)
        assert (b["display"], b["rated"], b["kev"], b["prioritized"]) == ("MEDIUM", True, True, True)   # KEV does not raise CVSS band
        assert "CVSS 5" in b["basis"] and "CISA KEV listed" in b["basis"]
        assert di.severity_basis(dict(self.VULN, severity="CRITICAL"), 5.0, True)["display"] == "MEDIUM"

    def test_non_vulnerability_records_show_the_apex_label_marked_as_heuristic(self):
        b = di.severity_basis({"title": "Phishing campaign targets bank customers", "description": "credential theft", "severity": "HIGH"}, None, False)
        assert b["display"] == "HIGH" and b["severity_source"] == "apex_heuristic" and b["rated"] is False and b["prioritized"] is True
        assert "APEX composite label" in b["note"]

    @pytest.mark.parametrize("title,expected", [
        ("PHP Composer flaws enable remote command execution", True), ("Magento PolyShell Flaw Enables Unauthenticated Uploads, RCE", True),
        ("Zero-day exploited in the wild", True), ("Phishing campaign targets bank customers", False),
        ("LockBit affiliate arrested", False), ("Quarterly threat landscape report", False),
    ])
    def test_vulnerability_record_detection(self, title, expected):
        assert di.is_vulnerability_record({"title": title, "description": ""}) is expected

    def test_source_stated_conditions_are_quoted_not_invented(self):
        c = di.source_stated_conditions({"description": "An unauthenticated attacker can run arbitrary code. Patch available."})
        assert c and "unauthenticated" in c[0].lower()
        assert di.source_stated_conditions({"description": "Version bump"}) == []

    def test_unrated_unauth_rce_is_neither_low_nor_routine(self):
        for sfx in ("4336641f-c816-41e7-9fbe-f50ab0c2c056", "cd8b9080-1761-4a1a-a092-653fc0ecf9f5", "49e15ebe-9d10-4e51-92a8-72cb3aef4f74"):
            item = _by_suffix(sfx)
            assert item["severity"] == "LOW" and item.get("cvss_score") is None
            t = visible_text(assert_dossier_invariants(item))
            assert "PRIORITY NOT DETERMINED" in t and "CUSTOMER EXPOSURE: UNKNOWN" in t and re.search(r"Severity:\s*UNRATED", t)
            assert "apply patch in routine cycle" not in t.lower()

    def test_kev_listed_cve_without_cvss_page_shows_unrated_severity_plus_kev_priority(self):
        item = _by_suffix("beed0c4d-2598-4224-a532-5dc17d943f47")
        item.pop("cvss_score", None)
        item["severity"] = "CRITICAL"                     # the pipeline's KEV-policy label
        t = visible_text(assert_dossier_invariants(item))
        assert re.search(r"Severity:\s*UNRATED", t) and "KEV CONFIRMED" in t.upper()
        assert "IMMEDIATE PATCH REQUIRED" in t           # operational priority comes from KEV, attributed separately
        assert "not a severity rating" in t and "KEV listed" in t

    def test_rated_and_kev_record_shows_cvss_band_with_kev_as_separate_evidence(self):
        item = _by_suffix("beed0c4d-2598-4224-a532-5dc17d943f47")
        assert item["severity"] == "HIGH" and item["cvss_score"] == 9.8 and item["kev_present"] is True
        t = visible_text(assert_dossier_invariants(item))
        assert "UNRATED" not in t and "KEV CONFIRMED" in t.upper()
        assert re.search(r"Severity:\s*CRITICAL", t) and "superseded" in t

    @pytest.mark.parametrize("legacy", ["NO", "false", "0", "", None])
    def test_legacy_kev_strings_are_not_confirmed_in_header_or_body(self, legacy):
        item = _by_suffix("ffbf724f0ac1")
        item["kev_present"] = legacy
        item["kev"] = legacy
        t = visible_text(render(item)).upper()
        assert "KEV CONFIRMED" not in t and "YES ⚠" not in t

    def test_stale_or_absent_kev_lookup_is_never_presented_as_proof_of_no_exploitation(self):
        t = visible_text(render(_by_suffix("ffbf724f0ac1")))
        assert "No KEV listing found" in t or "no CISA KEV listing was found" in t.replace("\n", " ")
        assert "does not establish that the flaw is not being exploited" in re.sub(r"\s+", " ", t)
        # the record carries no KEV lookup timestamp, so the page must not claim a verified 'not listed' as-of date
        assert not re.search(r"not listed as of", t, re.I)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Rendered-dossier invariants (real fixtures, labelled CLEAR)
# ─────────────────────────────────────────────────────────────────────────────
class TestRenderedDossiers:
    @pytest.mark.parametrize("rid", sorted(_records()))
    @pytest.mark.parametrize("tier", ["free", "pro", "enterprise"])
    def test_real_records_satisfy_all_invariants(self, rid, tier):
        assert_dossier_invariants(_records()[rid], tier)

    def test_generated_pages_carry_no_trial_offer_or_contract_forbidden_pattern(self):
        for item in _records().values():
            for tier in ("free", "pro", "enterprise"):
                page = render(item, tier)
                for label, rx in vcc.FORBIDDEN_PRICE_PATTERNS:
                    assert not rx.search(page), (label, tier)
                assert "/trial" not in page and "Free 7-Day" not in page

    def test_banner_has_no_trial_button_and_no_active_threat_claim(self):
        for tier in ("free", "pro"):
            b = enh.build_monetization_banner(_by_suffix("ffbf724f0ac1"), tier)
            assert "trial" not in b.lower() and "THREAT ACTIVE" not in b
        assert enh.build_monetization_banner(_by_suffix("ffbf724f0ac1"), "enterprise") == ""
        # its IOC numbers are the same qualified numbers every other card shows
        item = _by_suffix("e6c2ae740ffa")
        q = di.qualify_iocs(item["iocs"], item)
        assert f"{q['count']} IOC observable(s), {q['validated_count']} validated" in enh.build_monetization_banner(item, "free")

    def test_contaminated_ioc_list_yields_one_count_everywhere_and_no_value_leak(self):
        item = _by_suffix("4336641f-c816-41e7-9fbe-f50ab0c2c056")
        item["iocs"] = ["CVE-2026-3300", "https://nvd.nist.gov/vuln/detail/CVE-2026-3300", "composer.js", "cyberdudebivash.com",
                        "45.153.204.118", "45.153.204[.]118", "192.168.0.1"]
        free = render(item, "free")
        obs, val = ioc_numbers_in(free)
        assert set(obs) == {1} and set(val) == {0}
        assert "45.153.204.118" not in free and "CVE-2026-3300</td>" not in free
        pro = render(item, "pro")
        obs, val = ioc_numbers_in(pro)
        assert set(obs) == {1} and set(val) == {0}
        assert pro.count("45.153.204.118") == 1
        assert "composer.js</td>" not in pro and "192.168.0.1" not in pro and "UNVERIFIED" in pro and ">OBSERVED<" not in pro

    def test_validated_indicator_is_counted_once_with_corroborated_source_and_shown_to_pro_only(self):
        item = _by_suffix("4336641f-c816-41e7-9fbe-f50ab0c2c056")
        item["source"] = "abuse.ch"
        item["iocs"] = [{"value": "c2.evil.ru", "source": "abuse.ch", "verdict": "malicious"},
                        {"value": "benign-cdn.example.com", "source": "abuse.ch"},
                        {"value": "spoofed.example.org", "source": "CISA KEV", "verdict": "malicious"},
                        "badsite.com"]
        for tier, shown in (("free", False), ("pro", True)):
            page = render(item, tier)
            obs, val = ioc_numbers_in(page)
            assert set(obs) == {4} and set(val) == {1}, (tier, obs, val)
            assert ("c2.evil.ru" in page) is shown
        pro = visible_text(render(item, "pro"))
        assert "SOURCE-CLAIMED (UNCORROBORATED)" in pro and "UNVERIFIED" in pro

    def test_empty_ioc_collection_renders_zero_and_no_placeholder_row(self):
        card = enh.build_ioc_table_section({"iocs": []}, "enterprise")
        t = visible_text(card)
        assert "count: 0" in t and re.search(r"IOC observables:\s*0", t) and re.search(r"validated as malicious:\s*0", t)
        assert "<tr" not in card and "No IOCs in current data feed" not in card

    def test_only_unqualifiable_values_still_zero(self):
        card = enh.build_ioc_table_section({"iocs": ["CVE-2026-1", "x.js"]}, "enterprise")
        assert re.search(r"IOC observables:\s*0", visible_text(card)) and "<tr" not in card
        assert "2 non-indicator" in visible_text(card)

    def test_gated_sections_are_absent_from_public_html_not_just_blurred(self):
        item = _by_suffix("ffbf724f0ac1")
        free, pro = render(item, "free"), render(item, "pro")
        assert "IMMEDIATE TRIAGE" not in free
        assert 'style="filter:blur' not in free
        assert "IMMEDIATE TRIAGE" in pro and "enh-locked" in free

    def test_unattributed_cluster_is_not_presented_as_tracked_actor(self):
        t = visible_text(render(_by_suffix("4336641f-c816-41e7-9fbe-f50ab0c2c056")))
        assert "NO THREAT ACTOR ATTRIBUTED" in t and "Tracking cluster" not in t

    def test_no_detection_readiness_claim_and_conditional_regulatory_language(self):
        t = visible_text(render(_by_suffix("ffbf724f0ac1")))
        assert "none is claimed to be production-ready" in t
        assert "APPLICABILITY: UNKNOWN" in t and "POTENTIALLY RELEVANT" in t and "syntax-validated" not in t

    def test_bis_withheld_without_cvss_epss_kev(self):
        assert gen._compute_bis(5.0, None, None, False, 3, 2)["score"] is None
        assert gen._compute_bis(5.0, 7.5, None, False, 3, 2)["score"] is not None

    def test_html_and_script_payloads_in_source_text_are_escaped(self):
        item = _by_suffix("ffbf724f0ac1")
        item["title"] = 'CVE-2026-1 <script>alert(1)</script> "x" onerror=alert(2)'
        item["description"] = "<img src=x onerror=alert(3)> unauthenticated RCE"
        item["source"] = "abuse.ch"
        item["iocs"] = [{"value": '<script>alert(4)</script>.evil-domain.example.com', "source": "abuse.ch"}]
        item["kill_chain"] = [{"phase": "<script>alert(5)</script>", "description": "<b onmouseover=alert(6)>"}]
        page = render(item, "pro")
        for needle in ("<script>alert", "<img src=x", "<b onmouseover"):
            assert needle not in page

    def test_malformed_unicode_long_titles_and_empty_records_do_not_crash(self):
        weird = {"id": "intel--abc", "tlp": "TLP:CLEAR", "title": ("A" * 6000) + "\x00‮﻿", "description": "\x00" * 10}
        page = render(weird)
        obs, val = ioc_numbers_in(page)
        assert set(obs) <= {0} and set(val) <= {0}
        for partial in ({"id": "intel--x", "tlp": "TLP:CLEAR"}, {"id": "x", "tlp": "TLP:CLEAR", "iocs": None, "ttps": None},
                        {"id": "y", "tlp": "TLP:CLEAR", "severity": None}):
            render(partial)

    def test_enhancement_is_idempotent(self):
        item = _by_suffix("ffbf724f0ac1")
        page = gen.render_report(copy.deepcopy(item), PREFIX)
        once = enh.enhance_report_html(page, item, "pro")
        assert once == enh.enhance_report_html(once, item, "pro")

    def test_kill_chain_requires_source_phases(self):
        card = enh.build_kill_chain_section({"severity": "CRITICAL"})
        assert "ATTACK-CHAIN EVIDENCE: NOT PROVIDED" in card and "Persistence" not in card and "beacon" not in card.lower()
        card2 = enh.build_kill_chain_section({"kill_chain": [{"phase": "Delivery", "description": "phish"}]})
        assert "Delivery" in card2 and "not independently verified" in card2


# ─────────────────────────────────────────────────────────────────────────────
# 6. Commercial-contract drift at its generating source
# ─────────────────────────────────────────────────────────────────────────────
class TestCommercialContract:
    def test_enhancer_source_has_no_trial_wording_or_dead_route_link(self):
        src = (ROOT / "scripts" / "report_enhancer.py").read_text(encoding="utf-8")
        body = re.sub(r"#.*", "", src)                    # comments may explain the deprecation
        assert not re.search(r"\d{1,2}[- ]day\s+(free\s+)?trial|Start\s+(a\s+|your\s+)?(free\s+)?trial|openTrialModal|/api/leads/trial", body, re.I)
        assert "{trial_url}" not in src and "{trial_text}" not in src

    def test_example_dossiers_in_docs_pass_the_repo_wide_buyer_page_scan(self):
        for p in (ROOT / "docs" / "p0_721" / "examples").glob("*.html"):
            txt = p.read_text(encoding="utf-8")
            for label, rx in vcc.FORBIDDEN_PRICE_PATTERNS:
                assert not rx.search(txt), (p.name, label)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Real-manifest sweep (production data, explicitly labelled CLEAR for rendering)
# ─────────────────────────────────────────────────────────────────────────────
def _sample_manifest(step=47):
    return [_clear(x) for x in json.loads(MANIFEST.read_text(encoding="utf-8"))[::step]]


@pytest.mark.skipif(not MANIFEST.exists(), reason="data/apex_enriched_manifest.json not present")
@pytest.mark.parametrize("item", _sample_manifest() if MANIFEST.exists() else [], ids=lambda i: i["id"][-12:])
def test_sampled_production_records_satisfy_invariants(item):
    assert_dossier_invariants(item, "free")


@pytest.mark.skipif(not MANIFEST.exists(), reason="data/apex_enriched_manifest.json not present")
def test_every_unlabelled_production_record_is_denied_publication():
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert items and all(tlp.publication_decision(i, NO_POLICY)["reason_code"] == "MISSING_LABEL" for i in items[:200])


# ─────────────────────────────────────────────────────────────────────────────
# 8. Golden-eight harness (BLOCKED until authorized, sanitized records are supplied)
# ─────────────────────────────────────────────────────────────────────────────
GOLDEN_CVES = ["CVE-2026-71183", "CVE-2026-89191", "CVE-2026-12260", "CVE-2026-4894",
               "CVE-2026-105110", "CVE-2026-107466", "CVE-2026-87426", "CVE-2026-107510"]
_golden = sorted(GOLDEN_DIR.glob("*.json")) if GOLDEN_DIR.exists() else []


@pytest.mark.skipif(not _golden, reason=(
    "BLOCKED (#721): the eight dossier source records are not available to this repository, and the originals are "
    "TLP-restricted (do NOT commit them to this public repo). Supply authorized, sanitized feed records in "
    "tests/fixtures/golden_721/ to enforce them."))
@pytest.mark.parametrize("path", _golden, ids=lambda p: p.stem)
def test_golden_eight_dossiers(path):
    rec = _clear(json.loads(path.read_text(encoding="utf-8")))
    for tier in ("free", "pro"):
        assert_dossier_invariants(rec, tier)


@pytest.mark.skipif(not _golden, reason="BLOCKED: golden fixtures absent")
def test_golden_set_is_complete():
    text = " ".join(p.read_text(encoding="utf-8") for p in _golden)
    assert [c for c in GOLDEN_CVES if c not in text] == []
