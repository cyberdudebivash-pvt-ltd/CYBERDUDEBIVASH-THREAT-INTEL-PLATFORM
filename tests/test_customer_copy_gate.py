from pathlib import Path
import pytest
from scripts.customer_copy_gate import customer_copy_violations, require_clean_customer_copy
from scripts.build_dist_artifact import build_manifest


@pytest.mark.parametrize('text', [
    '<h2>MODULE 10 — EXECUTIVE INTELLIGENCE BRIEF · PHASE 3</h2>',
    '<h2>Phase 52 · Graph Intelligence</h2>',
    '<span>PHASE 96</span>',
    '<input placeholder="MODULE 2 — Search">',
    '<button aria-label="Phase 3 — Review">Review</button>',
    '<h2>Executive Brief · PHASE 3</h2>',
    '<script>node.innerHTML = "MODULE 4 — Sector Heatmap";</script>',
    '<h2>MODULE <span>10</span> — Executive Brief</h2>',
    '<h2>&#80;HASE &#51; — Review</h2>',
])
def test_rejects_development_labels(text):
    assert customer_copy_violations(text)


@pytest.mark.parametrize('text', [
    '<h2>EXECUTIVE INTELLIGENCE BRIEF</h2>',
    '<h2>0-24 Hours (Containment)</h2>',
    '<p>CMMC Phase II requirements apply.</p>',
    '<p>During phase 2 of the attack, the actor moved laterally.</p>',
    '<script type="module" src="module-10.js"></script>',
    '<div id="phase-3">Review</div>',
    '<!-- Phase 3: historical implementation note -->',
])
def test_preserves_technical_context_and_functional_identifiers(text):
    assert not customer_copy_violations(text)


def test_manifest_blocks_reintroduced_label(tmp_path):
    (tmp_path / 'nested').mkdir()
    page = tmp_path / 'nested' / 'page.html'
    page.write_text('<h2>MODULE 10 — Executive Brief</h2>')
    with pytest.raises(ValueError, match='Customer development label'):
        build_manifest(tmp_path, 'test', 'test', 'test')
    page.write_text('<h2>Executive Brief</h2>')
    assert build_manifest(tmp_path, 'test', 'test', 'test')['total_files'] == 1


def test_javascript_generated_labels_are_blocked(tmp_path):
    source = tmp_path / 'feature.js'
    source.write_text('element.textContent = "PHASE 5 — Trust Center";')
    with pytest.raises(ValueError): require_clean_customer_copy(source)


def test_report_generator_does_not_reintroduce_numbered_headings():
    source = (Path(__file__).resolve().parents[1] / 'scripts/report_generator.py').read_text()
    assert '>Phase 1 — 0-24 Hours' not in source
    assert '>0-24 Hours (Containment)' in source
