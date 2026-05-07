"""
Tests for WATER-CLOCK single-pass fingerprinting via tree-sitter .scm queries.

Validates that get_node_tokens() produces the expected COV tokens for
Python and TypeScript function bodies, matching what the two-pass Tier 1+4
rules would produce.
"""
import textwrap
import pytest
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

from bgi.core.cov import COV
from bgi.gate1.query_fingerprinter import get_node_tokens, _load_query


_PY = Language(tspython.language())
_PY_PARSER = Parser(_PY)

_TS = Language(tsts.language_typescript())
_TS_PARSER = Parser(_TS)


def _py_body(src: str):
    """Parse a Python function and return its body node."""
    src = textwrap.dedent(src).strip()
    tree = _PY_PARSER.parse(src.encode())
    fn = tree.root_node.children[0]
    return fn.child_by_field_name("body")


def _ts_body(src: str):
    """Parse a TypeScript function and return its body node."""
    src = textwrap.dedent(src).strip()
    tree = _TS_PARSER.parse(src.encode())
    fn = tree.root_node.children[0]
    return fn.child_by_field_name("body")


def cov_set(tokens) -> set[COV]:
    return {cov for cov, _ in tokens}


# ── Query file availability ──────────────────────────────────────────────────

def test_python_query_loads():
    assert _load_query("python") is not None


def test_typescript_query_loads():
    assert _load_query("typescript") is not None


def test_unknown_lang_returns_none():
    assert _load_query("cobol") is None


# ── Python structural patterns ────────────────────────────────────────────────

class TestPythonStructural:
    def test_return_gives_output(self):
        body = _py_body("def f(x):\n    return x")
        tokens = get_node_tokens(body, "python")
        assert COV.OUTPUT in cov_set(tokens)

    def test_yield_gives_emit(self):
        body = _py_body("def f():\n    yield 1")
        tokens = get_node_tokens(body, "python")
        assert COV.EMIT in cov_set(tokens)

    def test_with_statement_gives_scope(self):
        body = _py_body("def f():\n    with open('x') as g:\n        pass")
        tokens = get_node_tokens(body, "python")
        assert COV.SCOPE in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _py_body("def f(x):\n    if x: pass")
        tokens = get_node_tokens(body, "python")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_for_gives_loop(self):
        body = _py_body("def f(xs):\n    for x in xs: pass")
        tokens = get_node_tokens(body, "python")
        assert COV.LOOP in cov_set(tokens)

    def test_raise_gives_raise(self):
        body = _py_body("def f():\n    raise ValueError('err')")
        tokens = get_node_tokens(body, "python")
        assert COV.RAISE in cov_set(tokens)

    def test_except_gives_recover(self):
        body = _py_body("def f():\n    try:\n        pass\n    except Exception:\n        pass")
        tokens = get_node_tokens(body, "python")
        assert COV.RECOVER in cov_set(tokens)

    def test_finally_gives_defer(self):
        body = _py_body("def f():\n    try:\n        pass\n    finally:\n        pass")
        tokens = get_node_tokens(body, "python")
        assert COV.DEFER in cov_set(tokens)

    def test_await_gives_async(self):
        body = _py_body("async def f():\n    x = await foo()")
        # body is the block node, which contains the await expression
        tokens = get_node_tokens(body, "python")
        assert COV.ASYNC in cov_set(tokens)

    def test_augmented_assignment_gives_mutate(self):
        body = _py_body("def f(x):\n    x += 1")
        tokens = get_node_tokens(body, "python")
        assert COV.MUTATE in cov_set(tokens)

    def test_list_comprehension_gives_transform(self):
        body = _py_body("def f(xs):\n    return [x*2 for x in xs]")
        tokens = get_node_tokens(body, "python")
        assert COV.TRANSFORM in cov_set(tokens)

    def test_assert_gives_guard(self):
        body = _py_body("def f(x):\n    assert x > 0")
        tokens = get_node_tokens(body, "python")
        assert COV.GUARD in cov_set(tokens)


# ── Python method-name patterns ───────────────────────────────────────────────

class TestPythonMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _py_body("def f(repo, obj):\n    repo.save(obj)")
        tokens = get_node_tokens(body, "python")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _py_body("def f(repo):\n    return repo.get(1)")
        tokens = get_node_tokens(body, "python")
        assert COV.FETCH in cov_set(tokens)

    def test_obj_emit_gives_emit(self):
        body = _py_body("def f(bus):\n    bus.emit('event', data)")
        tokens = get_node_tokens(body, "python")
        assert COV.EMIT in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _py_body("def f():\n    logger.info('hello')")
        tokens = get_node_tokens(body, "python")
        assert COV.LOG in cov_set(tokens)

    def test_metrics_record_gives_measure(self):
        body = _py_body("def f():\n    metrics.record('latency', 42)")
        tokens = get_node_tokens(body, "python")
        assert COV.MEASURE in cov_set(tokens)

    def test_method_confidence_is_0_75(self):
        body = _py_body("def f(repo):\n    repo.save(obj)")
        tokens = get_node_tokens(body, "python")
        persist_conf = [c for cov, c in tokens if cov == COV.PERSIST]
        assert persist_conf and persist_conf[0] == pytest.approx(0.75)

    def test_structural_confidence_is_1_0(self):
        body = _py_body("def f(x):\n    return x")
        tokens = get_node_tokens(body, "python")
        output_conf = [c for cov, c in tokens if cov == COV.OUTPUT]
        assert output_conf and output_conf[0] == pytest.approx(1.0)


# ── TypeScript structural patterns ────────────────────────────────────────────

class TestTypeScriptStructural:
    def test_return_gives_output(self):
        body = _ts_body("function f(x: number) { return x; }")
        tokens = get_node_tokens(body, "typescript")
        assert COV.OUTPUT in cov_set(tokens)

    def test_throw_gives_raise(self):
        body = _ts_body("function f() { throw new Error('x'); }")
        tokens = get_node_tokens(body, "typescript")
        assert COV.RAISE in cov_set(tokens)

    def test_catch_gives_recover(self):
        body = _ts_body("function f() { try {} catch(e) {} }")
        tokens = get_node_tokens(body, "typescript")
        assert COV.RECOVER in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _ts_body("function f(x: number) { if (x > 0) {} }")
        tokens = get_node_tokens(body, "typescript")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_for_gives_loop(self):
        body = _ts_body("function f(xs: number[]) { for (const x of xs) {} }")
        tokens = get_node_tokens(body, "typescript")
        assert COV.LOOP in cov_set(tokens)

    def test_await_gives_async(self):
        body = _ts_body("async function f() { const x = await fetch('/api'); }")
        tokens = get_node_tokens(body, "typescript")
        assert COV.ASYNC in cov_set(tokens)

    def test_augmented_assignment_gives_mutate(self):
        body = _ts_body("function f(x: number) { x += 1; }")
        tokens = get_node_tokens(body, "typescript")
        assert COV.MUTATE in cov_set(tokens)


# ── Fallback behaviour ────────────────────────────────────────────────────────

def test_no_query_for_unknown_lang_returns_none():
    body = _py_body("def f():\n    return 1")
    result = get_node_tokens(body, "cobol")
    assert result is None


def test_empty_body_returns_empty_list():
    body = _py_body("def f():\n    pass")
    tokens = get_node_tokens(body, "python")
    assert tokens is not None
    assert tokens == []
