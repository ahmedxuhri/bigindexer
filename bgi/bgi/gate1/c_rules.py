"""Gate 1 — C-specific COV mapping rules."""
from __future__ import annotations

from tree_sitter import Node

from bgi.core.cov import COV


def node_text(node: Node | None) -> str:
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


_TIER1: dict[str, COV] = {
    "return_statement": COV.OUTPUT,
    "if_statement": COV.CONDITIONAL,
    "switch_statement": COV.CONDITIONAL,
    "while_statement": COV.LOOP,
    "for_statement": COV.LOOP,
    "do_statement": COV.LOOP,
}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


def apply_tier2(name: str) -> list[tuple[COV, float]]:
    lowered = name.lower()
    results = []
    if name == "main" or any(part in lowered for part in {"init", "initialize", "setup"}):
        results.append((COV.INIT, 0.95 if name == "main" else 0.9))
    if any(part in lowered for part in {"free", "destroy", "cleanup", "teardown", "close", "shutdown"}):
        results.append((COV.TEARDOWN, 0.9))
    if lowered.startswith("test"):
        results.append((COV.TEST, 0.9))
    return results


def apply_tier3(annotation: str) -> list[tuple[COV, float]]:
    return []


_FETCH_METHODS = {"malloc", "calloc", "realloc"}
_TEARDOWN_METHODS = {"free"}
_LOG_METHODS = {"printf", "fprintf", "sprintf"}
_PERSIST_METHODS = {"fopen", "fread", "fwrite", "fclose"}
_TRANSFORM_METHODS = {"memcpy", "memmove", "memset", "strcpy", "strncpy"}


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    results = []
    fn = call_node.child_by_field_name("function")
    if fn is None:
        return results

    method = ""
    if fn.type == "field_expression":
        method = node_text(fn.named_children[-1] if fn.named_children else None)
    elif fn.type == "identifier":
        method = node_text(fn)

    if not method:
        return results

    lowered = method.lower()
    if lowered in _FETCH_METHODS:
        results.append((COV.FETCH, 0.75))
    if lowered in _TEARDOWN_METHODS:
        results.append((COV.TEARDOWN, 0.75))
    if lowered in _LOG_METHODS:
        results.append((COV.LOG, 0.75))
    if lowered in _PERSIST_METHODS:
        results.append((COV.PERSIST, 0.75))
    if lowered in _TRANSFORM_METHODS:
        results.append((COV.TRANSFORM, 0.75))
    return results


def apply_tier5(base_name: str) -> list[tuple[COV, float]]:
    return []
