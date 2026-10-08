"""P0 #721 -- enterprise dossier intelligence integrity.

Regression + negative-control tests for the evidence rules in
scripts/dossier_integrity.py and their wiring into the live dossier renderers
(scripts/generate_intel_reports.py, scripts/report_enhancer.py) and the ATT&CK
mapping engine (scripts/apex_mitre_attack_engine.py).

Fixtures
  * tests/fixtures/dossier_p0_721_real_records.json -- verbatim production feed
    records (NOT the eight issue-#721 dossiers: those originals are not in the
    repository). They reproduce the same defect classes (unrated unauthenticated
    RCE/SQLi labelled LOW, contaminated IOC lists, KEV+CVSS-rated control).
  * tests/fixtures/golden_721/*.json -- drop the eight originals here (one
    feed record per file) and test_golden_eight_* starts enforcing them.
"""
from __future__ import annotations

import copy
import html as _html
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
import apex_mitre_attack_engine as mae  # noqa: E402
import importlib.util  # noqa: E402

# A byte-for-byte duplicate of this module also sits at the repo root (no importers; flagged
# MERGE in the #721 register) -- load the canonical scripts/ copy explicitly, never by name.
_spec = importlib.util.spec_from_file_location("scripts_apex_sigma_templates", ROOT / "scripts" / "apex_sigma_templates.py")
sigma = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sigma)
import generate_intel_reports as gen  # noqa: E402
import report_enhancer as enh  # noqa: E402

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


def _records():
    return {r["id"]: r for r in json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]}


def _by_suffix(sfx):
    return copy.deepcopy(next(r for i, r in _records().items() if i.endswith(sfx)))


def render(item, tier="free"):
    page = gen.render_report(copy.deepcopy(item), PREFIX)
    return enh.enhance_report_html(page, copy.deepcopy(item), tier)


def visible_text(page):
    page = re.sub(r"<(style|script).*?</\1>", " ", page, flags=re.S | re.I)
    return _html.unescape(re.sub(r"<[^>]+>", " ", page))


def ioc_counts_in(page):
    """Every IOC count a customer can see on the page."""
    t = visible_text(page)
    pats = [r"IOCs?:\s*(\d+)", r"IOC Count\s+(\d+)", r"IOC Density\s+(\d+)\s+indicators",
            r"Qualified indicators:\s*(\d+)", r"(\d+)\s+indicator\(s\)\s+of compromise recorded",
            r"(\d+)\s+qualified indicator\(s\) recorded", r"(\d+)\s+QUALIFIED IOCs",
            r"(\d+)\s*/\s*\d+\s*IOCs?"]
    out = []
    for p in pats:
        out += [int(x) for x in re.findall(p, t)]
    return out


# phrases the old fixed templates emitted for EVERY advisory
FORBIDDEN_FABRICATIONS = [
    "beacon interval 60s", "Implant beacons to C2", "Backdoor/RAT installed", "OSINT collection on target",
    "re-generated C2 infrastructure", "No IOCs in current data feed", "T1190.001",
    "Breach notification obligations may apply", "FAIR-aligned", "500-advisory rolling baseline",
    "within 4–6 hours of exploitation",
]


def assert_dossier_invariants(item, tier="free"):
    page = render(item, tier)
    text = visible_text(page)
    # 1. one IOC count, everywhere
    counts = set(ioc_counts_in(page))
    assert len(counts) <= 1, f"IOC count mismatch across sections: {sorted(counts)}"
    expected = di.qualify_iocs(item.get("iocs"))["count"]
    if counts:
        assert counts == {expected}, f"page shows {counts}, qualified count is {expected}"
    # 2. no fabricated template claims
    for bad in FORBIDDEN_FABRICATIONS:
        assert bad not in text and bad not in page, f"fabricated claim present: {bad!r}"
    assert not re.search(r"\bAPPLIES\b", text)
    # 3. no invalid ATT&CK id anywhere in the page (incl. Navigator data-URI layer)
    for tid in set(re.findall(r"\bT\d{4}\.\d{3}\b", text + urllib.parse.unquote(page))):
        assert di.validate_technique(tid)["status"] == "VALID", f"invalid ATT&CK id rendered: {tid}"
    # 4. an internal key is never presented as a STIX id
    assert not re.search(r"STIX ID\s*(?:intel--|intrusion-set--)", text)
    # 5. LOW/MEDIUM/etc. is never shown for an unrated vulnerability record
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
    if cvss not in (None, "", 0) and di.is_vulnerability_record(item) and not kev:
        band = di._ste.cvss_rating(float(cvss))
        assert re.search(rf"Severity:\s*{band}\b", text), f"CVSS {cvss} should display as {band}"
    return page


# ─────────────────────────────────────────────────────────────────────────────
# 1. IOC qualification (negative controls)
# ─────────────────────────────────────────────────────────────────────────────
class TestIocQualification:
    def test_empty_none_and_non_list_are_zero(self):
        for raw in ([], None, "", 0, {}, "not-a-list"):
            q = di.qualify_iocs(raw)
            assert q["count"] == 0 and q["actionable"] == [] and q["rejected"] == []

    def test_cve_ids_and_advisory_urls_are_references_not_iocs(self):
        q = di.qualify_iocs(["CVE-2026-3300", "cve-2026-0001",
                             "https://nvd.nist.gov/vuln/detail/CVE-2026-3300",
                             "https://www.cisa.gov/notification"])
        assert q["count"] == 0
        assert {r["reason_class"] for r in q["rejected"]} <= {"cve_reference", "contextual_reference"}

    def test_filenames_software_names_and_platform_domains_not_counted(self):
        q = di.qualify_iocs(["composer.js", "RegSvcs.exe", "worddecoder.decodeheader",
                             "alf.io", "cyberdudebivash.com", "api.cyberdudebivash.com"])
        assert q["count"] == 0 and len(q["rejected"]) == 6

    def test_private_malformed_and_version_strings_rejected(self):
        q = di.qualify_iocs(["192.168.1.10", "10.0.0.1", "999.1.1.1", "12.01.01.37", "", "   ", None, {"value": ""}])
        assert q["count"] == 0

    def test_valid_indicators_counted_and_original_shape_preserved(self):
        raw = ["45.153.204.118", {"type": "domain", "value": "update.microsoft-cdn.net", "source": "feedX"},
               "a" * 64]
        q = di.qualify_iocs(raw)
        assert q["count"] == 3
        assert q["actionable"][0] == "45.153.204.118"          # legacy bare string stays a string
        assert isinstance(q["actionable"][1], dict) and q["actionable"][1]["evidence_state"] == "SOURCE_REPORTED"

    def test_duplicates_collapse_across_case_defang_and_root_dot(self):
        q = di.qualify_iocs(["45.153.204.118", "45.153.204[.]118", "Evil-Login.example.com",
                             "evil-login.example.com.", "EVIL-LOGIN.EXAMPLE.COM"])
        assert q["count"] == 2 and q["duplicates"] == 3

    def test_generated_candidates_are_never_counted(self):
        q = di.qualify_iocs([{"type": "ipv4", "value": "45.153.204.118", "generated": True},
                             {"type": "ipv4", "value": "45.153.204.119"}])
        assert q["count"] == 1 and len(q["generated"]) == 1

    def test_observed_requires_marker_and_source(self):
        assert di.ioc_evidence_state({"value": "x"}) == "UNVERIFIED"
        assert di.ioc_evidence_state("1.2.3.4") == "UNVERIFIED"
        assert di.ioc_evidence_state({"value": "x", "source": "s"}) == "SOURCE_REPORTED"
        assert di.ioc_evidence_state({"value": "x", "observed_in_wild": True}) == "UNVERIFIED"   # no source
        assert di.ioc_evidence_state({"value": "x", "observed_in_wild": True, "source": "s"}) == "OBSERVED"
        assert di.ioc_evidence_state({"value": "x", "source": "s", "generated": True}) == "GENERATED"

    def test_count_always_equals_len_actionable(self):
        for item in _records().values():
            q = di.qualify_iocs(item.get("iocs"))
            assert q["count"] == len(q["actionable"])
            assert sum(q["by_state"].values()) == q["count"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. ATT&CK authority
# ─────────────────────────────────────────────────────────────────────────────
class TestAttack:
    def test_t1190_has_no_subtechniques(self):
        assert di.validate_technique("T1190")["status"] == "VALID"
        r = di.validate_technique("T1190.001")
        assert r["status"] == "SUBTECHNIQUE_NOT_DEFINED" and r["parent_id"] == "T1190"
        assert di.canonical_technique_id("T1190.001") == "T1190"

    @pytest.mark.parametrize("bad", ["", "foo", "T12", "T1190.1", "T9999", "TA0001", None, 1190])
    def test_malformed_or_unknown_ids_are_never_publishable(self, bad):
        assert di.canonical_technique_id(bad) is None

    def test_official_names_not_invented(self):
        assert di.technique_name("T1190") == "Exploit Public-Facing Application"
        assert di.technique_name("T9999") is None
        assert enh._mitre_name("T9999").startswith("Unvalidated")

    def test_names_pass_through_ids_are_canonicalised(self):
        out, rej = di.filter_valid_techniques(["Active Scanning", "T1190.001", "T9999", "T1190", "T1059"])
        assert out == ["Active Scanning", "T1190", "T1059"]
        assert [r["id"] for r in rej] == ["T9999"]

    def test_engine_publishes_only_valid_ids_for_every_library_keyword_and_cwe(self):
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

    def test_sqli_maps_to_real_parent_technique_and_is_marked_inference(self):
        out = mae.enrich_attack_mapping({"title": "SQL injection in X", "description": "UNION SELECT via filter",
                                         "cwe_id": "CWE-89"})
        ids = out["attck_technique_ids"]
        assert "T1190" in ids and "T1190.001" not in ids
        for t in out["ttps"]:
            assert t["evidence_state"] == "ANALYST_INFERENCE"
            assert t["behavior_status"] == "HYPOTHESIS_NOT_OBSERVED"
            assert t["observed_behavior"].startswith("NOT OBSERVED")
            assert "v16" not in json.dumps(t)

    def test_sigma_tags_keep_subtechnique_dot_and_drop_unknown_ids(self):
        r = sigma.APEXSigmaGenerator().generate("t", "CVE-2026-1", "sqli",
                                                ["T1190", "T1059.001", "T1190.001", "T9999"], [], "high")
        assert "attack.t1059.001" in r.tags and "attack.t1059001" not in r.tags
        assert "attack.t9999" not in r.tags
        assert r.tags.count("attack.t1190") == 1

    def test_navigator_layer_contains_only_valid_ids(self):
        item = _by_suffix("ffbf724f0ac1")
        item["ttps"] = ["T1190.001", "T1059", "Active Scanning", "T9999"]
        page = gen.render_report(item, PREFIX)
        m = re.search(r"href='data:application/json;charset=utf-8,([^']+)'", page)
        assert m, "navigator layer expected for valid techniques"
        layer = json.loads(urllib.parse.unquote(m.group(1)))
        ids = [t["techniqueID"] for t in layer["techniques"]]
        assert set(ids) <= {"T1190", "T1059"} and ids
        assert all(di.validate_technique(i)["status"] == "VALID" for i in ids)
        assert any(md["name"] == "attack_dataset_sha256" for md in layer["metadata"])

    def test_defensive_matrix_has_no_default_techniques_and_no_blanket_high(self):
        html0 = enh.build_defensive_matrix_section({"mitre_techniques": []})
        assert "T1566" not in html0 and "T1078" not in html0 and "HIGH" not in html0
        html1 = enh.build_defensive_matrix_section({"ttps": ["T1190.001", "T9999"]})
        assert "T1190" in html1 and "T9999" not in html1 and "T1190.001" not in html1
        assert ">HIGH<" not in html1

    def test_dataset_pin_is_recorded_and_no_release_number_invented(self):
        pin = di.attack_dataset_pin()
        assert pin["available"] and pin["content_hash"] and pin["technique_count"] > 600
        assert pin["attack_release"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. STIX ids, severity basis, TLP
# ─────────────────────────────────────────────────────────────────────────────
class TestIdentifiersSeverityTlp:
    @pytest.mark.parametrize("val,ok", [
        ("intel--0a1b2c3d4e5f60718293a4b5", False),                       # internal key shape from #721
        ("intel--", False), ("", False), (None, False), (123, False),
        ("bundle--911f92e0-2983-4dc3-acac-035709e76d26", True),
        ("vulnerability--911f92e0-2983-4dc3-acac-035709e76d26", True),
        ("Vulnerability--911f92e0-2983-4dc3-acac-035709e76d26", False),   # type must be lowercase
        ("vulnerability--911F92E0-2983-4DC3-ACAC-035709E76D26", False),   # uuid must be lowercase
        ("vulnerability--911f92e0-2983-6dc3-acac-035709e76d26", False),   # bad version nibble
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

    def test_severity_basis_matrix(self):
        vuln = {"title": "CVE-2026-1 unauthenticated RCE", "description": "d", "severity": "LOW"}
        un = di.severity_basis(vuln, None, False)
        assert (un["authoritative"], un["display"], un["composite"]) == (False, "UNRATED", "LOW")
        assert "not a rating" in un["note"]
        for missing in (0, 0.0, "", "n/a"):                      # zero/blank/garbage CVSS is missing, never a rating
            assert di.severity_basis(vuln, missing, False)["display"] == "UNRATED"
        hi = di.severity_basis(vuln, 9.8, False)                  # CVSS band supersedes a contradicting composite label
        assert (hi["display"], hi["composite"], hi["conflict"]) == ("CRITICAL", "LOW", True)
        assert "superseded" in hi["note"] and "vector unavailable" in hi["basis"]
        ok = di.severity_basis(dict(vuln, severity="CRITICAL"), 9.8, False)
        assert ok["display"] == "CRITICAL" and ok["conflict"] is False and ok["note"] == ""
        for score, band in ((0.1, "LOW"), (3.9, "LOW"), (4.0, "MEDIUM"), (6.9, "MEDIUM"), (7.0, "HIGH"), (8.9, "HIGH"), (9.0, "CRITICAL")):
            assert di.severity_basis(vuln, score, False)["display"] == band
        assert di.severity_basis(vuln, None, True)["authoritative"] is True
        kv = di.severity_basis(dict(vuln, severity="HIGH"), 9.8, True)     # KEV may only raise, never lower
        assert (kv["display"], kv["conflict"]) == ("CRITICAL", True)
        assert di.severity_basis(dict(vuln, severity="CRITICAL"), 5.0, True)["display"] == "CRITICAL"
        assert di.severity_basis(dict(vuln, severity="HIGH"), None, True)["display"] == "HIGH"
        phish = {"title": "Phishing campaign targets bank customers", "description": "credential theft", "severity": "HIGH"}
        assert di.severity_basis(phish, None, False)["display"] == "HIGH"   # not a vulnerability record

    @pytest.mark.parametrize("title,expected", [
        ("PHP Composer flaws enable remote command execution", True),
        ("Magento PolyShell Flaw Enables Unauthenticated Uploads, RCE", True),
        ("Zero-day exploited in the wild", True),
        ("Phishing campaign targets bank customers", False),
        ("LockBit affiliate arrested", False),
        ("Quarterly threat landscape report", False),
    ])
    def test_vulnerability_record_detection(self, title, expected):
        assert di.is_vulnerability_record({"title": title, "description": ""}) is expected

    def test_source_stated_conditions_are_quoted_not_invented(self):
        c = di.source_stated_conditions({"description": "An unauthenticated attacker can run arbitrary code. Patch available."})
        assert c and "unauthenticated" in c[0].lower()
        assert di.source_stated_conditions({"description": "Version bump"}) == []

    def test_unrated_unauth_rce_is_neither_low_nor_routine(self):
        for sfx in ("4336641f-c816-41e7-9fbe-f50ab0c2c056", "cd8b9080-1761-4a1a-a092-653fc0ecf9f5",
                    "49e15ebe-9d10-4e51-92a8-72cb3aef4f74"):
            item = _by_suffix(sfx)
            assert item["severity"] == "LOW" and item.get("cvss_score") is None   # real fixture precondition
            page = assert_dossier_invariants(item)
            t = visible_text(page)
            assert "PRIORITY NOT DETERMINED" in t and "CUSTOMER EXPOSURE: UNKNOWN" in t
            assert "Apply patch in routine cycle".lower() not in t.lower()
            assert re.search(r"Severity:\s*UNRATED", t)

    def test_rated_and_kev_record_keeps_its_severity(self):
        item = _by_suffix("beed0c4d-2598-4224-a532-5dc17d943f47")
        assert item["severity"] == "HIGH" and item["cvss_score"] == 9.8 and item["kev_present"] is True
        t = visible_text(assert_dossier_invariants(item))
        assert "UNRATED" not in t and "KEV CONFIRMED" in t.upper()
        assert re.search(r"Severity:\s*CRITICAL", t) and "superseded" in t     # no 'HIGH' beside CVSS 9.8

    @pytest.mark.parametrize("legacy", ["NO", "false", "0", "", None])
    def test_legacy_kev_strings_are_not_confirmed_in_header_or_body(self, legacy):
        item = _by_suffix("ffbf724f0ac1")
        item["kev_present"] = legacy
        item["kev"] = legacy
        page = render(item)
        t = visible_text(page).upper()
        assert "KEV CONFIRMED" not in t and "YES ⚠" not in t

    def test_tlp_public_conflict(self):
        assert not di.tlp_public_conflict(None)
        assert not di.tlp_public_conflict("TLP:CLEAR") and not di.tlp_public_conflict("tlp-white")
        for t in ("TLP:GREEN", "TLP:AMBER", "TLP:RED", "TLP:AMBER+STRICT"):
            assert di.tlp_public_conflict(t)
        item = _by_suffix("ffbf724f0ac1")
        assert "PUBLICATION REVIEW REQUIRED" not in visible_text(render(item))
        item["tlp"] = "TLP:GREEN"
        t = visible_text(render(item))
        assert "PUBLICATION REVIEW REQUIRED" in t and "TLP:GREEN" in t   # label preserved, never silently relabelled


# ─────────────────────────────────────────────────────────────────────────────
# 4. Rendered-dossier invariants (real fixtures)
# ─────────────────────────────────────────────────────────────────────────────
class TestRenderedDossiers:
    @pytest.mark.parametrize("rid", sorted(_records()))
    @pytest.mark.parametrize("tier", ["free", "pro"])
    def test_real_records_satisfy_all_invariants(self, rid, tier):
        assert_dossier_invariants(_records()[rid], tier)

    def test_contaminated_ioc_list_yields_one_count_everywhere_and_no_value_leak(self):
        item = _by_suffix("4336641f-c816-41e7-9fbe-f50ab0c2c056")
        item["iocs"] = ["CVE-2026-3300", "https://nvd.nist.gov/vuln/detail/CVE-2026-3300", "composer.js",
                        "cyberdudebivash.com", "45.153.204.118", "45.153.204[.]118", "192.168.0.1"]
        free = render(item, "free")
        assert set(ioc_counts_in(free)) == {1}
        assert "45.153.204.118" not in free                      # public tier: IOC values never emitted
        assert "CVE-2026-3300</td>" not in free
        pro = render(item, "pro")
        assert set(ioc_counts_in(pro)) == {1}
        assert pro.count("45.153.204.118") == 1                   # deduplicated, shown once
        assert "composer.js</td>" not in pro and "192.168.0.1" not in pro
        assert "UNVERIFIED" in pro                                # provenance not recorded -> never OBSERVED
        assert ">OBSERVED<" not in pro

    def test_empty_ioc_collection_renders_zero_and_no_placeholder_row(self):
        card = enh.build_ioc_table_section({"iocs": []}, "enterprise")
        t = visible_text(card)
        assert "count: 0" in t and re.search(r"Qualified indicators:\s*0", t)
        assert "<tr" not in card and "No IOCs in current data feed" not in card

    def test_only_unqualifiable_values_still_zero(self):
        card = enh.build_ioc_table_section({"iocs": ["CVE-2026-1", "x.js"]}, "enterprise")
        assert re.search(r"Qualified indicators:\s*0", visible_text(card)) and "<tr" not in card
        assert "2 non-indicator" in visible_text(card)

    def test_gated_sections_are_absent_from_public_html_not_just_blurred(self):
        item = _by_suffix("ffbf724f0ac1")
        free, pro = render(item, "free"), render(item, "pro")
        assert "IMMEDIATE TRIAGE" not in free
        assert 'style="filter:blur' not in free        # the old CSS-blur wrapper around still-present content
        assert "IMMEDIATE TRIAGE" in pro
        assert "enh-locked" in free

    def test_unattributed_cluster_is_not_presented_as_tracked_actor(self):
        t = visible_text(render(_by_suffix("4336641f-c816-41e7-9fbe-f50ab0c2c056")))
        assert "NO THREAT ACTOR ATTRIBUTED" in t and "Tracking cluster" not in t

    def test_no_detection_readiness_claim_and_conditional_regulatory_language(self):
        t = visible_text(render(_by_suffix("ffbf724f0ac1")))
        assert "none is claimed to be production-ready" in t
        assert "APPLICABILITY: UNKNOWN" in t and "POTENTIALLY RELEVANT" in t
        assert "syntax-validated" not in t

    def test_bis_withheld_without_cvss_epss_kev(self):
        assert gen._compute_bis(5.0, None, None, False, 3, 2)["score"] is None
        assert gen._compute_bis(5.0, 7.5, None, False, 3, 2)["score"] is not None

    def test_html_and_script_payloads_in_source_text_are_escaped(self):
        item = _by_suffix("ffbf724f0ac1")
        item["title"] = 'CVE-2026-1 <script>alert(1)</script> "x" onerror=alert(2)'
        item["description"] = "<img src=x onerror=alert(3)> unauthenticated RCE"
        item["iocs"] = ['<script>alert(4)</script>.evil-domain.example.com']
        item["kill_chain"] = [{"phase": "<script>alert(5)</script>", "description": "<b onmouseover=alert(6)>"}]
        page = render(item, "pro")
        for needle in ("<script>alert", "<img src=x", "<b onmouseover"):
            assert needle not in page

    def test_malformed_unicode_long_titles_and_empty_records_do_not_crash(self):
        weird = {"id": "intel--abc", "title": ("A" * 6000) + "\x00‮﻿", "description": "\x00" * 10}
        page = render(weird)
        assert "IOCs: " in visible_text(page) and set(ioc_counts_in(page)) <= {0}
        for partial in ({"id": "intel--x"}, {"id": "x", "iocs": None, "ttps": None}, {"id": "y", "severity": None}):
            render(partial)

    def test_enhancement_is_idempotent(self):
        item = _by_suffix("ffbf724f0ac1")
        page = gen.render_report(copy.deepcopy(item), PREFIX)
        once = enh.enhance_report_html(page, item, "pro")
        twice = enh.enhance_report_html(once, item, "pro")
        assert once == twice

    def test_kill_chain_requires_source_phases(self):
        card = enh.build_kill_chain_section({"severity": "CRITICAL"})
        assert "NONE REPORTED" in card and "Persistence" not in card and "beacon" not in card.lower()
        card2 = enh.build_kill_chain_section({"kill_chain": [{"phase": "Delivery", "description": "phish"}]})
        assert "Delivery" in card2 and "not independently verified" in card2


# ─────────────────────────────────────────────────────────────────────────────
# 5. Real-manifest sweep (production data, not synthetic)
# ─────────────────────────────────────────────────────────────────────────────
def _sample_manifest(step=47):
    return json.loads(MANIFEST.read_text(encoding="utf-8"))[::step]


@pytest.mark.skipif(not MANIFEST.exists(), reason="data/apex_enriched_manifest.json not present")
@pytest.mark.parametrize("item", _sample_manifest() if MANIFEST.exists() else [], ids=lambda i: i["id"][-12:])
def test_sampled_production_records_satisfy_invariants(item):
    assert_dossier_invariants(item, "free")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Golden-eight harness (BLOCKED until the originals are supplied)
# ─────────────────────────────────────────────────────────────────────────────
GOLDEN_CVES = ["CVE-2026-71183", "CVE-2026-89191", "CVE-2026-12260", "CVE-2026-4894",
               "CVE-2026-105110", "CVE-2026-107466", "CVE-2026-87426", "CVE-2026-107510"]
_golden = sorted(GOLDEN_DIR.glob("*.json")) if GOLDEN_DIR.exists() else []


@pytest.mark.skipif(not _golden, reason=(
    "BLOCKED (#721): the eight dossier source records are not in the repository or the issue. "
    "Place one feed record per file in tests/fixtures/golden_721/ to enforce them."))
@pytest.mark.parametrize("path", _golden, ids=lambda p: p.stem)
def test_golden_eight_dossiers(path):
    rec = json.loads(path.read_text(encoding="utf-8"))
    for tier in ("free", "pro"):
        assert_dossier_invariants(rec, tier)


@pytest.mark.skipif(not _golden, reason="BLOCKED: golden fixtures absent")
def test_golden_set_is_complete():
    text = " ".join(p.read_text(encoding="utf-8") for p in _golden)
    assert [c for c in GOLDEN_CVES if c not in text] == []
