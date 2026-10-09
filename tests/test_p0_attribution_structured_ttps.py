"""P0 sentinel-blogger #2519: mixed dictionary/string ATT&CK TTP input must not crash.

The real 2026-10-08 Stage 2.4 crash was
TypeError: sequence item 0: expected str instance, dict found
from apex_attribution_engine_v2._text(), followed by a latent unhashable dict
failure in the S3 TTP set. These tests are purely offline negative controls.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import apex_attribution_engine_v2 as attribution


def test_attack_id_extraction_mixed_types_without_inventing_ids():
    sample = [
        "T1190", "t1566.001", {"technique_id": "T1190"},
        {"id": "T1566.001", "name": "Spearphishing Attachment"},
        {"name": "No technique evidence"}, {"technique_id": "not-a-technique"},
        {}, 23, None, ["T1059"], {"id": ["T1486"]},
    ]
    assert attribution._technique_ids(sample) == {"T1190", "T1566.001"}
    assert attribution._technique_ids({"id": "T1190"}) == set()
    assert attribution._technique_ids(None) == set()


def test_text_normalization_ignores_dict_repr_and_non_string_tags():
    item = {
        "title": "Generic security update", "description": "No known actor attributed",
        "tags": ["defensive", {"arbitrary": "fabricated attribution token"}, None],
        "ttps": [{"technique_id": "T1190", "name": "Exploit Public-Facing Application"}, "T1566.001", {"unknown": "discarded"}],
        "cve_ids": ["CVE-2026-1000", {"bogus": "not a CVE"}],
    }
    text = attribution._text(item)
    assert "t1190" in text
    assert "t1566.001" in text
    assert "defensive" in text
    assert "fabricated attribution token" not in text
    assert "discarded" not in text
    assert "{'" not in text


def test_s3_actor_overlap_works_on_dictionary_ttps_without_false_names():
    item = {
        "title": "Generic advisory", "description": "No actor identity evidence",
        "ttps": [{"technique_id": "T1190"}, {"technique_id": "T1566.001"}, {"technique_id": "TINVALID"}, None],
        "actor_ttps": [{"id": "T1190"}],
    }
    actor = {"name_patterns": [], "ttps": ["T1190"], "sectors": []}
    score, signals = attribution._score_actor(attribution._text(item), item, "unit-fixture", actor)
    assert 0 < score < attribution.THRESHOLD
    assert any(str(x).startswith("S3:ttp_overlap") for x in signals)
    assert not any(str(x).startswith("S1:name_match") for x in signals)


def test_live_pipeline_shape_enrichment_does_not_throw_or_fabricate_attribution():
    item = {
        "id": "intel--test-mixed-ttp-shape", "title": "Generic security bulletin",
        "description": "No named threat actor supported by this source.",
        "source": "unattributed-source", "ttps": [
            {"technique_id": "T1190", "name": "Exploit Public-Facing Application"},
            {"technique_id": "T1566.001", "name": "Spearphishing Attachment"},
        ],
        "actor_ttps": [{"id": "T1190"}],
        "tags": ["defensive-review", {"unsupported": "do-not-score"}],
        "cve_ids": ["CVE-2026-1000"],
    }
    result = attribution.enrich_item(item)
    assert isinstance(result, dict)
    assert result["id"] == item["id"]
    assert isinstance(result["actor_confidence"], (int, float))
    assert result["actor_confidence"] < attribution.THRESHOLD
    assert result.get("attribution_method") != "verified_actor_name"
