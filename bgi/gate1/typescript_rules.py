"""
Gate 1 — TypeScript-specific COV mapping rules (Tiers 1–5).

TypeScript AST node types differ from Python in several key ways:
  - yield_expression (not 'yield')
  - throw_statement (not 'raise_statement')
  - for_in_statement covers both for-of and for-in
  - catch_clause is a sibling of try_statement (not nested inside)
  - augmented_assignment_expression (not 'augmented_assignment')
  - assignment_expression LHS is member_expression for attribute mutation
  - Decorators sit directly on class/method nodes (not in parent decorated_definition)
  - Class heritage uses class_heritage > extends_clause / implements_clause
"""
from __future__ import annotations
import re

from tree_sitter import Node

from bgi.core.cov import COV


# ── Helpers ───────────────────────────────────────────────────────────────────

def node_text(node: Node | None) -> str:
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


# ── Tier 1 — AST node type → COV (confidence 1.0) ────────────────────────────

_TIER1: dict[str, COV] = {
    "return_statement":                 COV.OUTPUT,
    "yield_expression":                 COV.EMIT,
    "throw_statement":                  COV.RAISE,
    "catch_clause":                     COV.RECOVER,
    "finally_clause":                   COV.DEFER,
    "for_statement":                    COV.LOOP,
    "for_in_statement":                 COV.LOOP,   # for-of and for-in
    "while_statement":                  COV.LOOP,
    "do_statement":                     COV.LOOP,
    "if_statement":                     COV.CONDITIONAL,
    "switch_statement":                 COV.CONDITIONAL,
    "await_expression":                 COV.ASYNC,
    "augmented_assignment_expression":  COV.MUTATE,
}

# assignment_expression → MUTATE only if LHS is member_expression
_MUTATION_LHS = {"member_expression", "subscript_expression"}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    if node.type == "assignment_expression":
        left = node.child_by_field_name("left")
        if left and left.type in _MUTATION_LHS:
            return (COV.MUTATE, 1.0)
        return None

    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


# ── Tier 2 — function/method name → COV (confidence 0.95) ────────────────────

_TIER2_INIT = {
    "constructor",
    # Angular lifecycle
    "ngOnInit", "ngAfterViewInit", "ngOnChanges", "ngAfterContentInit",
    # React lifecycle
    "componentDidMount", "componentDidUpdate", "componentWillMount",
    # Jest / test frameworks
    "beforeEach", "beforeAll",
    # General patterns
    "setup", "setUp", "initialize", "init",
    "startup", "onStartup", "onInit",
}

_TIER2_TEARDOWN = {
    "ngOnDestroy", "ngAfterViewDestroyed",
    "componentWillUnmount", "componentWillUnmount",
    "afterEach", "afterAll",
    "teardown", "tearDown", "destroy", "dispose", "cleanup",
    "shutdown", "onShutdown", "onDestroy",
}

_TIER2_TEST_PREFIXES = ("test_", "test", "it_", "spec_")
_TIER2_TEST_EXACT = {"it", "test", "describe", "expect"}  # jest global fns used as method names


def apply_tier2(func_name: str) -> list[tuple[COV, float]]:
    results = []
    if func_name in _TIER2_INIT:
        results.append((COV.INIT, 0.95))
    if func_name in _TIER2_TEARDOWN:
        results.append((COV.TEARDOWN, 0.95))
    if (func_name.startswith("test") and len(func_name) > 4) or func_name in _TIER2_TEST_EXACT:
        results.append((COV.TEST, 0.95))
    return results


# ── Tier 3 — decorator → COV (confidence 0.9) ────────────────────────────────

# NestJS
_NESTJS_ROUTE   = re.compile(r"@(Controller|Get|Post|Put|Delete|Patch|Head|Options|All)\b")
_NESTJS_AUTH    = re.compile(r"@(UseGuards|Guard|AuthGuard)\b")
_NESTJS_AUTHZ   = re.compile(r"@(Roles|Permissions|RequireRole)\b")
_NESTJS_INJECT  = re.compile(r"@(Injectable|Inject|Module)\b")
_NESTJS_PIPE    = re.compile(r"@(UsePipes|Pipe)\b")
_NESTJS_INTER   = re.compile(r"@(UseInterceptors|Interceptor)\b")

# Angular
_ANGULAR_COMP   = re.compile(r"@(Component|NgModule|Pipe|Directive)\b")
_ANGULAR_SVC    = re.compile(r"@Injectable\b")

# General
_ROUTE_PATTERNS   = re.compile(r"@(route|Route|router\.|app\.)(get|post|put|delete|patch|route|use)\b", re.I)
_AUTH_PATTERNS    = re.compile(r"@(auth|login|requires?Auth|jwt|bearer|session)", re.I)
_SUBSCRIBE_PAT    = re.compile(r"@(On|EventPattern|MessagePattern|Subscribe)\b")
_SCOPE_PAT        = re.compile(r"@(Transactional|Transaction|transactional)\b")
_RECOVER_PAT      = re.compile(r"@(Retry|retry|backoff|Backoff)\b")
_MEMOIZE_PAT      = re.compile(r"@(Memoize|memoize|Cache|cache|CacheKey)\b")
_VALIDATE_PAT     = re.compile(r"@(Validate|validate|ValidateNested|IsValid)\b")
_LIFECYCLE_START  = re.compile(r"@(OnApplicationBootstrap|OnModuleInit|app\.on\(['\"]ready)")
_LIFECYCLE_STOP   = re.compile(r"@(OnApplicationShutdown|OnModuleDestroy|app\.on\(['\"]close)")


def apply_tier3(decorator_text: str) -> list[tuple[COV, float]]:
    d = decorator_text
    results = []

    if _LIFECYCLE_START.search(d):
        results.append((COV.INIT, 0.9))
    elif _LIFECYCLE_STOP.search(d):
        results.append((COV.TEARDOWN, 0.9))
    elif _SUBSCRIBE_PAT.search(d):
        results.append((COV.SUBSCRIBE, 0.9))

    if _NESTJS_ROUTE.search(d) or _ROUTE_PATTERNS.search(d):
        results.append((COV.ROUTE, 0.9))
    if _NESTJS_AUTH.search(d) or _AUTH_PATTERNS.search(d):
        results.append((COV.AUTHENTICATE, 0.9))
    if _NESTJS_AUTHZ.search(d):
        results.append((COV.AUTHORIZE, 0.9))
    if _NESTJS_INJECT.search(d) or _ANGULAR_COMP.search(d) or _ANGULAR_SVC.search(d):
        results.append((COV.CONTRACT, 0.9))
    if _NESTJS_PIPE.search(d) or _VALIDATE_PAT.search(d):
        results.append((COV.VALIDATE, 0.9))
    if _NESTJS_INTER.search(d):
        results.append((COV.DELEGATE, 0.9))  # interceptors delegate to next handler
    if _SCOPE_PAT.search(d):
        results.append((COV.SCOPE, 0.9))
    if _RECOVER_PAT.search(d):
        results.append((COV.RECOVER, 0.9))
    if _MEMOIZE_PAT.search(d):
        results.append((COV.FETCH, 0.8))    # MEMOIZE → extension zone; FETCH for now

    return results


# ── Tier 4 — call target → COV (confidence 0.75) ─────────────────────────────

_PERSIST_METHODS  = {"save", "insert", "create", "write", "persist", "add", "put", "store", "upsert"}
_FETCH_METHODS    = {"find", "get", "read", "query", "fetch", "load", "select", "filter", "findOne", "findAll", "findBy"}
_EMIT_METHODS     = {"emit", "publish", "dispatch", "send", "broadcast", "trigger", "next"}
_SUBSCRIBE_METHODS = {"on", "subscribe", "listen", "addListener", "addEventListener", "pipe"}
_TRANSFORM_METHODS = {"map", "transform", "convert", "serialize", "deserialize", "encode", "decode", "format", "parse"}
_MUTATE_METHODS   = {"update", "append", "push", "splice", "pop", "delete", "remove", "clear", "set", "patch"}
_VALIDATE_METHODS = {"validate", "check", "ensure", "verify", "assert", "assertValid"}

_LOG_OBJECTS      = re.compile(r"^(console|logger|log|Logger|winston|pino|bunyan)$")
_MEASURE_OBJECTS  = re.compile(r"^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$")


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    """Extract COV from a call_expression node."""
    results = []
    fn = call_node.child_by_field_name("function")
    if fn is None:
        return results

    method: str | None = None
    obj: str | None = None

    if fn.type == "member_expression":
        obj_node = fn.child_by_field_name("object")
        prop_node = fn.child_by_field_name("property")
        obj = node_text(obj_node) if obj_node else None
        method = node_text(prop_node) if prop_node else None
    elif fn.type == "identifier":
        method = node_text(fn)

    if method is None:
        return results

    if method in _PERSIST_METHODS:
        results.append((COV.PERSIST, 0.75))
    elif method in _FETCH_METHODS:
        results.append((COV.FETCH, 0.75))

    if method in _EMIT_METHODS:
        results.append((COV.EMIT, 0.75))
    if method in _SUBSCRIBE_METHODS:
        results.append((COV.SUBSCRIBE, 0.75))
    if method in _TRANSFORM_METHODS:
        results.append((COV.TRANSFORM, 0.75))
    if method in _MUTATE_METHODS:
        results.append((COV.MUTATE, 0.75))
    if method in _VALIDATE_METHODS:
        results.append((COV.VALIDATE, 0.75))

    if obj and _LOG_OBJECTS.match(obj):
        results.append((COV.LOG, 0.75))
    if obj and _MEASURE_OBJECTS.match(obj):
        results.append((COV.MEASURE, 0.75))

    return results


# ── Tier 5 — class heritage (extends / implements) → COV (confidence 0.9) ─────

_HERITAGE_CONTRACT  = re.compile(r"^(BaseModel|Schema|Model|Serializable|DTO|Entity|ValueObject|Enum|interface)$")
_HERITAGE_RAISE     = re.compile(r"(Error|Exception|Fault)$")
_HERITAGE_TEST      = re.compile(r"(TestCase|Spec|Suite)$")
_HERITAGE_PERSIST   = re.compile(r"(Repository|BaseRepository|Store|Dao|AbstractRepository)$")
_HERITAGE_SUBSCRIBE = re.compile(r"(Consumer|Subscriber|Handler|Listener|EventHandler)$")
_HERITAGE_ROUTE     = re.compile(r"(Controller|Router|View|BaseView|ControllerBase)$")
_HERITAGE_AUTH      = re.compile(r"(Guard|AuthGuard|CanActivate|CanActivateChild|CanDeactivate)$")
_HERITAGE_AUTHZ     = re.compile(r"(PermissionGuard|RoleGuard|AccessGuard)$")

# interface_declaration is always CONTRACT
INTERFACE_TOKEN = COV.CONTRACT


def apply_tier5(heritage_name: str) -> list[tuple[COV, float]]:
    results = []
    if _HERITAGE_CONTRACT.match(heritage_name):
        results.append((COV.CONTRACT, 0.9))
    if _HERITAGE_RAISE.search(heritage_name):
        results.append((COV.RAISE, 0.9))
    if _HERITAGE_TEST.search(heritage_name):
        results.append((COV.TEST, 0.9))
    if _HERITAGE_PERSIST.search(heritage_name):
        results.append((COV.PERSIST, 0.9))
    if _HERITAGE_SUBSCRIBE.search(heritage_name):
        results.append((COV.SUBSCRIBE, 0.9))
    if _HERITAGE_ROUTE.search(heritage_name):
        results.append((COV.ROUTE, 0.9))
    if _HERITAGE_AUTH.search(heritage_name):
        results.append((COV.AUTHENTICATE, 0.9))
    if _HERITAGE_AUTHZ.search(heritage_name):
        results.append((COV.AUTHORIZE, 0.9))
    return results
