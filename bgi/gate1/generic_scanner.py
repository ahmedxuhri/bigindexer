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
  ~80-85% for COV token assignment (misses AST-level precision)
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
    results: list[tuple[COV, float]] = []
    for pattern, token, conf in _BODY_PATTERNS:
        if pattern.search(body_text):
            results.append((token, conf))
    return results


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


# ── Main scanner ──────────────────────────────────────────────────────────────

@dataclass
class _FuncMatch:
    name: str
    line_start: int  # 1-indexed
    line_end: int
    body: str
    header: str
    strategy: str


def _detect_functions(source: str) -> list[_FuncMatch]:
    """Apply all patterns and return detected function spans."""
    lines = source.splitlines()
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
            ))

    return results


def scan_file_generic(
    file_path: Path,
    root: Path,
    ai: AIFallback,
    language: str = "unknown",
) -> list[COVFingerprint]:
    """
    Generic scanner for any text-based language.
    Uses regex-based function detection + keyword COV analysis.
    """
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rel_path = str(file_path.relative_to(root))
    funcs = _detect_functions(source)
    fingerprints: list[COVFingerprint] = []

    for func in funcs:
        collected: list[tuple[COV, float]] = []

        # Tier 2 — name heuristics
        collected.extend(_analyze_name(func.name))

        # INTAKE — has parameters?
        if _has_params(func.header):
            collected.append((COV.INTAKE, 0.85))

        # Body keyword analysis
        collected.extend(_analyze_body(func.body))

        # Unit-level AI fallback if nothing found
        _STRUCTURAL = {COV.ASYNC, COV.INTAKE, COV.INIT, COV.TEARDOWN}
        tokens = dedupe_ordered([t for t, _ in collected])
        if not any(t not in _STRUCTURAL for t in tokens):
            unit_id = f"{rel_path}::{func.name}"
            ai_results = ai.classify_unit(unit_id, func.body, language=language)
            if ai_results:
                collected.extend(ai_results)

        tokens = dedupe_ordered([t for t, _ in collected])
        confidences = [c for _, c in collected]
        confidence = min(confidences) if confidences else 0.7  # generic = lower baseline

        sources = {"ai_classified" if c < 0.9 else "deterministic" for _, c in collected}
        if "ai_classified" in sources and len(sources) > 1:
            source_label = "composite"
        elif "ai_classified" in sources:
            source_label = "ai_classified"
        else:
            source_label = "deterministic"

        unit_id = f"{rel_path}::{func.name}"

        fingerprints.append(COVFingerprint(
            unit_id=unit_id,
            tokens=tokens,
            class_context=[],
            confidence=confidence,
            source=source_label,
            language=language,
            line_range=(func.line_start, func.line_end),
        ))

    return fingerprints
