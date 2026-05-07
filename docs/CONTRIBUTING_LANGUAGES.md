# Contributing Language Support to BGI

Thank you for contributing to BGI! This guide walks you through adding support for a new programming language end-to-end.

---

## Quick Start Checklist

- [ ] **Step 1:** Choose your language
- [ ] **Step 2:** Explore tree-sitter AST
- [ ] **Step 3:** Write `.scm` patterns
- [ ] **Step 4:** Create unit tests
- [ ] **Step 5:** Create integration test
- [ ] **Step 6:** Validate on real code
- [ ] **Step 7:** Submit PR with documentation

---

## Step 1: Choose Your Language

Pick a language you know well. BGI uses **tree-sitter** for parsing, so verify your language has a tree-sitter grammar:

```bash
npm search tree-sitter- | grep <lang>
# Example: npm search tree-sitter- | grep ruby
```

Languages with mature tree-sitter support:
- ✅ Python, JavaScript/TypeScript, Rust, Go, Java, C, C++, Ruby, PHP, Kotlin
- ⚠️ Less mature: R, Swift, Scala, Elixir, Haskell

---

## Step 2: Explore Tree-Sitter AST

Install `tree-sitter-cli` and the language parser:

```bash
npm install -g tree-sitter-cli
npm install tree-sitter-<lang>  # e.g., tree-sitter-ruby
```

Create a sample file with representative code:

```bash
cat > sample.<ext> << 'EOF'
// Sample code covering:
// - function/method definitions
// - control flow (if, loops)
// - method calls and assignments
// - data operations (returns, yields)
EOF
```

Explore the AST:

```bash
tree-sitter parse sample.<ext>
tree-sitter query --capture <lang>.scm sample.<ext>  # (after creating .scm)
```

### Key Questions to Answer

1. **How are functions defined?** (e.g., `def`, `function`, `func`, `fun`)
2. **How are method calls written?** (e.g., `obj.method()`, `obj::method()`, `obj->method()`)
3. **What node types represent data flow?** (e.g., `return_statement`, `assignment`)
4. **How are decorators/attributes applied?** (if language supports them)

---

## Step 3: Write `.scm` Patterns

Create `/root/mad/sessions/bgi/bgi/bgi/gate1/queries/<lang>.scm`.

### Pattern Template

Start with this minimal set of patterns:

```scheme
;; <Language> COV Token Query Patterns — WATER-CLOCK
;; Run scoped to function bodies for function-level fingerprinting.
;; Reference: docs/LANGUAGE_SUPPORT.md

;; ── Data Flow ────────────────────────────────────────────────────────────

;; OUTPUT: return statements
;; TODO: Add pattern for return-like statements

;; EMIT: yield or generator statements
;; TODO: Add pattern for yield-like statements

;; TRANSFORM: collection/array methods
;; TODO: Add pattern for map/filter/reduce equivalents

;; MUTATE: mutations and assignments
;; TODO: Add pattern for assignments and mutating method calls

;; FETCH: I/O and external data access
;; TODO: Add pattern for network/file/DB access

;; ── Control Flow ──────────────────────────────────────────────────────────

;; CONDITIONAL: if/switch statements
;; TODO: Add pattern for conditionals

;; LOOP: for/while/foreach statements
;; TODO: Add pattern for loops

;; EXCEPTION: exception handling
;; TODO: Add pattern for try/catch equivalents

;; ── Other ────────────────────────────────────────────────────────────

;; GUARD: type checks and validation
;; TODO: Add pattern for guards/type assertions

;; ASYNC: async/await or futures
;; TODO: Add pattern for async equivalents

;; FORK: threading/multiprocessing
;; TODO: Add pattern for spawn/fork equivalents
```

### Example: Adding Ruby Patterns

```scheme
;; Ruby COV Token Query Patterns

;; OUTPUT: return statements (explicit and implicit)
((return_statement) @output)

;; EMIT: yield statements
((yield_statement) @emit)

;; TRANSFORM: collection methods
((call
  receiver: _ @_recv
  method: (identifier) @name
  (#match? @name "^(map|select|reject|reduce|collect|each_with_index)$"))
 @transform)

;; MUTATE: assignment and mutation methods
((assignment_statement) @mutate)

((call
  receiver: _ @_recv
  method: (identifier) @name
  (#match? @name "^(push|pop|shift|unshift|<<|delete|clear)$"))
 @mutate)

;; FETCH: network and file I/O
((call
  receiver: _ @_recv
  method: (identifier) @name
  (#match? @name "^(get|post|put|delete|open|read|fetch|download)$"))
 @fetch)

;; CONDITIONAL: if/unless/case
((if_statement) @conditional)
((unless_statement) @conditional)
((case_statement) @conditional)

;; LOOP: for/while/loop
((for_statement) @loop)
((while_statement) @loop)
((until_statement) @loop)

;; EXCEPTION: begin/rescue/ensure
((begin_block) @exception)

;; GUARD: type checks
((if_statement
  condition: (call
    method: (identifier) @name
    (#match? @name "^(is_a\\?|kind_of\\?|instance_of\\?)$")))
 @guard)

;; ASYNC: fiber and thread operations
((call
  method: (identifier) @name
  (#match? @name "^(async|await|sleep)$"))
 @async)

;; FORK: threading and multiprocessing
((call
  method: (identifier) @name
  (#match? @name "^(spawn|fork|thread|new)$"))
 @fork)
```

**Tips:**
- Use **exact regex patterns** for method names
- **Test early**: use `tree-sitter query` to validate
- **Start simple**: implement OUTPUT, MUTATE, FETCH first
- **Add comments** explaining what each pattern captures

---

## Step 4: Create Unit Tests

Create `/root/mad/sessions/bgi/tests/test_<lang>_language.py`:

```python
import pytest
from bgi.gate1.fingerprinter import QueryFingerprinter
from bgi.core.types import COVToken

@pytest.fixture
def lang_fingerprinter():
    """Fixture for <Lang> fingerprinter."""
    return QueryFingerprinter("<lang>", "bgi/bgi/gate1/queries/<lang>.scm")

class TestOutputToken:
    def test_return_statement(self, lang_fingerprinter):
        """Test OUTPUT token for return statements."""
        code = """
        # Sample return
        return value
        """
        fingerprint = lang_fingerprinter.fingerprint(code)
        assert COVToken.OUTPUT in fingerprint.tokens

class TestMutateToken:
    def test_assignment(self, lang_fingerprinter):
        """Test MUTATE token for assignments."""
        code = """
        x = 42
        """
        fingerprint = lang_fingerprinter.fingerprint(code)
        assert COVToken.MUTATE in fingerprint.tokens

    def test_mutating_method(self, lang_fingerprinter):
        """Test MUTATE token for method calls."""
        code = """
        arr.push(x)
        """
        fingerprint = lang_fingerprinter.fingerprint(code)
        assert COVToken.MUTATE in fingerprint.tokens

class TestFetchToken:
    def test_http_fetch(self, lang_fingerprinter):
        """Test FETCH token for HTTP requests."""
        code = """
        response = http.get(url)
        """
        fingerprint = lang_fingerprinter.fingerprint(code)
        assert COVToken.FETCH in fingerprint.tokens

class TestTransformToken:
    def test_map_operation(self, lang_fingerprinter):
        """Test TRANSFORM token for map/filter operations."""
        code = """
        result = collection.map { |x| x * 2 }
        """
        fingerprint = lang_fingerprinter.fingerprint(code)
        assert COVToken.TRANSFORM in fingerprint.tokens

class TestConditionalToken:
    def test_if_statement(self, lang_fingerprinter):
        """Test CONDITIONAL token for if statements."""
        code = """
        if condition
          do_something()
        end
        """
        fingerprint = lang_fingerprinter.fingerprint(code)
        assert COVToken.CONDITIONAL in fingerprint.tokens

class TestLoopToken:
    def test_for_loop(self, lang_fingerprinter):
        """Test LOOP token for for loops."""
        code = """
        for item in collection
          process(item)
        end
        """
        fingerprint = lang_fingerprinter.fingerprint(code)
        assert COVToken.LOOP in fingerprint.tokens

class TestExceptionToken:
    def test_try_catch(self, lang_fingerprinter):
        """Test EXCEPTION token for exception handling."""
        code = """
        begin
          risky_operation()
        rescue => e
          handle_error(e)
        end
        """
        fingerprint = lang_fingerprinter.fingerprint(code)
        assert COVToken.EXCEPTION in fingerprint.tokens
```

**Guidance:**
- Write one test per COV token type
- Use realistic code examples
- Test both positive cases (token present) and edge cases
- Run with: `python3 -m pytest tests/test_<lang>_language.py -v`

---

## Step 5: Create Integration Test

Create `/root/mad/sessions/bgi/tests/test_gate1_<lang>.py`:

```python
"""Integration test for Gate 1 with <Language> support."""
import pytest
import os
import tempfile
from pathlib import Path
from bgi.gate1.parallel_scanner import ParallelScanner
from bgi.core.types import COVToken

@pytest.fixture
def lang_repo(tmp_path):
    """Create a temporary <Language> repository."""
    sample_files = {
        "lib/utils.rb": '''
def fetch_user(user_id)
  response = http.get("/users/#{user_id}")
  json = parse(response)
  return json
end
''',
        "lib/processor.rb": '''
def process_items(items)
  result = items.map { |x| x * 2 }
  result.each { |r| puts r }
  return result
end
''',
    }
    
    for file_path, content in sample_files.items():
        file_full_path = tmp_path / file_path
        file_full_path.parent.mkdir(parents=True, exist_ok=True)
        file_full_path.write_text(content)
    
    return tmp_path

def test_gate1_scan_lang_repo(lang_repo):
    """Test Gate 1 scanning <Language> repository."""
    scanner = ParallelScanner(num_workers=1)
    units = scanner.scan(
        str(lang_repo),
        lang="<lang>",
        incremental=False
    )
    
    # Verify units extracted
    assert len(units) > 0, "No units extracted from repository"
    
    # Verify at least one unit has fingerprint
    assert any(u.fingerprint for u in units), "No fingerprints generated"

def test_gate1_lang_token_coverage(lang_repo):
    """Test that key COV tokens are detected."""
    scanner = ParallelScanner(num_workers=1)
    units = scanner.scan(
        str(lang_repo),
        lang="<lang>",
        incremental=False
    )
    
    # Collect all tokens
    all_tokens = set()
    for unit in units:
        if unit.fingerprint:
            all_tokens.update(unit.fingerprint.tokens)
    
    # Verify key tokens are present
    expected_tokens = {
        COVToken.OUTPUT,    # return statement
        COVToken.FETCH,     # http.get
        COVToken.TRANSFORM, # map operation
    }
    
    for expected in expected_tokens:
        assert expected in all_tokens, f"{expected} not detected in repository"
```

---

## Step 6: Validate on Real Code

Test your implementation on a real-world repository:

```bash
cd /root/mad/sessions/bgi

# Clone a sample repo
git clone https://github.com/<user>/<lang>-sample-repo /tmp/test_<lang>_repo

# Run Gate 1 with your new language
python3 -m bgi.pipeline scan /tmp/test_<lang>_repo --lang <lang> --output-dir output/

# Verify results
cat output/units.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    unit = json.loads(line)
    if 'fingerprint' in unit:
        print(f'{unit[\"name\"]}: {unit[\"fingerprint\"][\"tokens\"][:3]}...')
" | head -20
```

**Validation checklist:**
- ✅ No errors or exceptions
- ✅ Units extracted from multiple files
- ✅ Fingerprints include expected COV tokens
- ✅ Token diversity (not just one token type)

---

## Step 7: Submit PR

### File Checklist

- [ ] `bgi/bgi/gate1/queries/<lang>.scm` — Pattern queries
- [ ] `tests/test_<lang>_language.py` — Unit tests
- [ ] `tests/test_gate1_<lang>.py` — Integration test
- [ ] Updated `docs/LANGUAGE_SUPPORT.md` if needed (add language to reference table)

### PR Description Template

```markdown
## Add <Language> Support to BGI

### What
Adds `.scm` query patterns for <Language> to enable single-pass fingerprinting via tree-sitter.

### Coverage
- ✅ OUTPUT (return statements)
- ✅ MUTATE (assignments, mutating methods)
- ✅ FETCH (network/file I/O)
- ✅ TRANSFORM (map/filter/reduce)
- ✅ CONDITIONAL (if/switch)
- ✅ LOOP (for/while)
- ✅ EXCEPTION (try/catch)
- ✅ GUARD (type checks)
- ✅ ASYNC (async/await)
- ✅ FORK (threading/multiprocessing)

### Testing
- 12 unit tests in `tests/test_<lang>_language.py`
- 2 integration tests in `tests/test_gate1_<lang>.py`
- Validated on [sample repo](link)

### Performance
Gate 1 with <Language> support: ~X sec on Y files (X tokens/sec)

### Example
```<lang>
function_example()
```

Closes #XXX
```

---

## Troubleshooting

### Pattern Not Matching?

Debug with:

```bash
# Test pattern in isolation
tree-sitter query --capture bgi/bgi/gate1/queries/<lang>.scm sample.<ext>

# Check AST structure
tree-sitter parse sample.<ext> --quiet | head -50
```

### Fallback Triggered?

Verify the `.scm` file:

```bash
python3 << 'EOF'
from bgi.gate1.lang_registry import LanguageRegistry
reg = LanguageRegistry()
info = reg.get_handler("<lang>")
print(f"Using .scm: {info['scm_file']}")
print(f"Fallback rules: {len(info.get('fallback_rules', []))}")
EOF
```

### Tests Failing?

Run with verbose output:

```bash
python3 -m pytest tests/test_<lang>_language.py -vvs --tb=short
```

---

## Need Help?

- **Questions about .scm format?** See [`docs/LANGUAGE_SUPPORT.md`](LANGUAGE_SUPPORT.md)
- **Tree-sitter documentation?** https://tree-sitter.github.io/tree-sitter/
- **BGI architecture?** See [`README.md`](../README.md)
- **File an issue:** https://github.com/ahmedxuhri/bigindexer/issues

---

## Thank You! 🎉

Your contribution helps BGI support more languages and unlocks behavioral analysis for the broader developer community.
