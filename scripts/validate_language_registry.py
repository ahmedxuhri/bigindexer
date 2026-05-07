#!/usr/bin/env python3
"""
Standalone validation script for language registry.

Run: python3 scripts/validate_language_registry.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bgi.gate1.lang_registry import LanguageRegistry, get_registry


def test_registry_initialization():
    """Test registry initializes without errors."""
    registry = LanguageRegistry()
    assert registry is not None
    assert len(registry.handlers) > 0
    return True


def test_language_discovery():
    """Test that .scm languages are discovered."""
    registry = LanguageRegistry()
    scm_langs = registry.list_scm_languages()
    
    assert "python" in scm_langs, "Python should have .scm patterns"
    assert "typescript" in scm_langs, "TypeScript should have .scm patterns"
    return True


def test_get_handler_scm_language():
    """Test getting handler for .scm language."""
    registry = LanguageRegistry()
    handler = registry.get_handler("python")
    
    assert handler is not None
    assert handler.lang == "python"
    assert handler.uses_scm is True
    assert handler.scm_file is not None
    return True


def test_has_language():
    """Test language existence check."""
    registry = LanguageRegistry()
    
    assert registry.has_language("python") is True
    assert registry.has_language("typescript") is True
    assert registry.has_language("nonexistent_lang_xyz") is False
    return True


def test_scm_files_exist():
    """Test that .scm files exist in queries directory."""
    from bgi.gate1 import lang_registry
    import os
    
    queries_dir = os.path.join(
        os.path.dirname(lang_registry.__file__), "queries"
    )
    
    assert os.path.isdir(queries_dir), f"Queries dir not found: {queries_dir}"
    scm_files = list(Path(queries_dir).glob("*.scm"))
    
    assert len(scm_files) > 0, "No .scm files found in queries directory"
    return True


def test_scm_file_syntax_valid():
    """Test that all .scm files have valid S-expression syntax."""
    from bgi.gate1 import lang_registry
    import os
    
    queries_dir = os.path.join(
        os.path.dirname(lang_registry.__file__), "queries"
    )
    
    scm_files = sorted(Path(queries_dir).glob("*.scm"))
    
    for scm_path in scm_files:
        content = scm_path.read_text()
        assert content.strip(), f"Empty .scm file: {scm_path}"
        
        # Check matching parentheses
        open_parens = content.count("(")
        close_parens = content.count(")")
        assert open_parens == close_parens, (
            f"Unmatched parentheses in {scm_path.name}: "
            f"{open_parens} open, {close_parens} close"
        )
    return True


# Test suite
TESTS = [
    ("Registry initialization", test_registry_initialization),
    ("Language discovery", test_language_discovery),
    ("Get handler for .scm language", test_get_handler_scm_language),
    ("Language existence check", test_has_language),
    (".scm files exist", test_scm_files_exist),
    (".scm file syntax valid", test_scm_file_syntax_valid),
]


def main():
    """Run all tests."""
    print("=" * 70)
    print("Language Registry Validation Tests")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for test_name, test_func in TESTS:
        try:
            result = test_func()
            if result:
                print(f"✓ {test_name}")
                passed += 1
            else:
                print(f"✗ {test_name} — returned False")
                failed += 1
        except AssertionError as e:
            print(f"✗ {test_name} — {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_name} — {type(e).__name__}: {e}")
            failed += 1
    
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    # Print registry status
    print("\n" + "=" * 70)
    print("Registry Status")
    print("=" * 70)
    registry = get_registry()
    registry.print_status()
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
