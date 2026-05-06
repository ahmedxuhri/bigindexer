"""
Query-based fingerprinting using tree-sitter .scm query files (WATER-CLOCK).

Extracts COV tokens by running tree-sitter queries against source code AST.
Falls back to regex-based extraction if .scm not available.
"""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint

if TYPE_CHECKING:
    import tree_sitter as ts


# Query file capture name → COV token mapping
_CAPTURE_TO_COV: dict[str, COV] = {
    "intake": COV.INTAKE,
    "output": COV.OUTPUT,
    "transform": COV.TRANSFORM,
    "mutate": COV.MUTATE,
    "sanitize": COV.SANITIZE,
    "conditional": COV.CONDITIONAL,
    "loop": COV.LOOP,
    "guard": COV.GUARD,
    "route": COV.ROUTE,
    "scope": COV.SCOPE,
    "fetch": COV.FETCH,
    "persist": COV.PERSIST,
    "emit": COV.EMIT,
    "subscribe": COV.SUBSCRIBE,
    "delegate": COV.DELEGATE,
    "contract": COV.CONTRACT,
    "compose": COV.COMPOSE,
    "init": COV.INIT,
    "teardown": COV.TEARDOWN,
    "raise": COV.RAISE,
    "recover": COV.RECOVER,
    "defer": COV.DEFER,
    "authenticate": COV.AUTHENTICATE,
    "authorize": COV.AUTHORIZE,
    "validate": COV.VALIDATE,
    "log": COV.LOG,
    "measure": COV.MEASURE,
    "async": COV.ASYNC,
    "test": COV.TEST,
}


def get_query_file(lang: str) -> Path | None:
    """
    Get path to .scm query file for language.
    
    Returns None if not available (will fall back to regex).
    """
    query_dir = Path(__file__).parent
    query_file = query_dir / f"{lang}.scm"
    return query_file if query_file.exists() else None


def fingerprint_with_query(
    source_code: str,
    lang: str,
    file_path: str,
    unit_id: str,
    start_line: int = 0,
    end_line: int = 0,
) -> COVFingerprint | None:
    """
    Extract COV tokens using tree-sitter queries.
    
    Args:
        source_code: Source file content
        lang: Language (python, typescript, js, etc.)
        file_path: File path for context
        unit_id: Function/method identifier
        start_line: Start line (if known)
        end_line: End line (if known)
    
    Returns:
        COVFingerprint with extracted tokens, or None if parsing fails
    """
    query_file = get_query_file(lang)
    if not query_file:
        # No query file available — return None, let caller fall back to regex
        return None
    
    try:
        # Try to import tree-sitter and parse
        import tree_sitter_python as tsp
        from tree_sitter import Language, Parser
        
        # Select language parser
        if lang == "python":
            parser = Parser()
            parser.set_language(Language(tsp.language(), "python"))
        else:
            # For other languages, return None (no parser configured)
            return None
        
        # Parse source
        tree = parser.parse(source_code.encode("utf-8"))
        
        # Load and run queries
        query_text = query_file.read_text()
        query = Language(tsp.language(), "python").query(query_text)
        
        # Extract matched captures
        tokens: set[COV] = set()
        captures = query.captures(tree.root_node)
        
        for node, capture_name in captures:
            # Map capture name to COV token
            if capture_name in _CAPTURE_TO_COV:
                tokens.add(_CAPTURE_TO_COV[capture_name])
        
        # Determine confidence (query-based is high confidence)
        confidence = 0.95
        
        # Return fingerprint
        return COVFingerprint(
            unit_id=unit_id,
            tokens=list(tokens),
            class_context=[],
            confidence=confidence,
            source="query-based",
            language=lang,
            line_range=(start_line, end_line),
        )
    
    except Exception:
        # If anything fails (import, parsing, querying), return None
        # Caller will fall back to regex-based extraction
        return None
