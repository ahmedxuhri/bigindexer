# BGI Language Support Guide

BGI uses **tree-sitter `.scm` query files** to extract behavioral fingerprints (COV tokens) from source code. This document explains the `.scm` format, COV token reference, and how to add support for new programming languages.

---

## Table of Contents

1. [Overview](#overview)
2. [COV Token Reference](#cov-token-reference)
3. [.scm File Format](#scm-file-format)
4. [Language-Specific Patterns](#language-specific-patterns)
5. [Example: Adding a New Language](#example-adding-a-new-language)
6. [Testing Your Language](#testing-your-language)
7. [Troubleshooting](#troubleshooting)

---

## Overview

### What is a .scm File?

A `.scm` file is a **tree-sitter query specification** that defines patterns to match AST (Abstract Syntax Tree) nodes and extract behavioral signals. Each match emits a COV token.

### Design Principles

1. **Single-Pass Fingerprinting:** Parse the file once, extract all COV tokens.
2. **Language-Agnostic COV Tokens:** The same COV tokens (OUTPUT, MUTATE, FETCH, etc.) appear in all languages.
3. **Fallback Strategy:** If a `.scm` file is missing, BGI falls back to regex-based rules (no regression).
4. **Scope:** Patterns should be run **scoped to function bodies** for function-level fingerprinting.

### Directory Structure

```
bgi/bgi/gate1/
├── queries/
│   ├── __init__.py              # Language registry initialization
│   ├── python.scm               # Python patterns
│   ├── typescript.scm           # TypeScript/JavaScript/TSX patterns
│   ├── go.scm                   # Go patterns
│   ├── rust.scm                 # Rust patterns
│   ├── java.scm                 # Java patterns
│   ├── csharp.scm               # C# patterns
│   ├── php.scm                  # PHP patterns
│   ├── ruby.scm                 # Ruby patterns
│   ├── kotlin.scm               # Kotlin patterns
│   └── scala.scm                # Scala patterns
├── parallel_scanner.py          # Multiprocessing Gate 1
├── fingerprinter.py             # COV token extraction
└── ...
```

---

## COV Token Reference

### Core COV Tokens

| Token | Meaning | Examples |
|-------|---------|----------|
| **OUTPUT** | Returns data / produces output | `return`, `print`, `write`, `emit` |
| **EMIT** | Yields or streams data | `yield`, `yield*`, `async yield` |
| **TRANSFORM** | Transforms/maps data | `map`, `filter`, `reduce`, `flatMap` |
| **CONDITIONAL** | Control flow branch | `if`, `else if`, `switch`, `ternary` |
| **LOOP** | Iterates over data | `for`, `while`, `do...while`, `forEach` |
| **MUTATE** | Modifies state in-place | `+=`, `-=`, `.append()`, `.push()`, `obj.prop = x` |
| **FETCH** | Reads external data | HTTP methods (`fetch`, `GET`, `POST`), DB queries |
| **SANITIZE** | Escapes/cleans data (security) | `escape`, `strip`, `sanitize`, `encode` |
| **GUARD** | Type check / validation | `isinstance`, `typeof`, `if x is None`, guards |
| **ASYNC** | Asynchronous execution | `await`, `async def`, `Promise` |
| **FORK** | Spawns new process/thread | `spawn`, `multiprocessing.Process`, `threading.Thread` |
| **EXCEPTION** | Exception handling | `try...catch`, `except`, `throw` |
| **CONFIG** | Configuration/settings | `.config`, `.settings`, `.env` |

### Token Tiers (Context)

BGI extracts tokens in 5 tiers:

1. **Tier 1 — AST Structure:** Patterns for control flow, data ops (covered by `.scm`)
2. **Tier 2 — Function Name:** Inferred from function signature (separate from `.scm`)
3. **Tier 3 — Decorators:** Applied to the function (separate from `.scm`)
4. **Tier 4 — Call Target Methods:** Method names in function calls (covered by `.scm`)
5. **Tier 5 — Class Context:** Containing class name (separate from `.scm`)

---

## .scm File Format

### Basic Syntax

A `.scm` file contains **S-expression queries** matching tree-sitter AST nodes:

```scheme
;; Comment: describe what this pattern captures

;; Pattern 1: Simple match
((node_type) @cov_token_name)

;; Pattern 2: Structured match with predicates
((parent_node
  child: (child_type @capture_name)
  (#match? @capture_name "^regex_pattern$"))
 @cov_token_name)
```

### Key Concepts

#### Captures (`@name`)

- `@capture_name` — Labels a node for later reference (used in predicates)
- `@cov_token_name` — The final COV token emitted (e.g., `@output`, `@mutate`)

#### Predicates

Predicates filter matches:

```scheme
;; Match method calls to specific functions
((call_expression
  function: (identifier) @name
  (#match? @name "^(fetch|get|post|request)$"))
 @fetch)

;; Negation
(#not-match? @name "^test_")

;; Type checks
(#eq? @type "string")

;; Structural checks
(#is-not? ancestor_node parent_type)
```

### Example Pattern Breakdown

```scheme
;; Python: Detect mutations via method calls
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(update|append|extend|remove|pop)$"))
 @mutate)
```

**Breakdown:**
- `call` — Match a function call node
- `function: (attribute ...)` — The function is an attribute access (e.g., `obj.method`)
- `attribute: (identifier) @name` — Capture the method name
- `(#match? @name "^(update|append|...)")` — Filter to methods matching the regex
- `@mutate` — Emit a MUTATE token

---

## Language-Specific Patterns

### Python (.scm)

**Key AST nodes:**
- Control flow: `if_statement`, `while_statement`, `for_statement`
- Functions: `function_definition`, `return_statement`
- Methods: `call` (function calls), `attribute` (method access)
- Comprehensions: `list_comprehension`, `dict_comprehension`

**Example: Detect fetch operations**
```scheme
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(request|urlopen|open)$"))
 @fetch)
```

### TypeScript/JavaScript (.scm)

**Key AST nodes:**
- Control flow: `if_statement`, `switch_statement`, `for_statement`, `while_statement`
- Functions: `function_declaration`, `arrow_function`, `function_expression`
- Methods: `call_expression`, `member_expression`
- Array methods: `call_expression` with `property_identifier` for `map`, `filter`, etc.

**Example: Detect array transformations**
```scheme
((call_expression
  function: (member_expression
    property: (property_identifier) @name)
  (#match? @name "^(map|filter|reduce)$"))
 @transform)
```

### Rust (.scm)

**Key AST nodes:**
- Functions: `function_item`, `closure_expression`
- Control flow: `if_expression`, `match_expression`, `loop_expression`
- Methods: `call_expression`, `method_call_expression`, `field_expression`

**Example: Detect mutable operations**
```scheme
((binary_expression
  left: _ @_lhs
  operator: "="
  right: _)
 @mutate)

((method_call_expression
  method: (field_identifier) @name
  (#match? @name "^(push|pop|extend)$"))
 @mutate)
```

### Go (.scm)

**Key AST nodes:**
- Functions: `function_declaration`, `method_declaration`
- Control flow: `if_statement`, `for_statement`, `switch_statement`
- Methods: `call_expression`, `selector_expression`

**Example: Detect goroutines**
```scheme
((go_statement) @fork)

((call_expression
  function: (identifier) @name
  (#match? @name "^(http\\.|net\\.)"))
 @fetch)
```

---

## Example: Adding a New Language

Let's add support for **Ruby**.

### Step 1: Identify Tree-Sitter Node Names

Use `tree-sitter` CLI to explore Ruby's AST:

```bash
npm install -g tree-sitter-cli
npm install tree-sitter-ruby
cat > test.rb << 'EOF'
def fetch_data(url)
  response = HTTPClient.get(url)
  response.body
end
EOF

tree-sitter parse test.rb
```

Output shows AST structure. Key nodes for Ruby:
- `method` — method definition
- `if` — conditional
- `block` — iteration block
- `call` — method call with arguments

### Step 2: Create `ruby.scm`

```scheme
;; Ruby COV Token Query Patterns
;; Run scoped to method body for function-level fingerprinting.

;; OUTPUT: return statements (implicit or explicit)
((return_statement) @output)

;; EMIT: yield statements (generator blocks)
((yield) @emit)

;; TRANSFORM: collection methods
((call
  receiver: _
  method: (identifier) @name
  (#match? @name "^(map|select|reduce|collect|each_with_index)$"))
 @transform)

;; CONDITIONAL: if/unless/case statements
((if_statement) @conditional)
((unless_statement) @conditional)
((case_statement) @conditional)

;; LOOP: for/while/loop statements
((for_statement) @loop)
((while_statement) @loop)
((until_statement) @loop)

;; MUTATE: assignment and method mutations
((assignment_statement) @mutate)

((call
  method: (identifier) @name
  (#match? @name "^(push|<<|pop|shift|unshift|delete|clear)$"))
 @mutate)

;; FETCH: HTTP and file operations
((call
  method: (identifier) @name
  (#match? @name "^(get|post|put|delete|patch|open|read|fetch)$"))
 @fetch)

;; EXCEPTION: begin/rescue/ensure
((begin_block) @exception)
```

### Step 3: Place the File

```bash
cp ruby.scm /root/mad/sessions/bgi/bgi/bgi/gate1/queries/
```

### Step 4: Register the Language

The language registry (`bgi/bgi/gate1/lang_registry.py`) will auto-discover `.scm` files. Verify by running:

```bash
python3 -c "from bgi.gate1.lang_registry import LanguageRegistry; reg = LanguageRegistry(); print(reg.list_languages())"
```

Ruby should appear in the output.

---

## Testing Your Language

### Unit Test Template

Create `tests/test_ruby_language.py`:

```python
import pytest
from bgi.gate1.fingerprinter import QueryFingerprinter
from bgi.core.types import COVToken, Tier

@pytest.fixture
def ruby_fingerprinter():
    return QueryFingerprinter("ruby", "bgi/bgi/gate1/queries/ruby.scm")

def test_ruby_output_token(ruby_fingerprinter):
    """Test OUTPUT token detection for return statements."""
    code = """
    def fetch_user(id)
      user = db.find(id)
      return user
    end
    """
    fingerprint = ruby_fingerprinter.fingerprint(code)
    assert COVToken.OUTPUT in fingerprint.tokens
    assert fingerprint.tier_1_tokens == {COVToken.OUTPUT}

def test_ruby_transform_token(ruby_fingerprinter):
    """Test TRANSFORM token detection for collection methods."""
    code = """
    def process_items(items)
      items.map { |x| x * 2 }
    end
    """
    fingerprint = ruby_fingerprinter.fingerprint(code)
    assert COVToken.TRANSFORM in fingerprint.tokens

def test_ruby_fetch_token(ruby_fingerprinter):
    """Test FETCH token detection for HTTP methods."""
    code = """
    def fetch_data(url)
      response = HTTPClient.get(url)
      response.body
    end
    """
    fingerprint = ruby_fingerprinter.fingerprint(code)
    assert COVToken.FETCH in fingerprint.tokens
```

### Integration Test

Create `tests/test_gate1_ruby.py`:

```python
def test_gate1_ruby_pipeline():
    """Integration test: Gate 1 processing Ruby code."""
    from bgi.pipeline import Pipeline
    
    pipeline = Pipeline("bgi/bgi/gate1")
    units = pipeline.scan("test_repo/", lang="ruby", incremental=False)
    
    # Verify units are extracted
    assert len(units) > 0
    
    # Verify COV tokens are present
    for unit in units:
        assert hasattr(unit, "fingerprint")
        assert len(unit.fingerprint.tokens) > 0
```

### Run Tests

```bash
cd /root/mad/sessions/bgi
python3 -m pytest tests/test_ruby_language.py -v
```

---

## Troubleshooting

### Pattern Not Matching

**Symptom:** COV tokens not detected for expected code patterns.

**Solution:**
1. Verify AST node names using `tree-sitter parse`
2. Test patterns in isolation: use `tree-sitter query` CLI
3. Check predicate syntax (exact regex syntax required)

### Fallback Triggered

**Symptom:** Messages indicate regex fallback is active (slower than `.scm`).

**Solution:**
1. Check if `.scm` file exists in `bgi/bgi/gate1/queries/<lang>.scm`
2. Verify file is valid S-expressions (no syntax errors)
3. Run `python3 tests/test_language_registry.py` to validate registration

### Missing Node Types

**Symptom:** Some COV tokens never appear in fingerprints.

**Solution:**
1. Tree-sitter language may lack specific node types
2. Use broader patterns (e.g., match multiple node types with alternatives)
3. File an issue if tree-sitter grammar is incomplete

### Performance Issues

**Symptom:** Scanning is slow despite `.scm` implementation.

**Solution:**
1. Verify language is using `.scm` (not fallback): check logs
2. Reduce pattern complexity if possible (fewer nested predicates)
3. Profile with `python3 -m cProfile` to identify bottleneck

---

## Best Practices

1. **Start Small:** Begin with a few high-value patterns (OUTPUT, MUTATE, FETCH).
2. **Test Early:** Add unit tests for each pattern as you write it.
3. **Use Predicates Wisely:** `#match?` is powerful but can be slow on large trees.
4. **Document Patterns:** Include comments explaining what each pattern captures.
5. **Run Integration Tests:** Validate on real code repositories before submitting.
6. **Keep Patterns Language-Agnostic:** Where possible, emit the same COV tokens as other languages.

---

## Quick Reference: COV Token Coverage by Language

| Token | Python | TypeScript | Rust | Go | Java | C# | PHP | Ruby | Kotlin | Scala |
|-------|--------|-----------|------|----|------|----|-----|------|--------|-------|
| OUTPUT | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| EMIT | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| TRANSFORM | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CONDITIONAL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| LOOP | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MUTATE | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| FETCH | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SANITIZE | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| GUARD | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## Questions?

For issues, PRs, or questions about adding a language, see [`docs/CONTRIBUTING_LANGUAGES.md`](CONTRIBUTING_LANGUAGES.md).
