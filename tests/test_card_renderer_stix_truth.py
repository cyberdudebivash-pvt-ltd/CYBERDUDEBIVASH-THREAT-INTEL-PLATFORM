"""P0 R15 #721: customer-visible STIX truth, preserving the commercial card.

The feed's legacy `intel--...` advisory key is not a STIX 2.1 object ID.
Never claim the display card itself has a verified STIX bundle merely
because its identifier uses the historical `stix_id` field.
"""
from pathlib import Path

CARD = (Path(__file__).resolve().parents[1] / "js" / "card_renderer.js").read_text(encoding="utf-8")


def test_card_never_certifies_a_bundle_without_validated_export_evidence():
    assert "STIX 2.1 Verified Bundle" not in CARD
    assert "✓ STIX 2.1" not in CARD
    assert 'title="SENTINEL APEX advisory reference; exported STIX objects are validated separately"' in CARD
    assert "INTEL ADVISORY" in CARD


def test_original_intelligence_card_and_copy_identifier_survive():
    assert 'class="sapx-trust-badge sapx-trust-stix"' in CARD
    assert 'class="sapx-stix-id"' in CARD
    assert 'data-full-id="${esc(item.stix_id)}"' in CARD
    assert 'title="Advisory reference: ${esc(item.stix_id)} — click to copy"' in CARD
    assert "copyStixId(this)" in CARD


def test_paid_stix_unlock_and_download_controls_are_preserved():
    assert "item.stix_bundle_locked" in CARD
    assert "item.stix_bundle_upgrade_url" in CARD
    assert "item.stix_bundle_url" in CARD
    assert "sapx-stix-bundle-locked" in CARD
    assert "sapx-stix-bundle-link" in CARD


def test_report_and_mitre_indicators_remain_present():
    assert "renderTrustFooter(item)" in CARD
    assert "item.has_ttps" in CARD
    assert "sapx-trust-mitre" in CARD
    assert "sapx-report-cta" in CARD
