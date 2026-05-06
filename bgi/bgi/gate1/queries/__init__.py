"""
Query-based COV token fingerprinting using tree-sitter .scm query files.

This module implements tree-sitter query-based extraction of COV tokens,
replacing the regex-based approach for improved accuracy and performance.

Workflow:
  1. Load .scm file for language
  2. Parse source file with tree-sitter
  3. Run queries to extract token patterns
  4. Map matched patterns to COV tokens
  5. Return COVFingerprint with extracted tokens
"""
