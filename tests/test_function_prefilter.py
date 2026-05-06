"""
Tests for Phase 3 function pre-filter.

Verifies:
  1. Pattern matching for different languages
  2. File filtering accuracy
  3. Reduction in files to scan
"""
import pytest
from pathlib import Path

from bgi.gate1.function_prefilter import (
    should_parse_file, filter_files_by_content, compile_patterns, PREFILTER_PATTERNS
)


class TestPatternCompilation:
    """Test pattern compilation."""
    
    def test_compile_patterns_typescript(self):
        """Compile TypeScript patterns."""
        patterns = compile_patterns("typescript")
        assert len(patterns) > 0
        assert all(hasattr(p, 'search') for p in patterns)
    
    def test_compile_patterns_all_languages(self):
        """All languages have patterns."""
        for lang in ["python", "typescript", "javascript", "java", "go", "rust"]:
            patterns = compile_patterns(lang)
            assert len(patterns) > 0


class TestShouldParseFile:
    """Test file parsing decision."""
    
    def test_parse_file_with_function_python(self, tmp_path):
        """Parse Python file with function."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    pass")
        
        assert should_parse_file(test_file, "python")
    
    def test_skip_file_without_function_python(self, tmp_path):
        """Skip Python file without function."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# Just a comment\nx = 1")
        
        assert not should_parse_file(test_file, "python")
    
    def test_parse_file_with_class(self, tmp_path):
        """Parse file with class definition."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("export class MyClass { }")
        
        assert should_parse_file(test_file, "typescript")
    
    def test_parse_file_with_export(self, tmp_path):
        """Parse file with export statement."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("export const x = 1;")
        
        assert should_parse_file(test_file, "typescript")
    
    def test_skip_empty_file(self, tmp_path):
        """Skip empty file."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("")
        
        assert not should_parse_file(test_file, "typescript")
    
    def test_parse_typescript_function_declaration(self, tmp_path):
        """Parse TypeScript function declaration."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("export async function hello() { }")
        
        assert should_parse_file(test_file, "typescript")
    
    def test_parse_javascript_arrow_function(self, tmp_path):
        """Parse JavaScript arrow function."""
        test_file = tmp_path / "test.js"
        test_file.write_text("const hello = () => { };")
        
        assert should_parse_file(test_file, "javascript")
    
    def test_skip_config_file(self, tmp_path):
        """Skip config file (no functions)."""
        test_file = tmp_path / "config.ts"
        test_file.write_text('{\n  "key": "value"\n}')
        
        assert not should_parse_file(test_file, "typescript")
    
    def test_parse_java_method(self, tmp_path):
        """Parse Java file with method."""
        test_file = tmp_path / "Test.java"
        test_file.write_text("public class Test { public void hello() { } }")
        
        assert should_parse_file(test_file, "java")
    
    def test_parse_go_function(self, tmp_path):
        """Parse Go function."""
        test_file = tmp_path / "main.go"
        test_file.write_text("func main() { }")
        
        assert should_parse_file(test_file, "go")
    
    def test_parse_rust_function(self, tmp_path):
        """Parse Rust function."""
        test_file = tmp_path / "lib.rs"
        test_file.write_text("pub fn main() { }")
        
        assert should_parse_file(test_file, "rust")
    
    def test_handle_unreadable_file(self, tmp_path):
        """Handle file read errors gracefully."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("function test() { }")
        
        # Mock a read error by using a directory instead
        dir_path = tmp_path / "dir.ts"
        dir_path.mkdir()
        
        # Should return True on error (safer to parse than skip)
        assert should_parse_file(dir_path, "typescript")


class TestFilterFilesByContent:
    """Test file filtering."""
    
    def test_filter_mixed_files(self, tmp_path):
        """Filter mixed Python files."""
        # File with function
        file1 = tmp_path / "test1.py"
        file1.write_text("def hello(): pass")
        
        # File without function
        file2 = tmp_path / "test2.py"
        file2.write_text("# comment\nx = 1")
        
        # File with class
        file3 = tmp_path / "test3.py"
        file3.write_text("class MyClass: pass")
        
        files = [file1, file2, file3]
        filtered, skipped = filter_files_by_content(files, "python")
        
        assert len(filtered) == 2  # file1 and file3
        assert skipped == 1  # file2
        assert file2 not in filtered
    
    def test_filter_typescript_files(self, tmp_path):
        """Filter TypeScript files."""
        # With function
        file1 = tmp_path / "component.tsx"
        file1.write_text("export function Component() { return null; }")
        
        # Config file (no function)
        file2 = tmp_path / "config.ts"
        file2.write_text("export const config = { };")
        
        # Empty-ish file
        file3 = tmp_path / "empty.ts"
        file3.write_text("")
        
        files = [file1, file2, file3]
        filtered, skipped = filter_files_by_content(files, "typescript")
        
        assert len(filtered) >= 1  # At least component
        assert skipped >= 1  # At least empty.ts
    
    def test_filter_empty_list(self):
        """Filter empty file list."""
        filtered, skipped = filter_files_by_content([], "typescript")
        
        assert filtered == []
        assert skipped == 0
    
    def test_filter_reduction_estimate(self, tmp_path):
        """Estimate file reduction."""
        # Create mix of files
        code_files = []
        for i in range(3):
            f = tmp_path / f"code{i}.ts"
            f.write_text(f"export function func{i}() {{}}")
            code_files.append(f)
        
        config_files = []
        for i in range(7):
            f = tmp_path / f"config{i}.json"
            f.write_text("{}")
            config_files.append(f)
        
        files = code_files + config_files
        filtered, skipped = filter_files_by_content(files, "typescript")
        
        # Should reduce significantly (80% is target)
        reduction_ratio = skipped / len(files)
        assert skipped > 0  # Some files skipped
        print(f"Reduction: {reduction_ratio:.1%} files skipped")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
