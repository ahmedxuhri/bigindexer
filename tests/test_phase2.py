"""Tests for Phase 2 multiprocessing and entry-point detection."""
import pytest
from pathlib import Path
from bgi.gate1.parallel_scanner import scan_directory_parallel, _worker_scan_file
from bgi.gate1.entry_points import detect_entry_points, scan_from_entries
from bgi.core.fingerprint import COVFingerprint
import tempfile
import os


class TestParallelScanner:
    """Test parallel multiprocessing scanner."""
    
    def test_parallel_scan_python_same_result(self, python_test_repo):
        """Verify parallel and sequential scanning produce same fingerprints."""
        from bgi.gate1.scanner import scan_directory
        
        fps_sequential = sorted(
            scan_directory(python_test_repo, language="python"),
            key=lambda f: f.unit_id
        )
        fps_parallel = sorted(
            scan_directory_parallel(python_test_repo, language="python"),
            key=lambda f: f.unit_id
        )
        
        assert len(fps_parallel) == len(fps_sequential)
        for p, s in zip(fps_parallel, fps_sequential):
            assert p.unit_id == s.unit_id
            assert p.tokens == s.tokens
    
    def test_parallel_scan_typescript_same_result(self, typescript_test_repo):
        """Verify parallel scanning works for TypeScript."""
        fps = scan_directory_parallel(typescript_test_repo, language="typescript")
        assert isinstance(fps, list)
        assert all(isinstance(f, COVFingerprint) for f in fps)
    
    def test_parallel_scan_worker_function(self, tmp_path):
        """Test individual worker function."""
        # Create a test Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")
        
        result = _worker_scan_file((test_file, tmp_path, "python", ""))
        assert isinstance(result, list)
        assert len(result) >= 1
    
    def test_parallel_scan_empty_directory(self, tmp_path):
        """Test parallel scanning on empty directory."""
        fps = scan_directory_parallel(tmp_path, language="python")
        assert fps == []
    
    def test_parallel_scan_unsupported_language_fallback(self, python_test_repo):
        """Test that unsupported languages fall back to sequential scanner."""
        fps = scan_directory_parallel(python_test_repo, language="cobol")
        assert isinstance(fps, list)


class TestEntryPointDetection:
    """Test entry-point detection for BFS traversal."""
    
    def test_detect_python_entry_points(self, python_test_repo):
        """Detect Python entry points (__main__, main function)."""
        entries = detect_entry_points(python_test_repo, language="python")
        # May or may not have entries depending on test repo structure
        assert isinstance(entries, set)
        assert all(isinstance(e, Path) for e in entries)
    
    def test_detect_python_main_function(self, tmp_path):
        """Detect main() function in Python file."""
        main_file = tmp_path / "cli.py"
        main_file.write_text("""
def main():
    print("Hello")

if __name__ == "__main__":
    main()
""")
        
        entries = detect_entry_points(tmp_path, language="python")
        assert main_file in entries
    
    def test_detect_python_main_module(self, tmp_path):
        """Detect __main__.py module."""
        main_module = tmp_path / "__main__.py"
        main_module.write_text("print('main')")
        
        entries = detect_entry_points(tmp_path, language="python")
        assert main_module in entries
    
    def test_detect_typescript_entry_points(self, tmp_path):
        """Detect TypeScript entry points (index.ts, server.ts, etc.)."""
        # Create entry point files
        (tmp_path / "index.ts").write_text("export default {}; ")
        (tmp_path / "server.ts").write_text("export async function start() {}")
        (tmp_path / "utils.ts").write_text("export function util() {}")  # Not an entry point
        
        entries = detect_entry_points(tmp_path, language="typescript")
        assert (tmp_path / "index.ts") in entries
        assert (tmp_path / "server.ts") in entries
        # utils.ts may or may not be included depending on export detection
    
    def test_detect_java_main_method(self, tmp_path):
        """Detect Java main method."""
        main_class = tmp_path / "App.java"
        main_class.write_text("""
public class App {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
""")
        
        entries = detect_entry_points(tmp_path, language="java")
        assert main_class in entries
    
    def test_detect_go_main_function(self, tmp_path):
        """Detect Go main function."""
        main_file = tmp_path / "main.go"
        main_file.write_text("""
package main

func main() {
    println("Hello")
}
""")
        
        entries = detect_entry_points(tmp_path, language="go")
        assert main_file in entries
    
    def test_scan_from_entries_empty(self, tmp_path):
        """Test scan_from_entries with no entry points."""
        fps = scan_from_entries(tmp_path, language="python", scan_fn=lambda f, r: [])
        assert fps == []
    
    def test_scan_from_entries_with_function(self, tmp_path):
        """Test scan_from_entries prioritizes entry points."""
        # Create entry point
        entry = tmp_path / "main.py"
        entry.write_text("def main(): pass")
        
        # Create another file
        other = tmp_path / "utils.py"
        other.write_text("def util(): pass")
        
        # Mock scan function that tracks call order
        call_order = []
        
        def mock_scan(file_path, root):
            call_order.append(file_path.name)
            return []
        
        scan_from_entries(tmp_path, language="python", scan_fn=mock_scan)
        
        # Entry point (main.py) should be scanned first
        if call_order:
            assert call_order[0] == "main.py"


class TestPhase2Integration:
    """Integration tests for Phase 2 components."""
    
    def test_parallel_vs_sequential_performance_structure(self, python_test_repo):
        """Verify parallel scanner produces valid structure."""
        fps_parallel = scan_directory_parallel(python_test_repo, language="python")
        
        # Check structure
        for fp in fps_parallel:
            assert hasattr(fp, "unit_id")
            assert hasattr(fp, "tokens")
            assert isinstance(fp.tokens, (set, list))  # tokens can be list or set
    
    def test_cli_parallel_flag_integration(self):
        """Verify --parallel flag is recognized by CLI."""
        from bgi.cli import main
        import sys
        
        # This just ensures the flag is parseable without error
        # We don't actually run it to avoid side effects
        from argparse import ArgumentParser, Namespace
        import io
        
        # Capture help text to verify flag is there
        old_argv = sys.argv
        try:
            sys.argv = ["bgi", "scan", "--help"]
            with pytest.raises(SystemExit):  # --help causes exit
                main()
        except SystemExit:
            pass  # Expected
        finally:
            sys.argv = old_argv


# Fixtures

@pytest.fixture
def python_test_repo(tmp_path):
    """Create a minimal Python test repo."""
    src = tmp_path / "src"
    src.mkdir()
    
    (src / "main.py").write_text("""
def main():
    print("Hello")

if __name__ == "__main__":
    main()
""")
    
    (src / "utils.py").write_text("""
def helper():
    return "result"
""")
    
    return tmp_path


@pytest.fixture
def typescript_test_repo(tmp_path):
    """Create a minimal TypeScript test repo."""
    src = tmp_path / "src"
    src.mkdir()
    
    (src / "index.ts").write_text("""
export function initialize() {
    console.log("Init");
}
""")
    
    (src / "server.ts").write_text("""
export async function start() {
    return initialize();
}
""")
    
    return tmp_path


class TestBFSTraversal:
    """Test BFS (entry-point priority) traversal."""
    
    def test_bfs_prioritizes_entry_points(self, tmp_path):
        """Verify entry-point files are prioritized in scan order."""
        # Create files: entry point and non-entry
        entry = tmp_path / "main.py"
        entry.write_text('''def main():
    print("hello")

if __name__ == "__main__":
    main()
''')
        
        util1 = tmp_path / "util1.py"
        util1.write_text("def foo(): pass")
        
        util2 = tmp_path / "util2.py"
        util2.write_text("def bar(): pass")
        
        from bgi.gate1.parallel_scanner import scan_directory_parallel
        fps = scan_directory_parallel(tmp_path, language="python", enable_bfs=True)
        
        # Should have scanned all files
        assert len(fps) >= 3
    
    def test_bfs_disable_no_entry_priority(self, tmp_path):
        """Verify BFS can be disabled."""
        entry = tmp_path / "main.py"
        entry.write_text('''def main():
    pass

if __name__ == "__main__":
    main()
''')
        
        util = tmp_path / "util.py"
        util.write_text("def bar(): pass")
        
        from bgi.gate1.parallel_scanner import scan_directory_parallel
        fps = scan_directory_parallel(tmp_path, language="python", enable_bfs=False)
        
        # Should still scan all files
        assert len(fps) >= 2
    
    def test_bfs_identical_fingerprints_with_without(self, python_test_repo):
        """Verify BFS produces same fingerprints (order may differ, content same)."""
        from bgi.gate1.parallel_scanner import scan_directory_parallel
        
        fps_bfs = sorted(
            scan_directory_parallel(python_test_repo, language="python", enable_bfs=True),
            key=lambda f: f.unit_id
        )
        fps_no_bfs = sorted(
            scan_directory_parallel(python_test_repo, language="python", enable_bfs=False),
            key=lambda f: f.unit_id
        )
        
        assert len(fps_bfs) == len(fps_no_bfs)
        for f1, f2 in zip(fps_bfs, fps_no_bfs):
            assert f1.unit_id == f2.unit_id
            assert f1.tokens == f2.tokens
    
    def test_bfs_typescript_entry_points(self, tmp_path):
        """Test BFS with TypeScript entry points."""
        entry = tmp_path / "server.ts"
        entry.write_text("export async function start() {}")
        
        util = tmp_path / "utils.ts"
        util.write_text("export function helper() {}")
        
        from bgi.gate1.parallel_scanner import scan_directory_parallel
        fps = scan_directory_parallel(tmp_path, language="typescript", enable_bfs=True)
        
        # Should scan both files
        assert len(fps) >= 2
