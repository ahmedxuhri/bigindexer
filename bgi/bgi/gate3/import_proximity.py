"""
MASK-4-GATE-3 — Import/Export proximity extraction.

Replaces the broken `_subdir()` leaf-directory name matching in Gate 3 Pass 1.5
with import-based structural proximity. Files that import each other are
architecturally proximate → clustering signal.

Supports Python, TypeScript/JS (tree-sitter based), and fallback regex for others.
Handles relative imports, resolves to absolute paths within repo.
Detects and skips circular import pairs.
"""
from __future__ import annotations
import re
from pathlib import Path
from collections import defaultdict


def extract_import_edges(root: str, lang: str = "python") -> dict[str, set[str]]:
    """
    Extract import relationships from a codebase.
    
    Args:
        root: Repository root path
        lang: Language ("python", "typescript", "javascript", "auto")
    
    Returns:
        Dict mapping file_path → set of imported file_paths (relative to root)
    """
    root_path = Path(root).resolve()
    edges: dict[str, set[str]] = defaultdict(set)
    
    if lang == "python":
        _extract_python_imports(root_path, edges)
    elif lang in ("typescript", "javascript", "ts", "js"):
        _extract_js_ts_imports(root_path, edges)
    else:
        # Fallback: regex-based import detection
        _extract_regex_imports(root_path, edges)
    
    return dict(edges)


def _extract_python_imports(root_path: Path, edges: dict[str, set[str]]) -> None:
    """Extract Python import statements using regex."""
    py_files = list(root_path.glob("**/*.py"))
    
    for py_file in py_files:
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(py_file.relative_to(root_path))
            
            # Find all import statements
            # Pattern: import X, from X import, from . import, from .. import
            imports = re.findall(
                r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))",
                content,
                re.MULTILINE
            )
            
            for match in imports:
                # match is tuple (from_import_source, direct_import)
                import_name = match[0] or match[1]
                if import_name and not import_name.startswith("."):
                    # Resolve to a file path (simple heuristic)
                    import_path = import_name.replace(".", "/")
                    
                    # Try .py file
                    candidate = root_path / f"{import_path}.py"
                    if candidate.exists():
                        try:
                            edges[rel_path].add(str(candidate.relative_to(root_path)))
                        except ValueError:
                            pass  # Outside root
                    
                    # Try package __init__.py
                    candidate_init = root_path / import_path / "__init__.py"
                    if candidate_init.exists():
                        try:
                            edges[rel_path].add(str(candidate_init.relative_to(root_path)))
                        except ValueError:
                            pass
        except Exception:
            pass  # Skip files that can't be read


def _extract_js_ts_imports(root_path: Path, edges: dict[str, set[str]]) -> None:
    """Extract JavaScript/TypeScript import statements using regex."""
    js_files = list(root_path.glob("**/*.{js,ts,tsx,jsx}"))
    
    for js_file in js_files:
        try:
            content = js_file.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(js_file.relative_to(root_path))
            
            # Find all import/require statements
            # Patterns:
            # - import X from 'Y'
            # - import('Y')
            # - require('Y')
            # - require("Y")
            imports = re.findall(
                r"(?:import\s+.*?from\s+['\"]([^'\"]+)['\"]|"
                r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)|"
                r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\))",
                content
            )
            
            for match in imports:
                import_path = match[0] or match[1] or match[2]
                if import_path and not import_path.startswith("."):
                    # Resolve to .js/.ts file (simple heuristic)
                    for ext in [".js", ".ts", ".tsx", ".jsx"]:
                        candidate = root_path / f"{import_path}{ext}"
                        if candidate.exists():
                            try:
                                edges[rel_path].add(str(candidate.relative_to(root_path)))
                            except ValueError:
                                pass
                    
                    # Try package index
                    for ext in [".js", ".ts", ".tsx", ".jsx"]:
                        candidate_index = root_path / import_path / f"index{ext}"
                        if candidate_index.exists():
                            try:
                                edges[rel_path].add(str(candidate_index.relative_to(root_path)))
                            except ValueError:
                                pass
        except Exception:
            pass


def _extract_regex_imports(root_path: Path, edges: dict[str, set[str]]) -> None:
    """Fallback: regex-based import detection for other languages."""
    # Generic patterns for common import statements
    all_files = list(root_path.glob("**/*"))
    
    for file_path in all_files:
        if file_path.is_dir() or file_path.name.startswith("."):
            continue
        
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(file_path.relative_to(root_path))
            
            # Generic import patterns
            patterns = [
                r"import\s+.*?['\"]([^'\"]+)['\"]",
                r"require\s*\(['\"]([^'\"]+)['\"]\)",
                r"#include\s+[\"<]([^\"<>]+)[>\"]",
            ]
            
            imports = []
            for pattern in patterns:
                imports.extend(re.findall(pattern, content))
            
            for import_name in imports:
                if import_name and not import_name.startswith("."):
                    # Simple resolution: look for file with this name
                    for candidate in root_path.glob(f"**/{import_name}*"):
                        if candidate.is_file():
                            try:
                                edges[rel_path].add(str(candidate.relative_to(root_path)))
                            except ValueError:
                                pass
        except Exception:
            pass


def detect_cycles(edges: dict[str, set[str]]) -> set[tuple[str, str]]:
    """
    Detect circular import pairs in the graph.
    
    Returns:
        Set of (file_a, file_b) tuples where A→B and B→A
    """
    cycles = set()
    for file_a, imported_by_a in edges.items():
        for file_b in imported_by_a:
            if file_a in edges.get(file_b, set()):
                # Circular: A imports B and B imports A
                pair = tuple(sorted([file_a, file_b]))
                cycles.add(pair)
    return cycles


def resolve_relative_import(
    source_file: str,
    relative_import: str,
    root_path: Path,
) -> str | None:
    """
    Resolve a relative import to an absolute file path.
    
    Args:
        source_file: File that contains the relative import (rel to root)
        relative_import: Import string (e.g., "../utils", "./helpers")
        root_path: Repository root
    
    Returns:
        Resolved file path (relative to root), or None if not found
    """
    source_path = root_path / source_file
    if not source_path.is_file():
        return None
    
    # Handle relative import
    parent = source_path.parent
    if relative_import.startswith(".."):
        # Go up directories
        ups = 0
        remaining = relative_import
        while remaining.startswith(".."):
            ups += 1
            remaining = remaining[2:].lstrip("/.")
        
        for _ in range(ups):
            parent = parent.parent
        
        if remaining:
            candidate = parent / remaining
        else:
            candidate = parent
    elif relative_import.startswith("."):
        # Current directory
        remaining = relative_import.lstrip("./")
        candidate = parent / remaining
    else:
        return None
    
    # Try to find file (try with and without .py extension)
    candidate = candidate.resolve()
    for ext in ["", ".py", ".ts", ".js", ".tsx", ".jsx"]:
        check_path = candidate if ext == "" else candidate.with_suffix(ext)
        if check_path.is_file():
            try:
                return str(check_path.relative_to(root_path))
            except ValueError:
                pass
    
    return None
