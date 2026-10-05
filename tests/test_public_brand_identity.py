from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "CYBERDUDEBIVASH ECOSYSTEM®"

# Build retired identities without embedding the complete personal-name literal
# in this guard itself, so the scanner cannot self-trigger.
_PERSONAL = "BIVASHA" + " KUMAR" + " NAYAK"
_PERSONAL_MIXED = "Bivash" + " Kumar" + " Nayak"
RETIRED = (
    _PERSONAL,
    _PERSONAL_MIXED,
    _PERSONAL + " trading as CYBERDUDEBIVASH",
)

# These are internal statutory/mirror sources, not customer-facing branding.
# They retain the legally required seller identity for GST/invoice correctness.
ALLOWLIST = {
    Path("config/commercial-contract.json"),
    Path("workers/intel-gateway/src/cyber-watchdog.js"),
    Path("workers/intel-gateway/src/__tests__/fixtures/watchdog-v2/cyber-watchdog.js"),
    Path("deploy/cyber-watchdog/safe-rollback/overlay/workers/intel-gateway/src/cyber-watchdog.js"),
}

TEXT_SUFFIXES = {
    ".html", ".htm", ".txt", ".md", ".json", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".py", ".yml", ".yaml", ".xml", ".css",
}


def _iter_customer_capable_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if rel in ALLOWLIST:
            continue
        if any(part in {".git", "node_modules", ".venv", "venv", "__pycache__"} for part in rel.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield rel, path


def test_retired_personal_identity_is_absent_from_customer_capable_surfaces():
    violations = []
    for rel, path in _iter_customer_capable_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for retired in RETIRED:
            if retired.casefold() in text.casefold():
                violations.append(str(rel))
                break

    assert not violations, (
        "Retired personal identity found outside statutory internal sources: "
        + ", ".join(sorted(violations))
    )


def test_canonical_public_identity_is_defined_in_commercial_contract():
    contract = (ROOT / "config/commercial-contract.json").read_text(encoding="utf-8")
    assert f'"seller_display_name": "{CANONICAL}"' in contract
