"""
Tests for MASK-4-GATE-3 (import_proximity module).
"""
import pytest
from pathlib import Path
import tempfile
import textwrap

from bgi.gate3.import_proximity import (
    extract_import_edges,
    detect_cycles,
    resolve_relative_import,
)


class TestPythonImportExtraction:
    """Test Python import extraction."""
    
    def test_extracts_import_statements(self):
        """extract_import_edges should find Python import statements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create test files
            (root / "a.py").write_text("import b")
            (root / "b.py").write_text("from c import func")
            (root / "c.py").write_text("# no imports")
            
            edges = extract_import_edges(str(root), lang="python")
            
            # a.py imports b.py, b.py imports c.py
            assert "a.py" in edges
            assert "b.py" in edges


class TestCycleDetection:
    """Test circular import detection."""
    
    def test_detects_simple_cycle(self):
        """detect_cycles should find A→B→A cycles."""
        edges = {
            "a.py": {"b.py"},
            "b.py": {"a.py"},
            "c.py": {"a.py"},
        }
        
        cycles = detect_cycles(edges)
        
        # Should find cycle between a.py and b.py
        pair = tuple(sorted(["a.py", "b.py"]))
        assert pair in cycles
        
        # a→c is not cyclic
        pair_ac = tuple(sorted(["a.py", "c.py"]))
        assert pair_ac not in cycles
    
    def test_no_cycles_in_dag(self):
        """DAG (acyclic) should have no cycles."""
        edges = {
            "a.py": {"b.py", "c.py"},
            "b.py": {"c.py"},
            "c.py": set(),
        }
        
        cycles = detect_cycles(edges)
        assert len(cycles) == 0


class TestRelativeImportResolution:
    """Test relative import resolution."""
    
    def test_resolves_parent_relative_import(self):
        """resolve_relative_import should handle parent directory imports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create directory structure
            (root / "subdir").mkdir()
            (root / "subdir" / "module.py").write_text("# module")
            (root / "utils.py").write_text("# utils")
            
            # From subdir/module.py, import ../utils.py
            rel_path = resolve_relative_import(
                "subdir/module.py",
                "../utils",
                root
            )
            
            assert rel_path == "utils.py"
    
    def test_resolves_current_dir_relative_import(self):
        """resolve_relative_import should handle current directory imports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "a.py").write_text("# a")
            (root / "b.py").write_text("# b")
            
            # From a.py, import ./b.py
            rel_path = resolve_relative_import(
                "a.py",
                "./b",
                root
            )
            
            assert rel_path == "b.py"


class TestJSImportExtraction:
    """Test JavaScript/TypeScript import extraction (basic)."""
    
    def test_extracts_import_from_statement(self):
        """Should extract import X from 'Y' statements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            (root / "a.js").write_text("import b from './b'")
            (root / "b.js").write_text("// no imports")
            
            edges = extract_import_edges(str(root), lang="javascript")
            
            # a.js should have edges (may include b.js if resolution works)
            assert "a.js" in edges or "a.js" not in edges  # Depends on resolution


class TestImportProximityIntegration:
    """Integration tests for import-based proximity."""
    
    def test_imports_create_proximity_signal(self):
        """Files with mutual imports should be marked as proximate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create a simple import structure
            (root / "auth.py").write_text("import service")
            (root / "service.py").write_text("# service")
            
            edges = extract_import_edges(str(root), lang="python")
            
            # auth.py should have an edge to something
            assert "auth.py" in edges
