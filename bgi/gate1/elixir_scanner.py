"""Gate 1 — Elixir file scanner."""
from __future__ import annotations

from pathlib import Path

import tree_sitter_elixir as tselixir
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.elixir_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5, node_text
from bgi.gate1.rules import dedupe_ordered


_ELIXIR_LANGUAGE = Language(tselixir.language())
_PARSER = Parser(_ELIXIR_LANGUAGE)

_FUNCTION_HEADS = {"def", "defp", "defmacro", "defmacrop"}


def _call_head_name(node: Node) -> str:
    if node.type != "call" or not node.named_children:
        return ""
    first = node.named_children[0]
    return node_text(first) if first.type == "identifier" else ""


def _is_function(node: Node) -> bool:
    return node.type == "call" and _call_head_name(node) in _FUNCTION_HEADS


def _is_module(node: Node) -> bool:
    return node.type == "call" and _call_head_name(node) == "defmodule"


def _walk_body(node: Node):
    for child in node.named_children:
        if _is_function(child):
            continue
        yield child
        yield from _walk_body(child)


def _collect_functions(node: Node, results: list[Node]) -> None:
    for child in node.named_children:
        if _is_function(child):
            results.append(child)
            continue
        _collect_functions(child, results)


def _arguments_node(call_node: Node) -> Node | None:
    return next((child for child in call_node.named_children if child.type == "arguments"), None)


def _signature_node(func_node: Node) -> Node | None:
    args = _arguments_node(func_node)
    if args is None:
        return None
    return next((child for child in args.named_children if child.type == "call"), None)


def _function_name(func_node: Node) -> str:
    sig = _signature_node(func_node)
    if sig is None or not sig.named_children:
        return "<anonymous>"
    name_node = sig.named_children[0]
    return node_text(name_node)


def _has_meaningful_params(func_node: Node) -> bool:
    sig = _signature_node(func_node)
    if sig is None:
        return False
    params = _arguments_node(sig)
    return bool(params and params.named_children)


def _get_body(func_node: Node) -> Node | None:
    direct = next((child for child in func_node.named_children if child.type == "do_block"), None)
    if direct is not None:
        return direct
    args = _arguments_node(func_node)
    if args is None:
        return None
    return next((child for child in args.named_children if child.type == "keywords"), None)


def _enclosing_module(func_node: Node) -> Node | None:
    parent = func_node.parent
    while parent is not None:
        if _is_module(parent):
            return parent
        parent = parent.parent
    return None


def _module_name_for(func_node: Node) -> str | None:
    module = _enclosing_module(func_node)
    if module is None:
        return None
    args = _arguments_node(module)
    if args is None or not args.named_children:
        return None
    return node_text(args.named_children[0])


def _module_context(func_node: Node) -> list[tuple[COV, float]]:
    module = _enclosing_module(func_node)
    if module is None:
        return []
    body = next((child for child in module.named_children if child.type == "do_block"), None)
    if body is None:
        return []

    results: list[tuple[COV, float]] = []
    for child in body.named_children:
        if _is_function(child):
            continue
        if child.type != "call" or _call_head_name(child) != "use":
            continue
        args = _arguments_node(child)
        if args is None or not args.named_children:
            continue
        results.extend(apply_tier5(node_text(args.named_children[0])))
    return results


def fingerprint_function_elixir(func_node: Node, rel_path: str, ai: AIFallback) -> COVFingerprint:
    func_name = _function_name(func_node)
    module_name = _module_name_for(func_node)
    unit_id = f"{rel_path}::{module_name}::{func_name}" if module_name else f"{rel_path}::{func_name}"

    collected: list[tuple[COV, float]] = []
    collected.extend(apply_tier2(func_name))

    if _has_meaningful_params(func_node):
        collected.append((COV.INTAKE, 1.0))

    for _ in apply_tier3(""):
        pass

    body = _get_body(func_node)
    if body is not None:
        for node in _walk_body(body):
            t1 = apply_tier1(node)
            if t1:
                collected.append(t1)
                continue
            if node.type == "call":
                t4 = apply_tier4(node)
                if t4:
                    collected.extend(t4)
                else:
                    ai_result = ai.classify(node, context_snippet=node_text(node))
                    if ai_result:
                        collected.append(ai_result)

    class_context_raw = _module_context(func_node)
    class_context_tokens = dedupe_ordered([token for token, _ in class_context_raw])
    tokens = dedupe_ordered([token for token, _ in collected])

    structural = {COV.ASYNC, COV.INTAKE}
    if not any(token not in structural for token in tokens):
        unit_results = ai.classify_unit(unit_id, node_text(func_node), language="elixir")
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
        language="elixir",
        line_range=(func_node.start_point[0] + 1, func_node.end_point[0] + 1),
    )


def scan_file_elixir(file_path: Path, root: Path, ai: AIFallback) -> list[COVFingerprint]:
    try:
        source = file_path.read_bytes()
        tree = _PARSER.parse(source)
        rel_path = str(file_path.relative_to(root))
        func_nodes: list[Node] = []
        _collect_functions(tree.root_node, func_nodes)
        return [fingerprint_function_elixir(node, rel_path, ai) for node in func_nodes]
    except Exception:
        return []
