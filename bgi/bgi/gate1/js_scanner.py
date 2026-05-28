"""
Gate 1 — JavaScript / JSX file scanner.

Walks .js and .jsx files, parses with tree-sitter-javascript,
and produces COVFingerprint objects for every function/method/arrow-function.

Units collected:
  - function_declaration             → top-level named functions
  - generator_function_declaration   → generator functions
  - method_definition (in class)     → class methods
  - arrow_function in variable_declarator → const f = () => ...

JavaScript uses the same AST structure as TypeScript (minus type annotations
and interface_declaration). The same typescript_rules.py applies here —
Tier 3 decorator patterns, Tier 4 call targets, and Tier 5 heritage names
are all valid for JavaScript (including NestJS-JS, Angular-JS, etc.).
"""
from __future__ import annotations
from pathlib import Path

import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.rules import dedupe_ordered
from bgi.gate1.typescript_rules import (
    apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5,
    node_text,
    extract_route_call_info, extract_route_handler,
)
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.query_fingerprinter import get_node_tokens


_JS_LANGUAGE = Language(tsjs.language())


def _make_parser() -> Parser:
    return Parser(_JS_LANGUAGE)


# Function/method node types we scan
_FUNC_TYPES = {
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "arrow_function",
    "function",
}

_STOP_RECURSE = _FUNC_TYPES


def _walk_body(node: Node):
    """Yield all descendant nodes, stopping at nested function boundaries."""
    for child in node.children:
        yield child
        if child.type not in _STOP_RECURSE:
            yield from _walk_body(child)


# ── INTAKE detection ──────────────────────────────────────────────────────────

_MEANINGFUL_PARAMS = {
    "identifier",
    "rest_pattern",
    "assignment_pattern",
    "object_pattern",
    "array_pattern",
}


def _has_meaningful_params(params_node: Node | None) -> bool:
    if params_node is None:
        return False
    for child in params_node.children:
        if child.type in _MEANINGFUL_PARAMS:
            return True
    return False


# ── Decorator extraction ──────────────────────────────────────────────────────

def _get_decorators(func_or_class_node: Node) -> list[str]:
    return [
        node_text(child)
        for child in func_or_class_node.children
        if child.type == "decorator"
    ]


# ── Class context ─────────────────────────────────────────────────────────────

def _get_class_context(func_node: Node) -> list[tuple[COV, float]]:
    parent = func_node.parent
    while parent is not None:
        if parent.type == "class_declaration":
            break
        parent = parent.parent

    if parent is None:
        return []

    results: list[tuple[COV, float]] = []

    for dec_text in _get_decorators(parent):
        results.extend(apply_tier3(dec_text))

    # JS class_heritage: `extends <identifier>` — no extends_clause wrapper
    heritage = next((c for c in parent.children if c.type == "class_heritage"), None)
    if heritage:
        # Skip the `extends` keyword token, collect identifiers
        skip_next = False
        for item in heritage.children:
            if item.type == "extends":
                skip_next = False
                continue
            if item.type == "identifier":
                results.extend(apply_tier5(node_text(item)))

    return results


def _class_name_for(func_node: Node) -> str | None:
    parent = func_node.parent
    while parent is not None:
        if parent.type == "class_declaration":
            name_node = parent.child_by_field_name("name")
            return node_text(name_node) if name_node else None
        parent = parent.parent
    return None


# ── Unit name extraction ───────────────────────────────────────────────────────

def _func_name(node: Node, parent_var_name: str | None = None) -> str:
    if node.type in ("function_declaration", "generator_function_declaration"):
        name_node = node.child_by_field_name("name")
        return node_text(name_node) if name_node else "<anonymous>"

    if node.type in ("method_definition",):
        name_node = node.child_by_field_name("name")
        return node_text(name_node) if name_node else "<anonymous>"

    if node.type in ("arrow_function", "function"):
        return parent_var_name or "<arrow>"

    return "<anonymous>"


# ── Body extraction ────────────────────────────────────────────────────────────

def _get_body(func_node: Node) -> Node | None:
    body = func_node.child_by_field_name("body")
    if body:
        return body
    for child in reversed(func_node.children):
        if child.type not in {"=>", "formal_parameters", "identifier"}:
            return child
    return None


# ── Async detection ───────────────────────────────────────────────────────────

def _is_async(func_node: Node) -> bool:
    return any(c.type == "async" for c in func_node.children)


# ── Core fingerprinting ───────────────────────────────────────────────────────

def fingerprint_function_js(
    func_node: Node,
    rel_path: str,
    ai: AIFallback,
    parent_var_name: str | None = None,
    route_info: tuple[str, str] | None = None,
) -> COVFingerprint:
    """Produce a COVFingerprint for a single JS function/method/arrow."""

    if route_info:
        http_method, path = route_info
        func_name = f"{http_method}:{path}"
        unit_id   = f"{rel_path}::{func_name}"
        collected: list[tuple[COV, float]] = [(COV.ROUTE, 1.0)]
        class_name = None
    else:
        func_name = _func_name(func_node, parent_var_name)
        class_name = _class_name_for(func_node)
        unit_id = (
            f"{rel_path}::{class_name}::{func_name}"
            if class_name
            else f"{rel_path}::{func_name}"
        )
        collected: list[tuple[COV, float]] = []

    if _is_async(func_node):
        collected.append((COV.ASYNC, 1.0))

    # Tier 2 — function name (skip for route handlers: name is synthetic)
    if not route_info:
        collected.extend(apply_tier2(func_name))

    params = func_node.child_by_field_name("parameters") or func_node.child_by_field_name("parameter")
    if _has_meaningful_params(params):
        collected.append((COV.INTAKE, 1.0))

    for dec_text in _get_decorators(func_node):
        collected.extend(apply_tier3(dec_text))

    body = _get_body(func_node)
    if body:
        query_tokens = get_node_tokens(body, "javascript")
        if query_tokens is not None:
            collected.extend(query_tokens)
        else:
            for node in _walk_body(body):
                t1 = apply_tier1(node)
                if t1:
                    collected.append(t1)
                    continue
                if node.type == "call_expression":
                    t4 = apply_tier4(node)
                    if t4:
                        collected.extend(t4)
                    else:
                        ai_result = ai.classify(node, context_snippet=node_text(node))
                        if ai_result:
                            collected.append(ai_result)

    class_context_raw = _get_class_context(func_node)
    class_context_tokens = dedupe_ordered([t for t, _ in class_context_raw])

    tokens = dedupe_ordered([t for t, _ in collected])

    # Unit-level AI fallback — fires when no behavioural tokens were found
    _STRUCTURAL = {COV.ASYNC, COV.INTAKE}
    if not any(t not in _STRUCTURAL for t in tokens):
        source_text = node_text(func_node)
        unit_results = ai.classify_unit(unit_id, source_text, language="javascript")
        if unit_results:
            collected.extend(unit_results)
            tokens = dedupe_ordered([t for t, _ in collected])

    confidences = [c for _, c in collected]
    confidence = min(confidences) if confidences else 1.0

    sources = {"ai_classified" if c < 0.9 else "deterministic" for _, c in collected}
    if "ai_classified" in sources and len(sources) > 1:
        source = "composite"
    elif "ai_classified" in sources:
        source = "ai_classified"
    else:
        source = "deterministic"

    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=class_context_tokens,
        confidence=confidence,
        source=source,
        language="javascript",
        line_range=(
            func_node.start_point[0] + 1,
            func_node.end_point[0] + 1,
        ),
    )


# ── Function collection ───────────────────────────────────────────────────────

def _collect_js_units(
    node: Node,
    results: list,
    depth: int = 0,
) -> None:
    for child in node.children:
        if child.type in ("function_declaration", "generator_function_declaration"):
            results.append(("func", child, None))
            continue

        if child.type == "class_declaration":
            _collect_js_units(child, results, depth + 1)
            continue

        if child.type == "class_body":
            for method in child.children:
                if method.type == "method_definition":
                    results.append(("func", method, None))
            continue

        if child.type in ("lexical_declaration", "variable_declaration"):
            for decl in child.children:
                if decl.type == "variable_declarator":
                    var_name_node = decl.child_by_field_name("name")
                    var_name = node_text(var_name_node) if var_name_node else None
                    value = decl.child_by_field_name("value")
                    if value and value.type in ("arrow_function", "function"):
                        results.append(("func", value, var_name))

        # Route registration: router.get('/path', ..., handler)
        if child.type == "expression_statement":
            for gc in child.children:
                if gc.type == "call_expression":
                    route_info = extract_route_call_info(gc)
                    if route_info:
                        handler = extract_route_handler(gc)
                        if handler:
                            results.append(("route", handler, route_info))

        if child.type not in _FUNC_TYPES and depth < 10:
            _collect_js_units(child, results, depth + 1)


# ── File-level scan ───────────────────────────────────────────────────────────

def scan_file_js(
    file_path: Path,
    root: Path,
    ai: AIFallback,
) -> list[COVFingerprint]:
    """Parse one JavaScript/JSX file and return fingerprints for all units."""
    source = file_path.read_bytes()
    parser = _make_parser()
    tree = parser.parse(source)
    rel_path = str(file_path.relative_to(root))

    units: list = []
    _collect_js_units(tree.root_node, units)

    fingerprints = []
    for kind, node, extra in units:
        if kind == "route":
            fingerprints.append(fingerprint_function_js(node, rel_path, ai, route_info=extra))
        else:
            fingerprints.append(fingerprint_function_js(node, rel_path, ai, parent_var_name=extra))
    return fingerprints
