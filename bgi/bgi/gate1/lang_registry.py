"""
Language registry for BGI — manages tree-sitter .scm patterns and fallback rules.

Architecture:
- Auto-discovers .scm files from bgi/bgi/gate1/queries/*.scm
- Maps language → (.scm_file, QueryFingerprinter)
- Falls back to regex rules if .scm not found or fails to load
- Provides language validation and handler lookup
"""

import os
import json
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

# Fallback regex rules per language (if .scm not available)
FALLBACK_REGEX_RULES = {
    "python": {
        "output": r"return\s+",
        "mutate": r"(\+=|-=|\*=|/=|\.(?:append|pop|extend|remove|clear|update|delete|insert))",
        "fetch": r"(?:requests\.|urllib\.request|open\(|socket\.|http\.)",
        "transform": r"map\(|filter\(|reduce\(|\.(?:map|filter|reduce)",
    },
    "javascript": {
        "output": r"return\s+",
        "mutate": r"(\+=|-=|\*=|/=|\.(?:push|pop|shift|unshift|splice|delete|clear|update))",
        "fetch": r"fetch\(|http\.|XMLHttpRequest|axios\.|request\(",
        "transform": r"\.(?:map|filter|reduce|forEach)\(",
    },
    "typescript": {
        "output": r"return\s+",
        "mutate": r"(\+=|-=|\*=|/=|\.(?:push|pop|shift|unshift|splice|delete|clear|update))",
        "fetch": r"fetch\(|http\.|XMLHttpRequest|axios\.|request\(",
        "transform": r"\.(?:map|filter|reduce|forEach)\(",
    },
    "rust": {
        "output": r"return\s+|Ok\(|Err\(",
        "mutate": r"\.(?:push|pop|extend|remove|insert|clear)|\.as_mut\(\)",
        "fetch": r"reqwest::|hyper::|std::fs|tokio::net",
        "transform": r"\.(?:map|filter|fold)\(",
    },
    "go": {
        "output": r"return\s+",
        "mutate": r"append\(|delete\(|\[\w+\]\s*=",
        "fetch": r"http\.|net\.|ioutil\.|os\.Open",
        "transform": r"range\s+",
    },
}


class LanguageHandler:
    """Metadata and handler for a single language."""

    def __init__(
        self,
        lang: str,
        scm_file: Optional[str] = None,
        fingerprinter=None,
        fallback_rules: Optional[Dict] = None,
    ):
        self.lang = lang
        self.scm_file = scm_file
        self.fingerprinter = fingerprinter
        self.fallback_rules = fallback_rules or {}
        self.uses_scm = scm_file is not None and fingerprinter is not None

    def to_dict(self) -> Dict:
        """Serialize to dictionary for logging/inspection."""
        return {
            "language": self.lang,
            "scm_file": self.scm_file,
            "uses_scm": self.uses_scm,
            "fallback_rules": len(self.fallback_rules),
        }


class LanguageRegistry:
    """Manages language support across tree-sitter .scm patterns and regex fallback."""

    def __init__(self, queries_dir: Optional[str] = None):
        """
        Initialize registry.

        Args:
            queries_dir: Directory containing .scm files. Defaults to bgi/bgi/gate1/queries/
        """
        if queries_dir is None:
            queries_dir = os.path.join(
                os.path.dirname(__file__), "queries"
            )
        
        self.queries_dir = queries_dir
        self.handlers: Dict[str, LanguageHandler] = {}
        
        # Lazy-load fingerprinters to avoid import-time dependencies
        self._fingerprinter_cache = {}
        
        self._discover_languages()

    def _discover_languages(self) -> None:
        """Auto-discover .scm files and register languages."""
        if not os.path.isdir(self.queries_dir):
            logger.warning(f"Queries directory not found: {self.queries_dir}")
            self._register_fallback_languages()
            return

        scm_files = sorted(Path(self.queries_dir).glob("*.scm"))
        
        for scm_path in scm_files:
            lang = scm_path.stem
            scm_file = str(scm_path)
            
            # Try to validate .scm file
            is_valid = self._load_fingerprinter(lang, scm_file)
            
            # Get fallback rules
            fallback_rules = FALLBACK_REGEX_RULES.get(lang, {})
            
            # Register handler
            handler = LanguageHandler(
                lang,
                scm_file=scm_file if is_valid else None,
                fingerprinter=is_valid,  # True/None marker
                fallback_rules=fallback_rules,
            )
            self.handlers[lang] = handler
            
            if is_valid:
                logger.debug(f"Registered {lang} with .scm patterns from {scm_file}")
            else:
                logger.warning(f"Failed to validate .scm for {lang}, using regex fallback")

        # Register any languages with only fallback rules
        self._register_fallback_languages()

    def _register_fallback_languages(self) -> None:
        """Register languages with fallback regex rules (no .scm file)."""
        for lang, fallback_rules in FALLBACK_REGEX_RULES.items():
            if lang not in self.handlers:
                handler = LanguageHandler(
                    lang,
                    scm_file=None,
                    fingerprinter=None,
                    fallback_rules=fallback_rules,
                )
                self.handlers[lang] = handler
                logger.debug(f"Registered {lang} with regex fallback rules")

    def _load_fingerprinter(self, lang: str, scm_file: str):
        """
        Validate that a .scm file exists and is well-formed.
        
        Returns True if file exists and has valid S-expression syntax, False otherwise.
        """
        try:
            # Validate .scm file exists and is readable
            if not os.path.isfile(scm_file):
                logger.warning(f".scm file not found: {scm_file}")
                return None
            
            # Validate syntax: matching parentheses
            content = open(scm_file).read()
            open_parens = content.count("(")
            close_parens = content.count(")")
            if open_parens != close_parens:
                logger.warning(
                    f"Invalid .scm syntax in {scm_file}: "
                    f"{open_parens} open, {close_parens} close parens"
                )
                return None
            
            # File is valid; return a marker (we don't instantiate QueryFingerprinter here)
            return scm_file
        except Exception as e:
            logger.warning(f"Failed to validate .scm for {lang}: {e}")
            return None

    def get_handler(self, lang: str) -> Optional[LanguageHandler]:
        """
        Get handler for a language.
        
        Returns LanguageHandler with .scm or fallback rules, or None if not found.
        """
        return self.handlers.get(lang.lower())

    def has_language(self, lang: str) -> bool:
        """Check if language is supported."""
        return lang.lower() in self.handlers

    def list_languages(self) -> List[str]:
        """List all supported languages."""
        return sorted(self.handlers.keys())

    def list_scm_languages(self) -> List[str]:
        """List languages with .scm support (not just fallback)."""
        return sorted([
            lang for lang, handler in self.handlers.items()
            if handler.uses_scm
        ])

    def list_fallback_languages(self) -> List[str]:
        """List languages using regex fallback (no .scm)."""
        return sorted([
            lang for lang, handler in self.handlers.items()
            if not handler.uses_scm
        ])

    def validate_language(self, lang: str) -> Tuple[bool, str]:
        """
        Validate that a language is registered and ready.
        
        Returns: (is_valid: bool, message: str)
        """
        handler = self.get_handler(lang)
        
        if not handler:
            return False, f"Language '{lang}' not registered"
        
        if handler.uses_scm:
            return True, f"Language '{lang}' ready (.scm patterns from {handler.scm_file})"
        else:
            return True, f"Language '{lang}' ready (regex fallback)"

    def get_status(self) -> Dict:
        """Get registry status for debugging."""
        scm_langs = self.list_scm_languages()
        fallback_langs = self.list_fallback_languages()
        
        return {
            "total_languages": len(self.handlers),
            "scm_languages": len(scm_langs),
            "fallback_languages": len(fallback_langs),
            "queries_dir": self.queries_dir,
            "languages": {
                lang: self.handlers[lang].to_dict()
                for lang in sorted(self.handlers.keys())
            },
        }

    def print_status(self) -> None:
        """Print registry status."""
        status = self.get_status()
        print(f"\n=== BGI Language Registry ===")
        print(f"Total: {status['total_languages']} languages")
        print(f"  .scm patterns: {status['scm_languages']} languages")
        print(f"  Regex fallback: {status['fallback_languages']} languages")
        print(f"Queries dir: {status['queries_dir']}")
        print(f"\nLanguages:")
        for lang in sorted(self.handlers.keys()):
            handler = self.handlers[lang]
            mode = ".scm" if handler.uses_scm else "fallback"
            print(f"  {lang:15} [{mode}]")


# Global registry instance (lazy-initialized on first use)
_global_registry: Optional[LanguageRegistry] = None


def get_registry() -> LanguageRegistry:
    """Get or create global language registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = LanguageRegistry()
    return _global_registry


def validate_language(lang: str) -> bool:
    """Quick check if a language is registered."""
    return get_registry().has_language(lang)


if __name__ == "__main__":
    # CLI: python3 -m bgi.gate1.lang_registry
    registry = get_registry()
    registry.print_status()
