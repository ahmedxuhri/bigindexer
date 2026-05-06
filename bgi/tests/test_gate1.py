"""
Tests for Gate 1 — Python COV fingerprinting.

Tests parse real Python snippets through tree-sitter and assert on the
COVFingerprint produced by scan_source() / apply_tier* functions directly.
"""
import pytest
import textwrap
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from bgi.core.cov import COV
from bgi.gate1.python_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5
from bgi.gate1.scanner import fingerprint_function, _collect_functions
from bgi.gate1.ai_fallback import AIFallback


# ── Helpers ──────────────────────────────────────────────────────────────────

_PY = Language(tspython.language())
_PARSER = Parser(_PY)
_NO_AI = AIFallback(enabled=False)


def fingerprints_for(src: str) -> list:
    """Parse snippet and return all fingerprints (no AI fallback)."""
    src = textwrap.dedent(src)
    tree = _PARSER.parse(src.encode())
    func_nodes: list = []
    _collect_functions(tree.root_node, func_nodes)
    return [fingerprint_function(fn, "test.py", _NO_AI) for fn in func_nodes]


def tokens_of(fp) -> list[str]:
    return [str(t) for t in fp.tokens]


def class_tokens_of(fp) -> list[str]:
    return [str(t) for t in fp.class_context]


# ── Tier 1 — AST node type ────────────────────────────────────────────────────

class TestTier1Nodes:
    def test_return_produces_output(self):
        fps = fingerprints_for("""
            def f(x):
                return x
        """)
        assert any("COV.OUTPUT" in t or t == "COV.OUTPUT" or t.endswith("OUTPUT") for fp in fps for t in tokens_of(fp))

    def _tokens_for_single_func(self, src: str) -> list[str]:
        fps = fingerprints_for(src)
        assert len(fps) == 1
        return tokens_of(fps[0])

    def test_yield_produces_emit(self):
        toks = self._tokens_for_single_func("""
            def gen():
                yield 1
        """)
        assert "COV.EMIT" in toks

    def test_yield_from_produces_emit(self):
        toks = self._tokens_for_single_func("""
            def gen():
                yield from range(10)
        """)
        assert "COV.EMIT" in toks

    def test_raise_produces_raise(self):
        toks = self._tokens_for_single_func("""
            def f():
                raise ValueError("bad")
        """)
        assert "COV.RAISE" in toks

    def test_assert_produces_guard(self):
        toks = self._tokens_for_single_func("""
            def f(x):
                assert x > 0
        """)
        assert "COV.GUARD" in toks

    def test_try_except_produces_recover(self):
        toks = self._tokens_for_single_func("""
            def f():
                try:
                    pass
                except Exception:
                    pass
        """)
        assert "COV.RECOVER" in toks

    def test_finally_produces_defer(self):
        toks = self._tokens_for_single_func("""
            def f():
                try:
                    pass
                finally:
                    pass
        """)
        assert "COV.DEFER" in toks

    def test_for_loop_produces_loop(self):
        toks = self._tokens_for_single_func("""
            def f(items):
                for x in items:
                    pass
        """)
        assert "COV.LOOP" in toks

    def test_while_loop_produces_loop(self):
        toks = self._tokens_for_single_func("""
            def f():
                while True:
                    break
        """)
        assert "COV.LOOP" in toks

    def test_if_produces_conditional(self):
        toks = self._tokens_for_single_func("""
            def f(x):
                if x:
                    pass
        """)
        assert "COV.CONDITIONAL" in toks

    def test_with_produces_scope(self):
        toks = self._tokens_for_single_func("""
            def f():
                with open("x") as fh:
                    pass
        """)
        assert "COV.SCOPE" in toks

    def test_await_produces_async(self):
        toks = self._tokens_for_single_func("""
            async def f():
                await something()
        """)
        assert "COV.ASYNC" in toks

    def test_augmented_assignment_produces_mutate(self):
        toks = self._tokens_for_single_func("""
            def f(lst):
                lst += [1]
        """)
        assert "COV.MUTATE" in toks

    def test_attribute_assignment_produces_mutate(self):
        toks = self._tokens_for_single_func("""
            def f(self):
                self.x = 1
        """)
        assert "COV.MUTATE" in toks

    def test_plain_assignment_no_mutate(self):
        toks = self._tokens_for_single_func("""
            def f():
                x = 1
        """)
        assert "COV.MUTATE" not in toks

    def test_list_comprehension_produces_transform(self):
        toks = self._tokens_for_single_func("""
            def f(items):
                return [x * 2 for x in items]
        """)
        assert "COV.TRANSFORM" in toks

    def test_dict_comprehension_produces_transform(self):
        toks = self._tokens_for_single_func("""
            def f(items):
                return {k: v for k, v in items}
        """)
        assert "COV.TRANSFORM" in toks


# ── Tier 2 — function name ───────────────────────────────────────────────────

class TestTier2FunctionName:
    def test_init_dunder_produces_init(self):
        fps = fingerprints_for("""
            class A:
                def __init__(self):
                    self.x = 0
        """)
        init_fp = next(fp for fp in fps if "__init__" in fp.unit_id)
        assert "COV.INIT" in tokens_of(init_fp)

    def test_del_dunder_produces_teardown(self):
        fps = fingerprints_for("""
            class A:
                def __del__(self):
                    pass
        """)
        del_fp = next(fp for fp in fps if "__del__" in fp.unit_id)
        assert "COV.TEARDOWN" in tokens_of(del_fp)

    def test_test_prefix_produces_test(self):
        fps = fingerprints_for("""
            def test_something():
                assert True
        """)
        assert "COV.TEST" in tokens_of(fps[0])

    def test_setup_method_produces_init(self):
        fps = fingerprints_for("""
            class T:
                def setUp(self):
                    pass
        """)
        fp = next(fp for fp in fps if "setUp" in fp.unit_id)
        assert "COV.INIT" in tokens_of(fp)


# ── Tier 3 — decorator ───────────────────────────────────────────────────────

class TestTier3Decorator:
    def test_apply_tier3_route(self):
        result = apply_tier3("@app.route('/home')")
        tokens = [t for t, _ in result]
        assert COV.ROUTE in tokens

    def test_apply_tier3_lru_cache(self):
        result = apply_tier3("@lru_cache(maxsize=128)")
        tokens = [t for t, _ in result]
        assert COV.FETCH in tokens   # MEMOIZE mapped to FETCH

    def test_apply_tier3_contextmanager_produces_scope(self):
        result = apply_tier3("@contextmanager")
        tokens = [t for t, _ in result]
        assert COV.SCOPE in tokens

    def test_apply_tier3_login_required(self):
        result = apply_tier3("@login_required")
        tokens = [t for t, _ in result]
        assert COV.AUTHENTICATE in tokens

    def test_apply_tier3_retry(self):
        result = apply_tier3("@retry(max_attempts=3)")
        tokens = [t for t, _ in result]
        assert COV.RECOVER in tokens

    def test_apply_tier3_startup_lifecycle(self):
        result = apply_tier3('@app.on_event("startup")')
        tokens = [t for t, _ in result]
        assert COV.INIT in tokens

    def test_apply_tier3_shutdown_lifecycle(self):
        result = apply_tier3('@app.on_event("shutdown")')
        tokens = [t for t, _ in result]
        assert COV.TEARDOWN in tokens


# ── Tier 4 — call target ─────────────────────────────────────────────────────

class TestTier4CallTarget:
    def test_save_produces_persist(self):
        toks = [t for t, _ in apply_tier4(_make_call_node("obj.save()"))]
        assert COV.PERSIST in toks

    def test_get_produces_fetch(self):
        toks = [t for t, _ in apply_tier4(_make_call_node("obj.get(id)"))]
        assert COV.FETCH in toks

    def test_emit_produces_emit(self):
        toks = [t for t, _ in apply_tier4(_make_call_node("bus.emit('event')"))]
        assert COV.EMIT in toks

    def test_logger_produces_log(self):
        toks = [t for t, _ in apply_tier4(_make_call_node("logger.info('msg')"))]
        assert COV.LOG in toks

    def test_append_produces_mutate(self):
        toks = [t for t, _ in apply_tier4(_make_call_node("lst.append(1)"))]
        assert COV.MUTATE in toks

    def test_validate_call_produces_validate(self):
        toks = [t for t, _ in apply_tier4(_make_call_node("schema.validate(data)"))]
        assert COV.VALIDATE in toks


def _make_call_node(src: str):
    """Parse a call expression and return the call node."""
    tree = _PARSER.parse(src.encode())
    root = tree.root_node
    return _find_call(root)


def _find_call(node):
    if node.type == "call":
        return node
    for child in node.children:
        result = _find_call(child)
        if result:
            return result
    return None


# ── Tier 5 — class base ──────────────────────────────────────────────────────

class TestTier5ClassBase:
    def test_base_model_produces_contract(self):
        fps = fingerprints_for("""
            from pydantic import BaseModel
            class User(BaseModel):
                def get_name(self):
                    return self.name
        """)
        get_name_fp = next(fp for fp in fps if "get_name" in fp.unit_id)
        assert "COV.CONTRACT" in class_tokens_of(get_name_fp)

    def test_exception_base_produces_raise(self):
        fps = fingerprints_for("""
            class MyError(Exception):
                def __init__(self, msg):
                    super().__init__(msg)
        """)
        init_fp = next(fp for fp in fps if "__init__" in fp.unit_id)
        assert "COV.RAISE" in class_tokens_of(init_fp)

    def test_testcase_base_produces_test_in_class_context(self):
        fps = fingerprints_for("""
            import unittest
            class TestSomething(unittest.TestCase):
                def test_works(self):
                    assert True
        """)
        test_fp = next(fp for fp in fps if "test_works" in fp.unit_id)
        assert "COV.TEST" in class_tokens_of(test_fp)

    def test_class_context_not_in_tokens(self):
        fps = fingerprints_for("""
            class MyError(Exception):
                def describe(self):
                    return "error"
        """)
        describe_fp = next(fp for fp in fps if "describe" in fp.unit_id)
        # RAISE is in class_context but NOT in tokens
        assert "COV.RAISE" not in tokens_of(describe_fp)
        assert "COV.RAISE" in class_tokens_of(describe_fp)

    def test_all_tokens_combines_both(self):
        fps = fingerprints_for("""
            class MyError(Exception):
                def describe(self):
                    return "error"
        """)
        describe_fp = next(fp for fp in fps if "describe" in fp.unit_id)
        all_toks = [str(t) for t in describe_fp.all_tokens()]
        assert "COV.RAISE" in all_toks


# ── Deduplication and ordering ───────────────────────────────────────────────

class TestDeduplication:
    def test_no_duplicate_tokens(self):
        fps = fingerprints_for("""
            def f(x):
                if x:
                    return x
                return None
        """)
        toks = tokens_of(fps[0])
        assert len(toks) == len(set(toks))

    def test_multi_token_fingerprint(self):
        fps = fingerprints_for("""
            def f(items):
                try:
                    for x in items:
                        if x:
                            return x
                except Exception:
                    raise
        """)
        toks = set(tokens_of(fps[0]))
        # Should have several tokens
        assert "COV.LOOP" in toks
        assert "COV.CONDITIONAL" in toks
        assert "COV.OUTPUT" in toks
        assert "COV.RECOVER" in toks
        assert "COV.RAISE" in toks


# ── INTAKE from parameters ───────────────────────────────────────────────────

class TestIntake:
    def test_params_produce_intake(self):
        fps = fingerprints_for("""
            def f(x, y):
                return x + y
        """)
        assert "COV.INTAKE" in tokens_of(fps[0])

    def test_no_params_no_intake(self):
        fps = fingerprints_for("""
            def f():
                return 1
        """)
        assert "COV.INTAKE" not in tokens_of(fps[0])
