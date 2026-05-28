"""Gate 1 — PHP file scanner."""
from __future__ import annotations

from pathlib import Path

import tree_sitter_php as tsphp
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.php_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5, node_text
from bgi.gate1.rules import dedupe_ordered
from bgi.gate1.query_fingerprinter import get_node_tokens



_PHP_LANGUAGE = Language(tsphp.language_php())
_PARSER = Parser(_PHP_LANGUAGE)

_FUNC_TYPES = {"method_declaration", "function_definition"}
_STOP_RECURSE = _FUNC_TYPES
_MEANINGFUL_PARAM_TYPES = {"simple_parameter", "variadic_parameter", "property_promotion_parameter"}
_CALL_TYPES = {"member_call_expression", "scoped_call_expression", "function_call_expression"}


def _walk_body(node: Node):
    for child in node.children:
        yield child
        if child.type not in _STOP_RECURSE:
            yield from _walk_body(child)


def _collect_functions(root: Node) -> list[Node]:
    results: list[Node] = []
    for child in root.named_children:
        if child.type == "class_declaration":
            body = next((c for c in child.named_children if c.type == "declaration_list"), None)
            if body is None:
                continue
            for member in body.named_children:
                if member.type == "method_declaration":
                    results.append(member)
        elif child.type == "function_definition":
            results.append(child)
    return results


def _get_php_attributes(func_node: Node) -> list[str]:
    attrs = [node_text(child) for child in func_node.children if child.type == "attribute_list"]
    if attrs:
        return attrs
    parent = func_node.parent
    if parent is None:
        return []
    attrs = []
    for child in parent.children:
        if child == func_node:
            break
        if child.type == "attribute_list":
            attrs.append(node_text(child))
        else:
            attrs.clear()
    return attrs


def _has_meaningful_params(params_node: Node | None) -> bool:
    if params_node is None:
        return False
    return any(child.type in _MEANINGFUL_PARAM_TYPES for child in params_node.named_children)


def _enclosing_class(func_node: Node) -> Node | None:
    parent = func_node.parent
    while parent is not None:
        if parent.type == "class_declaration":
            return parent
        parent = parent.parent
    return None


def _class_name_for(func_node: Node) -> str | None:
    cls = _enclosing_class(func_node)
    if cls is None:
        return None
    return node_text(cls.child_by_field_name("name")) or None


def _extract_name_texts(node: Node | None) -> list[str]:
    if node is None:
        return []
    if node.type == "name":
        return [node_text(node)]
    results: list[str] = []
    for child in node.named_children:
        results.extend(_extract_name_texts(child))
    return results


def _get_class_context(func_node: Node) -> list[tuple[COV, float]]:
    cls = _enclosing_class(func_node)
    if cls is None:
        return []
    results: list[tuple[COV, float]] = []
    for child in cls.named_children:
        if child.type in {"base_clause", "class_interface_clause"}:
            for name in _extract_name_texts(child):
                results.extend(apply_tier5(name))
    return results


def fingerprint_function_php(func_node: Node, rel_path: str, ai: AIFallback) -> COVFingerprint:
    func_name = node_text(func_node.child_by_field_name("name")) or "<anonymous>"
    class_name = _class_name_for(func_node)
    unit_id = f"{rel_path}::{class_name}::{func_name}" if class_name else f"{rel_path}::{func_name}"

    collected: list[tuple[COV, float]] = []
    collected.extend(apply_tier2(func_name))

    if _has_meaningful_params(func_node.child_by_field_name("parameters")):
        collected.append((COV.INTAKE, 1.0))

    for attr in _get_php_attributes(func_node):
        collected.extend(apply_tier3(attr))

    body = func_node.child_by_field_name("body")
    if body is not None:
        query_tokens = get_node_tokens(body, "php")
        if query_tokens is not None:
            collected.extend(query_tokens)
        else:
            for node in _walk_body(body):
                t1 = apply_tier1(node)
                if t1:
                    collected.append(t1)
                    continue
                if node.type in _CALL_TYPES:
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
        unit_results = ai.classify_unit(unit_id, node_text(func_node), language="php")
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
        language="php",
        line_range=(func_node.start_point[0] + 1, func_node.end_point[0] + 1),
    )


def scan_file_php(file_path: Path, root: Path, ai: AIFallback) -> list[COVFingerprint]:
    try:
        source = file_path.read_bytes()
        tree = _PARSER.parse(source)
        rel_path = str(file_path.relative_to(root))
        return [fingerprint_function_php(node, rel_path, ai) for node in _collect_functions(tree.root_node)]
    except Exception:
        return []
