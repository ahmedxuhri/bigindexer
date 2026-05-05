"""Gate 1 — Lua file scanner."""
from __future__ import annotations

from pathlib import Path

import tree_sitter_lua as tslua
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.lua_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5, node_text
from bgi.gate1.rules import dedupe_ordered


_LUA_LANGUAGE = Language(tslua.language())
_PARSER = Parser(_LUA_LANGUAGE)

_STOP_RECURSE = {"function_declaration", "function_definition"}


def _walk_body(node: Node):
    for child in node.named_children:
        if child.type in _STOP_RECURSE:
            continue
        yield child
        yield from _walk_body(child)


def _has_meaningful_params(params_node: Node | None) -> bool:
    return bool(params_node and any(child.type == "identifier" for child in params_node.named_children))


def _assignment_function(node: Node) -> Node | None:
    if node.type != "assignment_statement":
        return None
    expr_list = next((child for child in node.named_children if child.type == "expression_list"), None)
    if expr_list is None or not expr_list.named_children:
        return None
    fn = expr_list.named_children[0]
    return fn if fn.type == "function_definition" else None


def _collect_functions(node: Node, results: list[Node]) -> None:
    for child in node.named_children:
        if child.type == "function_declaration":
            results.append(child)
            continue
        if _assignment_function(child) is not None:
            results.append(child)
            continue
        if child.type in _STOP_RECURSE:
            continue
        _collect_functions(child, results)


def _get_name_parts(func_node: Node) -> tuple[str, str | None]:
    if func_node.type == "assignment_statement":
        var_list = next((child for child in func_node.named_children if child.type == "variable_list"), None)
        target = var_list.named_children[0] if var_list and var_list.named_children else None
    else:
        target = func_node.child_by_field_name("name") or next(
            (child for child in func_node.named_children if child.type in {"identifier", "dot_index_expression", "method_index_expression"}),
            None,
        )

    if target is None:
        return "<anonymous>", None

    if target.type == "identifier":
        return node_text(target), None

    if target.type in {"dot_index_expression", "method_index_expression"}:
        ids = [node_text(child) for child in target.named_children if child.type == "identifier"]
        if len(ids) >= 2:
            return ids[-1], ids[0]

    return node_text(target), None


def _owner_for(func_node: Node) -> tuple[str | None, bool]:
    if func_node.type == "assignment_statement":
        name, owner = _get_name_parts(func_node)
        return owner, False if owner else False

    target = func_node.child_by_field_name("name") or next(
        (child for child in func_node.named_children if child.type in {"identifier", "dot_index_expression", "method_index_expression"}),
        None,
    )
    if target is None:
        return None, False
    if target.type == "method_index_expression":
        ids = [node_text(child) for child in target.named_children if child.type == "identifier"]
        return (ids[0], True) if len(ids) >= 2 else (None, False)
    if target.type == "dot_index_expression":
        ids = [node_text(child) for child in target.named_children if child.type == "identifier"]
        return (ids[0], False) if len(ids) >= 2 else (None, False)
    return None, False


def _get_body(func_node: Node) -> Node | None:
    if func_node.type == "assignment_statement":
        fn = _assignment_function(func_node)
        if fn is None:
            return None
        return next((child for child in fn.named_children if child.type == "block"), None)
    return next((child for child in func_node.named_children if child.type == "block"), None)


def fingerprint_function_lua(func_node: Node, rel_path: str, ai: AIFallback) -> COVFingerprint:
    func_name, _ = _get_name_parts(func_node)
    owner, is_method = _owner_for(func_node)
    unit_id = f"{rel_path}::{owner}::{func_name}" if owner else f"{rel_path}::{func_name}"

    collected: list[tuple[COV, float]] = []
    collected.extend(apply_tier2(func_name))

    params_node = None
    if func_node.type == "assignment_statement":
        fn = _assignment_function(func_node)
        params_node = next((child for child in fn.named_children if child.type == "parameters"), None) if fn else None
    else:
        params_node = next((child for child in func_node.named_children if child.type == "parameters"), None)
    if _has_meaningful_params(params_node):
        collected.append((COV.INTAKE, 1.0))

    for decorator in apply_tier3(""):
        collected.append(decorator)

    body = _get_body(func_node)
    if body is not None:
        for node in _walk_body(body):
            t1 = apply_tier1(node)
            if t1:
                collected.append(t1)
                continue
            if node.type == "function_call":
                t4 = apply_tier4(node)
                if t4:
                    collected.extend(t4)
                else:
                    ai_result = ai.classify(node, context_snippet=node_text(node))
                    if ai_result:
                        collected.append(ai_result)

    class_context_raw = apply_tier5(owner) if is_method and owner else []
    class_context_tokens = dedupe_ordered([token for token, _ in class_context_raw])
    tokens = dedupe_ordered([token for token, _ in collected])

    structural = {COV.ASYNC, COV.INTAKE}
    if not any(token not in structural for token in tokens):
        unit_results = ai.classify_unit(unit_id, node_text(func_node), language="lua")
        if unit_results:
            collected.extend(unit_results)
            tokens = dedupe_ordered([token for token, _ in collected])

    confidences = [confidence for _, confidence in collected]
    confidence = min(confidences) if confidences else 1.0

    sources = {"ai_classified" if confidence < 0.9 else "deterministic" for _, confidence in collected}
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
        language="lua",
        line_range=(func_node.start_point[0] + 1, func_node.end_point[0] + 1),
    )


def scan_file_lua(file_path: Path, root: Path, ai: AIFallback) -> list[COVFingerprint]:
    try:
        source = file_path.read_bytes()
        tree = _PARSER.parse(source)
        rel_path = str(file_path.relative_to(root))
        func_nodes: list[Node] = []
        _collect_functions(tree.root_node, func_nodes)
        return [fingerprint_function_lua(node, rel_path, ai) for node in func_nodes]
    except Exception:
        return []
