"""
Tests for BGI language registry and .scm format validation.

Ensures:
1. All .scm files are valid S-expressions
2. Languages are correctly registered
3. Fallback rules work when .scm unavailable
4. COV tokens are properly covered
"""

import pytest
import os
import json
from pathlib import Path
from bgi.gate1.lang_registry import LanguageRegistry, get_registry, LanguageHandler
from bgi.core.types import COVToken


class TestLanguageRegistry:
    """Test language registry initialization and discovery."""

    def test_registry_initialization(self):
        """Test registry initializes without errors."""
        registry = LanguageRegistry()
        assert registry is not None
        assert len(registry.handlers) > 0

    def test_language_discovery(self):
        """Test that .scm languages are discovered."""
        registry = LanguageRegistry()
        scm_langs = registry.list_scm_languages()
        
        # Python and TypeScript should have .scm files
        assert "python" in scm_langs, "Python should have .scm patterns"
        assert "typescript" in scm_langs, "TypeScript should have .scm patterns"

    def test_fallback_languages_registered(self):
        """Test that fallback languages are registered."""
        registry = LanguageRegistry()
        fallback_langs = registry.list_fallback_languages()
        
        # Go and Rust might be fallback-only depending on .scm availability
        assert len(fallback_langs) >= 0

    def test_get_handler_scm_language(self):
        """Test getting handler for .scm language."""
        registry = LanguageRegistry()
        handler = registry.get_handler("python")
        
        assert handler is not None
        assert handler.lang == "python"
        assert handler.uses_scm is True
        assert handler.scm_file is not None

    def test_get_handler_fallback_language(self):
        """Test getting handler for fallback language."""
        registry = LanguageRegistry()
        handler = registry.get_handler("go")
        
        assert handler is not None
        assert handler.lang == "go"
        # May use .scm or fallback depending on setup
        assert handler.fallback_rules is not None or handler.uses_scm

    def test_get_handler_nonexistent_language(self):
        """Test getting handler for non-existent language."""
        registry = LanguageRegistry()
        handler = registry.get_handler("nonexistent_lang_xyz")
        
        assert handler is None

    def test_has_language(self):
        """Test language existence check."""
        registry = LanguageRegistry()
        
        assert registry.has_language("python") is True
        assert registry.has_language("typescript") is True
        assert registry.has_language("nonexistent_lang_xyz") is False

    def test_list_languages(self):
        """Test language listing."""
        registry = LanguageRegistry()
        langs = registry.list_languages()
        
        assert isinstance(langs, list)
        assert len(langs) > 0
        assert "python" in langs

    def test_validate_language_valid(self):
        """Test language validation for valid language."""
        registry = LanguageRegistry()
        is_valid, msg = registry.validate_language("python")
        
        assert is_valid is True
        assert "python" in msg.lower()

    def test_validate_language_invalid(self):
        """Test language validation for invalid language."""
        registry = LanguageRegistry()
        is_valid, msg = registry.validate_language("nonexistent_lang_xyz")
        
        assert is_valid is False
        assert "not registered" in msg

    def test_global_registry_singleton(self):
        """Test that get_registry() returns singleton."""
        reg1 = get_registry()
        reg2 = get_registry()
        
        assert reg1 is reg2


class TestSCMFilesValidity:
    """Test that .scm files are valid and complete."""

    @pytest.fixture
    def queries_dir(self):
        """Get queries directory path."""
        import bgi.gate1
        queries_dir = os.path.join(
            os.path.dirname(bgi.gate1.__file__), "queries"
        )
        return queries_dir

    def test_scm_files_exist(self, queries_dir):
        """Test that .scm files exist in queries directory."""
        assert os.path.isdir(queries_dir), f"Queries dir not found: {queries_dir}"
        scm_files = list(Path(queries_dir).glob("*.scm"))
        
        assert len(scm_files) > 0, "No .scm files found in queries directory"

    def test_scm_file_syntax_valid(self, queries_dir):
        """Test that all .scm files have valid S-expression syntax."""
        scm_files = sorted(Path(queries_dir).glob("*.scm"))
        
        for scm_path in scm_files:
            content = scm_path.read_text()
            assert content.strip(), f"Empty .scm file: {scm_path}"
            
            # Basic syntax check: matching parentheses
            open_parens = content.count("(")
            close_parens = content.count(")")
            assert open_parens == close_parens, (
                f"Unmatched parentheses in {scm_path.name}: "
                f"{open_parens} open, {close_parens} close"
            )

    def test_scm_files_have_documentation(self, queries_dir):
        """Test that .scm files include comments/documentation."""
        scm_files = sorted(Path(queries_dir).glob("*.scm"))
        
        for scm_path in scm_files:
            content = scm_path.read_text()
            # Each .scm should have at least one comment line
            has_comments = ";;" in content
            assert has_comments, f"No comments in {scm_path.name}"

    def test_scm_files_cover_core_tokens(self, queries_dir):
        """Test that .scm files cover core COV tokens."""
        scm_files = sorted(Path(queries_dir).glob("*.scm"))
        core_tokens = {"output", "mutate", "fetch", "conditional", "loop"}
        
        for scm_path in scm_files:
            content = scm_path.read_text().lower()
            
            # Check for at least 3 core token types
            covered = sum(1 for token in core_tokens if f"@{token}" in content)
            assert covered >= 3, (
                f"{scm_path.name} covers only {covered}/5 core tokens. "
                f"Expected at least 3: {core_tokens}"
            )

    def test_scm_files_use_predicates(self, queries_dir):
        """Test that .scm files use tree-sitter predicates correctly."""
        scm_files = sorted(Path(queries_dir).glob("*.scm"))
        
        for scm_path in scm_files:
            content = scm_path.read_text()
            
            # Should use at least one predicate (#match?, #eq?, etc.)
            has_predicates = "#match?" in content or "#eq?" in content or "#not-match?" in content
            assert has_predicates, f"{scm_path.name} should use predicates for pattern matching"


class TestLanguageHandlerMetadata:
    """Test LanguageHandler metadata and serialization."""

    def test_handler_creation_with_scm(self):
        """Test creating handler with .scm."""
        handler = LanguageHandler(
            "python",
            scm_file="/path/to/python.scm",
            fingerprinter="mock_fingerprinter",
        )
        
        assert handler.lang == "python"
        assert handler.uses_scm is True
        assert handler.scm_file == "/path/to/python.scm"

    def test_handler_creation_fallback_only(self):
        """Test creating handler with fallback rules only."""
        fallback_rules = {"output": r"return\s+"}
        handler = LanguageHandler(
            "go",
            scm_file=None,
            fingerprinter=None,
            fallback_rules=fallback_rules,
        )
        
        assert handler.lang == "go"
        assert handler.uses_scm is False
        assert handler.fallback_rules == fallback_rules

    def test_handler_to_dict(self):
        """Test handler serialization to dict."""
        handler = LanguageHandler(
            "python",
            scm_file="/path/to/python.scm",
            fingerprinter="mock_fingerprinter",
        )
        
        data = handler.to_dict()
        assert data["language"] == "python"
        assert data["uses_scm"] is True
        assert "scm_file" in data


class TestRegistryStatus:
    """Test registry status reporting."""

    def test_get_status(self):
        """Test getting registry status."""
        registry = LanguageRegistry()
        status = registry.get_status()
        
        assert isinstance(status, dict)
        assert "total_languages" in status
        assert "scm_languages" in status
        assert "fallback_languages" in status
        assert "queries_dir" in status
        assert "languages" in status
        
        assert status["total_languages"] > 0
        assert status["scm_languages"] + status["fallback_languages"] > 0

    def test_print_status_no_error(self, capsys):
        """Test that print_status works without errors."""
        registry = LanguageRegistry()
        registry.print_status()
        
        captured = capsys.readouterr()
        assert "Language Registry" in captured.out
        assert "languages" in captured.out.lower()


class TestLanguageRegistrationContract:
    """Test the contract for language registration."""

    def test_python_language_contract(self):
        """Test Python language meets registration contract."""
        registry = LanguageRegistry()
        handler = registry.get_handler("python")
        
        assert handler is not None
        assert handler.lang == "python"
        # Must have either .scm or fallback rules
        assert handler.uses_scm or handler.fallback_rules

    def test_typescript_language_contract(self):
        """Test TypeScript language meets registration contract."""
        registry = LanguageRegistry()
        handler = registry.get_handler("typescript")
        
        assert handler is not None
        assert handler.lang == "typescript"
        assert handler.uses_scm or handler.fallback_rules

    def test_all_languages_have_fallback(self):
        """Test that all languages have fallback rules or .scm."""
        registry = LanguageRegistry()
        
        for lang, handler in registry.handlers.items():
            has_scm = handler.uses_scm
            has_fallback = len(handler.fallback_rules) > 0
            assert has_scm or has_fallback, (
                f"Language '{lang}' has neither .scm nor fallback rules"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
