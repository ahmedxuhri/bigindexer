"""Tests for benchmark module."""
import pytest
from pathlib import Path
import json
from bgi.benchmark import (
    BenchmarkResult,
    benchmark_scan,
    compare_benchmarks,
    save_benchmarks,
)


class TestBenchmarkResult:
    """Test BenchmarkResult data structure."""
    
    def test_create_benchmark_result(self, tmp_path):
        """Create a benchmark result."""
        result = BenchmarkResult("test", tmp_path)
        assert result.name == "test"
        assert result.total_fingerprints == 0
    
    def test_total_time_calculation(self, tmp_path):
        """Verify total_time aggregates gate times."""
        result = BenchmarkResult("test", tmp_path)
        result.gate1_time = 1.0
        result.gate2_time = 2.0
        result.gate3_time = 3.0
        
        assert result.total_time == 6.0
    
    def test_to_dict_serialization(self, tmp_path):
        """Convert result to dictionary."""
        result = BenchmarkResult("test", tmp_path)
        result.gate1_time = 1.5
        result.total_fingerprints = 100
        
        d = result.to_dict()
        assert d["name"] == "test"
        assert d["gate1_time"] == 1.5
        assert d["total_fingerprints"] == 100
        assert "total_time" in d


class TestBenchmarkComparison:
    """Test benchmark comparison."""
    
    def test_compare_benchmarks(self, tmp_path):
        """Compare two benchmark runs."""
        baseline = BenchmarkResult("baseline", tmp_path)
        baseline.gate1_time = 10.0
        baseline.gate2_time = 5.0
        baseline.gate3_time = 2.0
        
        optimized = BenchmarkResult("optimized", tmp_path)
        optimized.gate1_time = 5.0
        optimized.gate2_time = 3.0
        optimized.gate3_time = 1.0
        
        comp = compare_benchmarks(baseline, optimized)
        
        assert comp["gate1_speedup"] == 2.0  # 10 / 5
        assert abs(comp["total_speedup"] - 1.889) < 0.01  # (10+5+2) / (5+3+1) ≈ 1.889
    
    def test_compare_with_missing_times(self, tmp_path):
        """Handle comparison with missing times."""
        baseline = BenchmarkResult("baseline", tmp_path)
        baseline.gate1_time = 10.0
        
        optimized = BenchmarkResult("optimized", tmp_path)
        optimized.gate1_time = None
        
        comp = compare_benchmarks(baseline, optimized)
        assert comp["gate1_speedup"] is None


class TestBenchmarkScan:
    """Test benchmark scanning."""
    
    def test_benchmark_scan_python(self, python_test_repo):
        """Benchmark a Python repository."""
        result = benchmark_scan(python_test_repo, language="python", use_parallel=True)
        
        assert result.gate1_time is not None
        assert result.gate1_time > 0
        assert result.total_fingerprints > 0
        assert len(result.errors) == 0
    
    def test_benchmark_scan_with_and_without_parallel(self, python_test_repo):
        """Verify benchmarks capture parallel vs sequential."""
        result_seq = benchmark_scan(python_test_repo, language="python", use_parallel=False)
        result_par = benchmark_scan(python_test_repo, language="python", use_parallel=True)
        
        # Both should complete
        assert result_seq.gate1_time is not None
        assert result_par.gate1_time is not None
        
        # Both should find same fingerprints
        assert result_seq.total_fingerprints == result_par.total_fingerprints


class TestBenchmarkPersistence:
    """Test benchmark result persistence."""
    
    def test_save_benchmarks(self, tmp_path, python_test_repo):
        """Save benchmark results to file."""
        output = tmp_path / "benchmarks.json"
        
        result = benchmark_scan(python_test_repo, language="python")
        save_benchmarks([result], output)
        
        assert output.exists()
        
        # Verify JSON structure
        data = json.loads(output.read_text())
        assert "timestamp" in data
        assert "benchmarks" in data
        assert len(data["benchmarks"]) == 1
        assert data["benchmarks"][0]["name"] == f"{python_test_repo.name} (python)"


@pytest.fixture
def python_test_repo(tmp_path):
    """Create a test Python repository."""
    src = tmp_path / "src"
    src.mkdir()
    
    (src / "main.py").write_text("""
def main():
    print("hello")
""")
    
    (src / "utils.py").write_text("""
def helper():
    return "result"
""")
    
    return tmp_path
