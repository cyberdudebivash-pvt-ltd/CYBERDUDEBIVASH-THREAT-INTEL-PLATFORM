#!/usr/bin/env python3
"""
CYBERDUDEBIVASH(R) SENTINEL APEX(TM) — CTI DOSSIER RENDERER v4.0
================================================================
Presentation-only post-processor for generated intelligence reports.

Design goals
------------
* Transform long-form report HTML into an enterprise SOC/CTI dossier UI.
* Preserve report text, evidence boundaries, provenance, links and tables.
* Never invent severity, confidence, TLP, CVSS, KEV, ATT&CK or IOC data.
* Remain Blogger-safe: no framework dependency and no JavaScript required.
* Be idempotent and usable against full HTML documents or Blogger fragments.
* Keep print/PDF and mobile rendering first-class.

This module intentionally does not alter intelligence generation or scoring.
It only derives display metadata already present in the rendered report.
"""
from __future__ import annotations

import argparse
import html as html_lib
import logging
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

log = logging.getLogger("CDB-CTI-DOSSIER")

MARKER = "<!-- CDB-CTI-DOSSIER-V4 -->"
END_MARKER = "<!-- /CDB-CTI-DOSSIER-V4 -->"
ROOT_CLASS = "cdb-cti-report"

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")


def _strip_tags(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html_lib.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _first(patterns: Iterable[str], text: str, default: str = "") -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I | re.S)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return default


def _slug(value: str) -> str:
    value = html_lib.unescape(_strip_tags(value)).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:72] or "section"


def _extract_metadata(report_html: str) -> Dict[str, str]:
    plain = _strip_tags(report_html)

    title = _first(
        [
            r"<h1\b[^>]*>(.*?)</h1>",
            r"<title\b[^>]*>(.*?)</title>",
        ],
        report_html,
        "Threat Intelligence Report",
    )
    title = _strip_tags(title)

    severity = ""
    for sev in SEVERITIES:
        if re.search(rf"\b(?:severity|priority|risk)\s*[:\-]?\s*{sev}\b", plain, flags=re.I):
            severity = sev
            break
    if not severity:
        # A standalone severity badge may exist, but avoid treating incidental prose
        # such as "high confidence" as report severity.
        m = re.search(r"\b(CRITICAL|HIGH|MEDIUM|LOW|INFO)\s+SEVERITY\b", plain, flags=re.I)
        severity = m.group(1).upper() if m else "UNSPECIFIED"

    report_id = _first(
        [
            r"\bReport\s*ID\s*[:#]?\s*([A-Z0-9][A-Z0-9._\-]{6,})",
            r"\b(CDB-(?:CTI|APEX|INTEL)-[A-Z0-9._\-]+)\b",
        ],
        plain,
        "NOT-EXPOSED",
    )

    source = _first(
        [
            r"\bSource\s+publisher\s*:\s*([^|•\n]{2,100})",
            r"\bPrimary provenance is\s+([^.|]{2,100})",
            r"\bSource system\s*[:]?\s*([A-Za-z0-9_\-]{2,80})",
        ],
        plain,
        "SOURCE-LINKED",
    )

    generated = _first(
        [
            r"\bGenerated\s+UTC\s*[:]?\s*([0-9TZ:+.\-]{10,40})",
            r"\bGenerated(?:\s+at)?\s*[:]?\s*([0-9TZ:+.\-]{10,40})",
        ],
        plain,
        "NOT-EXPOSED",
    )

    certification = _first(
        [r"\bCertification\s*[:]?\s*([^|•\n]{3,120})"], plain, "EVIDENCE-BOUND"
    )

    tlp = _first([r"\b(TLP:(?:CLEAR|GREEN|AMBER(?:\+STRICT)?|RED))\b"], plain, "TLP:UNSPECIFIED")

    confidence = _first(
        [
            r"\bConfidence(?:\s+in\s+severity\s+rating)?\s*(?:is|:)?\s*(High|Medium|Low)\b",
            r"\bAnalytic\s+Confidence\s*[:]?\s*(High|Medium|Low)\b",
        ],
        plain,
        "UNSPECIFIED",
    ).upper()

    category = _first(
        [
            r"\bReport family\s*:\s*([^.|]{2,80})",
            r"\b(?:Category|Class)\s*:\s*([^|•\n]{2,80})",
        ],
        plain,
        "CYBER THREAT INTELLIGENCE",
    )

    return {
        "title": title,
        "severity": severity,
        "report_id": report_id,
        "source": source,
        "generated": generated,
        "certification": certification,
        "tlp": tlp,
        "confidence": confidence,
        "category": category,
    }


def _badge(label: str, value: str, cls: str = "") -> str:
    return (
        f'<div class="cdb-kpi {cls}">'
        f'<span class="cdb-kpi-label">{html_lib.escape(label)}</span>'
        f'<strong>{html_lib.escape(value)}</strong>'
        f"</div>"
    )


def _command_header(meta: Dict[str, str]) -> str:
    sev_cls = f"sev-{meta['severity'].lower()}" if meta["severity"] in SEVERITIES else "sev-unspecified"
    return f"""
<header class="cdb-command-header {sev_cls}" aria-label="Threat intelligence command header">
  <div class="cdb-command-eyebrow">
    <span>CYBERDUDEBIVASH(R) INTEL FACTORY</span>
    <span>SENTINEL APEX(TM) // ADVANCED CTI DOSSIER</span>
  </div>
  <h1 class="cdb-command-title">{html_lib.escape(meta['title'])}</h1>
  <div class="cdb-command-subline">
    <span>{html_lib.escape(meta['category'])}</span>
    <span class="cdb-dot">/</span>
    <span>{html_lib.escape(meta['report_id'])}</span>
  </div>
  <div class="cdb-kpi-grid" role="list" aria-label="Report intelligence metadata">
    {_badge('SEVERITY', meta['severity'], 'cdb-kpi-severity')}
    {_badge('CONFIDENCE', meta['confidence'])}
    {_badge('TLP', meta['tlp'])}
    {_badge('SOURCE', meta['source'])}
    {_badge('GENERATED UTC', meta['generated'])}
    {_badge('CERTIFICATION', meta['certification'])}
  </div>
  <div class="cdb-trust-strip">
    <span class="cdb-live-dot" aria-hidden="true"></span>
    <span>Evidence-preserving presentation layer</span>
    <span>Source-linked</span>
    <span>Analytic boundaries retained</span>
  </div>
</header>
"""


def _anchor_headings(report_html: str) -> Tuple[str, List[Tuple[str, str]]]:
    sections: List[Tuple[str, str]] = []
    used: Dict[str, int] = {}

    pattern = re.compile(r"<(h[23])([^>]*)>(.*?)</\1>", flags=re.I | re.S)

    def repl(match: re.Match[str]) -> str:
        tag, attrs, body = match.group(1), match.group(2), match.group(3)
        label = _strip_tags(body)
        if not label:
            return match.group(0)
        existing = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I)
        if existing:
            anchor = existing.group(1)
        else:
            base = _slug(label)
            used[base] = used.get(base, 0) + 1
            anchor = base if used[base] == 1 else f"{base}-{used[base]}"
            attrs = f'{attrs} id="{anchor}"'
        if len(sections) < 36:
            sections.append((anchor, label))
        return f"<{tag}{attrs}>{body}</{tag}>"

    return pattern.sub(repl, report_html), sections


def _navigation(sections: List[Tuple[str, str]]) -> str:
    if not sections:
        return ""
    links = "".join(
        f'<a href="#{html_lib.escape(anchor)}">{html_lib.escape(label[:52])}</a>'
        for anchor, label in sections
    )
    return f"""
<nav class="cdb-report-nav" aria-label="Intelligence report sections">
  <div class="cdb-nav-title">REPORT NAVIGATION</div>
  <div class="cdb-nav-links">{links}</div>
</nav>
"""


def _style() -> str:
    # Selector scope is intentionally rooted at .cdb-cti-report to avoid Blogger
    # theme collisions. The command header is within that root.
    return r"""
<style id="cdb-cti-dossier-v4-style">
.cdb-cti-report{
  --cdb-bg:#05080d;--cdb-surface:#09111c;--cdb-panel:#0d1726;
  --cdb-panel2:#101d2e;--cdb-border:rgba(79,209,255,.22);
  --cdb-cyan:#28d7ff;--cdb-blue:#4d7dff;--cdb-purple:#9c6cff;
  --cdb-green:#39e58c;--cdb-amber:#ffb020;--cdb-orange:#ff7a18;
  --cdb-red:#ff4255;--cdb-text:#eef6ff;--cdb-muted:#8fa6bd;
  --cdb-shadow:0 24px 80px rgba(0,0,0,.35);
  color:var(--cdb-text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  line-height:1.75;position:relative;background:
    radial-gradient(circle at 8% 0%,rgba(40,215,255,.08),transparent 28rem),
    radial-gradient(circle at 92% 14%,rgba(156,108,255,.07),transparent 30rem),
    var(--cdb-bg);padding:clamp(14px,2.5vw,30px);border-radius:18px;
}
.cdb-cti-report *{box-sizing:border-box}
.cdb-cti-report a{color:var(--cdb-cyan);text-decoration-thickness:1px;text-underline-offset:3px}
.cdb-command-header{position:relative;overflow:hidden;border:1px solid var(--cdb-border);border-top:4px solid var(--cdb-cyan);background:linear-gradient(135deg,rgba(13,23,38,.98),rgba(5,8,13,.98));box-shadow:var(--cdb-shadow);padding:clamp(20px,4vw,42px);margin:0 0 18px;border-radius:16px}
.cdb-command-header:after{content:"";position:absolute;inset:auto -8% -65% 28%;height:260px;background:radial-gradient(circle,rgba(40,215,255,.16),transparent 66%);pointer-events:none}
.cdb-command-header.sev-critical{border-top-color:var(--cdb-red)}
.cdb-command-header.sev-high{border-top-color:var(--cdb-orange)}
.cdb-command-header.sev-medium{border-top-color:var(--cdb-amber)}
.cdb-command-header.sev-low{border-top-color:var(--cdb-cyan)}
.cdb-command-eyebrow{display:flex;gap:12px;justify-content:space-between;flex-wrap:wrap;color:var(--cdb-cyan);font:700 11px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.16em;text-transform:uppercase}
.cdb-command-title{font-size:clamp(27px,4.5vw,54px)!important;line-height:1.05!important;letter-spacing:-.035em!important;margin:22px 0 12px!important;color:#fff!important;max-width:1050px;text-wrap:balance}
.cdb-command-subline{display:flex;flex-wrap:wrap;gap:10px;color:var(--cdb-muted);font:700 11px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.08em;text-transform:uppercase}.cdb-dot{color:var(--cdb-cyan)}
.cdb-kpi-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin-top:28px;position:relative;z-index:1}
.cdb-kpi{min-height:82px;padding:13px;border:1px solid rgba(143,166,189,.18);background:rgba(0,0,0,.23);border-radius:10px;display:flex;flex-direction:column;justify-content:space-between;min-width:0}
.cdb-kpi-label{font:700 9px/1.2 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--cdb-muted);letter-spacing:.12em}.cdb-kpi strong{font-size:clamp(11px,1.3vw,15px);line-height:1.25;overflow-wrap:anywhere;color:#fff}.cdb-kpi-severity strong{color:var(--cdb-orange)}.sev-critical .cdb-kpi-severity strong{color:var(--cdb-red)}.sev-medium .cdb-kpi-severity strong{color:var(--cdb-amber)}.sev-low .cdb-kpi-severity strong{color:var(--cdb-cyan)}
.cdb-trust-strip{position:relative;z-index:1;display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:16px;color:var(--cdb-muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em}.cdb-live-dot{width:8px;height:8px;border-radius:50%;background:var(--cdb-green);box-shadow:0 0 15px rgba(57,229,140,.75)}
.cdb-report-nav{position:sticky;top:8px;z-index:30;border:1px solid var(--cdb-border);background:rgba(5,8,13,.94);backdrop-filter:blur(14px);padding:10px 12px;border-radius:12px;margin:0 0 22px}.cdb-nav-title{font:800 9px/1.2 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--cdb-cyan);letter-spacing:.14em;margin-bottom:8px}.cdb-nav-links{display:flex;gap:7px;overflow-x:auto;padding-bottom:4px;scrollbar-width:thin}.cdb-nav-links a{flex:0 0 auto;text-decoration:none!important;border:1px solid rgba(143,166,189,.16);background:var(--cdb-panel);color:var(--cdb-muted)!important;border-radius:999px;padding:6px 10px;font-size:10px;font-weight:700;white-space:nowrap}.cdb-nav-links a:hover{color:#fff!important;border-color:var(--cdb-cyan)}
.cdb-report-content{max-width:1180px;margin:0 auto}
.cdb-report-content>h2,.cdb-report-content>h3,.cdb-report-content section>h2,.cdb-report-content section>h3{scroll-margin-top:78px}
.cdb-cti-report h2{position:relative;margin:30px 0 13px!important;padding:13px 16px!important;border:1px solid var(--cdb-border);border-left:4px solid var(--cdb-cyan);border-radius:10px;background:linear-gradient(90deg,rgba(40,215,255,.09),rgba(13,23,38,.72));color:#fff!important;font-size:clamp(17px,2vw,22px)!important;letter-spacing:-.01em}
.cdb-cti-report h3{margin:24px 0 10px!important;color:#fff!important;font-size:clamp(15px,1.8vw,19px)!important;border-bottom:1px solid rgba(143,166,189,.16);padding-bottom:8px}
.cdb-cti-report h4{color:var(--cdb-cyan)!important;letter-spacing:.02em}
.cdb-cti-report p{color:#dce7f3;margin:10px 0 15px}.cdb-cti-report strong{color:#fff}.cdb-cti-report em{color:#b9c9d9}
.cdb-cti-report ul,.cdb-cti-report ol{border-left:2px solid rgba(40,215,255,.16);background:rgba(13,23,38,.42);padding:13px 18px 13px 34px;border-radius:0 10px 10px 0;margin:12px 0 18px}.cdb-cti-report li{margin:6px 0;color:#dce7f3}.cdb-cti-report li::marker{color:var(--cdb-cyan)}
.cdb-cti-report blockquote{margin:18px 0;padding:17px 20px;border:1px solid rgba(255,176,32,.2);border-left:4px solid var(--cdb-amber);background:rgba(255,176,32,.055);border-radius:10px;color:#f3ead6}
.cdb-cti-report table{width:100%!important;border-collapse:separate!important;border-spacing:0!important;margin:18px 0!important;border:1px solid var(--cdb-border)!important;border-radius:12px!important;overflow:hidden;background:var(--cdb-panel)}
.cdb-cti-report th{background:#0b1b2a!important;color:var(--cdb-cyan)!important;text-align:left!important;font:800 10px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace!important;letter-spacing:.08em!important;text-transform:uppercase;padding:12px!important;border-bottom:1px solid var(--cdb-border)!important}
.cdb-cti-report td{padding:12px!important;color:#dbe7f2!important;border-bottom:1px solid rgba(143,166,189,.12)!important;vertical-align:top!important}.cdb-cti-report tr:last-child td{border-bottom:0!important}.cdb-cti-report tr:hover td{background:rgba(40,215,255,.035)!important}
.cdb-cti-report code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;color:#a8f3ff;background:#07121a;border:1px solid rgba(40,215,255,.12);padding:2px 5px;border-radius:5px}.cdb-cti-report pre{overflow:auto;background:#03070b;border:1px solid var(--cdb-border);border-radius:12px;padding:15px;color:#bfefff}
.cdb-cti-report hr{border:0;border-top:1px solid rgba(143,166,189,.18);margin:30px 0}
.cdb-cti-report img,.cdb-cti-report svg{max-width:100%;height:auto}
.cdb-cti-report [class*="card"],.cdb-cti-report [class*="panel"]{border-color:var(--cdb-border)}
.cdb-cti-report [id*="provenance"],.cdb-cti-report [id*="certification"]{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
@media (max-width:980px){.cdb-kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:640px){.cdb-cti-report{padding:10px;border-radius:0}.cdb-command-header{padding:18px 14px}.cdb-command-eyebrow{display:block}.cdb-command-eyebrow span{display:block;margin-bottom:5px}.cdb-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cdb-kpi{min-height:72px}.cdb-report-nav{top:0;border-radius:8px}.cdb-cti-report table{display:block!important;overflow-x:auto!important;white-space:normal}.cdb-cti-report h2{margin-top:24px!important}.cdb-trust-strip{gap:8px}.cdb-command-subline{font-size:9px}}
@media print{.cdb-cti-report{--cdb-bg:#fff;--cdb-surface:#fff;--cdb-panel:#fff;--cdb-panel2:#fff;--cdb-text:#111;--cdb-muted:#475569;background:#fff!important;color:#111!important;padding:0!important}.cdb-report-nav{display:none!important}.cdb-command-header{box-shadow:none!important;background:#fff!important;color:#111!important;break-inside:avoid}.cdb-command-title,.cdb-command-header strong,.cdb-cti-report h2,.cdb-cti-report h3,.cdb-cti-report strong{color:#111!important}.cdb-cti-report p,.cdb-cti-report li,.cdb-cti-report td{color:#222!important}.cdb-cti-report h2,.cdb-cti-report ul,.cdb-cti-report ol,.cdb-cti-report blockquote,.cdb-cti-report table{background:#fff!important;break-inside:avoid}.cdb-cti-report a{color:#075985!important}.cdb-kpi{background:#fff!important;border-color:#cbd5e1!important}.cdb-trust-strip{color:#475569!important}}
</style>
"""


def decorate_html(report_html: str) -> str:
    """Return a presentation-enhanced report while preserving original content."""
    if not report_html or not report_html.strip():
        return report_html
    if MARKER in report_html:
        return report_html

    meta = _extract_metadata(report_html)
    anchored, sections = _anchor_headings(report_html)
    style = _style()
    header = _command_header(meta)
    nav = _navigation(sections)

    # Full HTML document: inject stylesheet in head, then wrap body contents.
    body_match = re.search(r"<body\b([^>]*)>", anchored, flags=re.I)
    if body_match:
        if "</head>" in anchored.lower():
            anchored = re.sub(r"</head>", style + "\n</head>", anchored, count=1, flags=re.I)
            inline_style = ""
        else:
            inline_style = style

        start = body_match.end()
        end_match = re.search(r"</body>", anchored[start:], flags=re.I)
        if end_match:
            end = start + end_match.start()
            original_body = anchored[start:end]
            wrapped = (
                f"\n{MARKER}\n{inline_style}<div class=\"{ROOT_CLASS}\">"
                f"{header}{nav}<main class=\"cdb-report-content\">{original_body}</main>"
                f"</div>\n{END_MARKER}\n"
            )
            return anchored[:start] + wrapped + anchored[end:]

    # Blogger/body fragment: style is embedded with the report and every selector
    # is scoped, so it is safe alongside the theme CSS.
    return (
        f"{MARKER}\n{style}<div class=\"{ROOT_CLASS}\">{header}{nav}"
        f"<main class=\"cdb-report-content\">{anchored}</main></div>\n{END_MARKER}"
    )


def process_file(src: Path, dst: Path | None = None, check_only: bool = False) -> bool:
    src = Path(src)
    dst = Path(dst) if dst else src
    text = src.read_text(encoding="utf-8", errors="replace")
    enhanced = decorate_html(text)
    changed = enhanced != text
    if check_only:
        return MARKER in enhanced and ROOT_CLASS in enhanced
    if changed:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(enhanced, encoding="utf-8")
        log.info("CTI dossier rendered: %s", dst)
    return changed


def process_tree(root: Path, check_only: bool = False) -> Dict[str, int]:
    root = Path(root)
    stats = {"scanned": 0, "decorated": 0, "valid": 0, "errors": 0}
    if not root.exists():
        return stats
    for path in sorted(root.rglob("*.html")):
        stats["scanned"] += 1
        try:
            if check_only:
                if process_file(path, check_only=True):
                    stats["valid"] += 1
            elif process_file(path):
                stats["decorated"] += 1
        except Exception as exc:  # fail-open for one malformed historical report
            stats["errors"] += 1
            log.error("Dossier render failed for %s: %s", path, exc)
    return stats


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Sentinel APEX CTI dossier presentation")
    parser.add_argument("--input", type=Path, help="Single HTML report or Blogger body fragment")
    parser.add_argument("--output", type=Path, help="Optional output path for --input")
    parser.add_argument("--reports-root", type=Path, default=Path("reports"), help="Report tree to process")
    parser.add_argument("--check", action="store_true", help="Validate dossier marker rather than mutate")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when any processing error occurs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] CTI-DOSSIER %(levelname)s %(message)s")

    if args.input:
        ok = process_file(args.input, args.output, check_only=args.check)
        if args.check and not ok:
            log.error("Dossier validation failed: %s", args.input)
            return 2
        return 0

    stats = process_tree(args.reports_root, check_only=args.check)
    log.info(
        "CTI dossier v4: scanned=%d decorated=%d valid=%d errors=%d",
        stats["scanned"], stats["decorated"], stats["valid"], stats["errors"],
    )
    if args.strict and stats["errors"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
