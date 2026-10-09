"""P0 R16: rate-limit delay belongs after local reject gates, not before them.

Exact observed trigger: sentinel-blogger run #2522 spent three seconds per
locally rejected feed candidate and exceeded the 1,200-second engine budget.
Static structure tests do not consume network or Cloudflare quota.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "agent" / "sentinel_blogger.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _called(node, name):
    return any(
        isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == name
        for x in ast.walk(node)
    )


def _delay(node):
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and (
        isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "time"
        and node.value.func.attr == "sleep"
    )


def _phase2_entry_loop():
    matches = [
        node for node in ast.walk(TREE)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name) and node.target.id == "entry"
        and isinstance(node.iter, ast.Name) and node.iter.id == "entries"
        and _called(node, "process_entry")
    ]
    assert len(matches) == 1, "multi-feed candidate processing loop must be unambiguous"
    return matches[0]


def test_phase2_no_unconditional_sleep_before_first_local_duplicate_filter():
    loop = _phase2_entry_loop()
    assert not _delay(loop.body[0]), "rejected candidates must not consume API pacing"
    throttle_indices = [i for i, n in enumerate(loop.body) if _delay(n)]
    assert len(throttle_indices) == 1


def test_throttle_occurs_only_after_all_local_rejection_filters():
    loop = _phase2_entry_loop()
    delay_index = next(i for i, n in enumerate(loop.body) if _delay(n))
    precheck_source = ast.get_source_segment(SOURCE, loop)[:SOURCE.index("NOT_A_REAL_SENTINEL") if "NOT_A_REAL_SENTINEL" in SOURCE else 5000]
    # Structural checks: a delayed accepted candidate follows the short-
    # circuiting quality/temporal/dedup branches.
    assert delay_index >= 6
    preceding = ast.get_source_segment(SOURCE, loop.body[0])
    assert "_intel_engine" in preceding
    earlier = "\n".join(ast.get_source_segment(SOURCE, n) or "" for n in loop.body[:delay_index])
    for marker in ("is_duplicate", "is_temporally_relevant", "_quality_gate", "_sst", "_fps"):
        assert marker in earlier


def test_throttle_remains_immediately_before_processing():
    loop = _phase2_entry_loop()
    idx = next(i for i, n in enumerate(loop.body) if _delay(n))
    assert isinstance(loop.body[idx + 1], ast.Try)
    assert _called(loop.body[idx + 1], "process_entry")
    throttle = loop.body[idx].value
    assert len(throttle.args) == 1
    assert isinstance(throttle.args[0], ast.Name)
    assert throttle.args[0].id == "RATE_LIMIT_DELAY"


def test_delay_configuration_not_diluted_to_force_green():
    import sys
    sys.path.insert(0, str(ROOT))
    from agent.config import RATE_LIMIT_DELAY
    assert RATE_LIMIT_DELAY == 3
