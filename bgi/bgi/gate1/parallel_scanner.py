"""
Phase 5 Task 2 — Multiprocessing Gate 1 scanning (WATER-CLOCK speed layer).

Replaces the original per-file worker dispatch with a batch-per-worker design:
- Files are split into `max_workers` batches, one batch per worker process.
- Each worker imports parsers once, scans its entire batch, returns all fingerprints.
- This amortises tree-sitter import + parser-init cost across the batch and
  reduces IPC (pickle/unpickle) overhead from O(num_files) to O(num_workers).

Also supports `language=auto` — groups files by extension and distributes
mixed-language batches across workers.

Public API::

    fps = scan_directory_parallel(root, language="python", max_workers=None)
    fps = scan_directory_parallel(root, language="auto",   max_workers=None)
"""
from __future__ import annotations
import math
import os
from multiprocessing import Pool
from pathlib import Path

from bgi.core.fingerprint import COVFingerprint

# ── Language → file extension map (mirrors scanner._EXT_TO_LANG) ─────────────
# Kept here so workers don't need to import the full scanner module at load time.
_LANG_TO_EXTS: dict[str, list[str]] = {
    "python":     [".py"],
    "typescript": [".ts", ".tsx"],
    "javascript": [".js", ".jsx"],
    "java":       [".java"],
    "go":         [".go"],
    "rust":       [".rs"],
    "ruby":       [".rb"],
    "csharp":     [".cs"],
    "php":        [".php"],
    "kotlin":     [".kt", ".kts"],
    "c":          [".c", ".h"],
    "scala":      [".scala"],
    "lua":        [".lua"],
    "elixir":     [".ex", ".exs"],
}

# All extensions we care about in auto mode
_ALL_EXTS: set[str] = {ext for exts in _LANG_TO_EXTS.values() for ext in exts}


# ── Worker functions (must be module-level for pickling) ─────────────────────

def _worker_scan_batch(args: tuple) -> list[COVFingerprint]:
    """
    Worker: scan a batch of files for a single language.
    Parsers and WATER-CLOCK query objects are initialised once per worker process.
    """
    file_batch: list[str]
    root_str: str
    language: str
    file_batch, root_str, language = args

    from bgi.gate1.ai_fallback import AIFallback
    ai = AIFallback(enabled=False)
    root = Path(root_str)

    scan_fn = _get_scan_fn(language)
    if scan_fn is None:
        return []

    results: list[COVFingerprint] = []
    for f_str in file_batch:
        try:
            fps = scan_fn(Path(f_str), root, ai)
            results.extend(fps)
        except Exception as exc:
            print(f"[BGI-Worker] Warning: skipped {f_str}: {exc}")
    return results


def _worker_scan_batch_auto(args: tuple) -> list[COVFingerprint]:
    """Worker: scan a mixed-language batch using _scan_file_auto."""
    file_batch: list[str]
    root_str: str
    file_batch, root_str = args

    from bgi.gate1.ai_fallback import AIFallback
    from bgi.gate1.scanner import _scan_file_auto
    ai = AIFallback(enabled=False)
    root = Path(root_str)

    results: list[COVFingerprint] = []
    for f_str in file_batch:
        try:
            fps = _scan_file_auto(Path(f_str), root, ai)
            results.extend(fps)
        except Exception as exc:
            print(f"[BGI-Worker] Warning: skipped {f_str}: {exc}")
    return results


def _get_scan_fn(language: str):
    """Return the per-file scan function for *language*, or None if unsupported."""
    lang = language.lower()
    if lang == "python":
        from bgi.gate1.scanner import scan_file
        return scan_file
    if lang in ("typescript", "tsx", "ts"):
        from bgi.gate1.ts_scanner import scan_file_ts
        return scan_file_ts
    if lang in ("javascript", "jsx", "js"):
        from bgi.gate1.js_scanner import scan_file_js
        return scan_file_js
    if lang == "java":
        from bgi.gate1.java_scanner import scan_file_java
        return scan_file_java
    if lang == "go":
        from bgi.gate1.go_scanner import scan_file_go
        return scan_file_go
    if lang == "rust":
        from bgi.gate1.rust_scanner import scan_file_rust
        return scan_file_rust
    if lang == "ruby":
        from bgi.gate1.ruby_scanner import scan_file_ruby
        return scan_file_ruby
    if lang == "csharp":
        from bgi.gate1.csharp_scanner import scan_file_csharp
        return scan_file_csharp
    if lang == "php":
        from bgi.gate1.php_scanner import scan_file_php
        return scan_file_php
    if lang == "kotlin":
        from bgi.gate1.kotlin_scanner import scan_file_kotlin
        return scan_file_kotlin
    if lang == "c":
        from bgi.gate1.c_scanner import scan_file_c
        return scan_file_c
    if lang == "scala":
        from bgi.gate1.scala_scanner import scan_file_scala
        return scan_file_scala
    if lang == "lua":
        from bgi.gate1.lua_scanner import scan_file_lua
        return scan_file_lua
    if lang == "elixir":
        from bgi.gate1.elixir_scanner import scan_file_elixir
        return scan_file_elixir
    return None


# ── File collection ───────────────────────────────────────────────────────────

def _collect_files(root: Path, language: str) -> list[Path]:
    """Collect source files for *language* under *root*."""
    lang = language.lower()
    exts = _LANG_TO_EXTS.get(lang)
    if not exts:
        return []
    files: list[Path] = []
    for ext in exts:
        for f in root.rglob(f"*{ext}"):
            if lang in ("typescript", "ts") and f.name.endswith(".d.ts"):
                continue
            files.append(f)
    return sorted(files)


def _collect_files_auto(root: Path) -> list[Path]:
    """Collect all recognised source files under *root* for auto mode."""
    files: list[Path] = []
    for ext in _ALL_EXTS:
        for f in root.rglob(f"*{ext}"):
            if f.name.endswith(".d.ts"):
                continue
            files.append(f)
    return sorted(files)


# ── Batch helpers ─────────────────────────────────────────────────────────────

def _make_batches(files: list[Path], n: int) -> list[list[str]]:
    """Split *files* into *n* roughly-equal batches of string paths."""
    if not files:
        return []
    batch_size = math.ceil(len(files) / n)
    str_files = [str(f) for f in files]
    return [str_files[i:i + batch_size] for i in range(0, len(str_files), batch_size)]


# ── Public API ────────────────────────────────────────────────────────────────

def scan_directory_parallel(
    root: Path,
    language: str = "python",
    max_workers: int | None = None,
    enable_bfs: bool = False,  # accepted for backwards compat; ignored in batch design
) -> list[COVFingerprint]:
    """
    Scan *root* in parallel using a multiprocessing Pool.

    For single-language mode, files are split into ``max_workers`` batches;
    each worker process scans its batch sequentially, amortising parser
    initialisation overhead.

    For ``language="auto"``, all recognised source files are split into batches
    and workers use ``_scan_file_auto`` to handle mixed-language files.

    Falls back gracefully to sequential scanning when:
    - Only one CPU is available
    - The file list is very short (< 8 files)
    - An unsupported language is requested
    """
    root = Path(root).resolve()
    lang = language.lower()
    n_cpu = max_workers or os.cpu_count() or 1

    if lang == "auto":
        files = _collect_files_auto(root)
    else:
        files = _collect_files(root, lang)
        if not files and lang not in _LANG_TO_EXTS:
            # Unknown language — delegate to sequential scanner
            from bgi.gate1.scanner import scan_directory
            return scan_directory(root, language=lang)

    if not files:
        return []

    # Sequential fallback for small repos or single-CPU
    if len(files) < 8 or n_cpu <= 1:
        if lang == "auto":
            from bgi.gate1.scanner import scan_repository
            return scan_repository(root)
        from bgi.gate1.scanner import scan_directory
        return scan_directory(root, language=lang)

    n_workers = min(n_cpu, len(files))
    batches = _make_batches(files, n_workers)
    root_str = str(root)

    all_fingerprints: list[COVFingerprint] = []
    if lang == "auto":
        worker_args = [(batch, root_str) for batch in batches]
        with Pool(processes=n_workers) as pool:
            for fps in pool.map(_worker_scan_batch_auto, worker_args):
                all_fingerprints.extend(fps)
    else:
        worker_args = [(batch, root_str, lang) for batch in batches]
        with Pool(processes=n_workers) as pool:
            for fps in pool.map(_worker_scan_batch, worker_args):
                all_fingerprints.extend(fps)

    return all_fingerprints


# ── Benchmark helper ──────────────────────────────────────────────────────────

def benchmark_parallel_vs_sequential(root: Path, language: str = "python") -> dict:
    """Compare parallel vs sequential Gate 1 time. For development use only."""
    import time
    from bgi.gate1.scanner import scan_directory, scan_repository

    t0 = time.perf_counter()
    if language == "auto":
        seq_fps = scan_repository(root)
    else:
        seq_fps = scan_directory(root, language=language)
    seq_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    par_fps = scan_directory_parallel(root, language=language)
    par_time = time.perf_counter() - t0

    return {
        "sequential_s": round(seq_time, 3),
        "parallel_s":   round(par_time, 3),
        "speedup":      round(seq_time / max(par_time, 0.001), 2),
        "units_seq":    len(seq_fps),
        "units_par":    len(par_fps),
        "units_match":  len(seq_fps) == len(par_fps),
    }

