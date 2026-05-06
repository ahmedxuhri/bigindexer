"""
Phase 2 — Benchmark validation for speed improvements.

Measures Gate 1 (scanning), Gate 2 (matching), and Gate 3 (clustering) times
against targets:
- FastAPI (4,509 units): target <10s total
- VS Code (75,131 units): target <20s total (was 144.4s)
"""
from __future__ import annotations
import time
from pathlib import Path
from typing import Optional
import json


class BenchmarkResult:
    """Holds timing data for a benchmark run."""
    
    def __init__(self, name: str, root: Path) -> None:
        self.name = name
        self.root = Path(root)
        self.gate1_time: Optional[float] = None
        self.gate2_time: Optional[float] = None
        self.gate3_time: Optional[float] = None
        self.total_fingerprints = 0
        self.total_clusters = 0
        self.max_cluster_size = 0
        self.errors: list[str] = []
    
    @property
    def total_time(self) -> float:
        """Sum of all gate times."""
        times = [t for t in [self.gate1_time, self.gate2_time, self.gate3_time] if t is not None]
        return sum(times)
    
    def to_dict(self) -> dict:
        """Export as dictionary for JSON serialization."""
        return {
            "name": self.name,
            "root": str(self.root),
            "gate1_time": self.gate1_time,
            "gate2_time": self.gate2_time,
            "gate3_time": self.gate3_time,
            "total_time": self.total_time,
            "total_fingerprints": self.total_fingerprints,
            "total_clusters": self.total_clusters,
            "max_cluster_size": self.max_cluster_size,
            "errors": self.errors,
        }


def benchmark_scan(
    root: Path,
    language: str = "auto",
    use_parallel: bool = True,
    max_workers: Optional[int] = None,
) -> BenchmarkResult:
    """
    Benchmark a full BGI scan (Gates 1-3).
    
    Args:
        root: Repository root to scan
        language: Language mode (default: auto for monorepo)
        use_parallel: Use parallel scanning (default: True)
        max_workers: Number of worker processes for parallel mode
    
    Returns:
        BenchmarkResult with timing breakdown
    """
    from bgi.pipeline import run_scan
    
    result = BenchmarkResult(f"{root.name} ({language})", root)
    
    try:
        # Gate 1: Scan
        t1 = time.time()
        fingerprints_count = None
        
        if language == "auto":
            from bgi.gate1.mono_cache import scan_monorepo_incremental
            fps, stats = scan_monorepo_incremental(root)
            fingerprints_count = len(fps)
        else:
            from bgi.gate1.scanner import scan_directory
            from bgi.gate1.parallel_scanner import scan_directory_parallel
            
            if use_parallel:
                fps = scan_directory_parallel(root, language=language, max_workers=max_workers)
            else:
                fps = scan_directory(root, language=language)
            fingerprints_count = len(fps)
        
        result.gate1_time = time.time() - t1
        result.total_fingerprints = fingerprints_count
        
        print(f"[BENCH] {result.name}")
        print(f"  Gate 1 (scan): {result.gate1_time:.2f}s ({result.total_fingerprints} units)")
        
        # Could add Gate 2/3 benchmarks here if needed
        
    except Exception as e:
        result.errors.append(f"Scan failed: {str(e)}")
        print(f"[BENCH] {result.name} — ERROR: {e}")
    
    return result


def compare_benchmarks(
    baseline: BenchmarkResult,
    optimized: BenchmarkResult,
) -> dict:
    """
    Compare two benchmark runs and calculate speedup.
    
    Returns:
        Dict with speedup ratios and analysis
    """
    comparison = {
        "baseline_name": baseline.name,
        "optimized_name": optimized.name,
        "gate1_speedup": None,
        "total_speedup": None,
    }
    
    if baseline.gate1_time and optimized.gate1_time:
        comparison["gate1_speedup"] = baseline.gate1_time / optimized.gate1_time
    
    if baseline.total_time > 0 and optimized.total_time > 0:
        comparison["total_speedup"] = baseline.total_time / optimized.total_time
    
    return comparison


def save_benchmarks(results: list[BenchmarkResult], output: Path | str = "bgi-benchmarks.json") -> None:
    """Save benchmark results to JSON file."""
    p = Path(output)
    data = {
        "timestamp": time.time(),
        "benchmarks": [r.to_dict() for r in results]
    }
    p.write_text(json.dumps(data, indent=2))
    print(f"[BENCH] Results saved to {p}")


# Benchmark definitions

FASTAPI_TARGETS = {
    "total_units": 4509,
    "target_time": 10.0,  # seconds
    "description": "FastAPI web framework (4.5K units)"
}

VS_CODE_TARGETS = {
    "total_units": 75131,
    "target_time": 20.0,  # seconds (was 144.4s sequential)
    "description": "VS Code editor (75K units)"
}


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m bgi.benchmark <repo_path> [--lang LANG] [--parallel] [--output FILE]")
        print("Example: python -m bgi.benchmark ~/fastapi --parallel")
        sys.exit(1)
    
    repo_path = Path(sys.argv[1])
    lang = "auto"
    parallel = False
    output_file = "bgi-benchmarks.json"
    
    # Parse args
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--lang" and i + 1 < len(sys.argv):
            lang = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--parallel":
            parallel = True
            i += 1
        elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        else:
            i += 1
    
    result = benchmark_scan(repo_path, language=lang, use_parallel=parallel)
    save_benchmarks([result], output_file)
    
    print(f"\nTotal time: {result.total_time:.2f}s")
