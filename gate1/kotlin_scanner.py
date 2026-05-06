"""Gate 1 — Kotlin file scanner."""
from __future__ import annotations

from pathlib import Path

import tree_sitter_kotlin as tskotlin
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.kotlin_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5, node_text
from bgi.gate1.rules import dedupe_ordered


_KOTLIN_LANGUAGE = Language(tskotlin.language())
_PARSER = Parser(_KOTLIN_LANGUAGE)

_FUNC_TYPES = {"function_declaration", "secondary_constructor"}
_STOP_RECURSE = _FUNC_TYPES


def _walk_body(node: Node):
    for child in node.children:
        yield child
        if child.type not in _STOP_RECURSE:
            yield from _walk_body(child)


def _collect_functions(root: Node) -> list[Node]:
    results: list[Node] = []
    for child in root.named_children:
        if child.type == "class_declaration":
            body = next((c for c in child.named_children if c.type == "class_body"), None)
            if body is None:
                continue
            for member in body.named_children:
                if member.type in _FUNC_TYPES:
                    results.append(member)
        elif child.type == "function_declaration":
            results.append(child)
    return results


def _get_kotlin_annotations(func_node: Node) -> list[str]:
    results: list[str] = []
    for child in func_node.children:
        if child.type == "modifiers":
            for ann in child.children:
                if ann.type == "annotation":
                    results.append(node_text(ann))
    return results


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


def _func_name(func_node: Node) -> str:
    if func_node.type == "secondary_constructor":
        return _class_name_for(func_node) or "constructor"
    return node_text(func_node.child_by_field_name("name") or next((c for c in func_node.named_children if c.type in {"identifier", "simple_identifier"}), None)) or "<anonymous>"


def _get_body(func_node: Node) -> Node | None:
    body = func_node.child_by_field_name("body")
    if body is not None:
        return body
    for child in reversed(func_node.named_children):
        if child.type in {"function_body", "block"}:
            return child
    return None


def _has_meaningful_params(params_node: Node | None) -> bool:
    return bool(params_node and any(child.type == "parameter" for child in params_node.named_children))


def _is_async(func_node: Node) -> bool:
    for child in func_node.children:
        if child.type == "modifiers":
            if any(grand.type == "function_modifier" and node_text(grand) == "suspend" for grand in child.children):
                return True
    body = _get_body(func_node)
    if body is None:
        return False
    for node in _walk_body(body):
        if node.type == "call_expression":
            t4 = apply_tier4(node)
            if any(token == COV.ASYNC for token, _ in t4):
                return True
    return False


def _extract_heritage_names(node: Node | None) -> list[str]:
    if node is None:
        return []
    if node.type in {"identifier", "type_identifier"}:
        return [node_text(node)]
    if node.type == "constructor_invocation":
        inner = next((child for child in node.named_children if child.type in {"user_type", "identifier", "type_identifier"}), None)
        return _extract_heritage_names(inner)
    if node.type == "user_type":
        inner = next((child for child in node.named_children if child.type in {"identifier", "type_identifier"}), None)
        return [node_text(inner)] if inner is not None else []
    results: list[str] = []
    for child in node.named_children:
        results.extend(_extract_heritage_names(child))
    return results


def _get_class_context(func_node: Node) -> list[tuple[COV, float]]:
    cls = _enclosing_class(func_node)
    if cls is None:
        return []
    specifiers = next((c for c in cls.named_children if c.type == "delegation_specifiers"), None)
    results: list[tuple[COV, float]] = []
    for name in _extract_heritage_names(specifiers):
        results.extend(apply_tier5(name))
    return results


def fingerprint_function_kotlin(func_node: Node, rel_path: str, ai: AIFallback) -> COVFingerprint:
    func_name = _func_name(func_node)
    class_name = _class_name_for(func_node)
    unit_id = f"{rel_path}::{class_name}::{func_name}" if class_name else f"{rel_path}::{func_name}"

    collected: list[tuple[COV, float]] = []
    if func_node.type == "secondary_constructor":
        collected.append((COV.INIT, 1.0))
    if _is_async(func_node):
        collected.append((COV.ASYNC, 1.0))

    collected.extend(apply_tier2(func_name))

    params = next((c for c in func_node.named_children if c.type in {"function_value_parameters", "parameters"}), None)
    if _has_meaningful_params(params):
        collected.append((COV.INTAKE, 1.0))

    for annotation in _get_kotlin_annotations(func_node):
        collected.extend(apply_tier3(annotation))

    body = _get_body(func_node)
    if body is not None:
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
    class_context_tokens = dedupe_ordered([token for token, _ in class_context_raw])
    tokens = dedupe_ordered([token for token, _ in collected])

    structural = {COV.ASYNC, COV.INTAKE}
    if not any(token not in structural for token in tokens):
        unit_results = ai.classify_unit(unit_id, node_text(func_node), language="kotlin")
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
        language="kotlin",
        line_range=(func_node.start_point[0] + 1, func_node.end_point[0] + 1),
    )


def scan_file_kotlin(file_path: Path, root: Path, ai: AIFallback) -> list[COVFingerprint]:
    try:
        source = file_path.read_bytes()
        tree = _PARSER.parse(source)
        rel_path = str(file_path.relative_to(root))
        return [fingerprint_function_kotlin(node, rel_path, ai) for node in _collect_functions(tree.root_node)]
    except Exception:
        return []
