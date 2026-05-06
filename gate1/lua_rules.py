"""Gate 1 — Lua-specific COV mapping rules."""
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
    "while_statement": COV.LOOP,
    "for_statement": COV.LOOP,
    "repeat_statement": COV.LOOP,
}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


_INIT_NAMES = {"new", "create", "init", "setup", "start", "open"}
_TEARDOWN_NAMES = {"destroy", "close", "cleanup", "shutdown", "teardown", "stop"}
_MUTATE_NAMES = {"update", "on_update", "tick"}


def apply_tier2(name: str) -> list[tuple[COV, float]]:
    results = []
    if name in _INIT_NAMES:
        results.append((COV.INIT, 0.9))
    if name in _TEARDOWN_NAMES:
        results.append((COV.TEARDOWN, 0.9))
    if name.startswith("test"):
        results.append((COV.TEST, 0.9))
    if name in _MUTATE_NAMES:
        results.append((COV.MUTATE, 0.85))
    return results


def apply_tier3(_: str) -> list[tuple[COV, float]]:
    return []


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    results = []
    fn = call_node.named_children[0] if call_node.named_children else None
    if fn is None:
        return results

    obj: str | None = None
    method: str | None = None

    if fn.type in {"dot_index_expression", "method_index_expression"}:
        ids = [node_text(child) for child in fn.named_children if child.type == "identifier"]
        if ids:
            obj = ids[0]
            method = ids[-1]
    elif fn.type == "identifier":
        method = node_text(fn)

    if not method:
        return results

    if method in {"error", "assert"}:
        results.append((COV.RAISE, 0.75))
    if method == "require":
        results.append((COV.FETCH, 0.75))
    if method in {"pcall", "xpcall"}:
        results.append((COV.RECOVER, 0.75))
    if obj == "coroutine" and method in {"wrap", "create"}:
        results.append((COV.ASYNC, 0.75))
    if method == "print" or (obj == "io" and method == "write"):
        results.append((COV.LOG, 0.75))
    return results


def apply_tier5(_: str) -> list[tuple[COV, float]]:
    return []
