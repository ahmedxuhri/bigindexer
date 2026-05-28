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
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

from bgi.core.cov import COV
from bgi.gate1.query_fingerprinter import get_node_tokens, _load_query


_PY = Language(tspython.language())
_PY_PARSER = Parser(_PY)

_TS = Language(tsts.language_typescript())
_TS_PARSER = Parser(_TS)

_JS = Language(tsjs.language())
_JS_PARSER = Parser(_JS)

import tree_sitter_go as tsgo
_GO = Language(tsgo.language())
_GO_PARSER = Parser(_GO)

import tree_sitter_rust as tsrust
_RUST = Language(tsrust.language())
_RUST_PARSER = Parser(_RUST)

import tree_sitter_java as tsjava
_JAVA = Language(tsjava.language())
_JAVA_PARSER = Parser(_JAVA)

import tree_sitter_c_sharp as tscs
_CS = Language(tscs.language())
_CS_PARSER = Parser(_CS)

import tree_sitter_php as tsphp
_PHP = Language(tsphp.language_php())
_PHP_PARSER = Parser(_PHP)

import tree_sitter_ruby as tsruby
_RUBY = Language(tsruby.language())
_RUBY_PARSER = Parser(_RUBY)

import tree_sitter_kotlin as tskotlin
_KOTLIN = Language(tskotlin.language())
_KOTLIN_PARSER = Parser(_KOTLIN)

import tree_sitter_scala as tsscala
_SCALA = Language(tsscala.language())
_SCALA_PARSER = Parser(_SCALA)






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


def _js_body(src: str):
    """Parse a JavaScript function and return its body node."""
    src = textwrap.dedent(src).strip()
    tree = _JS_PARSER.parse(src.encode())
    fn = tree.root_node.children[0]
    return fn.child_by_field_name("body")


def _go_body(src: str):
    """Parse a Go function and return its body node."""
    src = textwrap.dedent(src).strip()
    tree = _GO_PARSER.parse(src.encode())
    fn = tree.root_node.children[0]
    return fn.child_by_field_name("body")


def _rust_body(src: str):
    """Parse a Rust function and return its body node."""
    src = textwrap.dedent(src).strip()
    tree = _RUST_PARSER.parse(src.encode())
    fn = tree.root_node.children[0]
    return fn.child_by_field_name("body")


def _java_body(src: str):
    """Parse a Java method body and return its body node."""
    full_src = f"class Dummy {{ void f() {{ {src} }} }}"
    tree = _JAVA_PARSER.parse(full_src.encode())
    class_decl = tree.root_node.children[0]
    class_body = class_decl.child_by_field_name("body")
    method_decl = next(c for c in class_body.children if c.type == "method_declaration")
    return method_decl.child_by_field_name("body")


def _csharp_body(src: str):
    """Parse a C# method body and return its body node."""
    full_src = f"class Dummy {{ void f() {{ {src} }} }}"
    tree = _CS_PARSER.parse(full_src.encode())
    class_decl = tree.root_node.children[0]
    decl_list = next(c for c in class_decl.children if c.type == "declaration_list")
    method_decl = next(c for c in decl_list.children if c.type == "method_declaration")
    return method_decl.child_by_field_name("body")


def _php_body(src: str):
    """Parse a PHP method body and return its body node."""
    full_src = f"<?php class Dummy {{ public function f() {{ {src} }} }}"
    tree = _PHP_PARSER.parse(full_src.encode())
    class_decl = next(c for c in tree.root_node.children if c.type == "class_declaration")
    decl_list = class_decl.child_by_field_name("body")
    method_decl = next(c for c in decl_list.children if c.type == "method_declaration")
    return method_decl.child_by_field_name("body")


def _ruby_body(src: str):
    """Parse a Ruby method body and return its body node."""
    full_src = f"def f\n  {src}\nend"
    tree = _RUBY_PARSER.parse(full_src.encode())
    method_node = tree.root_node.children[0]
    return method_node.child_by_field_name("body")


def _kotlin_body(src: str):
    """Parse a Kotlin function and return its body node."""
    full_src = f"fun f() {{ {src} }}"
    tree = _KOTLIN_PARSER.parse(full_src.encode())
    fn_node = tree.root_node.children[0]
    return next(c for c in fn_node.children if c.type in {"function_body", "block"})


def _scala_body(src: str):
    """Parse a Scala function and return its body node."""
    full_src = f"def f() = {{ {src} }}"
    tree = _SCALA_PARSER.parse(full_src.encode())
    fn_node = tree.root_node.children[0]
    return fn_node.child_by_field_name("body")






def cov_set(tokens) -> set[COV]:
    return {cov for cov, _ in tokens}


# ── Query file availability ──────────────────────────────────────────────────

def test_python_query_loads():
    assert _load_query("python") is not None


def test_typescript_query_loads():
    assert _load_query("typescript") is not None


def test_javascript_query_loads():
    assert _load_query("javascript") is not None


def test_go_query_loads():
    assert _load_query("go") is not None


def test_rust_query_loads():
    assert _load_query("rust") is not None


def test_java_query_loads():
    assert _load_query("java") is not None


def test_csharp_query_loads():
    assert _load_query("csharp") is not None


def test_php_query_loads():
    assert _load_query("php") is not None


def test_ruby_query_loads():
    assert _load_query("ruby") is not None


def test_kotlin_query_loads():
    assert _load_query("kotlin") is not None


def test_scala_query_loads():
    assert _load_query("scala") is not None






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


# ── JavaScript structural patterns ────────────────────────────────────────────

class TestJavaScriptStructural:
    def test_return_gives_output(self):
        body = _js_body("function f(x) { return x; }")
        tokens = get_node_tokens(body, "javascript")
        assert COV.OUTPUT in cov_set(tokens)

    def test_throw_gives_raise(self):
        body = _js_body("function f() { throw new Error('x'); }")
        tokens = get_node_tokens(body, "javascript")
        assert COV.RAISE in cov_set(tokens)

    def test_await_gives_async(self):
        body = _js_body("async function f() { const x = await fetch('/api'); }")
        tokens = get_node_tokens(body, "javascript")
        assert COV.ASYNC in cov_set(tokens)

    def test_augmented_assignment_gives_mutate(self):
        body = _js_body("function f(x) { x += 1; }")
        tokens = get_node_tokens(body, "javascript")
        assert COV.MUTATE in cov_set(tokens)


# ── Go structural patterns ──────────────────────────────────────────────────

class TestGoStructural:
    def test_return_gives_output(self):
        body = _go_body("func f(x int) int { return x }")
        tokens = get_node_tokens(body, "go")
        assert COV.OUTPUT in cov_set(tokens)

    def test_go_statement_gives_async(self):
        body = _go_body("func f() { go worker() }")
        tokens = get_node_tokens(body, "go")
        assert COV.ASYNC in cov_set(tokens)

    def test_defer_gives_defer(self):
        body = _go_body("func f() { defer cleanup() }")
        tokens = get_node_tokens(body, "go")
        assert COV.DEFER in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _go_body("func f(x int) { if x > 0 {} }")
        tokens = get_node_tokens(body, "go")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_for_gives_loop(self):
        body = _go_body("func f() { for {} }")
        tokens = get_node_tokens(body, "go")
        assert COV.LOOP in cov_set(tokens)

    def test_send_statement_gives_emit(self):
        body = _go_body("func f(ch chan int) { ch <- 1 }")
        tokens = get_node_tokens(body, "go")
        assert COV.EMIT in cov_set(tokens)

    def test_receive_statement_gives_subscribe(self):
        body = _go_body("func f(ch chan int) { <-ch }")
        tokens = get_node_tokens(body, "go")
        assert COV.SUBSCRIBE in cov_set(tokens)


# ── Go method-name patterns ──────────────────────────────────────────────────

class TestGoMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _go_body("func f(repo *Repo) { repo.Save(obj) }")
        tokens = get_node_tokens(body, "go")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _go_body("func f(repo *Repo) { repo.Get(1) }")
        tokens = get_node_tokens(body, "go")
        assert COV.FETCH in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _go_body("func f() { logger.Info(\"hello\") }")
        tokens = get_node_tokens(body, "go")
        assert COV.LOG in cov_set(tokens)

    def test_router_handle_gives_route(self):
        body = _go_body("func f(r *Router) { r.HandleFunc(\"/api\", handler) }")
        tokens = get_node_tokens(body, "go")
        assert COV.ROUTE in cov_set(tokens)


# ── Rust structural patterns ──────────────────────────────────────────────────

class TestRustStructural:
    def test_return_gives_output(self):
        body = _rust_body("fn f(x: i32) -> i32 { return x; }")
        tokens = get_node_tokens(body, "rust")
        assert COV.OUTPUT in cov_set(tokens)

    def test_await_gives_async(self):
        body = _rust_body("async fn f() { foo().await; }")
        tokens = get_node_tokens(body, "rust")
        assert COV.ASYNC in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _rust_body("fn f(x: i32) { if x > 0 {} }")
        tokens = get_node_tokens(body, "rust")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_match_gives_conditional(self):
        body = _rust_body("fn f(x: i32) { match x { _ => {} } }")
        tokens = get_node_tokens(body, "rust")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_for_gives_loop(self):
        body = _rust_body("fn f() { for x in 0..10 {} }")
        tokens = get_node_tokens(body, "rust")
        assert COV.LOOP in cov_set(tokens)

    def test_try_expression_gives_recover(self):
        body = _rust_body("fn f() -> Result<(), ()> { foo()?; Ok(()) }")
        tokens = get_node_tokens(body, "rust")
        assert COV.RECOVER in cov_set(tokens)


# ── Rust method-name patterns ──────────────────────────────────────────────────

class TestRustMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _rust_body("fn f(repo: &Repo) { repo.save(obj); }")
        tokens = get_node_tokens(body, "rust")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _rust_body("fn f(repo: &Repo) { repo.get(1); }")
        tokens = get_node_tokens(body, "rust")
        assert COV.FETCH in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _rust_body("fn f() { log.info(\"hello\"); }")
        tokens = get_node_tokens(body, "rust")
        assert COV.LOG in cov_set(tokens)


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


# ── Java structural patterns ──────────────────────────────────────────────────

class TestJavaStructural:
    def test_return_gives_output(self):
        body = _java_body("return x;")
        tokens = get_node_tokens(body, "java")
        assert COV.OUTPUT in cov_set(tokens)

    def test_throw_gives_raise(self):
        body = _java_body("throw new RuntimeException();")
        tokens = get_node_tokens(body, "java")
        assert COV.RAISE in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _java_body("if (x > 0) {}")
        tokens = get_node_tokens(body, "java")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_for_gives_loop(self):
        body = _java_body("for (int i=0; i<10; i++) {}")
        tokens = get_node_tokens(body, "java")
        assert COV.LOOP in cov_set(tokens)

    def test_synchronized_gives_scope(self):
        body = _java_body("synchronized(this) {}")
        tokens = get_node_tokens(body, "java")
        assert COV.SCOPE in cov_set(tokens)


# ── Java method-name patterns ─────────────────────────────────────────────────

class TestJavaMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _java_body("repo.save(obj);")
        tokens = get_node_tokens(body, "java")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _java_body("repo.get(1);")
        tokens = get_node_tokens(body, "java")
        assert COV.FETCH in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _java_body("logger.info(\"hello\");")
        tokens = get_node_tokens(body, "java")
        assert COV.LOG in cov_set(tokens)


# ── C# structural patterns ────────────────────────────────────────────────────

class TestCSharpStructural:
    def test_return_gives_output(self):
        body = _csharp_body("return x;")
        tokens = get_node_tokens(body, "csharp")
        assert COV.OUTPUT in cov_set(tokens)

    def test_yield_gives_emit(self):
        body = _csharp_body("yield return x;")
        tokens = get_node_tokens(body, "csharp")
        assert COV.EMIT in cov_set(tokens)

    def test_throw_gives_raise(self):
        body = _csharp_body("throw new Exception();")
        tokens = get_node_tokens(body, "csharp")
        assert COV.RAISE in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _csharp_body("if (x > 0) {}")
        tokens = get_node_tokens(body, "csharp")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_foreach_gives_loop(self):
        body = _csharp_body("foreach (var item in list) {}")
        tokens = get_node_tokens(body, "csharp")
        assert COV.LOOP in cov_set(tokens)

    def test_await_gives_async(self):
        body = _csharp_body("await Task.Delay(1);")
        tokens = get_node_tokens(body, "csharp")
        assert COV.ASYNC in cov_set(tokens)

    def test_member_assignment_gives_mutate(self):
        body = _csharp_body("obj.prop = x;")
        tokens = get_node_tokens(body, "csharp")
        assert COV.MUTATE in cov_set(tokens)


# ── C# method-name patterns ───────────────────────────────────────────────────

class TestCSharpMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _csharp_body("repo.save(obj);")
        tokens = get_node_tokens(body, "csharp")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _csharp_body("repo.get(1);")
        tokens = get_node_tokens(body, "csharp")
        assert COV.FETCH in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _csharp_body("logger.info(\"hello\");")
        tokens = get_node_tokens(body, "csharp")
        assert COV.LOG in cov_set(tokens)


# ── PHP structural patterns ───────────────────────────────────────────────────

class TestPHPStructural:
    def test_return_gives_output(self):
        body = _php_body("return x;")
        tokens = get_node_tokens(body, "php")
        assert COV.OUTPUT in cov_set(tokens)

    def test_yield_gives_emit(self):
        body = _php_body("yield x;")
        tokens = get_node_tokens(body, "php")
        assert COV.EMIT in cov_set(tokens)

    def test_throw_gives_raise(self):
        body = _php_body("throw new Exception();")
        tokens = get_node_tokens(body, "php")
        assert COV.RAISE in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _php_body("if (x > 0) {}")
        tokens = get_node_tokens(body, "php")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_foreach_gives_loop(self):
        body = _php_body("foreach ($list as $item) {}")
        tokens = get_node_tokens(body, "php")
        assert COV.LOOP in cov_set(tokens)


# ── PHP method-name patterns ──────────────────────────────────────────────────

class TestPHPMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _php_body("$repo->save($obj);")
        tokens = get_node_tokens(body, "php")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _php_body("$repo->get(1);")
        tokens = get_node_tokens(body, "php")
        assert COV.FETCH in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _php_body("$logger->info(\"hello\");")
        tokens = get_node_tokens(body, "php")
        assert COV.LOG in cov_set(tokens)

    def test_static_logger_info_gives_log(self):
        body = _php_body("Logger::info(\"hello\");")
        tokens = get_node_tokens(body, "php")
        assert COV.LOG in cov_set(tokens)


# ── Ruby structural patterns ──────────────────────────────────────────────────

class TestRubyStructural:
    def test_return_gives_output(self):
        body = _ruby_body("return x")
        tokens = get_node_tokens(body, "ruby")
        assert COV.OUTPUT in cov_set(tokens)

    def test_yield_gives_emit(self):
        body = _ruby_body("yield x")
        tokens = get_node_tokens(body, "ruby")
        assert COV.EMIT in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _ruby_body("if x; end")
        tokens = get_node_tokens(body, "ruby")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_if_modifier_gives_conditional(self):
        body = _ruby_body("x if y")
        tokens = get_node_tokens(body, "ruby")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_for_gives_loop(self):
        body = _ruby_body("for x in xs; end")
        tokens = get_node_tokens(body, "ruby")
        assert COV.LOOP in cov_set(tokens)

    def test_rescue_gives_recover(self):
        body = _ruby_body("begin; rescue; end")
        tokens = get_node_tokens(body, "ruby")
        assert COV.RECOVER in cov_set(tokens)

    def test_ensure_gives_defer(self):
        body = _ruby_body("begin; ensure; end")
        tokens = get_node_tokens(body, "ruby")
        assert COV.DEFER in cov_set(tokens)


# ── Ruby method-name patterns ─────────────────────────────────────────────────

class TestRubyMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _ruby_body("repo.save(obj)")
        tokens = get_node_tokens(body, "ruby")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _ruby_body("repo.get(1)")
        tokens = get_node_tokens(body, "ruby")
        assert COV.FETCH in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _ruby_body("logger.info(\"hello\")")
        tokens = get_node_tokens(body, "ruby")
        assert COV.LOG in cov_set(tokens)

    def test_nested_logger_info_gives_log(self):
        body = _ruby_body("Rails.logger.info(\"hello\")")
        tokens = get_node_tokens(body, "ruby")
        assert COV.LOG in cov_set(tokens)


# ── Kotlin structural patterns ────────────────────────────────────────────────

class TestKotlinStructural:
    def test_return_gives_output(self):
        body = _kotlin_body("return x")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.OUTPUT in cov_set(tokens)

    def test_throw_gives_raise(self):
        body = _kotlin_body("throw Exception()")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.RAISE in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _kotlin_body("if (x > 0) {}")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_when_gives_conditional(self):
        body = _kotlin_body("when (x) {}")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_for_gives_loop(self):
        body = _kotlin_body("for (x in xs) {}")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.LOOP in cov_set(tokens)

    def test_catch_gives_recover(self):
        body = _kotlin_body("try {} catch(e: Exception) {}")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.RECOVER in cov_set(tokens)

    def test_finally_gives_defer(self):
        body = _kotlin_body("try {} finally {}")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.DEFER in cov_set(tokens)


# ── Kotlin method-name patterns ───────────────────────────────────────────────

class TestKotlinMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _kotlin_body("repo.save(obj)")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _kotlin_body("repo.get(1)")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.FETCH in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _kotlin_body("logger.info(\"hello\")")
        tokens = get_node_tokens(body, "kotlin")
        assert COV.LOG in cov_set(tokens)


# ── Scala structural patterns ─────────────────────────────────────────────────

class TestScalaStructural:
    def test_return_gives_output(self):
        body = _scala_body("return x")
        tokens = get_node_tokens(body, "scala")
        assert COV.OUTPUT in cov_set(tokens)

    def test_throw_gives_raise(self):
        body = _scala_body("throw new Exception()")
        tokens = get_node_tokens(body, "scala")
        assert COV.RAISE in cov_set(tokens)

    def test_if_gives_conditional(self):
        body = _scala_body("if (x > 0) {}")
        tokens = get_node_tokens(body, "scala")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_match_gives_conditional(self):
        body = _scala_body("x match { case _ => {} }")
        tokens = get_node_tokens(body, "scala")
        assert COV.CONDITIONAL in cov_set(tokens)

    def test_for_gives_loop(self):
        body = _scala_body("for (x <- xs) {}")
        tokens = get_node_tokens(body, "scala")
        assert COV.LOOP in cov_set(tokens)

    def test_catch_gives_recover(self):
        body = _scala_body("try {} catch { case e: Exception => {} }")
        tokens = get_node_tokens(body, "scala")
        assert COV.RECOVER in cov_set(tokens)

    def test_finally_gives_defer(self):
        body = _scala_body("try {} finally {}")
        tokens = get_node_tokens(body, "scala")
        assert COV.DEFER in cov_set(tokens)


# ── Scala method-name patterns ────────────────────────────────────────────────

class TestScalaMethodPredicates:
    def test_obj_save_gives_persist(self):
        body = _scala_body("repo.save(obj)")
        tokens = get_node_tokens(body, "scala")
        assert COV.PERSIST in cov_set(tokens)

    def test_obj_get_gives_fetch(self):
        body = _scala_body("repo.get(1)")
        tokens = get_node_tokens(body, "scala")
        assert COV.FETCH in cov_set(tokens)

    def test_logger_info_gives_log(self):
        body = _scala_body("logger.info(\"hello\")")
        tokens = get_node_tokens(body, "scala")
        assert COV.LOG in cov_set(tokens)




