"""P0 R16: regression and negative controls for source-level preview gate.

The source gate must remain fail-closed without false-negative results when
legitimate route implementation grows beyond 2,000 characters.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from feed_contract_validator import preview_envelope_from_worker_route  # noqa: E402


def _route(preview_field="preview: {\n        items, total_preview: items.length,\n      },",
           status='"ok"', filler=""):
    return (
        '  if (path === "/api/preview" || path === "/api/preview/") {\n'
        + filler
        + '    return jsonResp({\n'
        + f'      status: {status},\n'
        + f'      {preview_field}\n'
        + '    }, 200);\n'
        + '  }\n'
        + '  // --- /api/feed ---\n'
    )


def test_actual_worker_source_contract_passes_both_checks():
    source = (
        Path(__file__).resolve().parent.parent
        / "workers" / "intel-gateway" / "src" / "index.js"
    ).read_text(encoding="utf-8")
    assert preview_envelope_from_worker_route(source) == (True, True)


def test_legitimate_preview_beyond_old_2000_char_slice_is_accepted():
    filler = "    // bounded pagination and source provenance\n" * 125
    assert len(filler) > 2000
    assert preview_envelope_from_worker_route(_route(filler=filler)) == (True, True)


def test_inline_payload_without_total_preview_fails_shape():
    assert preview_envelope_from_worker_route(
        _route(preview_field="preview: {\n        items,\n      },")
    ) == (False, True)


def test_flat_success_payload_cannot_pass_nested_contract():
    assert preview_envelope_from_worker_route(
        _route(preview_field="items, total_preview: 3,")
    ) == (False, False)


def test_wrong_status_cannot_pass_even_with_nested_preview():
    assert preview_envelope_from_worker_route(_route(status='"failed"')) == (False, False)


def test_unrelated_route_does_not_satisfy_missing_preview_response():
    fake = (
        _route(preview_field="error: 'backend_unavailable',")
        + '  if (path === "/api/feed") {\n'
        + '    return jsonResp({ status: "ok", preview: { items, total_preview: 3 } });\n'
        + '  }\n'
    )
    assert preview_envelope_from_worker_route(fake) == (False, False)


def test_comment_only_preview_contract_does_not_pass():
    fake = (
        '  if (path === "/api/preview") {\n'
        '    // return jsonResp({ status: "ok", preview: { items, total_preview: 3 } });\n'
        '    return jsonResp({error:"unavailable"}, 503);\n'
        '  }\n'
    )
    assert preview_envelope_from_worker_route(fake) == (False, False)


def test_named_preview_payload_with_explicit_nesting_passes():
    code = (
        '  if (path === "/api/preview") {\n'
        '    const previewPayload = { items, total_preview: items.length };\n'
        '    return jsonResp({ status: "ok", preview: previewPayload });\n'
        '  }\n'
    )
    assert preview_envelope_from_worker_route(code) == (True, True)


def test_named_preview_payload_without_fields_fails():
    code = (
        '  if (path === "/api/preview") {\n'
        '    const previewPayload = { items };\n'
        '    return jsonResp({ status: "ok", preview: previewPayload });\n'
        '  }\n'
    )
    assert preview_envelope_from_worker_route(code) == (False, True)
