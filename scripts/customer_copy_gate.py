"""Reject development milestone labels in published customer copy."""
import re
from html.parser import HTMLParser

NUMBER = r"\d+[A-Za-z]?(?:[-/]\d+[A-Za-z]?)*"
LABEL = re.compile(r"\bMODULE\s*" + NUMBER + r"\b|^\s*PHASE\s*" + NUMBER + r"\b|[·—–]\s*PHASE\s*" + NUMBER + r"\b|\(PHASE\s*" + NUMBER + r"\)", re.I)
LITERAL = re.compile(r"[\"'`]\s*(?:MODULE|PHASE)\s*" + NUMBER + r"\s*[—–:·-]", re.I)


class CustomerText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.violations = []
        self.headings = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'title', 'label', 'button'):
            self.headings.append((tag, []))
        for key, value in attrs:
            if key in ('title', 'aria-label', 'placeholder', 'alt') and value and LABEL.search(value):
                self.violations.append(value[:160])

    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
        if self.headings and self.headings[-1][0] == tag:
            text = ''.join(self.headings.pop()[1]).strip()
            if LABEL.search(text): self.violations.append(text[:160])

    def handle_data(self, data):
        if not self.hidden:
            for _, fragments in self.headings: fragments.append(data)
        if not self.hidden and LABEL.search(data.strip()): self.violations.append(data.strip()[:160])


def customer_copy_violations(text, suffix='.html'):
    if not re.search(r'\b(?:module|phase)\s*(?:\d|&|<)|&#(?:0*(?:80|77|112|109)|x0*(?:50|4d|70|6d));', text, re.I): return []
    violations = []
    if suffix in ('.html', '.htm'):
        parser = CustomerText()
        parser.feed(text)
        violations.extend(parser.violations)
    violations.extend(match.group() for match in LITERAL.finditer(text))
    return violations


def require_clean_customer_copy(path):
    if path.suffix.lower() not in ('.html', '.htm', '.js', '.mjs', '.jsx', '.tsx'): return
    violations = customer_copy_violations(path.read_text(encoding='utf-8'), path.suffix.lower())
    if violations:
        raise ValueError(f'Customer development label in {path}: {violations[0]}')
