"""Gate 1 — Ruby file scanner."""
from __future__ import annotations

from pathlib import Path

import tree_sitter_ruby as tsruby
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.rules import dedupe_ordered
from bgi.gate1.ruby_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5, node_text
from bgi.gate1.query_fingerprinter import get_node_tokens



_RUBY_LANGUAGE = Language(tsruby.language())
_PARSER = Parser(_RUBY_LANGUAGE)

_FUNC_TYPES = {"method", "singleton_method"}
_STOP_RECURSE = _FUNC_TYPES


def _walk_body(node: Node):
    for child in node.children:
        yield child
        if child.type not in _STOP_RECURSE:
            yield from _walk_body(child)


def _collect_functions(node: Node, results: list[Node]) -> None:
    for child in node.children:
        if child.type in _FUNC_TYPES:
            results.append(child)
            continue
        _collect_functions(child, results)


def _enclosing_class(func_node: Node) -> Node | None:
    parent = func_node.parent
    while parent is not None:
        if parent.type == "class":
            return parent
        parent = parent.parent
    return None


def _class_name_for(func_node: Node) -> str | None:
    cls = _enclosing_class(func_node)
    if cls is None:
        return None
    name_node = cls.child_by_field_name("name") or next((child for child in cls.named_children if child.type == "constant"), None)
    return node_text(name_node) if name_node is not None else None


def _has_meaningful_params(params_node: Node | None) -> bool:
    return bool(params_node and params_node.named_children)


def _extract_names(node: Node | None) -> list[str]:
    if node is None:
        return []
    if node.type in {"constant", "identifier"}:
        return [node_text(node)]
    results: list[str] = []
    for child in node.named_children:
        results.extend(_extract_names(child))
    return results


def _get_class_context(func_node: Node) -> list[tuple[COV, float]]:
    cls = _enclosing_class(func_node)
    if cls is None:
        return []

    results: list[tuple[COV, float]] = []
    for name in _extract_names(cls.child_by_field_name("superclass")):
        results.extend(apply_tier5(name))

    body = cls.child_by_field_name("body")
    if body is not None:
        for child in body.named_children:
            if child.type != "call":
                continue
            named = list(child.named_children)
            if len(named) < 2:
                continue
            if node_text(named[0]) not in {"include", "extend", "prepend"}:
                continue
            for name in _extract_names(named[1]):
                results.extend(apply_tier5(name))
    return results


def fingerprint_function_ruby(func_node: Node, rel_path: str, ai: AIFallback) -> COVFingerprint:
    func_name = node_text(func_node.child_by_field_name("name")) or "<anonymous>"
    class_name = _class_name_for(func_node)
    unit_id = f"{rel_path}::{class_name}::{func_name}" if class_name else f"{rel_path}::{func_name}"

    collected: list[tuple[COV, float]] = []
    collected.extend(apply_tier2(func_name))

    if _has_meaningful_params(func_node.child_by_field_name("parameters")):
        collected.append((COV.INTAKE, 1.0))

    body = func_node.child_by_field_name("body")
    if body is not None:
        query_tokens = get_node_tokens(body, "ruby")
        if query_tokens is not None:
            collected.extend(query_tokens)
        else:
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

    class_context_raw = _get_class_context(func_node)
    class_context_tokens = dedupe_ordered([token for token, _ in class_context_raw])
    tokens = dedupe_ordered([token for token, _ in collected])

    structural = {COV.ASYNC, COV.INTAKE}
    if not any(token not in structural for token in tokens):
        unit_results = ai.classify_unit(unit_id, node_text(func_node), language="ruby")
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
        language="ruby",
        line_range=(func_node.start_point[0] + 1, func_node.end_point[0] + 1),
    )


def scan_file_ruby(file_path: Path, root: Path, ai: AIFallback) -> list[COVFingerprint]:
    try:
        source = file_path.read_bytes()
        tree = _PARSER.parse(source)
        rel_path = str(file_path.relative_to(root))
        func_nodes: list[Node] = []
        _collect_functions(tree.root_node, func_nodes)
        return [fingerprint_function_ruby(node, rel_path, ai) for node in func_nodes]
    except Exception:
        return []
