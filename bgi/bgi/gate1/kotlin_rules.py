"""Gate 1 — Kotlin-specific COV mapping rules."""
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
    "throw_expression": COV.RAISE,
    "if_expression": COV.CONDITIONAL,
    "when_expression": COV.CONDITIONAL,
    "for_statement": COV.LOOP,
    "while_statement": COV.LOOP,
    "do_while_statement": COV.LOOP,
    "catch_block": COV.RECOVER,
    "finally_block": COV.DEFER,
}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


_INIT_NAMES = {"setUp", "setUpClass", "beforeEach", "beforeAll", "main"}
_TEARDOWN_NAMES = {"tearDown", "tearDownClass", "afterEach", "afterAll"}


def apply_tier2(name: str) -> list[tuple[COV, float]]:
    results = []
    if name in _INIT_NAMES:
        results.append((COV.INIT, 0.95))
    if name in _TEARDOWN_NAMES:
        results.append((COV.TEARDOWN, 0.95))
    if name.startswith("test"):
        results.append((COV.TEST, 0.95))
    return results


_ROUTE_PAT = re.compile(r"@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping|RestController|Controller)\b")
_AUTH_PAT = re.compile(r"@(?:Secured|PreAuthorize|RolesAllowed)\b")
_SCOPE_PAT = re.compile(r"@Transactional\b")
_CONTRACT_PAT = re.compile(r"@(?:Autowired|Inject|Bean|Component|Service|Repository)\b")


def apply_tier3(annotation: str) -> list[tuple[COV, float]]:
    results = []
    if re.search(r"@(?:Test|ParameterizedTest|RepeatedTest)\b", annotation):
        results.append((COV.TEST, 0.9))
    if _ROUTE_PAT.search(annotation):
        results.append((COV.ROUTE, 0.9))
    if _AUTH_PAT.search(annotation):
        results.append((COV.AUTHORIZE, 0.9))
    if _SCOPE_PAT.search(annotation):
        results.append((COV.SCOPE, 0.9))
    if _CONTRACT_PAT.search(annotation):
        results.append((COV.CONTRACT, 0.9))
    if re.search(r"@(?:BeforeEach|BeforeAll|Before)\b", annotation):
        results.append((COV.INIT, 0.9))
    if re.search(r"@(?:AfterEach|AfterAll|After)\b", annotation):
        results.append((COV.TEARDOWN, 0.9))
    if re.search(r"@EventListener\b", annotation):
        results.append((COV.SUBSCRIBE, 0.9))
    return results


_PERSIST_METHODS = {"save", "insert", "create", "write", "persist", "add", "put", "store", "upsert"}
_FETCH_METHODS = {"find", "get", "read", "query", "fetch", "load", "select", "filter", "findone", "findall", "findby"}
_EMIT_METHODS = {"emit", "publish", "dispatch", "send", "broadcast", "trigger", "next"}
_SUBSCRIBE_METHODS = {"on", "subscribe", "listen", "addlistener"}
_TRANSFORM_METHODS = {"map", "transform", "convert", "serialize", "deserialize", "encode", "decode", "format", "parse"}
_MUTATE_METHODS = {"update", "append", "push", "splice", "pop", "delete", "remove", "clear", "set", "patch"}
_VALIDATE_METHODS = {"validate", "check", "ensure", "verify", "assert", "assertvalid"}
_LOG_OBJECTS = {"logger", "log", "console"}
_MEASURE_OBJECTS = {"metrics", "statsd", "counter", "gauge", "histogram", "timer", "telemetry", "prometheus"}


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    results = []
    fn = call_node.named_children[0] if call_node.named_children else None
    if fn is None:
        return results

    method = ""
    obj = ""
    if fn.type == "navigation_expression":
        ids = [node_text(child) for child in fn.named_children if child.type == "identifier"]
        if ids:
            obj = ids[0]
            method = ids[-1]
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
    if lowered in {"launch", "async"}:
        results.append((COV.ASYNC, 0.85))
    if obj_lower in _LOG_OBJECTS:
        results.append((COV.LOG, 0.75))
    if obj_lower in _MEASURE_OBJECTS:
        results.append((COV.MEASURE, 0.75))
    return results


_HERITAGE_CONTRACT = re.compile(r"(?:BaseModel|Schema|Model|Serializable|DTO|Entity|ValueObject)$")
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
