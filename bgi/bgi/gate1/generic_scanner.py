"""
Gate 1 — Generic / fallback language scanner.

Works on ANY text-based language by applying:
  - Multi-strategy function boundary detection (brace-counting, indent-based, keyword-end)
  - Keyword-to-COV body analysis (no AST required)
  - Tier 2 name heuristics

Supported boundary strategies (auto-detected per file):
  BRACE   — C, Java, Go, JS, Rust, Swift, Dart, Kotlin, C#, PHP, Scala ...
  INDENT  — Python, YAML-like, CoffeeScript, Nim ...
  ENDWORD — Ruby, Lua, Elixir, Crystal, VB, MATLAB ...

Accuracy compared to dedicated tree-sitter scanners:
  ~75-80% for COV token assignment (misses AST-level precision)
  ~95%    for function boundary detection in well-formatted code

Use this for any language without a dedicated scanner:
  Swift, Dart, R, Bash, COBOL, Haskell, F#, OCaml, Nim, Zig, V, ...
"""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.rules import dedupe_ordered
from bgi.gate1.ai_fallback import AIFallback


# ── Function definition patterns (ordered: most specific first) ───────────────

# Each entry: (regex, name_group, strategy_hint)
# strategy_hint: "brace" | "indent" | "endword" | "arrow"
_FUNC_PATTERNS: list[tuple[re.Pattern, int, str]] = [
    # Swift: func name(...) -> Type {
    (re.compile(r"^\s*(?:public|private|internal|open|fileprivate|static|class|override|mutating|async|throws|@\w+\s+)*func\s+(\w+)\s*[(<]"), 1, "brace"),
    # Dart: returnType name(...) { OR Future<X> name(...) async {
    (re.compile(r"^\s*(?:Future<\S+>|Stream<\S+>|\w+(?:<[^>]+>)?)\s+(\w+)\s*\(.*\)\s*(?:async\s*)?\{"), 1, "brace"),
    # R: name <- function(...) {  OR  name = function(...) {
    (re.compile(r"^\s*(\w+)\s*(?:<-|=)\s*function\s*\("), 1, "brace"),
    # Bash: name() { OR function name() {
    (re.compile(r"^\s*(?:function\s+)?(\w+)\s*\(\s*\)\s*\{"), 1, "brace"),
    # Haskell/F#/OCaml: let name args = or let rec name args =
    (re.compile(r"^\s*let\s+(?:rec\s+)?(\w+)\s+[^=]*="), 1, "indent"),
    # Nim: proc/func/method name(...):
    (re.compile(r"^\s*(?:proc|func|method|converter|iterator)\s+(\w+)\s*[*(]"), 1, "indent"),
    # Zig: fn name(...) RetType {
    (re.compile(r"^\s*(?:pub\s+)?fn\s+(\w+)\s*\("), 1, "brace"),
    # MATLAB/Octave: function [out] = name(args)  OR  function out = name(args)
    (re.compile(r"^\s*function\s+(?:\[?[\w,\s]*\]?\s*=\s*)?(\w+)\s*\("), 1, "endword"),
    # VB.NET / VBA: Sub/Function name(
    (re.compile(r"^\s*(?:Public|Private|Protected|Friend|Static|Shared|Override|MustOverride|Async)?\s*(?:Sub|Function)\s+(\w+)\s*\(", re.I), 1, "endword"),
    # Crystal: def name(...) [: Type]
    (re.compile(r"^\s*(?:abstract\s+)?def\s+(\w+)[\s(]"), 1, "endword"),
    # Erlang: name(Args) ->
    (re.compile(r"^(\w+)\s*\([^)]*\)\s*->"), 1, "endword"),
    # Clojure/Lisp: (defn name [args]
    (re.compile(r"^\s*\(def(?:n|un|method|multi)[-\s]+(\w[\w\-?!]*)"), 1, "paren"),
    # COBOL: PROCEDURE DIVISION or paragraph names (lines ending in .)
    (re.compile(r"^([A-Z][\w-]*)\s*\.\s*$"), 1, "cobol"),
    # Generic last-resort: function/def/func keyword
    (re.compile(r"^\s*(?:function|def|func|fn|sub|method|procedure)\s+(\w+)\s*[(\[]?"), 1, "brace"),
]

# Class context patterns — used to assign class_context to methods
_CLASS_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*class\s+(\w+)"),           # Python, Swift, Kotlin, C#, Java, PHP, Crystal
    re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)"),  # Rust, Go, Zig
    re.compile(r"^\s*(?:pub\s+)?impl\s+(\w+)"),    # Rust impl block
    re.compile(r"^\s*(?:pub\s+)?interface\s+(\w+)"),  # Go, TS, Java
    re.compile(r"^\s*(?:pub\s+)?enum\s+(\w+)"),    # many languages
    re.compile(r"^\s*(?:pub\s+)?object\s+(\w+)"),  # Scala, Kotlin
    re.compile(r"^\s*(?:pub\s+)?trait\s+(\w+)"),   # Rust, Scala
    re.compile(r"^\s*(?:pub\s+)?module\s+(\w+)"),  # Elixir, VB
    re.compile(r"^\s*(?:pub\s+)?namespace\s+(\w+)"), # PHP, C#, C++
]

# ── COV keyword → token mappings ──────────────────────────────────────────────

# (pattern, COV, confidence)
_BODY_PATTERNS: list[tuple[re.Pattern, COV, float]] = [
    # OUTPUT
    (re.compile(r"\breturn\b"), COV.OUTPUT, 0.9),
    # EMIT
    (re.compile(r"\byield\b"), COV.EMIT, 0.9),
    (re.compile(r"\bsend\b|\bemit\b|\bpublish\b|\bbroadcast\b|\bdispatch\b"), COV.EMIT, 0.75),
    # RAISE
    (re.compile(r"\bthrow\b|\braise\b|\bpanic\b|\berror\b|\bfail\b"), COV.RAISE, 0.85),
    # RECOVER
    (re.compile(r"\bcatch\b|\brescue\b|\bexcept\b|\brecover\b|\bpcall\b|\bxpcall\b"), COV.RECOVER, 0.9),
    # DEFER
    (re.compile(r"\bfinally\b|\bensure\b|\bdefer\b|\bafter\b"), COV.DEFER, 0.9),
    # ASYNC
    (re.compile(r"\basync\b|\bawait\b|\bgoroutine\b|\bspawn\b|\bthread\b|\blaunch\b|\bTask\."), COV.ASYNC, 0.85),
    # CONDITIONAL
    (re.compile(r"\bif\b|\bunless\b|\bswitch\b|\bcase\b|\bwhen\b|\bmatch\b|\bcond\b"), COV.CONDITIONAL, 0.8),
    # LOOP
    (re.compile(r"\bfor\b|\bwhile\b|\bloop\b|\beach\b|\bforEach\b|\brepeat\b|\buntil\b|\bmap\b"), COV.LOOP, 0.75),
    # MUTATE
    (re.compile(r"\bupdate\b|\bpatch\b|\bappend\b|\binsert\b|\bdelete\b|\bremove\b|\bpush\b|\bpop\b"), COV.MUTATE, 0.7),
    # PERSIST
    (re.compile(r"\bsave\b|\bwrite\b|\bstore\b|\bpersist\b|\bcommit\b|\bflush\b"), COV.PERSIST, 0.7),
    # FETCH
    (re.compile(r"\bfetch\b|\bload\b|\bread\b|\bget\b|\bfind\b|\bquery\b|\bselect\b|\bsearch\b"), COV.FETCH, 0.7),
    # TRANSFORM
    (re.compile(r"\btransform\b|\bconvert\b|\bserialize\b|\bdeserialize\b|\bencode\b|\bdecode\b|\bparse\b|\bformat\b"), COV.TRANSFORM, 0.7),
    # VALIDATE
    (re.compile(r"\bvalidate\b|\bverify\b|\bassert\b|\bcheck\b|\bensure\b"), COV.VALIDATE, 0.7),
    # SUBSCRIBE
    (re.compile(r"\bsubscribe\b|\blisten\b|\bon\b|\baddEventListener\b|\bhandle\b|\breceive\b"), COV.SUBSCRIBE, 0.7),
    # LOG
    (re.compile(r"\bprint\b|\bprintf\b|\blog\b|\bdebug\b|\binfo\b|\bwarn\b|\berror_log\b|\bputs\b|\bprintln\b"), COV.LOG, 0.7),
    # SCOPE
    (re.compile(r"\btransaction\b|\bwith\b|\busing\b|\bbegin\b|\bwithTransaction\b"), COV.SCOPE, 0.7),
    # MEASURE
    (re.compile(r"\bmetrics\b|\bcounter\b|\bgauge\b|\bhistogram\b|\btimer\b|\btelemetry\b|\bstatsd\b"), COV.MEASURE, 0.7),
]

# Tier 2 name → COV (applied to function names)
_NAME_INIT     = re.compile(r"^(init|initialize|setup|start|new|create|open|main|constructor|__init__|setUp|beforeEach|beforeAll|before)$", re.I)
_NAME_TEARDOWN = re.compile(r"^(destroy|cleanup|close|shutdown|teardown|stop|dispose|free|__del__|tearDown|afterEach|afterAll|after)$", re.I)
_NAME_TEST     = re.compile(r"^test[_A-Z]|^test$|^spec_|_test$|_spec$", re.I)
_NAME_ASYNC    = re.compile(r"async|spawn|goroutine", re.I)

# COV specificity: rarer/more precise tokens score higher.
# When token count exceeds MAX_COV_TOKENS, lowest-scoring ones are dropped.
_COV_SPECIFICITY: dict[COV, int] = {
    COV.EMIT:     10, COV.MEASURE:  10,
    COV.DEFER:     9, COV.SCOPE:     9,
    COV.PERSIST:   8, COV.FETCH:     8, COV.VALIDATE: 8, COV.TRANSFORM: 8,
    COV.RAISE:     7, COV.RECOVER:   7, COV.ASYNC:    7,
    COV.MUTATE:    6, COV.SUBSCRIBE: 6,
    COV.LOG:       5,
    COV.LOOP:      4, COV.TEST:      4, COV.INIT:      4, COV.TEARDOWN: 4,
    COV.CONDITIONAL: 3,
    COV.OUTPUT:    2, COV.INTAKE:    1,
}
MAX_COV_TOKENS = 6

# ── String/comment stripping — Enhancement 1 ─────────────────────────────────

# Ordered: triple-quoted first (greedy), then single-quoted
# (These were replaced by the _strip_noise state machine — kept as no-ops)


def _strip_noise(source: str) -> str:
    """
    State-machine character-level tokenizer.
    Replaces all string literals and comments with spaces (preserving newlines).
    Handles escape sequences, nested quotes, and all major comment styles.
    More accurate than regex for edge cases like escaped quotes and multiline strings.
    """
    result = []
    i = 0
    n = len(source)

    while i < n:
        c = source[i]
        p2 = source[i:i+2]
        p3 = source[i:i+3]
        p4 = source[i:i+4]

        # Triple-quoted strings (must check before single-quoted)
        if p3 in ('"""', "'''"):
            close = p3
            j = source.find(close, i + 3)
            end = j if j != -1 else n - 3
            chunk = source[i: end + 3 if j != -1 else n]
            result.append('\n' * chunk.count('\n'))
            i = end + 3 if j != -1 else n

        # Lua block comment  --[[ ... ]]
        elif p4 == '--[[':
            j = source.find(']]', i + 4)
            chunk = source[i: (j + 2) if j != -1 else n]
            result.append('\n' * chunk.count('\n'))
            i = (j + 2) if j != -1 else n

        # C-style block comment  /* ... */
        elif p2 == '/*':
            j = source.find('*/', i + 2)
            chunk = source[i: (j + 2) if j != -1 else n]
            result.append('\n' * chunk.count('\n'))
            i = (j + 2) if j != -1 else n

        # Line comment  //
        elif p2 == '//':
            j = source.find('\n', i)
            result.append('\n')
            i = (j + 1) if j != -1 else n

        # Line comment  --  (Lua, Haskell, SQL — but not ->)
        elif p2 == '--' and (i + 2 >= n or source[i + 2] != '>'):
            j = source.find('\n', i)
            result.append('\n')
            i = (j + 1) if j != -1 else n

        # Line comment  #
        elif c == '#':
            j = source.find('\n', i)
            result.append('\n')
            i = (j + 1) if j != -1 else n

        # Double-quoted string
        elif c == '"':
            i += 1
            while i < n:
                ch = source[i]
                if ch == '\\':
                    i += 2
                elif ch == '"':
                    i += 1
                    break
                else:
                    if ch == '\n':
                        result.append('\n')
                    i += 1

        # Single-quoted string
        elif c == "'":
            i += 1
            while i < n:
                ch = source[i]
                if ch == '\\':
                    i += 2
                elif ch == "'":
                    i += 1
                    break
                else:
                    if ch == '\n':
                        result.append('\n')
                    i += 1

        # Backtick string
        elif c == '`':
            i += 1
            while i < n:
                ch = source[i]
                if ch == '`':
                    i += 1
                    break
                else:
                    if ch == '\n':
                        result.append('\n')
                    i += 1

        else:
            result.append(c)
            i += 1

    return ''.join(result)


# ── Body extraction strategies ────────────────────────────────────────────────

def _extract_brace_body(lines: list[str], start: int) -> tuple[int, int]:
    """Find body between first { and matching }. Returns (body_start, body_end) line indices."""
    depth = 0
    in_body = False
    for i, line in enumerate(lines[start:], start):
        depth += line.count("{") - line.count("}")
        if not in_body and "{" in line:
            in_body = True
        if in_body and depth <= 0:
            return start, i
    return start, len(lines) - 1


def _extract_indent_body(lines: list[str], start: int) -> tuple[int, int]:
    """Extract indentation-based body (Python style)."""
    if start + 1 >= len(lines):
        return start, start
    # Find base indent level from next non-empty line
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        indent = len(lines[i]) - len(lines[i].lstrip())
        if indent <= base_indent:
            return start, i - 1
    return start, len(lines) - 1


def _extract_endword_body(lines: list[str], start: int) -> tuple[int, int]:
    """Find body terminated by 'end' keyword (Ruby/Lua/Elixir style)."""
    depth = 0
    _OPEN  = re.compile(r"\b(def|class|module|do|if|case|while|for|begin|function|unless|until)\b")
    _CLOSE = re.compile(r"^\s*end\b")
    for i, line in enumerate(lines[start:], start):
        depth += len(_OPEN.findall(line))
        if i > start and _CLOSE.match(line):
            depth -= 1
            if depth <= 0:
                return start, i
    return start, len(lines) - 1


def _extract_paren_body(lines: list[str], start: int) -> tuple[int, int]:
    """Lisp/Clojure: count parens."""
    depth = 0
    for i, line in enumerate(lines[start:], start):
        depth += line.count("(") - line.count(")")
        if i > start and depth <= 0:
            return start, i
    return start, len(lines) - 1


def _extract_body(lines: list[str], start: int, strategy: str) -> tuple[int, int]:
    if strategy == "indent":
        return _extract_indent_body(lines, start)
    elif strategy == "endword":
        return _extract_endword_body(lines, start)
    elif strategy == "paren":
        return _extract_paren_body(lines, start)
    else:  # brace, arrow, cobol, default
        return _extract_brace_body(lines, start)


# ── COV token extraction from body text ──────────────────────────────────────

def _analyze_body(body_text: str) -> list[tuple[COV, float]]:
    """Run COV patterns against noise-stripped (string/comment-free) body text."""
    clean = _strip_noise(body_text)
    results: list[tuple[COV, float]] = []
    for pattern, token, conf in _BODY_PATTERNS:
        if pattern.search(clean):
            results.append((token, conf))
    return results


def _cap_tokens(tokens: list[COV]) -> list[COV]:
    """Keep only the MAX_COV_TOKENS most-specific tokens to avoid noise floods."""
    if len(tokens) <= MAX_COV_TOKENS:
        return tokens
    return sorted(tokens, key=lambda t: _COV_SPECIFICITY.get(t, 0), reverse=True)[:MAX_COV_TOKENS]


def _analyze_name(func_name: str) -> list[tuple[COV, float]]:
    results: list[tuple[COV, float]] = []
    if _NAME_INIT.search(func_name):
        results.append((COV.INIT, 0.9))
    if _NAME_TEARDOWN.search(func_name):
        results.append((COV.TEARDOWN, 0.9))
    if _NAME_TEST.search(func_name):
        results.append((COV.TEST, 0.9))
    if _NAME_ASYNC.search(func_name):
        results.append((COV.ASYNC, 0.85))
    return results


def _has_params(header_line: str) -> bool:
    """Rough check — does the function signature have meaningful parameters?"""
    m = re.search(r"\(([^)]*)\)", header_line)
    if not m:
        return False
    params = m.group(1).strip()
    # Filter out empty, only `self`/`this`, only `void`
    cleaned = re.sub(r"\b(self|this|void)\b", "", params).replace(",", "").strip()
    return bool(cleaned)


# ── Class context tracking — Enhancement 2 ───────────────────────────────────

def _build_class_map(lines: list[str]) -> dict[int, str]:
    """
    Returns a map of {line_index: class_name} for every line that falls
    inside a class/struct/impl/module body. Uses indentation-based scoping
    for indent languages and brace-depth for brace languages.

    Strategy: on each class-opening line, record the indent level. Any
    subsequent line indented deeper belongs to that class until indent
    drops back to or below the class level.
    """
    class_stack: list[tuple[int, str]] = []  # (indent_level, class_name)
    result: dict[int, str] = {}

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())

        # Pop classes whose indent level is >= current (we've exited them)
        while class_stack and indent <= class_stack[-1][0]:
            class_stack.pop()

        # Check if this line opens a new class/struct/impl/...
        for pat in _CLASS_PATTERNS:
            m = pat.match(line)
            if m:
                class_stack.append((indent, m.group(1)))
                break

        # Record the innermost class for this line
        if class_stack:
            result[i] = class_stack[-1][1]

    return result


# ── Main scanner ──────────────────────────────────────────────────────────────

@dataclass
class _FuncMatch:
    name: str
    line_start: int  # 1-indexed
    line_end: int
    body: str
    header: str
    strategy: str
    class_name: str | None = None  # set by class context pass


def _detect_functions(source: str) -> list[_FuncMatch]:
    """Apply all patterns and return detected function spans with class context."""
    lines = source.splitlines()
    class_map = _build_class_map(lines)
    results: list[_FuncMatch] = []
    used_lines: set[int] = set()

    for pattern, name_group, strategy in _FUNC_PATTERNS:
        for i, line in enumerate(lines):
            if i in used_lines:
                continue
            m = pattern.match(line)
            if not m:
                continue
            name = m.group(name_group)
            # Skip very short names (likely false positives)
            if len(name) < 2:
                continue
            # Skip keywords misidentified as function names
            if name in {"if", "for", "while", "switch", "return", "case", "else",
                        "try", "catch", "do", "new", "class", "import", "from"}:
                continue

            body_start, body_end = _extract_body(lines, i, strategy)
            body_lines = lines[body_start:body_end + 1]
            body_text = "\n".join(body_lines)

            # Mark lines as used to prevent double-detection
            for li in range(i, min(body_end + 1, i + 5)):
                used_lines.add(li)

            results.append(_FuncMatch(
                name=name,
                line_start=i + 1,
                line_end=body_end + 1,
                body=body_text,
                header=line,
                strategy=strategy,
                class_name=class_map.get(i),
            ))

    return results


# ── Python AST fast-path — Enhancement 4 ─────────────────────────────────────
# Call names → COV (Tier 3 equivalent without tree-sitter)
_CALL_COV: list[tuple[re.Pattern, COV]] = [
    (re.compile(r"^(save|persist|commit|flush|write|store|insert|upsert)$"),       COV.PERSIST),
    (re.compile(r"^(find|fetch|get|load|read|query|select|search|retrieve|lookup)$"), COV.FETCH),
    (re.compile(r"^(update|patch|modify|append|delete|remove|pop|push|merge)$"),    COV.MUTATE),
    (re.compile(r"^(transform|convert|serialize|deserialize|encode|decode|parse|format|marshal|unmarshal)$"), COV.TRANSFORM),
    (re.compile(r"^(validate|verify|assert|check|ensure|require)$"),                COV.VALIDATE),
    (re.compile(r"^(log|debug|info|warn|warning|error|critical|print|printf|println|puts)$"), COV.LOG),
    (re.compile(r"^(send|emit|publish|broadcast|dispatch|notify|trigger|fire)$"),   COV.EMIT),
    (re.compile(r"^(subscribe|listen|on|handle|receive|register|watch)$"),          COV.SUBSCRIBE),
    (re.compile(r"^(measure|record|increment|decrement|track|gauge|counter|histogram|timer)$"), COV.MEASURE),
]


def _walk_ast_no_nested(node, stop_types: tuple) -> "Iterator[ast.AST]":
    """Yield AST descendants, stopping recursion into stop_types (but yielding them)."""
    import ast as _ast
    for child in _ast.iter_child_nodes(node):
        yield child
        if not isinstance(child, stop_types):
            yield from _walk_ast_no_nested(child, stop_types)


def _cov_from_ast_node(func_node) -> list[tuple[COV, float]]:
    """
    Walk an ast.FunctionDef / AsyncFunctionDef and return COV tokens.
    Does NOT recurse into nested function definitions (mirrors tree-sitter _walk_body).
    """
    import ast as _ast
    stop = (_ast.FunctionDef, _ast.AsyncFunctionDef)
    collected: list[tuple[COV, float]] = []

    if isinstance(func_node, _ast.AsyncFunctionDef):
        collected.append((COV.ASYNC, 0.95))

    for node in _walk_ast_no_nested(func_node, stop):
        if isinstance(node, _ast.Return) and node.value is not None:
            collected.append((COV.OUTPUT, 0.95))
        elif isinstance(node, (_ast.Yield, _ast.YieldFrom)):
            collected.append((COV.EMIT, 0.95))
        elif isinstance(node, _ast.Raise):
            collected.append((COV.RAISE, 0.95))
        elif isinstance(node, _ast.ExceptHandler):
            collected.append((COV.RECOVER, 0.95))
        elif isinstance(node, _ast.Try) and node.finalbody:
            collected.append((COV.DEFER, 0.95))
        elif isinstance(node, _ast.Await):
            collected.append((COV.ASYNC, 0.95))
        elif isinstance(node, (_ast.For, _ast.While, _ast.AsyncFor)):
            collected.append((COV.LOOP, 0.9))
        elif isinstance(node, _ast.If):
            collected.append((COV.CONDITIONAL, 0.9))
        elif isinstance(node, (_ast.With, _ast.AsyncWith)):
            collected.append((COV.SCOPE, 0.85))
        elif isinstance(node, _ast.Call):
            # Resolve call name (method or function)
            func = node.func
            name = func.attr if isinstance(func, _ast.Attribute) else (
                   func.id  if isinstance(func, _ast.Name) else None)
            if name:
                for pat, cov_token in _CALL_COV:
                    if pat.match(name):
                        collected.append((cov_token, 0.88))
                        break
        # Python 3.10+ structural pattern matching
        elif hasattr(_ast, 'Match') and isinstance(node, _ast.Match):
            collected.append((COV.CONDITIONAL, 0.9))

    return collected


def _python_ast_path(
    source: str,
    rel_path: str,
    ai: AIFallback,
) -> "list[COVFingerprint] | None":
    """
    Fast-path for Python: use the built-in ast module for exact function
    detection, class context, and COV analysis. Returns None on SyntaxError.
    """
    import ast as _ast

    try:
        tree = _ast.parse(source)
    except SyntaxError:
        return None

    lines = source.splitlines()
    fingerprints: list[COVFingerprint] = []

    class _Visitor(_ast.NodeVisitor):
        def __init__(self):
            self._cls: list[str] = []  # class context stack

        def visit_ClassDef(self, node: "_ast.ClassDef"):
            self._cls.append(node.name)
            self.generic_visit(node)
            self._cls.pop()

        def _handle_func(self, node):
            name = node.name
            class_ctx = self._cls[-1] if self._cls else None

            line_start = node.lineno
            line_end = getattr(node, "end_lineno", node.lineno) or node.lineno
            header = lines[line_start - 1] if line_start <= len(lines) else ""

            # Real params: exclude self/cls
            args = node.args
            all_args = list(args.args) + list(args.kwonlyargs)
            if args.vararg:  all_args.append(args.vararg)
            if args.kwarg:   all_args.append(args.kwarg)
            has_params = bool([a for a in all_args if a.arg not in ("self", "cls")])

            collected: list[tuple[COV, float]] = []
            collected.extend(_analyze_name(name))
            if has_params:
                collected.append((COV.INTAKE, 0.9))
            collected.extend(_cov_from_ast_node(node))

            _STRUCTURAL = {COV.ASYNC, COV.INTAKE, COV.INIT, COV.TEARDOWN}
            tokens = dedupe_ordered([t for t, _ in collected])
            if not any(t not in _STRUCTURAL for t in tokens):
                uid_tmp = f"{rel_path}::{name}"
                body = "\n".join(lines[line_start - 1:line_end])
                ai_res = ai.classify_unit(uid_tmp, body, language="python")
                if ai_res:
                    collected.extend(ai_res)

            tokens = _cap_tokens(dedupe_ordered([t for t, _ in collected]))
            confs  = [c for _, c in collected]
            conf   = min(confs) if confs else 0.85
            srcs   = {"ai_classified" if c < 0.9 else "deterministic" for _, c in collected}
            src_lbl = ("composite"    if "ai_classified" in srcs and len(srcs) > 1 else
                       "ai_classified" if "ai_classified" in srcs else "deterministic")

            uid         = f"{rel_path}::{class_ctx}::{name}" if class_ctx else f"{rel_path}::{name}"
            class_field = [class_ctx] if class_ctx else []

            fingerprints.append(COVFingerprint(
                unit_id=uid, tokens=tokens, class_context=class_field,
                confidence=conf, source=src_lbl, language="python",
                line_range=(line_start, line_end),
            ))

            # Walk nested functions with class stack cleared (they're not class methods)
            saved = self._cls[:]
            self._cls.clear()
            self.generic_visit(node)
            self._cls[:] = saved

        def visit_FunctionDef(self, node):      self._handle_func(node)
        def visit_AsyncFunctionDef(self, node): self._handle_func(node)

    _Visitor().visit(tree)
    return fingerprints


def scan_file_generic(
    file_path: Path,
    root: Path,
    ai: AIFallback,
    language: str = "unknown",
) -> list[COVFingerprint]:
    """
    Hybrid generic scanner for any text-based language.

    Fast-paths (when available):
      - Python: uses built-in ast module for exact structural COV + call-site analysis
    Fallback for all other languages:
      - Regex function detection + state-machine string/comment stripping + COV keywords
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel_path = str(file_path.relative_to(root))

    # ── Python AST fast-path ───────────────────────────────────────────────────
    if language == "python":
        result = _python_ast_path(source, rel_path, ai)
        if result is not None:
            return result
        # SyntaxError fallback: continue to regex path below

    funcs = _detect_functions(source)
    fingerprints: list[COVFingerprint] = []

    for func in funcs:
        collected: list[tuple[COV, float]] = []

        # Tier 2 — name heuristics
        collected.extend(_analyze_name(func.name))

        # INTAKE — has parameters?
        if _has_params(func.header):
            collected.append((COV.INTAKE, 0.85))

        # Body keyword analysis (on string/comment-cleaned text)
        collected.extend(_analyze_body(func.body))

        # Unit-level AI fallback if nothing found
        _STRUCTURAL = {COV.ASYNC, COV.INTAKE, COV.INIT, COV.TEARDOWN}
        tokens = dedupe_ordered([t for t, _ in collected])
        if not any(t not in _STRUCTURAL for t in tokens):
            unit_id = f"{rel_path}::{func.name}"
            ai_results = ai.classify_unit(unit_id, func.body, language=language)
            if ai_results:
                collected.extend(ai_results)

        # Enhancement 3: cap tokens by specificity before finalising
        tokens = _cap_tokens(dedupe_ordered([t for t, _ in collected]))
        confidences = [c for _, c in collected]
        confidence = min(confidences) if confidences else 0.7  # generic = lower baseline

        sources = {"ai_classified" if c < 0.9 else "deterministic" for _, c in collected}
        if "ai_classified" in sources and len(sources) > 1:
            source_label = "composite"
        elif "ai_classified" in sources:
            source_label = "ai_classified"
        else:
            source_label = "deterministic"

        # Enhancement 2: include class context in unit_id and class_context field
        if func.class_name:
            unit_id = f"{rel_path}::{func.class_name}::{func.name}"
            class_context = [func.class_name]
        else:
            unit_id = f"{rel_path}::{func.name}"
            class_context = []

        fingerprints.append(COVFingerprint(
            unit_id=unit_id,
            tokens=tokens,
            class_context=class_context,
            confidence=confidence,
            source=source_label,
            language=language,
            line_range=(func.line_start, func.line_end),
        ))

    return fingerprints
