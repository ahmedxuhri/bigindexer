"""Gate 1 — Rust file scanner."""
from __future__ import annotations

from pathlib import Path

import tree_sitter_rust as tsrust
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.rules import dedupe_ordered
from bgi.gate1.rust_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5, node_text


_RUST_LANGUAGE = Language(tsrust.language())
_PARSER = Parser(_RUST_LANGUAGE)

_FUNC_TYPES = {"function_item"}
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


def _get_rust_attributes(func_node: Node) -> list[str]:
    parent = func_node.parent
    if parent is None:
        return []
    attrs = []
    for child in parent.children:
        if child == func_node:
            break
        if child.type == "attribute_item":
            attrs.append(node_text(child))
        else:
            attrs.clear()
    return attrs


def _has_meaningful_params(params_node: Node | None) -> bool:
    if params_node is None:
        return False
    for child in params_node.named_children:
        text = node_text(child).strip()
        if text in {"self", "&self", "&mut self", "mut self"}:
            continue
        return True
    return False


def _enclosing_impl(func_node: Node) -> Node | None:
    parent = func_node.parent
    while parent is not None:
        if parent.type == "impl_item":
            return parent
        parent = parent.parent
    return None


def _type_name(node: Node | None) -> str:
    if node is None:
        return ""
    if node.type in {"type_identifier", "identifier", "self"}:
        return node_text(node)
    if node.type in {"generic_type", "scoped_type_identifier"}:
        inner = node.child_by_field_name("type") or node.child_by_field_name("name")
        if inner is None and node.named_children:
            inner = node.named_children[0]
        return node_text(inner)
    if node.type in {"reference_type", "pointer_type"} and node.named_children:
        return _type_name(node.named_children[-1])
    if node.named_children:
        return _type_name(node.named_children[-1])
    return node_text(node)


def _class_name_for(func_node: Node) -> str | None:
    impl_node = _enclosing_impl(func_node)
    if impl_node is None:
        return None
    type_name = _type_name(impl_node.child_by_field_name("type"))
    return type_name or None


def _get_class_context(func_node: Node) -> list[tuple[COV, float]]:
    impl_node = _enclosing_impl(func_node)
    if impl_node is None:
        return []
    trait_node = impl_node.child_by_field_name("trait")
    if trait_node is None:
        return []
    return apply_tier5(_type_name(trait_node))


def _is_async(func_node: Node) -> bool:
    return any(child.type == "function_modifiers" and "async" in node_text(child).split() for child in func_node.children)


def fingerprint_function_rust(func_node: Node, rel_path: str, ai: AIFallback) -> COVFingerprint:
    func_name = node_text(func_node.child_by_field_name("name")) or "<anonymous>"
    class_name = _class_name_for(func_node)
    unit_id = f"{rel_path}::{class_name}::{func_name}" if class_name else f"{rel_path}::{func_name}"

    collected: list[tuple[COV, float]] = []

    if _is_async(func_node):
        collected.append((COV.ASYNC, 1.0))

    collected.extend(apply_tier2(func_name))

    if _has_meaningful_params(func_node.child_by_field_name("parameters")):
        collected.append((COV.INTAKE, 1.0))

    for attr in _get_rust_attributes(func_node):
        collected.extend(apply_tier3(attr))

    body = func_node.child_by_field_name("body")
    if body is not None:
        for node in _walk_body(body):
            t1 = apply_tier1(node)
            if t1:
                collected.append(t1)
                continue
            if node.type in {"call_expression", "method_call_expression"}:
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
        unit_results = ai.classify_unit(unit_id, node_text(func_node), language="rust")
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
        language="rust",
        line_range=(func_node.start_point[0] + 1, func_node.end_point[0] + 1),
    )


def scan_file_rust(file_path: Path, root: Path, ai: AIFallback) -> list[COVFingerprint]:
    try:
        source = file_path.read_bytes()
        tree = _PARSER.parse(source)
        rel_path = str(file_path.relative_to(root))
        func_nodes: list[Node] = []
        _collect_functions(tree.root_node, func_nodes)
        return [fingerprint_function_rust(node, rel_path, ai) for node in func_nodes]
    except Exception:
        return []
