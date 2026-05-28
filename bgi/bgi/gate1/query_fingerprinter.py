"""
WATER-CLOCK: Single-pass COV token extraction via tree-sitter .scm queries.

Public API::

    tokens = get_node_tokens(func_body_node, "python")
    # returns list[(COV, confidence)] or None if no .scm file for the language

The key design properties:
  - Accepts an already-parsed tree-sitter Node (avoids re-parsing the file)
  - Runs one compiled query call instead of iterating every body node in Python
  - Caches compiled Language.query() objects per language (expensive to create)
  - Returns None → caller falls back to the existing two-pass (Tier 1 + Tier 4) walk
  - Returns [] → query ran successfully, function has no matching body patterns
"""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from bgi.core.cov import COV

if TYPE_CHECKING:
    from tree_sitter import Node


# ── Capture name → COV mapping ────────────────────────────────────────────────
# Only names that are actual COV tokens; internal filter captures (@name, @obj,
# @method, @_lhs) are intentionally absent and will be silently skipped.
_CAPTURE_TO_COV: dict[str, COV] = {
    "output":      COV.OUTPUT,
    "emit":        COV.EMIT,
    "transform":   COV.TRANSFORM,
    "mutate":      COV.MUTATE,
    "sanitize":    COV.SANITIZE,
    "conditional": COV.CONDITIONAL,
    "loop":        COV.LOOP,
    "guard":       COV.GUARD,
    "scope":       COV.SCOPE,
    "fetch":       COV.FETCH,
    "persist":     COV.PERSIST,
    "subscribe":   COV.SUBSCRIBE,
    "validate":    COV.VALIDATE,
    "log":         COV.LOG,
    "measure":     COV.MEASURE,
    "raise":       COV.RAISE,
    "recover":     COV.RECOVER,
    "defer":       COV.DEFER,
    "async":       COV.ASYNC,
    "route":        COV.ROUTE,
    "delegate":     COV.DELEGATE,
    "contract":     COV.CONTRACT,
    "compose":      COV.COMPOSE,
    "init":         COV.INIT,
    "teardown":     COV.TEARDOWN,
    "authenticate": COV.AUTHENTICATE,
    "authorize":    COV.AUTHORIZE,
    "test":         COV.TEST,
}

# Captures produced by pure structural AST patterns (no #match? predicates).
# These get confidence 1.0; all other (method-name predicate) captures get 0.75.
_STRUCTURAL_CAPTURES = frozenset({
    "output", "emit", "conditional", "loop", "guard",
    "scope", "raise", "recover", "defer", "async",
    "transform", "mutate",  # both have structural forms in the .scm files
})


# ── Per-language query cache ──────────────────────────────────────────────────
# Values: compiled Query object, or None if unavailable (prevents retrying)
_QUERY_CACHE: dict[str, object] = {}


def _load_query(lang: str) -> object | None:
    """Compile and cache the .scm query for *lang*. Returns None if unavailable."""
    if lang in _QUERY_CACHE:
        return _QUERY_CACHE[lang]

    scm_file = Path(__file__).parent / "queries" / f"{lang}.scm"
    if not scm_file.exists():
        _QUERY_CACHE[lang] = None
        return None

    try:
        from tree_sitter import Language

        if lang == "python":
            import tree_sitter_python as tsp
            ts_lang = Language(tsp.language())
        elif lang in ("typescript", "tsx"):
            import tree_sitter_typescript as tsts
            ts_lang = Language(tsts.language_typescript())
        elif lang == "javascript":
            import tree_sitter_javascript as tsjs
            ts_lang = Language(tsjs.language())
        elif lang == "go":
            import tree_sitter_go as tsgo
            ts_lang = Language(tsgo.language())
        elif lang == "rust":
            import tree_sitter_rust as tsrust
            ts_lang = Language(tsrust.language())
        elif lang == "java":
            import tree_sitter_java as tsjava
            ts_lang = Language(tsjava.language())
        elif lang == "csharp":
            import tree_sitter_c_sharp as tscs
            ts_lang = Language(tscs.language())
        elif lang == "php":
            import tree_sitter_php as tsphp
            ts_lang = Language(tsphp.language_php())
        elif lang == "ruby":
            import tree_sitter_ruby as tsruby
            ts_lang = Language(tsruby.language())
        elif lang == "kotlin":
            import tree_sitter_kotlin as tskotlin
            ts_lang = Language(tskotlin.language())
        elif lang == "scala":
            import tree_sitter_scala as tsscala
            ts_lang = Language(tsscala.language())
        else:
            _QUERY_CACHE[lang] = None
            return None

        compiled = ts_lang.query(scm_file.read_text())
        _QUERY_CACHE[lang] = compiled
        return compiled
    except Exception:
        _QUERY_CACHE[lang] = None
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def get_node_tokens(node: "Node", lang: str) -> list[tuple[COV, float]] | None:
    """
    Run the .scm query for *lang* against *node* (a function body or function node).

    Returns:
        None  — no .scm file for this language; caller should fall back to the
                existing two-pass walk (Tier 1 + Tier 4).
        []    — query ran successfully but found no matching patterns (trivial body).
        [...]  — list of (COV, confidence) pairs, one per distinct capture name.
    """
    query = _load_query(lang)
    if query is None:
        return None

    try:
        captures: dict[str, list] = query.captures(node)
    except Exception:
        return None

    results: list[tuple[COV, float]] = []
    for capture_name, nodes in captures.items():
        if not nodes:
            continue
        cov = _CAPTURE_TO_COV.get(capture_name)
        if cov is None:
            continue  # internal filter captures (@name, @obj, @method, @_lhs)
        confidence = 1.0 if capture_name in _STRUCTURAL_CAPTURES else 0.75
        results.append((cov, confidence))
    return results
