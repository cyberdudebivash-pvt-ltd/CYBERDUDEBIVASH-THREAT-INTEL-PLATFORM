#!/usr/bin/env python3
"""Fail CI if a forbidden claim string appears in public HTML."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / "config" / "claim_matrix.json").read_text())
FORBIDDEN = [c["text"].lower() for c in MATRIX["claims"] if c["status"].startswith("forbidden")]
FORBIDDEN += ["iso/iec 27001 • soc 2 type ii", "soc 2 type ii certified", "iso 27001 certified"]

def main() -> int:
    hits = []
    for html in Path.cwd().glob("*.html"):
        text = html.read_text(errors="ignore").lower()
        for phrase in FORBIDDEN:
            if phrase and phrase in text:
                hits.append(f"{html.name}: {phrase}")
    if hits:
        print("CLAIM MATRIX VIOLATIONS")
        print("\n".join(hits))
        return 1
    print("claim matrix scan clean (root html only)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
