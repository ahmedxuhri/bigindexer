"""Gate 1 — C#-specific COV mapping rules."""
from __future__ import annotations

import re

from tree_sitter import Node

from bgi.core.cov import COV


def node_text(node: Node | None) -> str:
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


_TIER1: dict[str, COV] = {
    "return_statement": COV.OUTPUT,
    "yield_statement": COV.EMIT,
    "throw_statement": COV.RAISE,
    "if_statement": COV.CONDITIONAL,
    "switch_statement": COV.CONDITIONAL,
    "while_statement": COV.LOOP,
    "for_statement": COV.LOOP,
    "foreach_statement": COV.LOOP,
    "do_statement": COV.LOOP,
    "catch_clause": COV.RECOVER,
    "finally_clause": COV.DEFER,
    "await_expression": COV.ASYNC,
}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    if node.type == "assignment_expression":
        left = node.child_by_field_name("left")
        if left is None and node.named_children:
            left = node.named_children[0]
        if left is not None and left.type == "member_access_expression":
            return (COV.MUTATE, 1.0)
        return None

    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


_INIT_NAMES = {
    "Main", "Setup", "SetUp", "Initialize", "Init", "OnStart", "OnStartAsync", "StartAsync",
}
_TEARDOWN_NAMES = {
    "Dispose", "Finalize", "Cleanup", "Shutdown", "Close", "TearDown", "TearDownAsync",
}


def apply_tier2(name: str) -> list[tuple[COV, float]]:
    results = []
    if name in _INIT_NAMES:
        results.append((COV.INIT, 0.95))
    if name in _TEARDOWN_NAMES:
        results.append((COV.TEARDOWN, 0.95))
    if name.startswith("Test") or name.startswith("test_"):
        results.append((COV.TEST, 0.95))
    return results


_ROUTE_PAT = re.compile(r"\[(?:HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch|ApiController)\b|\[Route\(")
_AUTH_PAT = re.compile(r"\[(?:Authorize|AllowAnonymous)\b")
_SCOPE_PAT = re.compile(r"\[(?:Transactional|Transaction)\b")
_CONTRACT_PAT = re.compile(r"\[(?:Inject|Injectable|ServiceFilter)\b")


def apply_tier3(annotation: str) -> list[tuple[COV, float]]:
    results = []
    if re.search(r"\[(?:Test|Fact|Theory|TestMethod)\b", annotation):
        results.append((COV.TEST, 0.9))
    if _ROUTE_PAT.search(annotation):
        results.append((COV.ROUTE, 0.9))
    if _AUTH_PAT.search(annotation):
        results.append((COV.AUTHENTICATE, 0.9))
    if _SCOPE_PAT.search(annotation):
        results.append((COV.SCOPE, 0.9))
    if _CONTRACT_PAT.search(annotation):
        results.append((COV.CONTRACT, 0.9))
    if re.search(r"\[(?:Setup|SetUp|ClassInitialize)\b", annotation):
        results.append((COV.INIT, 0.9))
    if re.search(r"\[(?:TearDown|ClassCleanup)\b", annotation):
        results.append((COV.TEARDOWN, 0.9))
    return results


_PERSIST_METHODS = {"save", "insert", "create", "write", "persist", "add", "put", "store", "upsert"}
_FETCH_METHODS = {"find", "get", "read", "query", "fetch", "load", "select", "filter", "findone", "findall", "findby"}
_EMIT_METHODS = {"emit", "publish", "dispatch", "send", "broadcast", "trigger", "next"}
_SUBSCRIBE_METHODS = {"on", "subscribe", "listen", "addlistener"}
_TRANSFORM_METHODS = {"map", "transform", "convert", "serialize", "deserialize", "encode", "decode", "format", "parse"}
_MUTATE_METHODS = {"update", "append", "push", "splice", "pop", "delete", "remove", "clear", "set", "patch"}
_VALIDATE_METHODS = {"validate", "check", "ensure", "verify", "assert", "assertvalid"}
_RAISE_METHODS = {"panic", "fail", "error"}
_RECOVER_METHODS = {"recover", "retry"}
_ASYNC_METHODS = {"runasync", "supplyasync", "thenapplyasync", "thencomposeasync"}
_LOG_OBJECTS = {"console", "logger", "log"}
_MEASURE_OBJECTS = {"metrics", "statsd", "counter", "gauge", "histogram", "timer", "telemetry", "prometheus"}


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    results = []
    fn = call_node.named_children[0] if call_node.named_children else None
    if fn is None:
        return results

    method = ""
    obj = ""
    if fn.type == "member_access_expression":
        method = node_text(fn.child_by_field_name("name") or (fn.named_children[-1] if fn.named_children else None))
        obj = node_text(fn.named_children[0] if fn.named_children else None)
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


_HERITAGE_CONTRACT = re.compile(r"^(?:BaseModel|Schema|Model|Serializable|DTO|Entity|ValueObject|interface)$")
_HERITAGE_RAISE = re.compile(r"(?:Error|Exception|Fault)$")
_HERITAGE_TEST = re.compile(r"(?:TestCase|Spec|Suite)$")
_HERITAGE_PERSIST = re.compile(r"(?:Repository|BaseRepository|Store|Dao|AbstractRepository)$")
_HERITAGE_SUBSCRIBE = re.compile(r"(?:Consumer|Subscriber|Handler|Listener|EventHandler)$")
_HERITAGE_ROUTE = re.compile(r"(?:Controller|Router|View|BaseView|ControllerBase)$")
_HERITAGE_AUTH = re.compile(r"(?:Guard|AuthGuard|CanActivate|CanActivateChild|CanDeactivate)$")
_HERITAGE_AUTHZ = re.compile(r"(?:PermissionGuard|RoleGuard|AccessGuard)$")


def apply_tier5(base_name: str) -> list[tuple[COV, float]]:
    base = base_name.split("<", 1)[0].split(".")[-1]
    results = []
    if _HERITAGE_CONTRACT.match(base):
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
