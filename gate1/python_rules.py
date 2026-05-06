"""
Gate 1 — Python-specific COV mapping rules (Tiers 1–5).
Each tier returns a list of (COV, confidence) pairs for a given node/context.
"""
from __future__ import annotations
import re

from tree_sitter import Node

from bgi.core.cov import COV
from bgi.gate1.rules import node_text, call_attribute_name, call_object_name


# ── Tier 1 — AST node type → COV (confidence 1.0) ────────────────────────────

_TIER1: dict[str, COV] = {
    "return_statement":        COV.OUTPUT,
    "yield":                   COV.EMIT,
    "yield_from":              COV.EMIT,
    "raise_statement":         COV.RAISE,
    "assert_statement":        COV.GUARD,
    "except_clause":           COV.RECOVER,
    "finally_clause":          COV.DEFER,
    "for_statement":           COV.LOOP,
    "while_statement":         COV.LOOP,
    "if_statement":            COV.CONDITIONAL,
    "elif_clause":             COV.CONDITIONAL,
    "match_statement":         COV.CONDITIONAL,  # PATTERN_MATCH → extension zone
    "with_statement":          COV.SCOPE,
    "await":                   COV.ASYNC,         # tree-sitter uses "await" not "await_expression"
    "augmented_assignment":    COV.MUTATE,
    "list_comprehension":      COV.TRANSFORM,
    "dictionary_comprehension": COV.TRANSFORM,
    "set_comprehension":        COV.TRANSFORM,
    "generator_expression":    COV.TRANSFORM,
}

# assignment → MUTATE only if left-hand side is attribute or subscript
_STATE_MUTATION_LHS = {"attribute", "subscript"}


def apply_tier1(node: Node) -> tuple[COV, float] | None:
    if node.type == "assignment":
        left = node.child_by_field_name("left")
        if left and left.type in _STATE_MUTATION_LHS:
            return (COV.MUTATE, 1.0)
        return None

    token = _TIER1.get(node.type)
    return (token, 1.0) if token else None


# ── Tier 2 — function name → COV (confidence 0.95) ───────────────────────────

_TIER2_INIT = {
    "__init__", "__new__", "__post_init__",
    "setUp", "setup_method", "setup",
    "startup", "on_startup",
}
_TIER2_TEARDOWN = {
    "__del__", "__exit__", "__aexit__",
    "tearDown", "teardown_method", "teardown",
    "shutdown", "on_shutdown",
}
_TIER2_TEST_PREFIXES = ("test_", "Test")


def apply_tier2(func_name: str) -> list[tuple[COV, float]]:
    results = []
    if func_name in _TIER2_INIT:
        results.append((COV.INIT, 0.95))
    if func_name in _TIER2_TEARDOWN:
        results.append((COV.TEARDOWN, 0.95))
    if func_name.startswith("test_") or func_name.startswith("Test"):
        results.append((COV.TEST, 0.95))
    return results


# ── Tier 3 — decorator → COV (confidence 0.9) ────────────────────────────────

_ROUTE_PATTERNS = re.compile(
    r"(app|router|blueprint|api)\.(route|get|post|put|delete|patch|head|options)\b"
)
_AUTH_PATTERNS    = re.compile(r"login_required|requires_auth|auth_required")
_AUTHZ_PATTERNS   = re.compile(r"permission_required|roles_required|requires_permission")
_SUBSCRIBE_PATTERNS = re.compile(r"receiver|signal|on_event\b")
_LIFECYCLE_START  = re.compile(r"on_event\s*\(\s*['\"]startup['\"]")
_LIFECYCLE_STOP   = re.compile(r"on_event\s*\(\s*['\"]shutdown['\"]")
_SCOPE_PATTERNS   = re.compile(r"(async)?contextmanager|transaction\.atomic")
_RECOVER_PATTERNS = re.compile(r"retry|backoff\.")
_MEMOIZE_PATTERNS = re.compile(r"(lru_cache|cache|cached)\b")
_VALIDATE_PATTERNS = re.compile(r"validate|validator\b")
_ASYNC_PATTERNS   = re.compile(r"(celery\.task|shared_task|task)\b")


def apply_tier3(decorator_text: str) -> list[tuple[COV, float]]:
    results = []
    d = decorator_text

    if _LIFECYCLE_START.search(d):
        results.append((COV.INIT, 0.9))
    elif _LIFECYCLE_STOP.search(d):
        results.append((COV.TEARDOWN, 0.9))
    elif _SUBSCRIBE_PATTERNS.search(d):
        results.append((COV.SUBSCRIBE, 0.9))

    if _ROUTE_PATTERNS.search(d):
        results.append((COV.ROUTE, 0.9))
    if _AUTH_PATTERNS.search(d):
        results.append((COV.AUTHENTICATE, 0.9))
    if _AUTHZ_PATTERNS.search(d):
        results.append((COV.AUTHORIZE, 0.9))
    if _SCOPE_PATTERNS.search(d):
        results.append((COV.SCOPE, 0.9))
    if _RECOVER_PATTERNS.search(d):
        results.append((COV.RECOVER, 0.9))
    if _MEMOIZE_PATTERNS.search(d):
        # MEMOIZE → extension zone; map to FETCH for now (it's a cache read)
        results.append((COV.FETCH, 0.8))
    if _VALIDATE_PATTERNS.search(d):
        results.append((COV.VALIDATE, 0.9))
    if _ASYNC_PATTERNS.search(d):
        results.append((COV.ASYNC, 0.9))

    return results


# ── Tier 4 — call target → COV (confidence 0.75) ─────────────────────────────

_PERSIST_METHODS = {
    "save", "insert", "create", "write", "persist",
    "add", "put", "store", "dump", "export",
}
_FETCH_METHODS = {
    "find", "get", "read", "query", "fetch", "load",
    "select", "filter", "all", "first", "last", "retrieve",
}
_EMIT_METHODS   = {"emit", "publish", "dispatch", "send", "broadcast", "trigger"}
_SUBSCRIBE_METHODS = {"on", "subscribe", "listen", "attach", "connect", "register"}
_TRANSFORM_METHODS = {"map", "transform", "convert", "project", "serialize", "deserialize", "encode", "decode"}
_MUTATE_METHODS = {"update", "append", "extend", "remove", "pop", "delete", "clear", "setdefault"}
_VALIDATE_METHODS = {"validate", "check", "ensure", "verify", "assert_valid"}

_LOG_OBJECTS    = re.compile(r"^(logging|logger|log|LOG)$")
_MEASURE_OBJECTS = re.compile(r"^(metrics|statsd|counter|gauge|histogram|timer|telemetry)$")


def apply_tier4(call_node: Node) -> list[tuple[COV, float]]:
    method = call_attribute_name(call_node)
    obj    = call_object_name(call_node)
    results = []

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


# ── Tier 5 — class base → COV (confidence 0.9) ───────────────────────────────

_BASE_CONTRACT  = {"ABC", "Protocol", "TypedDict", "BaseModel", "Schema", "Enum", "IntEnum", "NamedTuple"}
_BASE_RAISE     = {"Exception", "BaseException", "ValueError", "RuntimeError", "TypeError"}
_BASE_TEST      = {"TestCase", "TransactionTestCase", "AsyncTestCase"}
_BASE_TRANSFORM = {"Serializer", "ModelSerializer", "BaseSerializer"}
_BASE_PERSIST   = {"Repository", "BaseRepository"}
_BASE_SUBSCRIBE = {"Consumer", "Subscriber", "BaseConsumer"}
_BASE_ROUTE     = {"View", "APIView", "ViewSet", "ModelViewSet"}


def apply_tier5(base_name: str) -> list[tuple[COV, float]]:
    results = []
    if base_name in _BASE_CONTRACT:
        results.append((COV.CONTRACT, 0.9))
    if base_name in _BASE_RAISE:
        results.append((COV.RAISE, 0.9))
    if base_name in _BASE_TEST:
        results.append((COV.TEST, 0.9))
    if base_name in _BASE_TRANSFORM:
        results.append((COV.TRANSFORM, 0.9))
    if base_name in _BASE_PERSIST:
        results.append((COV.PERSIST, 0.9))
    if base_name in _BASE_SUBSCRIBE:
        results.append((COV.SUBSCRIBE, 0.9))
    if base_name in _BASE_ROUTE:
        results.append((COV.ROUTE, 0.9))
    return results


# ── Decorator route path extraction ──────────────────────────────────────────
# Parse the HTTP method and path from a route decorator string.
# Handles: @app.get("/users"), @router.post('/items/{id}'), @api.route("/", methods=["GET"])

_DECORATOR_ROUTE_RE = re.compile(
    r"""
    (?:app|router|blueprint|api|bp)             # object name
    \.(?P<method>route|get|post|put|delete|patch|head|options)  # HTTP verb
    \s*\(\s*                                    # opening paren
    (?P<q>['"])(?P<path>[^'"]+)(?P=q)           # first string arg = path
    """,
    re.VERBOSE,
)
# For @router.route("/path", methods=["GET", "POST"]) — extract methods list
_METHODS_ARG_RE = re.compile(r'methods\s*=\s*\[([^\]]+)\]')
_HTTP_METHODS_PY = {"get", "post", "put", "delete", "patch", "head", "options"}


def extract_python_route_info(decorator_text: str) -> tuple[str, str] | None:
    """
    Extract (METHOD, path) from a Python route decorator string.
    Returns None if this is not a recognized route decorator.

    Examples:
      @app.get("/users")            → ("GET", "/users")
      @router.post('/items/{id}')   → ("POST", "/items/{id}")
      @api.route("/", methods=["GET", "POST"]) → ("GET", "/")  # first method
    """
    m = _DECORATOR_ROUTE_RE.search(decorator_text)
    if not m:
        return None
    method_str = m.group("method").lower()
    path = m.group("path")
    if method_str == "route":
        # Extract from methods=[...] arg, default to GET
        mm = _METHODS_ARG_RE.search(decorator_text)
        if mm:
            raw = mm.group(1)
            methods = [x.strip().strip("'\"") for x in raw.split(",")]
            method_str = methods[0].lower() if methods else "get"
        else:
            method_str = "get"
    if method_str not in _HTTP_METHODS_PY:
        return None
    return (method_str.upper(), path)

