"""
tests/test_pre_deploy_gate_script_balance.py

Regression test for a false positive in STAGE 5.4.5d (scripts/pre_deploy_gate.py
Gate 9, "index.html script tags balanced"). Live production investigation of
run 31405878551 found the gate hard-failing with
`src.count('<script') == src.count('</script>')` evaluating 32 != 31, while
index.html has no actual unclosed/unmatched <script> element. The extra
"<script" match was line 5837 of index.html -- prose inside a JS comment
("...aborted this entire <script> block on every page load...") -- which the
naive substring-count check cannot distinguish from a real HTML tag.

Gate 9 was replaced with a tag-aware state machine (script_tags_balanced) that
mirrors the HTML5 tokenizer's "script data" raw-text mode: once inside an open
<script> element, only a literal </script> sequence ends it, so "<script"-
looking text inside a JS comment or string is inert content, exactly as real
browsers treat it. This test exercises the actual production function (loaded
directly from scripts/pre_deploy_gate.py via AST extraction, so it cannot
silently drift from what STAGE 5.4.5d really runs) against both the required
pass/fail matrix and the exact line-5837 failure class.
"""
import ast
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = REPO_ROOT / "scripts" / "pre_deploy_gate.py"


def _load_script_tags_balanced():
    """Extract script_tags_balanced (and its _SCRIPT_TAG_RE dependency) from
    the real pre_deploy_gate.py source and exec just those nodes in an
    isolated namespace -- pre_deploy_gate.py is a top-level script (runs
    file I/O and sys.exit() at import time), not an importable module, so
    this tests the actual production code without executing the rest of
    the gate or requiring a script-file refactor."""
    src = GATE_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    wanted = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_SCRIPT_TAG_RE" for t in node.targets
        ):
            wanted.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "script_tags_balanced":
            wanted.append(node)
    assert len(wanted) == 2, (
        f"expected to find _SCRIPT_TAG_RE and script_tags_balanced in "
        f"{GATE_SCRIPT}, found {len(wanted)} matching nodes -- gate source changed shape"
    )
    namespace = {"re": re}
    module = ast.Module(body=wanted, type_ignores=[])
    exec(compile(module, filename=str(GATE_SCRIPT), mode="exec"), namespace)
    return namespace["script_tags_balanced"]


class TestScriptTagsBalanced(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script_tags_balanced = staticmethod(_load_script_tags_balanced())

    def test_balanced_normal_script(self):
        self.assertTrue(self.script_tags_balanced("<script>\nconsole.log(1);\n</script>"))

    def test_script_with_attributes(self):
        self.assertTrue(self.script_tags_balanced('<script src="app.js"></script>'))

    def test_module_script(self):
        self.assertTrue(self.script_tags_balanced('<script type="module"></script>'))

    def test_comment_containing_script_tag_text(self):
        self.assertTrue(self.script_tags_balanced(
            "<script>\n  // This comment contains <script>\n</script>"
        ))

    def test_string_literal_containing_script_tag_text(self):
        self.assertTrue(self.script_tags_balanced(
            '<script>\n  const x = "<script>";\n</script>'
        ))

    def test_genuine_missing_closing_tag(self):
        self.assertFalse(self.script_tags_balanced("<script>"))

    def test_genuine_unmatched_closing_tag(self):
        self.assertFalse(self.script_tags_balanced("</script>"))

    def test_multiple_balanced_script_tags(self):
        self.assertTrue(self.script_tags_balanced(
            '<script></script>\n<script type="module"></script>'
        ))

    def test_line_5837_failure_class_reproduced_and_fixed(self):
        """The exact production failure shape: a multi-line JS comment,
        inside an already-open <script> block, whose prose happens to
        mention "<script>" while describing an unrelated past bug."""
        html = (
            "<script>\n"
            "  // v187.0 P0 FIX: the literal quotes inside onmouseover/onmouseout's\n"
            "  // inline JS (this.style.boxShadow='...') must be escaped (\\') since\n"
            "  // this whole HTML fragment is itself a single-quoted JS string --\n"
            "  // the previous unescaped quotes terminated the outer string early,\n"
            "  // making the following \"0\" an illegal token and throwing a\n"
            "  // SyntaxError that aborted this entire <script> block on every\n"
            "  // page load (silently breaking _loadReports/_preloadReportsBadge\n"
            "  // and every other function defined below it in the same block).\n"
            "  return 1;\n"
            "</script>"
        )
        self.assertTrue(
            self.script_tags_balanced(html),
            "a JS comment mentioning '<script>' as prose must not trigger a false failure",
        )

    def test_current_index_html_passes(self):
        """The actual production file that triggered the live STAGE 5.4.5d
        failure must now pass Gate 9 for the correct reason (not because
        the file changed -- it didn't; the check did)."""
        index_html = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertTrue(self.script_tags_balanced(index_html))


if __name__ == "__main__":
    unittest.main()
