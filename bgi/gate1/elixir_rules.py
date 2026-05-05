"""Gate 1 — Elixir-specific COV mapping rules."""
from __future__ import annotations

from tree_sitter import Node

from bgi.core.cov import COV


def node_text(node: Node | None) -> str:
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


_TIER1_CALLS = {
    "if": COV.CONDITIONAL,
    "unless": COV.CONDITIONAL,
    "cond": COV.CONDITIONAL,
    "case": COV.CONDITIONAL,
    "with": COV.CONDITIONAL,
    "for": COV.LOOP,
    "receive": COV.SUBSCRIBE,
    "raise": COV.RAISE,
    "throw": COV.RAISE,
}

_TIER1_NODES = {
    "rescue_block": COV.RECOVER,
    "catch_block": COV.RECOVER,
    "after_block": COV.DEFER,
}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    token = _TIER1_NODES.get(node.type)
    if token:
        return (token, 1.0)
    if node.type != "call" or not node.named_children:
        return None
    first = node.named_children[0]
    if first.type != "identifier":
        return None
    token = _TIER1_CALLS.get(node_text(first))
    return (token, 1.0) if token else None


_INIT_NAMES = {"init", "start_link", "start", "child_spec", "setup", "setup_all", "on_mount"}
_TEARDOWN_NAMES = {"terminate", "stop"}
_SUBSCRIBE_NAMES = {"handle_call", "handle_cast", "handle_info", "handle_continue", "handle_event", "handle_action"}


def apply_tier2(name: str) -> list[tuple[COV, float]]:
    results = []
    if name in _INIT_NAMES:
        results.append((COV.INIT, 0.95))
    if name in _TEARDOWN_NAMES:
        results.append((COV.TEARDOWN, 0.95))
    if name in _SUBSCRIBE_NAMES:
        results.append((COV.SUBSCRIBE, 0.95))
    if name.startswith("test"):
        results.append((COV.TEST, 0.95))
    return results


def apply_tier3(_: str) -> list[tuple[COV, float]]:
    return []


_FETCH_METHODS = {"all", "get", "get!", "find", "fetch", "one", "query"}
_PERSIST_METHODS = {"insert", "insert!", "create", "save", "write", "put"}
_MUTATE_METHODS = {"update", "update!", "patch", "delete", "delete!", "remove"}
_TRANSFORM_METHODS = {"map", "reduce", "filter", "transform", "encode", "decode", "parse"}
_EMIT_METHODS = {"emit", "broadcast", "publish", "dispatch", "push"}
_SUBSCRIBE_METHODS = {"subscribe", "subscribe!"}
_VALIDATE_METHODS = {"validate", "validate_changeset", "changeset"}


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    results = []
    if call_node.type != "call" or not call_node.named_children:
        return results

    first = call_node.named_children[0]
    obj: str | None = None
    method: str | None = None

    if first.type == "dot":
        parts = [child for child in first.named_children]
        if len(parts) >= 2:
            obj = node_text(parts[0])
            method = node_text(parts[-1])
    elif first.type == "identifier":
        method = node_text(first)

    if not method:
        return results

    if method in _FETCH_METHODS:
        results.append((COV.FETCH, 0.75))
    elif method in _PERSIST_METHODS:
        results.append((COV.PERSIST, 0.75))

    if method in _MUTATE_METHODS:
        results.append((COV.MUTATE, 0.75))
    if method in _TRANSFORM_METHODS:
        results.append((COV.TRANSFORM, 0.75))
    if method in _EMIT_METHODS:
        results.append((COV.EMIT, 0.75))
    if method in _SUBSCRIBE_METHODS:
        results.append((COV.SUBSCRIBE, 0.75))
    if method in _VALIDATE_METHODS:
        results.append((COV.VALIDATE, 0.75))

    if method in {"spawn", "spawn_link", "spawn_monitor"}:
        results.append((COV.ASYNC, 0.75))
    if obj == "Task" and method in {"async", "start"}:
        results.append((COV.ASYNC, 0.75))
    if obj == "GenServer" and method in {"call", "cast"}:
        results.append((COV.DELEGATE, 0.75))
    if (obj == "Logger" and method in {"info", "error", "debug"}) or (obj == "IO" and method in {"puts", "inspect"}):
        results.append((COV.LOG, 0.75))

    return results


def apply_tier5(use_target: str) -> list[tuple[COV, float]]:
    mapping = {
        "GenServer": COV.SUBSCRIBE,
        "Phoenix.Controller": COV.ROUTE,
        "Phoenix.LiveView": COV.SUBSCRIBE,
        "Ecto.Schema": COV.CONTRACT,
        "ExUnit.Case": COV.TEST,
        "Agent": COV.SUBSCRIBE,
        "Task": COV.ASYNC,
    }
    token = mapping.get(use_target)
    return [(token, 0.9)] if token else []
