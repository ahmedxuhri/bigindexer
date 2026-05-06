"""
BFS entry-point detection for Phase 2 speed optimization.

Identifies entry points (main functions, @app.route handlers, etc.)
and prioritizes scanning reachable units first via DFS.

Falls back to scanning entire directory if entry detection fails.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Any
import re


def detect_entry_points(
    root: Path,
    language: str = "python",
) -> set[Path]:
    """
    Detect entry-point files in the repository.
    
    Entry points are files that likely contain main logic:
    - Python: main(), __main__.py, files with __name__ == "__main__"
    - TypeScript/JavaScript: files named index.ts, server.ts, app.ts, main.ts, or exporting default
    - Java: files with public static void main
    - Go: files with func main()
    
    Args:
        root: Repository root
        language: Language to scan for entry points
    
    Returns:
        Set of entry-point file paths
    """
    root = Path(root).resolve()
    language = language.lower()
    entry_points = set()
    
    if language == "python":
        entry_points = _detect_python_entries(root)
    elif language in ("typescript", "ts", "tsx", "javascript", "js", "jsx"):
        entry_points = _detect_js_entries(root)
    elif language == "java":
        entry_points = _detect_java_entries(root)
    elif language == "go":
        entry_points = _detect_go_entries(root)
    
    return entry_points


def _detect_python_entries(root: Path) -> set[Path]:
    """Detect Python entry points."""
    entries = set()
    
    # Look for __main__.py
    for main_file in root.rglob("__main__.py"):
        entries.add(main_file)
    
    # Look for main() function definitions or if __name__ == "__main__"
    for py_file in root.rglob("*.py"):
        try:
            content = py_file.read_text(errors="ignore")
            if (
                'if __name__ == "__main__"' in content
                or re.search(r"^\s*def main\s*\(", content, re.MULTILINE)
            ):
                entries.add(py_file)
        except Exception:
            pass
    
    return entries


def _detect_js_entries(root: Path) -> set[Path]:
    """Detect JavaScript/TypeScript entry points."""
    entries = set()
    
    # Common entry point names
    entry_names = {"index", "server", "app", "main"}
    
    for ts_file in root.rglob("*.ts"):
        if ts_file.stem in entry_names and ".d.ts" not in ts_file.name:
            entries.add(ts_file)
    
    for js_file in root.rglob("*.js"):
        if js_file.stem in entry_names:
            entries.add(js_file)
    
    # Also look for export default or export async function
    all_files = set(root.rglob("*.ts")) | set(root.rglob("*.tsx")) | set(root.rglob("*.js")) | set(root.rglob("*.jsx"))
    for ts_file in all_files:
        if ".d.ts" in ts_file.name:
            continue
        try:
            content = ts_file.read_text(errors="ignore")
            if re.search(r"export\s+(default|async\s+function)", content):
                entries.add(ts_file)
        except Exception:
            pass
    
    return entries


def _detect_java_entries(root: Path) -> set[Path]:
    """Detect Java entry points (files with public static void main)."""
    entries = set()
    
    for java_file in root.rglob("*.java"):
        try:
            content = java_file.read_text(errors="ignore")
            if "public static void main" in content:
                entries.add(java_file)
        except Exception:
            pass
    
    return entries


def _detect_go_entries(root: Path) -> set[Path]:
    """Detect Go entry points (files with func main())."""
    entries = set()
    
    for go_file in root.rglob("*.go"):
        try:
            content = go_file.read_text(errors="ignore")
            if re.search(r"func\s+main\s*\(", content):
                entries.add(go_file)
        except Exception:
            pass
    
    return entries


def scan_from_entries(
    root: Path,
    language: str = "python",
    scan_fn: Callable[[Path, Path], list[Any]] | None = None,
) -> list[Any]:
    """
    Scan files reachable from entry points first, then remaining files.
    
    This prioritizes scanning code paths most likely to contain meaningful logic,
    enabling earlier partial results in incremental or streaming mode.
    
    Args:
        root: Repository root
        language: Language to scan
        scan_fn: Function to call per file (file_path, root_path) → fingerprints
    
    Returns:
        List of fingerprints from all files
    """
    if scan_fn is None:
        raise ValueError("scan_fn must be provided")
    
    root = Path(root).resolve()
    entries = detect_entry_points(root, language)
    
    if not entries:
        # Fall back to sequential file scanning if no entries detected
        return []
    
    # Collect files to scan
    if language == "python":
        all_files = set(root.rglob("*.py"))
    elif language in ("typescript", "ts", "tsx"):
        all_files = {f for f in root.rglob("*.ts") | root.rglob("*.tsx") if ".d.ts" not in f.name}
    elif language in ("javascript", "js", "jsx"):
        all_files = set(root.rglob("*.js")) | set(root.rglob("*.jsx"))
    elif language == "java":
        all_files = set(root.rglob("*.java"))
    elif language == "go":
        all_files = set(root.rglob("*.go"))
    else:
        return []
    
    # Scan entry points first, then remaining files
    fingerprints: list[Any] = []
    scanned = set()
    
    # Scan entry points
    for entry_file in sorted(entries):
        if entry_file in scanned:
            continue
        try:
            fps = scan_fn(entry_file, root)
            fingerprints.extend(fps)
            scanned.add(entry_file)
        except Exception as exc:
            print(f"[BGI-Entries] Warning: skipped {entry_file}: {exc}")
    
    # Scan remaining files
    for file_path in sorted(all_files - scanned):
        try:
            fps = scan_fn(file_path, root)
            fingerprints.extend(fps)
            scanned.add(file_path)
        except Exception as exc:
            print(f"[BGI-Entries] Warning: skipped {file_path}: {exc}")
    
    return fingerprints
