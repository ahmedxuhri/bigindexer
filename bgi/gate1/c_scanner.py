"""Gate 1 — C file scanner."""
from __future__ import annotations

from pathlib import Path

import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.c_rules import apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5, node_text
from bgi.gate1.rules import dedupe_ordered


_C_LANGUAGE = Language(tsc.language())
_PARSER = Parser(_C_LANGUAGE)

_FUNC_TYPES = {"function_definition"}
_STOP_RECURSE = _FUNC_TYPES


def _walk_body(node: Node):
    for child in node.children:
        yield child
        if child.type not in _STOP_RECURSE:
            yield from _walk_body(child)


def _collect_functions(root: Node) -> list[Node]:
    return [child for child in root.named_children if child.type == "function_definition"]


def _get_c_func_name(func_node: Node) -> str:
    decl = func_node.child_by_field_name("declarator")
    while decl is not None and decl.type != "function_declarator":
        decl = decl.child_by_field_name("declarator")
    if decl is None:
        return "<unknown>"
    name = decl.child_by_field_name("declarator")
    if name is None and decl.named_children:
        name = decl.named_children[0]
    return node_text(name) if name is not None else "<unknown>"


def _has_meaningful_params(func_node: Node) -> bool:
    decl = func_node.child_by_field_name("declarator")
    while decl is not None and decl.type != "function_declarator":
        decl = decl.child_by_field_name("declarator")
    if decl is None:
        return False
    params = next((c for c in decl.named_children if c.type == "parameter_list"), None)
    if params is None:
        return False
    return any(child.type == "parameter_declaration" for child in params.named_children)


def fingerprint_function_c(func_node: Node, rel_path: str, ai: AIFallback) -> COVFingerprint:
    func_name = _get_c_func_name(func_node)
    unit_id = f"{rel_path}::{func_name}"

    collected: list[tuple[COV, float]] = []
    collected.extend(apply_tier2(func_name))

    if _has_meaningful_params(func_node):
        collected.append((COV.INTAKE, 1.0))

    body = next((c for c in func_node.named_children if c.type == "compound_statement"), None)
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

    class_context_tokens: list[COV] = []
    tokens = dedupe_ordered([token for token, _ in collected])

    structural = {COV.ASYNC, COV.INTAKE}
    if not any(token not in structural for token in tokens):
        unit_results = ai.classify_unit(unit_id, node_text(func_node), language="c")
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
        language="c",
        line_range=(func_node.start_point[0] + 1, func_node.end_point[0] + 1),
    )


def scan_file_c(file_path: Path, root: Path, ai: AIFallback) -> list[COVFingerprint]:
    try:
        source = file_path.read_bytes()
        tree = _PARSER.parse(source)
        rel_path = str(file_path.relative_to(root))
        return [fingerprint_function_c(node, rel_path, ai) for node in _collect_functions(tree.root_node)]
    except Exception:
        return []
