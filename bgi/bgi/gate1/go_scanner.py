"""Gate 1 — Go file scanner."""
from __future__ import annotations

from pathlib import Path

import tree_sitter_go as tsgo
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.go_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5, node_text
from bgi.gate1.rules import dedupe_ordered
from bgi.gate1.query_fingerprinter import get_node_tokens


_GO_LANGUAGE = Language(tsgo.language())
_PARSER = Parser(_GO_LANGUAGE)

_FUNC_TYPES = {"function_declaration", "method_declaration"}
_STOP_RECURSE = _FUNC_TYPES
_MEANINGFUL_PARAM_TYPES = {"parameter_declaration", "variadic_parameter_declaration"}


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


def _func_name(node: Node) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        name_node = next((child for child in node.named_children if child.type in {"identifier", "field_identifier"}), None)
    return node_text(name_node) if name_node is not None else "<anonymous>"


def _receiver_type_name(node: Node) -> str | None:
    receiver = node.child_by_field_name("receiver")
    if receiver is None or not receiver.named_children:
        return None
    param = receiver.named_children[0]
    type_node = param.child_by_field_name("type")
    if type_node is None and param.named_children:
        type_node = param.named_children[-1]
    if type_node is None:
        return None
    if type_node.type == "pointer_type":
        inner = next((child for child in type_node.named_children if child.type.endswith("identifier")), None)
        return node_text(inner) if inner is not None else node_text(type_node).lstrip("*")
    return node_text(type_node)


def _class_name_for(node: Node) -> str | None:
    return _receiver_type_name(node) if node.type == "method_declaration" else None


def _has_meaningful_params(params_node: Node | None) -> bool:
    if params_node is None:
        return False
    return any(child.type in _MEANINGFUL_PARAM_TYPES for child in params_node.named_children)


def fingerprint_function_go(func_node: Node, rel_path: str, ai: AIFallback) -> COVFingerprint:
    func_name = _func_name(func_node)
    class_name = _class_name_for(func_node)
    unit_id = f"{rel_path}::{class_name}::{func_name}" if class_name else f"{rel_path}::{func_name}"

    collected: list[tuple[COV, float]] = []
    collected.extend(apply_tier2(func_name))

    if _has_meaningful_params(func_node.child_by_field_name("parameters")):
        collected.append((COV.INTAKE, 1.0))

    body = func_node.child_by_field_name("body")
    if body is not None:
        query_tokens = get_node_tokens(body, "go")
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

    class_context_tokens = dedupe_ordered([token for token, _ in apply_tier5("")])
    tokens = dedupe_ordered([token for token, _ in collected])

    structural = {COV.ASYNC, COV.INTAKE}
    if not any(token not in structural for token in tokens):
        unit_results = ai.classify_unit(unit_id, node_text(func_node), language="go")
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
        language="go",
        line_range=(func_node.start_point[0] + 1, func_node.end_point[0] + 1),
    )


def scan_file_go(file_path: Path, root: Path, ai: AIFallback) -> list[COVFingerprint]:
    try:
        source = file_path.read_bytes()
        tree = _PARSER.parse(source)
        rel_path = str(file_path.relative_to(root))
        func_nodes: list[Node] = []
        _collect_functions(tree.root_node, func_nodes)
        return [fingerprint_function_go(node, rel_path, ai) for node in func_nodes]
    except Exception:
        return []
