"""
Gate 1 — TypeScript / TSX file scanner.

Walks .ts and .tsx files, parses with tree-sitter-typescript,
and produces COVFingerprint objects for every function/method/arrow-function.

Units collected:
  - function_declaration             → top-level named functions
  - generator_function_declaration   → generator functions
  - method_definition (in class)     → class methods
  - arrow_function in variable_declarator → const f = () => ...
  - interface_declaration            → treated as a single CONTRACT unit

Unit IDs follow the same convention as Python:
  'path/file.ts::ClassName::methodName'
  'path/file.ts::funcName'
"""
from __future__ import annotations
from pathlib import Path

import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.rules import dedupe_ordered
from bgi.gate1.ast_cache import ASTCache
from bgi.gate1.typescript_rules import (
    apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5,
    node_text, INTERFACE_TOKEN,
    extract_route_call_info, extract_route_handler,
)
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.query_fingerprinter import get_node_tokens


_TS_LANGUAGE  = Language(tsts.language_typescript())
_TSX_LANGUAGE = Language(tsts.language_tsx())


def _make_parser(ext: str) -> Parser:
    lang = _TSX_LANGUAGE if ext in {".tsx", ".jsx"} else _TS_LANGUAGE
    return Parser(lang)


# Function/method node types we scan
_FUNC_TYPES = {
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "arrow_function",
}

_STOP_RECURSE = _FUNC_TYPES   # don't recurse into nested functions during body walk


def _walk_body(node: Node):
    """Yield all descendant nodes, stopping at nested function boundaries."""
    for child in node.children:
        yield child
        if child.type not in _STOP_RECURSE:
            yield from _walk_body(child)


# ── INTAKE detection ──────────────────────────────────────────────────────────

_MEANINGFUL_PARAMS = {
    "required_parameter",
    "optional_parameter",
    "rest_parameter",
    "identifier",              # unlabeled in some positions
}
_SKIP_PARAM_NAMES = {"this", "self"}  # TypeScript allows `this` as first param


def _has_meaningful_params(params_node: Node | None) -> bool:
    if params_node is None:
        return False
    for child in params_node.children:
        if child.type not in _MEANINGFUL_PARAMS:
            continue
        # Get the parameter name
        name_node = child.child_by_field_name("pattern") or child.child_by_field_name("name") or child
        name = node_text(name_node).split(":")[0].strip()   # strip type annotation if any
        if name and name not in _SKIP_PARAM_NAMES:
            return True
    return False


# ── Decorator extraction ──────────────────────────────────────────────────────

def _get_decorators(func_or_class_node: Node) -> list[str]:
    """
    Return decorator texts for a function/method/class node.

    Two locations are checked:
      1. Direct children of the node (class_declaration, some TS versions)
      2. Preceding siblings in the parent's children (method_definition in class_body)
         — the tree-sitter TS grammar places method decorators as siblings before
         the method_definition, not as children of it.
    """
    results = [
        node_text(child)
        for child in func_or_class_node.children
        if child.type == "decorator"
    ]
    # Also collect decorators that are preceding siblings in the parent container
    parent = func_or_class_node.parent
    if parent is not None and parent.type in ("class_body", "program", "statement_block", "module"):
        siblings = parent.children
        idx = next((i for i, s in enumerate(siblings) if s.id == func_or_class_node.id), None)
        if idx is not None:
            i = idx - 1
            while i >= 0 and siblings[i].type == "decorator":
                results.append(node_text(siblings[i]))
                i -= 1
    return results


# ── Class context ─────────────────────────────────────────────────────────────

def _get_class_context(func_node: Node) -> list[tuple[COV, float]]:
    """
    Walk up to the enclosing class_declaration (if any).
    Apply Tier 5 to its extends/implements names.
    Also collect class-level decorators.
    """
    parent = func_node.parent  # class_body or method wrapping
    while parent is not None:
        if parent.type == "class_declaration":
            break
        parent = parent.parent

    if parent is None:
        return []

    results: list[tuple[COV, float]] = []

    # Class decorators (@Injectable, @Component, etc.)
    for dec_text in _get_decorators(parent):
        results.extend(apply_tier3(dec_text))

    # class_heritage > extends_clause | implements_clause
    heritage = next((c for c in parent.children if c.type == "class_heritage"), None)
    if heritage:
        for clause in heritage.children:
            if clause.type in ("extends_clause", "implements_clause"):
                for item in clause.children:
                    if item.type in ("identifier", "type_identifier"):
                        results.extend(apply_tier5(node_text(item)))
                    elif item.type == "generic_type":
                        # e.g. Repository<User> — extract the base name
                        base = item.child_by_field_name("name") or item.children[0]
                        results.extend(apply_tier5(node_text(base)))

    return results


def _class_name_for(func_node: Node) -> str | None:
    """Return the enclosing class name, or None if at module level."""
    parent = func_node.parent
    while parent is not None:
        if parent.type == "class_declaration":
            name_node = parent.child_by_field_name("name")
            return node_text(name_node) if name_node else None
        parent = parent.parent
    return None


# ── Unit name extraction ───────────────────────────────────────────────────────

def _func_name(node: Node, parent_var_name: str | None = None) -> str:
    """Return the function/method name."""
    if node.type in ("function_declaration", "generator_function_declaration"):
        name_node = node.child_by_field_name("name")
        return node_text(name_node) if name_node else "<anonymous>"

    if node.type == "method_definition":
        name_node = node.child_by_field_name("name")
        return node_text(name_node) if name_node else "<anonymous>"

    if node.type == "arrow_function":
        return parent_var_name or "<arrow>"

    return "<anonymous>"


# ── Body of arrow functions ───────────────────────────────────────────────────

def _get_body(func_node: Node) -> Node | None:
    """Return the body node regardless of function type."""
    body = func_node.child_by_field_name("body")
    if body:
        return body
    # arrow functions can have expression bodies (no statement_block)
    # In that case, the body is the last non-=> child
    for child in reversed(func_node.children):
        if child.type not in {"=>", "formal_parameters", "identifier"}:
            return child
    return None


# ── Async detection ───────────────────────────────────────────────────────────

def _is_async(func_node: Node) -> bool:
    return any(c.type == "async" for c in func_node.children)


# ── Core fingerprinting ───────────────────────────────────────────────────────

def fingerprint_function_ts(
    func_node: Node,
    rel_path: str,
    ai: AIFallback,
    parent_var_name: str | None = None,
    route_info: tuple[str, str] | None = None,
) -> COVFingerprint:
    """Produce a COVFingerprint for a single TS function/method/arrow."""

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

    # ASYNC flag
    if _is_async(func_node):
        collected.append((COV.ASYNC, 1.0))

    # SCOPE — export status discrimination (TypeScript-specific optimization)
    export_type = _get_ts_export_type(func_node)
    if export_type == "export-default":
        collected.append((COV.SCOPE, 0.99))  # Default exports are explicit
    elif export_type == "export-public":
        collected.append((COV.SCOPE, 0.95))  # Named exports are public
    elif _is_internal_ts_function(func_node):
        collected.append((COV.SCOPE, 0.92))  # Internal/private functions

    # Tier 2 — function name (skip for route handlers: name is synthetic)
    if not route_info:
        collected.extend(apply_tier2(func_name))

    # INTAKE — meaningful parameters
    params = func_node.child_by_field_name("parameters") or func_node.child_by_field_name("parameter")
    if _has_meaningful_params(params):
        collected.append((COV.INTAKE, 1.0))

    # Tier 3 — decorators on this method/function
    for dec_text in _get_decorators(func_node):
        collected.extend(apply_tier3(dec_text))

    # WATER-CLOCK: single-pass body fingerprinting via .scm queries.
    # Falls back to two-pass walk (Tier 1 + Tier 4) when no query file exists.
    body = _get_body(func_node)
    if body:
        query_tokens = get_node_tokens(body, "typescript")
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

    # Class context (Tier 5) — kept separate
    class_context_raw = _get_class_context(func_node)
    class_context_tokens = dedupe_ordered([t for t, _ in class_context_raw])

    tokens = dedupe_ordered([t for t, _ in collected])

    # Unit-level AI fallback — fires when no behavioural tokens were found
    _STRUCTURAL = {COV.ASYNC, COV.INTAKE, COV.SCOPE}
    if not any(t not in _STRUCTURAL for t in tokens):
        source_text = node_text(func_node)
        unit_results = ai.classify_unit(unit_id, source_text, language="typescript")
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

    line_range = (
        func_node.start_point[0] + 1,
        func_node.end_point[0] + 1,
    )

    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=class_context_tokens,
        confidence=confidence,
        source=source,
        language="typescript",
        line_range=line_range,
    )


def _fingerprint_interface(
    iface_node: Node,
    rel_path: str,
) -> COVFingerprint:
    """
    An interface_declaration is a CONTRACT unit.
    Produces a single fingerprint representing the entire interface.
    """
    name_node = iface_node.child_by_field_name("name")
    iface_name = node_text(name_node) if name_node else "Interface"
    unit_id = f"{rel_path}::{iface_name}"

    return COVFingerprint(
        unit_id=unit_id,
        tokens=[COV.CONTRACT],
        class_context=[],
        confidence=1.0,
        source="deterministic",
        language="typescript",
        line_range=(
            iface_node.start_point[0] + 1,
            iface_node.end_point[0] + 1,
        ),
    )


# ── Function collection ───────────────────────────────────────────────────────

def _collect_ts_units(
    node: Node,
    results: list,
    depth: int = 0,
) -> None:
    """
    Recursively collect function/method/arrow/interface nodes.
    'results' receives tuples of (node, parent_var_name | None).
    Stops recursing into nested functions to avoid double-counting.
    """
    for child in node.children:
        if child.type == "interface_declaration":
            results.append(("interface", child, None))
            continue

        if child.type in ("function_declaration", "generator_function_declaration"):
            results.append(("func", child, None))
            # Don't recurse into function body for top-level collection
            continue

        if child.type == "class_declaration":
            # Recurse into class body to find methods
            _collect_ts_units(child, results, depth + 1)
            continue

        if child.type == "class_body":
            for method in child.children:
                if method.type == "method_definition":
                    results.append(("func", method, None))
            continue

        if child.type == "lexical_declaration":
            # const f = () => ..., const f = function() {}
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

        # Recurse into other containers (export, namespace, module, etc.)
        if child.type not in _FUNC_TYPES and depth < 10:
            _collect_ts_units(child, results, depth + 1)


# ── File-level scan ───────────────────────────────────────────────────────────

def scan_file_ts(
    file_path: Path,
    root: Path,
    ai: AIFallback,
    ast_cache: ASTCache | None = None,
) -> list[COVFingerprint]:
    """Parse one TypeScript/TSX file and return fingerprints for all units."""
    # Try to get cached AST if available
    tree = None
    if ast_cache:
        tree = ast_cache.get(file_path)
    
    if tree is None:
        # Parse and cache
        source = file_path.read_bytes()
        parser = _make_parser(file_path.suffix)
        tree = parser.parse(source)
        if ast_cache:
            ast_cache.set(file_path, tree)
    
    rel_path = str(file_path.relative_to(root))

    units: list = []
    _collect_ts_units(tree.root_node, units)

    fingerprints = []
    for kind, node, extra in units:
        if kind == "interface":
            fingerprints.append(_fingerprint_interface(node, rel_path))
        elif kind == "route":
            fingerprints.append(fingerprint_function_ts(node, rel_path, ai, route_info=extra))
        else:
            fingerprints.append(fingerprint_function_ts(node, rel_path, ai, parent_var_name=extra))

    return fingerprints


def _get_ts_export_type(func_node: Node) -> str | None:
    """
    Determine export type of TypeScript function.
    
    Returns:
        - "export-default": export default function/class/const
        - "export-public": export function/class/interface
        - "export-named": export named export (re-export or inline)
        - None: not exported
    """
    parent = func_node.parent
    
    # Check if parent is export_statement
    if parent and parent.type == "export_statement":
        export_text = node_text(parent)
        if "export default" in export_text:
            return "export-default"
        else:
            return "export-public"
    
    # Check for decorator-based exports (rare in TS but possible)
    return None


def _is_internal_ts_function(func_node: Node) -> bool:
    """
    Check if TypeScript function is marked as internal/private.
    
    Returns True for:
    - Private members (private keyword)
    - _internal or __internal naming
    - Functions inside internal namespaces
    """
    # Check private keyword
    for child in func_node.children:
        if child.type == "accessibility_modifier" and child.text == "private":
            return True
    
    func_name = node_text(func_node.child_by_field_name("name")) or ""
    if func_name.startswith("_"):
        return True
    
    return False
