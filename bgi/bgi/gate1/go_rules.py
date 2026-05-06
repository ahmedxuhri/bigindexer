"""Gate 1 — Go-specific COV mapping rules."""
from __future__ import annotations

from tree_sitter import Node

from bgi.core.cov import COV


def node_text(node: Node | None) -> str:
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


_TIER1: dict[str, COV] = {
    "return_statement": COV.OUTPUT,
    "go_statement": COV.ASYNC,
    "defer_statement": COV.DEFER,
    "if_statement": COV.CONDITIONAL,
    "for_statement": COV.LOOP,
    "expression_switch_statement": COV.CONDITIONAL,
    "type_switch_statement": COV.CONDITIONAL,
    "select_statement": COV.CONDITIONAL,
    "send_statement": COV.EMIT,
}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


_INIT_NAMES = {"init", "setup", "bootstrap"}
_TEARDOWN_NAMES = {"cleanup", "close", "shutdown", "teardown"}


def apply_tier2(name: str) -> list[tuple[COV, float]]:
    lowered = name.lower()
    results = []
    if lowered in _INIT_NAMES:
        results.append((COV.INIT, 0.95))
    if lowered in _TEARDOWN_NAMES:
        results.append((COV.TEARDOWN, 0.95))
    if lowered.startswith("test"):
        results.append((COV.TEST, 0.95))
    return results


def apply_tier3(annotation: str) -> list[tuple[COV, float]]:
    return []


_PERSIST_METHODS = {"save", "insert", "create", "write", "persist", "add", "put", "store", "upsert"}
_FETCH_METHODS = {"find", "get", "read", "query", "fetch", "load", "select", "filter", "findone", "findall", "findby"}
_EMIT_METHODS = {"emit", "publish", "dispatch", "send", "broadcast", "trigger", "next"}
_SUBSCRIBE_METHODS = {"on", "subscribe", "listen"}
_TRANSFORM_METHODS = {"map", "transform", "convert", "serialize", "deserialize", "encode", "decode", "format", "parse"}
_MUTATE_METHODS = {"update", "append", "push", "splice", "pop", "delete", "remove", "clear", "set", "patch"}
_VALIDATE_METHODS = {"validate", "check", "ensure", "verify", "assert"}
_RAISE_METHODS = {"panic"}
_RECOVER_METHODS = {"recover"}
_ASYNC_METHODS = {"go", "spawn"}
_LOG_OBJECTS = {"log", "logger"}
_MEASURE_OBJECTS = {"metrics", "statsd", "counter", "gauge", "histogram", "timer", "telemetry", "prometheus"}


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    results = []
    fn = call_node.child_by_field_name("function")
    if fn is None:
        return results

    method = ""
    obj = ""
    if fn.type == "selector_expression":
        method = node_text(fn.child_by_field_name("field"))
        obj = node_text(fn.child_by_field_name("operand"))
    elif fn.type == "identifier":
        method = node_text(fn)

    if not method:
        return results

    lowered = method.lower()
    obj_lower = obj.lower()

    if lowered in _PERSIST_METHODS:
        results.append((COV.PERSIST, 0.75))
    elif lowered in _FETCH_METHODS:
        results.append((COV.FETCH, 0.75))
    if lowered in _EMIT_METHODS:
        results.append((COV.EMIT, 0.75))
    if lowered in _SUBSCRIBE_METHODS:
        results.append((COV.SUBSCRIBE, 0.75))
    if lowered in _TRANSFORM_METHODS:
        results.append((COV.TRANSFORM, 0.75))
    if lowered in _MUTATE_METHODS:
        results.append((COV.MUTATE, 0.75))
    if lowered in _VALIDATE_METHODS:
        results.append((COV.VALIDATE, 0.75))
    if lowered in _RAISE_METHODS:
        results.append((COV.RAISE, 0.75))
    if lowered in _RECOVER_METHODS:
        results.append((COV.RECOVER, 0.75))
    if lowered in _ASYNC_METHODS:
        results.append((COV.ASYNC, 0.75))
    if obj_lower in _LOG_OBJECTS:
        results.append((COV.LOG, 0.75))
    if obj_lower in _MEASURE_OBJECTS:
        results.append((COV.MEASURE, 0.75))
    return results


def apply_tier5(base_name: str) -> list[tuple[COV, float]]:
    return []
