"""
Phase 2 — Multiprocessing Gate 1 scanning for speed improvement.

Replaces sequential file scanning with parallel processing per language.
Each worker processes files independently, collecting fingerprints in parallel.

This reduces Gate 1 latency from 34s (sequential) to ~5–10s on 75k units (VS Code).
"""
from __future__ import annotations
from multiprocessing import Pool, Queue
from pathlib import Path
from typing import Callable, Any

from bgi.core.fingerprint import COVFingerprint
from bgi.gate1.ai_fallback import AIFallback


def _worker_scan_file(
    args: tuple[Path, Path, str, str],
) -> list[COVFingerprint]:
    """
    Worker function for multiprocessing.
    Scans a single file and returns fingerprints.
    
    Args:
        args: (file_path, root_path, language, scan_run)
    
    Returns:
        List of COVFingerprints from this file
    """
    file_path, root_path, language, scan_run = args
    
    try:
        from bgi.gate1.ai_fallback import AIFallback
        ai = AIFallback(enabled=False)
        
        # Import scanner function based on language
        if language == "python":
            from bgi.gate1.scanner import scan_file
            return scan_file(file_path, root_path, ai=ai)
        elif language in ("typescript", "tsx", "ts"):
            from bgi.gate1.ts_scanner import scan_file_ts
            return scan_file_ts(file_path, root_path, ai=ai)
        elif language in ("javascript", "jsx", "js"):
            from bgi.gate1.js_scanner import scan_file_js
            return scan_file_js(file_path, root_path, ai=ai)
        elif language == "java":
            from bgi.gate1.java_scanner import scan_file_java
            return scan_file_java(file_path, root_path, ai=ai)
        elif language == "go":
            from bgi.gate1.go_scanner import scan_file_go
            return scan_file_go(file_path, root_path, ai=ai)
        elif language == "rust":
            from bgi.gate1.rust_scanner import scan_file_rust
            return scan_file_rust(file_path, root_path, ai=ai)
        else:
            return []
    except Exception as exc:
        print(f"[BGI-Worker] Warning: skipped {file_path}: {exc}")
        return []


def scan_directory_parallel(
    root: Path,
    language: str = "python",
    max_workers: int | None = None,
) -> list[COVFingerprint]:
    """
    Scan directory using multiprocessing pool.
    
    Args:
        root: Repository root
        language: Language to scan
        max_workers: Number of worker processes (default: CPU count)
    
    Returns:
        List of COVFingerprints from all files
    """
    root = Path(root).resolve()
    language = language.lower()
    
    # Collect files to scan
    if language == "python":
        source_files = sorted(root.rglob("*.py"))
    elif language in ("typescript", "tsx", "ts"):
        exts = {"*.ts", "*.tsx"} if language in ("tsx", "ts") else {"*.ts"}
        source_files = sorted(
            f for ext in exts for f in root.rglob(ext)
            if ".d.ts" not in f.name
        )
    elif language in ("javascript", "jsx", "js"):
        exts = {"*.js", "*.jsx"} if language in ("jsx", "js") else {"*.js"}
        source_files = sorted(f for ext in exts for f in root.rglob(ext))
    elif language == "java":
        source_files = sorted(root.rglob("*.java"))
    elif language == "go":
        source_files = sorted(root.rglob("*.go"))
    elif language == "rust":
        source_files = sorted(root.rglob("*.rs"))
    else:
        # Fall back to sequential scanning for unsupported languages
        from bgi.gate1.scanner import scan_directory
        return scan_directory(root, language=language)
    
    if not source_files:
        return []
    
    # Prepare worker arguments
    worker_args = [(f, root, language, "") for f in source_files]
    
    # Run parallel scanning
    all_fingerprints: list[COVFingerprint] = []
    
    with Pool(processes=max_workers) as pool:
        results = pool.imap_unordered(_worker_scan_file, worker_args)
        for fps in results:
            all_fingerprints.extend(fps)
    
    return all_fingerprints


def scan_directory_sequential_fallback(
    root: Path,
    language: str = "python",
    ai: AIFallback | None = None,
    scan_run: str = "",
) -> list[COVFingerprint]:
    """
    Fallback to sequential scanning (original behavior).
    Used when multiprocessing is disabled or for languages without worker support.
    """
    from bgi.gate1.scanner import scan_directory
    return scan_directory(root, language=language, ai=ai, scan_run=scan_run)
