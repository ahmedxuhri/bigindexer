"""Tests for the generic regex fallback scanner."""
import textwrap
from pathlib import Path
import tempfile

import pytest

from bgi.gate1.generic_scanner import scan_file_generic, _detect_functions
from bgi.gate1.ai_fallback import AIFallback
from bgi.core.cov import COV


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scan(source: str, language: str = "generic") -> list:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f = root / f"test.{language}"
        f.write_text(textwrap.dedent(source))
        ai = AIFallback()
        return scan_file_generic(f, root, ai, language=language)


# ── Function detection ────────────────────────────────────────────────────────

class TestFunctionDetection:
    def test_swift_func(self):
        src = """\
        func greet(name: String) -> String {
            return "Hello, \\(name)"
        }
        """
        funcs = _detect_functions(textwrap.dedent(src))
        assert any(f.name == "greet" for f in funcs)

    def test_r_function(self):
        src = """\
        add <- function(x, y) {
            return(x + y)
        }
        """
        funcs = _detect_functions(textwrap.dedent(src))
        assert any(f.name == "add" for f in funcs)

    def test_bash_function(self):
        src = """\
        deploy() {
            echo "deploying"
        }
        """
        funcs = _detect_functions(textwrap.dedent(src))
        assert any(f.name == "deploy" for f in funcs)

    def test_bash_function_keyword(self):
        src = """\
        function setup() {
            mkdir -p /tmp/work
        }
        """
        funcs = _detect_functions(textwrap.dedent(src))
        assert any(f.name == "setup" for f in funcs)

    def test_nim_proc(self):
        src = """\
        proc calculate(x: int): int =
          return x * 2
        """
        funcs = _detect_functions(textwrap.dedent(src))
        assert any(f.name == "calculate" for f in funcs)

    def test_zig_fn(self):
        src = """\
        pub fn add(a: i32, b: i32) i32 {
            return a + b;
        }
        """
        funcs = _detect_functions(textwrap.dedent(src))
        assert any(f.name == "add" for f in funcs)

    def test_dart_function(self):
        src = """\
        String greet(String name) {
            return 'Hello $name';
        }
        """
        funcs = _detect_functions(textwrap.dedent(src))
        assert any(f.name == "greet" for f in funcs)

    def test_multiple_functions(self):
        src = """\
        func fetchUser(id: Int) -> User {
            return db.find(id)
        }

        func saveUser(user: User) {
            db.save(user)
        }
        """
        funcs = _detect_functions(textwrap.dedent(src))
        names = {f.name for f in funcs}
        assert "fetchUser" in names
        assert "saveUser" in names


# ── COV token extraction ──────────────────────────────────────────────────────

class TestCOVExtraction:
    def test_output_cov(self):
        fps = _scan("""\
            func getAge() -> Int {
                return self.age
            }
        """, "swift")
        assert fps, "No fingerprints produced"
        tokens = fps[0].tokens
        assert COV.OUTPUT in tokens

    def test_raise_cov(self):
        fps = _scan("""\
            func validate(x: Int) {
                if x < 0 {
                    throw ValueError("negative")
                }
            }
        """, "swift")
        assert fps
        tokens = fps[0].tokens
        assert COV.RAISE in tokens or COV.CONDITIONAL in tokens

    def test_async_cov(self):
        fps = _scan("""\
            func loadData() async {
                await fetch("https://example.com")
            }
        """, "swift")
        assert fps
        tokens = fps[0].tokens
        assert COV.ASYNC in tokens

    def test_loop_cov(self):
        fps = _scan("""\
            func processItems() {
                for item in items {
                    print(item)
                }
            }
        """, "swift")
        assert fps
        tokens = fps[0].tokens
        assert COV.LOOP in tokens

    def test_persist_cov(self):
        fps = _scan("""\
            func saveRecord(record: Record) {
                db.save(record)
                db.commit()
            }
        """, "swift")
        assert fps
        tokens = fps[0].tokens
        assert COV.PERSIST in tokens

    def test_fetch_cov(self):
        fps = _scan("""\
            func findUser(id: Int) -> User {
                return db.find(id)
            }
        """, "swift")
        assert fps
        tokens = fps[0].tokens
        assert COV.FETCH in tokens

    def test_intake_when_params_present(self):
        fps = _scan("""\
            func greet(name: String) {
                print(name)
            }
        """, "swift")
        assert fps
        assert COV.INTAKE in fps[0].tokens

    def test_no_intake_when_no_params(self):
        fps = _scan("""\
            func run() {
                print("running")
            }
        """, "swift")
        assert fps
        assert COV.INTAKE not in fps[0].tokens


# ── Tier 2 name heuristics ────────────────────────────────────────────────────

class TestNameHeuristics:
    def test_init_name(self):
        fps = _scan("""\
            func initialize() {
                setup()
            }
        """, "swift")
        assert fps
        assert COV.INIT in fps[0].tokens

    def test_teardown_name(self):
        fps = _scan("""\
            func cleanup() {
                db.close()
            }
        """, "swift")
        assert fps
        assert COV.TEARDOWN in fps[0].tokens

    def test_test_name(self):
        fps = _scan("""\
            func testAddition() {
                assert(1 + 1 == 2)
            }
        """, "swift")
        assert fps
        assert COV.TEST in fps[0].tokens


# ── Fingerprint metadata ──────────────────────────────────────────────────────

class TestFingerprintMetadata:
    def test_unit_id_format(self):
        fps = _scan("""\
            func myFunc() {
                return 42
            }
        """, "swift")
        assert fps
        assert "myFunc" in fps[0].unit_id

    def test_language_recorded(self):
        fps = _scan("""\
            func myFunc() {
                return 42
            }
        """, "swift")
        assert fps
        assert fps[0].language == "swift"

    def test_line_range_set(self):
        fps = _scan("""\
            func myFunc() {
                return 42
            }
        """, "swift")
        assert fps
        lr = fps[0].line_range
        assert lr is not None
        assert lr[0] >= 1

    def test_r_language(self):
        fps = _scan("""\
            compute <- function(x, y) {
                return(x + y)
            }
        """, "r")
        assert fps
        assert fps[0].language == "r"
        assert COV.INTAKE in fps[0].tokens
        assert COV.OUTPUT in fps[0].tokens


# ── Enhancement 1: string/comment stripping ───────────────────────────────────

class TestBodyCleaning:
    def test_string_literal_not_cov(self):
        """Keywords inside string literals must not trigger COV tokens."""
        fps = _scan("""\
            func describe() -> String {
                return "use fetch to get data if needed"
            }
        """, "swift")
        assert fps
        # "fetch", "if" are inside a string literal — should NOT fire FETCH/CONDITIONAL
        # "return" is real code — OUTPUT should fire
        assert COV.OUTPUT in fps[0].tokens
        assert COV.FETCH not in fps[0].tokens
        assert COV.CONDITIONAL not in fps[0].tokens

    def test_comment_not_cov(self):
        """Keywords inside line comments must not trigger COV tokens."""
        fps = _scan("""\
            func compute(x: Int) -> Int {
                // if x is negative, raise an error and catch it
                return x * 2
            }
        """, "swift")
        assert fps
        tokens = fps[0].tokens
        assert COV.OUTPUT in tokens
        # if/raise/catch in comment — should not fire
        assert COV.CONDITIONAL not in tokens
        assert COV.RAISE not in tokens
        assert COV.RECOVER not in tokens

    def test_real_code_still_fires(self):
        """Real COV keywords in actual code must still fire after cleaning."""
        fps = _scan("""\
            func loadUser(id: Int) throws -> User {
                if id <= 0 {
                    throw InvalidIDError()
                }
                return db.fetch(id)
            }
        """, "swift")
        assert fps
        tokens = fps[0].tokens
        assert COV.CONDITIONAL in tokens
        assert COV.RAISE in tokens
        assert COV.OUTPUT in tokens


# ── Enhancement 2: class context tracking ────────────────────────────────────

class TestClassContext:
    def test_method_gets_class_prefix(self):
        """Methods inside a class should have ClassName::method unit_id."""
        fps = _scan("""\
            class UserService {
                func findUser(id: Int) -> User {
                    return db.find(id)
                }
            }
        """, "swift")
        assert fps
        assert any("UserService" in fp.unit_id for fp in fps)

    def test_method_class_context_field(self):
        fps = _scan("""\
            class AuthManager {
                func login(user: String) -> Bool {
                    return verify(user)
                }
            }
        """, "swift")
        assert fps
        fp = next(f for f in fps if "login" in f.unit_id)
        assert fp.class_context == ["AuthManager"]

    def test_top_level_function_no_class(self):
        fps = _scan("""\
            func helperFunc() -> Int {
                return 42
            }
        """, "swift")
        assert fps
        fp = fps[0]
        assert fp.class_context == []
        assert "helperFunc" in fp.unit_id
        assert "::" in fp.unit_id
        # Should NOT have a spurious class prefix
        parts = fp.unit_id.split("::")
        assert parts[-1] == "helperFunc"

    def test_python_class_method(self):
        fps = _scan("""\
            class Calculator:
                def add(self, a, b):
                    return a + b
        """, "python")
        assert fps
        fp = fps[0]
        assert "Calculator" in fp.unit_id
        assert "add" in fp.unit_id


# ── Enhancement 3: token capping ─────────────────────────────────────────────

class TestTokenCapping:
    def test_max_tokens_not_exceeded(self):
        """No fingerprint should have more than MAX_COV_TOKENS tokens."""
        from bgi.gate1.generic_scanner import MAX_COV_TOKENS
        # A function body that would trigger many keywords if uncapped
        fps = _scan("""\
            func doEverything(data: Data) throws -> Result {
                if data.isEmpty { throw DataError() }
                for item in data { log(item) }
                let result = fetch(data)
                save(result)
                return result
            }
        """, "swift")
        assert fps
        assert len(fps[0].tokens) <= MAX_COV_TOKENS

    def test_high_specificity_tokens_kept(self):
        """When capping, higher-specificity tokens should be retained."""
        from bgi.gate1.generic_scanner import MAX_COV_TOKENS
        fps = _scan("""\
            func handleEvent(data: Data) throws -> Result {
                defer { cleanup() }
                if data.isEmpty { throw DataError() }
                for item in data { process(item) }
                let result = fetch(data)
                save(result)
                return result
            }
        """, "swift")
        assert fps
        tokens = fps[0].tokens
        assert len(tokens) <= MAX_COV_TOKENS
        # DEFER (specificity 9) and RAISE (7) should survive over CONDITIONAL (3)
        assert COV.DEFER in tokens or COV.RAISE in tokens

class TestEdgeCases:
    def test_empty_file(self):
        fps = _scan("", "swift")
        assert fps == []

    def test_no_functions(self):
        fps = _scan("let x = 42\nlet y = x + 1\n", "swift")
        assert fps == []

    def test_keyword_not_function_name(self):
        funcs = _detect_functions("if condition {\n  doSomething()\n}\n")
        # 'if' should not be detected as a function name
        assert not any(f.name in {"if", "for", "while"} for f in funcs)

    def test_short_name_skipped(self):
        # Single-letter names should be filtered out as likely false positives
        funcs = _detect_functions("f() {\n  return 1\n}\n")
        assert not any(len(f.name) < 2 for f in funcs)
