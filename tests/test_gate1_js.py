"""
Tests for Gate 1 — JavaScript COV fingerprinting.
"""
import textwrap
import pytest
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

from bgi.core.cov import COV
from bgi.gate1.js_scanner import fingerprint_function_js, _collect_js_units, scan_file_js
from bgi.gate1.ai_fallback import AIFallback


# ── Helpers ───────────────────────────────────────────────────────────────────

_JS = Language(tsjs.language())
_PARSER = Parser(_JS)
_NO_AI = AIFallback(enabled=False)


def fingerprints_for(src: str) -> list:
    src = textwrap.dedent(src)
    tree = _PARSER.parse(src.encode())
    units: list = []
    _collect_js_units(tree.root_node, units)
    fps = []
    for kind, node, extra in units:
        if kind == "route":
            fps.append(fingerprint_function_js(node, "test.js", _NO_AI, route_info=extra))
        else:
            fps.append(fingerprint_function_js(node, "test.js", _NO_AI, parent_var_name=extra))
    return fps


def tokens_of(fp) -> list[str]:
    return [str(t) for t in fp.tokens]


def class_tokens_of(fp) -> list[str]:
    return [str(t) for t in fp.class_context]


def _single(src: str) -> list[str]:
    fps = fingerprints_for(src)
    assert len(fps) == 1, f"Expected 1 fingerprint, got {len(fps)}"
    return tokens_of(fps[0])


# ── Tier 1 — AST node types ───────────────────────────────────────────────────

class TestTier1Nodes:
    def test_return_produces_output(self):
        toks = _single("function f() { return 1; }")
        assert "COV.OUTPUT" in toks

    def test_throw_produces_raise(self):
        toks = _single("function f() { throw new Error('x'); }")
        assert "COV.RAISE" in toks

    def test_catch_produces_recover(self):
        toks = _single("function f() { try {} catch(e) {} }")
        assert "COV.RECOVER" in toks

    def test_finally_produces_defer(self):
        toks = _single("function f() { try {} finally {} }")
        assert "COV.DEFER" in toks

    def test_for_of_produces_loop(self):
        toks = _single("function f(xs) { for (const x of xs) {} }")
        assert "COV.LOOP" in toks

    def test_for_in_produces_loop(self):
        toks = _single("function f(obj) { for (const k in obj) {} }")
        assert "COV.LOOP" in toks

    def test_while_produces_loop(self):
        toks = _single("function f() { while (true) { break; } }")
        assert "COV.LOOP" in toks

    def test_if_produces_conditional(self):
        toks = _single("function f(x) { if (x > 0) {} }")
        assert "COV.CONDITIONAL" in toks

    def test_switch_produces_conditional(self):
        toks = _single("function f(x) { switch(x) { case 1: break; } }")
        assert "COV.CONDITIONAL" in toks

    def test_await_produces_async(self):
        toks = _single("async function f() { await something(); }")
        assert "COV.ASYNC" in toks

    def test_augmented_assignment_produces_mutate(self):
        toks = _single("function f() { let x = 0; x += 1; }")
        assert "COV.MUTATE" in toks

    def test_member_assignment_produces_mutate(self):
        toks = _single("function f(obj) { obj.name = 'hi'; }")
        assert "COV.MUTATE" in toks

    def test_yield_produces_emit(self):
        toks = _single("function* gen() { yield 1; }")
        assert "COV.EMIT" in toks


# ── Tier 2 — function name ────────────────────────────────────────────────────

class TestTier2FunctionName:
    def test_constructor_produces_init(self):
        fps = fingerprints_for("""
            class A {
                constructor(x) { this.x = x; }
            }
        """)
        ctor = next(fp for fp in fps if "constructor" in fp.unit_id)
        assert "COV.INIT" in tokens_of(ctor)

    def test_teardown_method_produces_teardown(self):
        fps = fingerprints_for("""
            class Suite {
                tearDown() {}
            }
        """)
        fp = next(fp for fp in fps if "tearDown" in fp.unit_id)
        assert "COV.TEARDOWN" in tokens_of(fp)

    def test_test_prefix_produces_test(self):
        fps = fingerprints_for("""
            class Suite {
                test_should_pass() {}
            }
        """)
        fp = next(fp for fp in fps if "test_should_pass" in fp.unit_id)
        assert "COV.TEST" in tokens_of(fp)


# ── Tier 4 — call targets ─────────────────────────────────────────────────────

class TestTier4CallTarget:
    def test_save_produces_persist(self):
        toks = _single("function f(repo, entity) { repo.save(entity); }")
        assert "COV.PERSIST" in toks

    def test_find_produces_fetch(self):
        toks = _single("function f(repo, id) { return repo.find(id); }")
        assert "COV.FETCH" in toks

    def test_emit_produces_emit(self):
        toks = _single("function f(emitter) { emitter.emit('event', {}); }")
        assert "COV.EMIT" in toks

    def test_console_log_produces_log(self):
        toks = _single("function f(msg) { console.log(msg); }")
        assert "COV.LOG" in toks

    def test_push_produces_mutate(self):
        toks = _single("function f(arr, item) { arr.push(item); }")
        assert "COV.MUTATE" in toks

    def test_map_produces_transform(self):
        toks = _single("function f(arr) { return arr.map(x => x * 2); }")
        assert "COV.TRANSFORM" in toks

    def test_validate_produces_validate(self):
        toks = _single("function f(schema, data) { schema.validate(data); }")
        assert "COV.VALIDATE" in toks


# ── Tier 5 — class heritage ───────────────────────────────────────────────────

class TestTier5Heritage:
    def test_extends_error_in_class_context(self):
        fps = fingerprints_for("""
            class NotFoundError extends Error {
                constructor(msg) { super(msg); }
            }
        """)
        fp = next(fp for fp in fps if "constructor" in fp.unit_id)
        assert "COV.RAISE" in class_tokens_of(fp)

    def test_extends_base_repo_in_class_context(self):
        fps = fingerprints_for("""
            class UserRepo extends BaseRepository {
                find(id) { return null; }
            }
        """)
        fp = next(fp for fp in fps if "find" in fp.unit_id)
        assert "COV.PERSIST" in class_tokens_of(fp)

    def test_class_context_not_in_tokens(self):
        fps = fingerprints_for("""
            class NotFoundError extends Error {
                describe() { return 'not found'; }
            }
        """)
        fp = next(fp for fp in fps if "describe" in fp.unit_id)
        assert "COV.RAISE" not in tokens_of(fp)
        assert "COV.RAISE" in class_tokens_of(fp)


# ── Arrow functions ───────────────────────────────────────────────────────────

class TestArrowFunctions:
    def test_arrow_with_params_produces_intake(self):
        fps = fingerprints_for("const add = (x, y) => x + y;")
        assert len(fps) == 1
        assert "COV.INTAKE" in tokens_of(fps[0])

    def test_arrow_no_params_no_intake(self):
        fps = fingerprints_for("const greet = () => 'hello';")
        assert len(fps) == 1
        assert "COV.INTAKE" not in tokens_of(fps[0])

    def test_arrow_name_from_variable(self):
        fps = fingerprints_for("const fetchUser = async (id) => { await db.get(id); };")
        assert "fetchUser" in fps[0].unit_id

    def test_async_arrow_produces_async(self):
        fps = fingerprints_for("const load = async () => { await fetch('/api'); };")
        assert "COV.ASYNC" in tokens_of(fps[0])


# ── INTAKE detection ──────────────────────────────────────────────────────────

class TestIntake:
    def test_params_produce_intake(self):
        toks = _single("function greet(name) { return name; }")
        assert "COV.INTAKE" in toks

    def test_no_params_no_intake(self):
        toks = _single("function hello() {}")
        assert "COV.INTAKE" not in toks

    def test_rest_param_produces_intake(self):
        toks = _single("function sum(...args) { return args.reduce((a,b) => a+b, 0); }")
        assert "COV.INTAKE" in toks

    def test_destructured_param_produces_intake(self):
        toks = _single("function f({x, y}) { return x + y; }")
        assert "COV.INTAKE" in toks


# ── Deduplication ─────────────────────────────────────────────────────────────

class TestDeduplication:
    def test_no_duplicate_tokens(self):
        toks = _single("""
            function process(items) {
                if (items.length === 0) { throw new Error('empty'); }
                for (const item of items) {}
                return items;
            }
        """)
        assert len(toks) == len(set(toks))

    def test_multi_token_fingerprint(self):
        toks = set(_single("""
            async function fetchAndProcess(id) {
                try {
                    const result = await db.findOne(id);
                    return result;
                } catch (e) {
                    throw e;
                }
            }
        """))
        assert "COV.ASYNC" in toks
        assert "COV.RECOVER" in toks
        assert "COV.OUTPUT" in toks
        assert "COV.RAISE" in toks


# ── Language tag ──────────────────────────────────────────────────────────────

class TestLanguageTag:
    def test_fingerprint_language_is_javascript(self):
        fps = fingerprints_for("function f() { return 1; }")
        assert fps[0].language == "javascript"

    def test_unit_id_uses_js_extension(self):
        fps = fingerprints_for("function f() {}")
        assert fps[0].unit_id.startswith("test.js::")


# ── Generator functions ───────────────────────────────────────────────────────

class TestGeneratorFunctions:
    def test_generator_yield_produces_emit(self):
        toks = _single("function* gen() { yield 1; yield 2; }")
        assert "COV.EMIT" in toks

    def test_generator_name_in_unit_id(self):
        fps = fingerprints_for("function* iterateItems(items) { for (const i of items) yield i; }")
        assert "iterateItems" in fps[0].unit_id


# ── Route detection ───────────────────────────────────────────────────────────

class TestRouteDetection:
    def test_express_get_route_has_route_token(self):
        fps = fingerprints_for("""
            router.get('/users', async (req, res) => {
                const users = await db.findAll();
                res.json(users);
            });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert len(route_fps) >= 1

    def test_express_post_route_unit_id(self):
        fps = fingerprints_for("""
            router.post('/users', async (req, res) => {
                const user = await db.create(req.body);
                res.json(user);
            });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert any("POST:/users" in fp.unit_id for fp in route_fps)

    def test_app_delete_route(self):
        fps = fingerprints_for("""
            app.delete('/users/:id', async (req, res) => {
                await db.remove(req.params.id);
                res.sendStatus(204);
            });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert len(route_fps) >= 1

    def test_route_with_middleware_chain(self):
        fps = fingerprints_for("""
            router.put('/items/:id', authenticate, async (req, res) => {
                await db.update(req.params.id, req.body);
                res.sendStatus(200);
            });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert any("PUT:/items/:id" in fp.unit_id for fp in route_fps)

    def test_non_route_call_ignored(self):
        fps = fingerprints_for("""
            console.get('something');
        """)
        assert len(fps) == 0
