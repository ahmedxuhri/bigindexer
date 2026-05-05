"""Gate 1 — Ruby-specific COV mapping rules."""
from __future__ import annotations

import re

from tree_sitter import Node

from bgi.core.cov import COV


def node_text(node: Node | None) -> str:
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


_TIER1: dict[str, COV] = {
    "return": COV.OUTPUT,
    "yield": COV.EMIT,
    "for": COV.LOOP,
    "while": COV.LOOP,
    "until": COV.LOOP,
    "if": COV.CONDITIONAL,
    "if_modifier": COV.CONDITIONAL,
    "unless": COV.CONDITIONAL,
    "unless_modifier": COV.CONDITIONAL,
    "case": COV.CONDITIONAL,
    "rescue": COV.RECOVER,
    "ensure": COV.DEFER,
    "raise": COV.RAISE,
}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


_INIT_NAMES = {"initialize", "setup", "before_each", "before_all"}
_TEARDOWN_NAMES = {"cleanup", "teardown", "tear_down", "after_each", "after_all", "shutdown"}


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
_FETCH_METHODS = {"find", "get", "read", "query", "fetch", "load", "select", "filter", "find_by", "find_by!", "find_or_create_by"}
_EMIT_METHODS = {"emit", "publish", "dispatch", "send", "broadcast", "trigger"}
_SUBSCRIBE_METHODS = {"subscribe", "listen", "on"}
_TRANSFORM_METHODS = {"map", "transform", "convert", "serialize", "deserialize", "encode", "decode", "format", "parse"}
_MUTATE_METHODS = {"update", "append", "push", "delete", "remove", "clear", "set", "merge!"}
_VALIDATE_METHODS = {"validate", "check", "ensure", "verify", "assert", "valid?"}
_RAISE_METHODS = {"raise", "fail"}
_RECOVER_METHODS = {"recover", "retry"}
_ASYNC_METHODS = {"perform_async", "deliver_later", "delay", "async", "enqueue_later"}
_LOG_OBJECTS = {"logger", "rails.logger", "log"}
_MEASURE_OBJECTS = {"metrics", "statsd", "counter", "gauge", "histogram", "timer", "telemetry", "prometheus"}


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    results = []
    named = list(call_node.named_children)
    if not named:
        return results

    method = ""
    obj = ""
    if len(named) >= 2 and named[1].type in {"identifier", "constant"}:
        obj = node_text(named[0])
        method = node_text(named[1])
    elif named[0].type in {"identifier", "constant"}:
        method = node_text(named[0])

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


_HERITAGE_CONTRACT = re.compile(r"(?:BaseModel|Schema|Model|Serializable|DTO|Entity|ValueObject)$")
_HERITAGE_RAISE = re.compile(r"(?:Error|Exception|Fault)$")
_HERITAGE_TEST = re.compile(r"(?:TestCase|Spec|Suite)$")
_HERITAGE_PERSIST = re.compile(r"(?:Repository|Store|Dao)$")
_HERITAGE_SUBSCRIBE = re.compile(r"(?:Consumer|Subscriber|Handler|Listener)$")
_HERITAGE_ROUTE = re.compile(r"(?:Controller|Router|View)$")
_HERITAGE_AUTH = re.compile(r"(?:Guard|AuthGuard|Authenticator)$")
_HERITAGE_AUTHZ = re.compile(r"(?:PermissionGuard|RoleGuard|AccessGuard)$")


def apply_tier5(base_name: str) -> list[tuple[COV, float]]:
    base = base_name.split("::")[-1]
    results = []
    if _HERITAGE_CONTRACT.search(base):
        results.append((COV.CONTRACT, 0.9))
    if _HERITAGE_RAISE.search(base):
        results.append((COV.RAISE, 0.9))
    if _HERITAGE_TEST.search(base):
        results.append((COV.TEST, 0.9))
    if _HERITAGE_PERSIST.search(base):
        results.append((COV.PERSIST, 0.9))
    if _HERITAGE_SUBSCRIBE.search(base):
        results.append((COV.SUBSCRIBE, 0.9))
    if _HERITAGE_ROUTE.search(base):
        results.append((COV.ROUTE, 0.9))
    if _HERITAGE_AUTH.search(base):
        results.append((COV.AUTHENTICATE, 0.9))
    if _HERITAGE_AUTHZ.search(base):
        results.append((COV.AUTHORIZE, 0.9))
    return results
