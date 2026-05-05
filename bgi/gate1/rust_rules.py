"""Gate 1 — Rust-specific COV mapping rules."""
from __future__ import annotations

import re

from tree_sitter import Node

from bgi.core.cov import COV


def node_text(node: Node | None) -> str:
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


_TIER1: dict[str, COV] = {
    "return_expression": COV.OUTPUT,
    "try_expression": COV.RECOVER,
    "if_expression": COV.CONDITIONAL,
    "match_expression": COV.CONDITIONAL,
    "for_expression": COV.LOOP,
    "while_expression": COV.LOOP,
    "loop_expression": COV.LOOP,
    "await_expression": COV.ASYNC,
}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


_INIT_NAMES = {"init", "initialize", "setup", "default"}
_TEARDOWN_NAMES = {"drop", "cleanup", "teardown", "shutdown"}


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


_ROUTE_PAT = re.compile(r"#\[(?:route|get|post|put|delete|patch)")


def apply_tier3(attribute: str) -> list[tuple[COV, float]]:
    attr = attribute.replace(" ", "")
    results = []
    if attr.startswith("#[derive("):
        return results
    if attr in {"#[test]", "#[tokio::test]", "#[async_std::test]"}:
        results.append((COV.TEST, 0.9))
    if attr in {"#[tokio::main]", "#[async_std::main]"}:
        results.append((COV.INIT, 0.9))
    if _ROUTE_PAT.search(attr) or attr == "#[handler]":
        results.append((COV.ROUTE, 0.9))
    if attr == "#[middleware]":
        results.append((COV.DELEGATE, 0.9))
    return results


_PERSIST_METHODS = {"save", "insert", "create", "write", "persist", "add", "put", "store", "upsert"}
_FETCH_METHODS = {"find", "get", "read", "query", "fetch", "load", "select", "filter", "find_one", "find_all", "find_by"}
_EMIT_METHODS = {"emit", "publish", "dispatch", "send", "broadcast", "trigger", "next"}
_SUBSCRIBE_METHODS = {"on", "subscribe", "listen", "poll_next"}
_TRANSFORM_METHODS = {"map", "transform", "convert", "serialize", "deserialize", "encode", "decode", "format", "parse", "into", "from"}
_MUTATE_METHODS = {"update", "append", "push", "splice", "pop", "delete", "remove", "clear", "set", "patch", "insert"}
_VALIDATE_METHODS = {"validate", "check", "ensure", "verify", "assert"}
_RAISE_METHODS = {"panic", "bail"}
_RECOVER_METHODS = {"recover", "or_else", "unwrap_or_else"}
_ASYNC_METHODS = {"spawn", "spawn_blocking"}
_LOG_OBJECTS = {"log", "logger", "tracing"}
_MEASURE_OBJECTS = {"metrics", "statsd", "counter", "gauge", "histogram", "timer", "telemetry", "prometheus"}


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    results = []
    method = ""
    obj = ""

    if call_node.type == "method_call_expression":
        method = node_text(call_node.child_by_field_name("name"))
        obj = node_text(call_node.child_by_field_name("value"))
    else:
        fn = call_node.child_by_field_name("function")
        if fn is None:
            return results
        if fn.type == "identifier":
            method = node_text(fn)
        elif fn.type == "scoped_identifier":
            method = node_text(fn.child_by_field_name("name") or fn.named_children[-1])
        elif fn.type == "field_expression":
            method = node_text(fn.child_by_field_name("field") or fn.named_children[-1])
            obj = node_text(fn.child_by_field_name("value") or fn.named_children[0])
        elif fn.type == "generic_function":
            inner = fn.child_by_field_name("function") or (fn.named_children[0] if fn.named_children else None)
            method = node_text(inner)

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
    base = base_name.split("<", 1)[0].split("::")[-1]
    mapping = {
        "From": (COV.TRANSFORM, 0.85),
        "Into": (COV.TRANSFORM, 0.85),
        "TryFrom": (COV.TRANSFORM, 0.85),
        "TryInto": (COV.TRANSFORM, 0.85),
        "Display": (COV.CONTRACT, 0.85),
        "Debug": (COV.CONTRACT, 0.85),
        "Serialize": (COV.CONTRACT, 0.85),
        "Deserialize": (COV.CONTRACT, 0.85),
        "Iterator": (COV.EMIT, 0.85),
        "Stream": (COV.EMIT, 0.85),
        "AsyncIterator": (COV.EMIT, 0.85),
        "Drop": (COV.TEARDOWN, 0.85),
        "Default": (COV.INIT, 0.85),
        "Error": (COV.RAISE, 0.85),
    }
    token = mapping.get(base)
    return [token] if token else []
