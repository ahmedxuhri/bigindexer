"""
Gate 1 — Python file scanner.
Walks a directory, parses Python files with tree-sitter,
and produces COVFingerprint objects for every function/method.
"""
from __future__ import annotations
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Node

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.rules import dedupe_ordered, node_text
from bgi.gate1.python_rules import (
    apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5,
)
from bgi.gate1.ai_fallback import AIFallback

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)

_FUNC_TYPES = {"function_definition"}  # tree-sitter uses function_definition for both sync & async
_STOP_RECURSE = _FUNC_TYPES  # don't walk into nested functions during body scan


def _walk_body(node: Node):
    """Yield all descendant nodes, stopping recursion at nested function definitions."""
    for child in node.children:
        yield child
        if child.type not in _STOP_RECURSE:
            yield from _walk_body(child)


_MEANINGFUL_PARAM_TYPES = {
    "identifier",          # plain param: def f(x)
    "typed_parameter",     # typed param: def f(x: int)
    "default_parameter",   # default param: def f(x=1)
    "typed_default_parameter",  # typed + default: def f(x: int = 1)
    "list_splat_pattern",  # *args
    "dictionary_splat_pattern",  # **kwargs
}


def _has_meaningful_params(params_node: Node) -> bool:
    """True if the function has at least one non-self/cls parameter."""
    if params_node is None:
        return False
    for child in params_node.children:
        if child.type not in _MEANINGFUL_PARAM_TYPES:
            continue
        name = node_text(child.child_by_field_name("name") or child)
        if name not in ("self", "cls"):
            return True
    return False


def _get_decorators(func_node: Node) -> list[str]:
    """
    Return decorator texts for a function node.
    In tree-sitter Python, decorators live in the parent decorated_definition.
    """
    parent = func_node.parent
    if parent is None or parent.type != "decorated_definition":
        return []
    return [
        node_text(child)
        for child in parent.children
        if child.type == "decorator"
    ]


def _get_class_context(func_node: Node) -> list[tuple[COV, float]]:
    """
    Walk up to the enclosing class_definition (if any) and apply Tier 5 rules
    to its base classes. Returns list of (COV, confidence).
    """
    parent = func_node.parent
    # parent is usually the block inside the class
    if parent and parent.type == "block":
        parent = parent.parent
    if parent is None or parent.type != "class_definition":
        return []

    argument_list = parent.child_by_field_name("superclasses")
    if argument_list is None:
        return []

    results = []
    for child in argument_list.children:
        if child.type in ("identifier", "attribute"):
            base_name = node_text(child).split(".")[-1]  # strip module prefix
            results.extend(apply_tier5(base_name))
    return results


def _class_name_for(func_node: Node) -> str | None:
    """Return the enclosing class name, or None for top-level functions."""
    parent = func_node.parent
    if parent and parent.type == "block":
        parent = parent.parent
    if parent and parent.type == "class_definition":
        name_node = parent.child_by_field_name("name")
        return node_text(name_node) if name_node else None
    return None


def fingerprint_function(
    func_node: Node,
    rel_path: str,
    ai: AIFallback,
) -> COVFingerprint:
    """Produce a COVFingerprint for a single function/method node."""

    func_name = node_text(func_node.child_by_field_name("name"))
    class_name = _class_name_for(func_node)
    unit_id = (
        f"{rel_path}::{class_name}::{func_name}"
        if class_name
        else f"{rel_path}::{func_name}"
    )

    collected: list[tuple[COV, float]] = []

    # ASYNC flag — tree-sitter marks async functions with an 'async' child token
    if any(c.type == "async" for c in func_node.children):
        collected.append((COV.ASYNC, 1.0))

    # Tier 2 — function name
    collected.extend(apply_tier2(func_name))

    # INTAKE — meaningful parameters
    params = func_node.child_by_field_name("parameters")
    if _has_meaningful_params(params):
        collected.append((COV.INTAKE, 1.0))

    # Tier 3 — decorators
    for dec_text in _get_decorators(func_node):
        collected.extend(apply_tier3(dec_text))

    # Walk function body — Tier 1 + Tier 4
    body = func_node.child_by_field_name("body")
    if body:
        for node in _walk_body(body):
            t1 = apply_tier1(node)
            if t1:
                collected.append(t1)
                continue
            if node.type == "call":
                t4 = apply_tier4(node)
                if t4:
                    collected.extend(t4)
                else:
                    # Tier 6 — AI fallback for unclassified calls
                    ai_result = ai.classify(node, context_snippet=node_text(node))
                    if ai_result:
                        collected.append(ai_result)

    # Class context (Tier 5) — kept separate
    class_context_raw = _get_class_context(func_node)
    class_context_tokens = dedupe_ordered([t for t, _ in class_context_raw])

    # Dedupe method-level tokens, preserve order
    tokens = dedupe_ordered([t for t, _ in collected])

    # Unit-level AI fallback — fires when no behavioural tokens were found
    _STRUCTURAL = {COV.ASYNC, COV.INTAKE}
    if not any(t not in _STRUCTURAL for t in tokens):
        source_text = node_text(func_node)
        unit_results = ai.classify_unit(unit_id, source_text, language="python")
        if unit_results:
            collected.extend(unit_results)
            tokens = dedupe_ordered([t for t, _ in collected])

    # Confidence = minimum across all matched rules
    confidences = [c for _, c in collected]
    confidence = min(confidences) if confidences else 1.0

    # Source type
    sources = {src for t, c in collected for src in (
        ["ai_classified"] if c < 0.9 and c > 0.0 else ["deterministic"]
    )}
    if "ai_classified" in sources and len(sources) > 1:
        source = "composite"
    elif "ai_classified" in sources:
        source = "ai_classified"
    else:
        source = "deterministic"

    # Line range (1-indexed)
    line_range = (
        func_node.start_point[0] + 1,
        func_node.end_point[0] + 1,
    )

    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=class_context_tokens,
        confidence=confidence,
        source=source,
        language="python",
        line_range=line_range,
    )


def _collect_functions(node: Node, results: list[Node], depth: int = 0) -> None:
    """Collect all function/method nodes, one level of nesting deep."""
    for child in node.children:
        if child.type in _FUNC_TYPES:
            results.append(child)
            # collect methods inside classes but not further nested functions
            if depth == 0:
                body = child.child_by_field_name("body")
                if body:
                    _collect_functions(body, results, depth + 1)
        elif child.type == "class_definition":
            body = child.child_by_field_name("body")
            if body:
                _collect_functions(body, results, depth)
        elif child.type == "decorated_definition":
            _collect_functions(child, results, depth)
        elif depth == 0:
            _collect_functions(child, results, depth)


def scan_file(
    file_path: Path,
    root: Path,
    ai: AIFallback,
) -> list[COVFingerprint]:
    """Parse one Python file and return fingerprints for all its functions."""
    source = file_path.read_bytes()
    tree = _PARSER.parse(source)
    rel_path = str(file_path.relative_to(root))

    func_nodes: list[Node] = []
    _collect_functions(tree.root_node, func_nodes)

    return [fingerprint_function(fn, rel_path, ai) for fn in func_nodes]


def scan_directory(
    root: Path,
    language: str = "python",
    ai: AIFallback | None = None,
    scan_run: str = "",
) -> list[COVFingerprint]:
    """
    Scan all source files under root and return fingerprints.
    Supported languages: python, typescript/tsx/ts, javascript/jsx/js, java, go, rust, ruby.
    """
    language = language.lower()
    ai = ai or AIFallback(enabled=False)
    fingerprints: list[COVFingerprint] = []

    if language == "python":
        source_files = sorted(root.rglob("*.py"))
        _scan_fn = scan_file
    elif language in ("typescript", "tsx", "ts"):
        from bgi.gate1.ts_scanner import scan_file_ts
        exts = {"*.ts", "*.tsx"} if language in ("tsx", "ts") else {"*.ts"}
        source_files = sorted(
            f for ext in exts for f in root.rglob(ext)
            if ".d.ts" not in f.name  # skip declaration files
        )
        _scan_fn = scan_file_ts
    elif language in ("javascript", "jsx", "js"):
        from bgi.gate1.js_scanner import scan_file_js
        exts = {"*.js", "*.jsx"} if language in ("jsx", "js") else {"*.js"}
        source_files = sorted(f for ext in exts for f in root.rglob(ext))
        _scan_fn = scan_file_js
    elif language == "java":
        from bgi.gate1.java_scanner import scan_file_java
        source_files = sorted(root.rglob("*.java"))
        _scan_fn = scan_file_java
    elif language == "go":
        from bgi.gate1.go_scanner import scan_file_go
        source_files = sorted(root.rglob("*.go"))
        _scan_fn = scan_file_go
    elif language == "rust":
        from bgi.gate1.rust_scanner import scan_file_rust
        source_files = sorted(root.rglob("*.rs"))
        _scan_fn = scan_file_rust
    elif language == "ruby":
        from bgi.gate1.ruby_scanner import scan_file_ruby
        source_files = sorted(root.rglob("*.rb"))
        _scan_fn = scan_file_ruby
    else:
        raise NotImplementedError(f"Language '{language}' not yet supported.")

    for src_file in source_files:
        try:
            fingerprints.extend(_scan_fn(src_file, root, ai))
        except Exception as exc:
            print(f"[BGI] Warning: skipped {src_file}: {exc}")

    # Flush unresolved call snippets to disk for curator consumption
    ai.flush(scan_run=scan_run)

    return fingerprints
