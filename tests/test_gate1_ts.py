"""
Tests for Gate 1 — TypeScript COV fingerprinting.
"""
import textwrap
import pytest
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

from bgi.core.cov import COV
from bgi.gate1.typescript_rules import (
    apply_tier1, apply_tier2, apply_tier3, apply_tier4, apply_tier5,
)
from bgi.gate1.ts_scanner import fingerprint_function_ts, _collect_ts_units, scan_file_ts
from bgi.gate1.ai_fallback import AIFallback


# ── Helpers ──────────────────────────────────────────────────────────────────

_TS = Language(tsts.language_typescript())
_PARSER = Parser(_TS)
_NO_AI = AIFallback(enabled=False)


def fingerprints_for(src: str) -> list:
    src = textwrap.dedent(src)
    tree = _PARSER.parse(src.encode())
    units: list = []
    _collect_ts_units(tree.root_node, units)
    fps = []
    for kind, node, extra in units:
        if kind == "interface":
            from bgi.gate1.ts_scanner import _fingerprint_interface
            fps.append(_fingerprint_interface(node, "test.ts"))
        elif kind == "route":
            fps.append(fingerprint_function_ts(node, "test.ts", _NO_AI, route_info=extra))
        else:
            fps.append(fingerprint_function_ts(node, "test.ts", _NO_AI, parent_var_name=extra))
    return fps


def tokens_of(fp) -> list[str]:
    return [str(t) for t in fp.tokens]


def class_tokens_of(fp) -> list[str]:
    return [str(t) for t in fp.class_context]


def _single(src: str) -> list[str]:
    fps = fingerprints_for(src)
    assert len(fps) == 1, f"Expected 1 fingerprint, got {len(fps)}: {[fp.unit_id for fp in fps]}"
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
        toks = _single("function f(xs: number[]) { for (const x of xs) {} }")
        assert "COV.LOOP" in toks

    def test_for_in_produces_loop(self):
        toks = _single("function f(obj: any) { for (const k in obj) {} }")
        assert "COV.LOOP" in toks

    def test_classic_for_produces_loop(self):
        toks = _single("function f() { for (let i=0; i<10; i++) {} }")
        assert "COV.LOOP" in toks

    def test_while_produces_loop(self):
        toks = _single("function f() { while (true) { break; } }")
        assert "COV.LOOP" in toks

    def test_if_produces_conditional(self):
        toks = _single("function f(x: number) { if (x > 0) {} }")
        assert "COV.CONDITIONAL" in toks

    def test_switch_produces_conditional(self):
        toks = _single("function f(x: number) { switch(x) { case 1: break; } }")
        assert "COV.CONDITIONAL" in toks

    def test_await_produces_async(self):
        toks = _single("async function f() { await something(); }")
        assert "COV.ASYNC" in toks

    def test_augmented_assignment_produces_mutate(self):
        toks = _single("function f() { let x = 0; x += 1; }")
        assert "COV.MUTATE" in toks

    def test_member_assignment_produces_mutate(self):
        toks = _single("function f(obj: any) { obj.name = 'hi'; }")
        assert "COV.MUTATE" in toks

    def test_plain_assignment_no_mutate(self):
        toks = _single("function f() { const x = 1; }")
        assert "COV.MUTATE" not in toks

    def test_yield_produces_emit(self):
        toks = _single("function* gen() { yield 1; }")
        assert "COV.EMIT" in toks


# ── Tier 2 — function name ────────────────────────────────────────────────────

class TestTier2FunctionName:
    def test_constructor_produces_init(self):
        fps = fingerprints_for("""
            class A {
                constructor(private x: number) {}
            }
        """)
        ctor = next(fp for fp in fps if "constructor" in fp.unit_id)
        assert "COV.INIT" in tokens_of(ctor)

    def test_ngOnDestroy_produces_teardown(self):
        fps = fingerprints_for("""
            class MyComp {
                ngOnDestroy() {}
            }
        """)
        fp = next(fp for fp in fps if "ngOnDestroy" in fp.unit_id)
        assert "COV.TEARDOWN" in tokens_of(fp)

    def test_ngOnInit_produces_init(self):
        fps = fingerprints_for("""
            class MyComp {
                ngOnInit() {}
            }
        """)
        fp = next(fp for fp in fps if "ngOnInit" in fp.unit_id)
        assert "COV.INIT" in tokens_of(fp)

    def test_beforeEach_produces_init(self):
        fps = fingerprints_for("""
            class Suite {
                beforeEach() {}
            }
        """)
        fp = next(fp for fp in fps if "beforeEach" in fp.unit_id)
        assert "COV.INIT" in tokens_of(fp)

    def test_afterAll_produces_teardown(self):
        fps = fingerprints_for("""
            class Suite {
                afterAll() {}
            }
        """)
        fp = next(fp for fp in fps if "afterAll" in fp.unit_id)
        assert "COV.TEARDOWN" in tokens_of(fp)


# ── Tier 3 — decorators ───────────────────────────────────────────────────────

class TestTier3Decorator:
    def test_get_decorator_produces_route(self):
        result = apply_tier3("@Get('/users')")
        toks = [t for t, _ in result]
        assert COV.ROUTE in toks

    def test_controller_decorator_produces_route(self):
        result = apply_tier3("@Controller('api')")
        toks = [t for t, _ in result]
        assert COV.ROUTE in toks

    def test_injectable_produces_contract(self):
        result = apply_tier3("@Injectable()")
        toks = [t for t, _ in result]
        assert COV.CONTRACT in toks

    def test_use_guards_produces_authenticate(self):
        result = apply_tier3("@UseGuards(JwtAuthGuard)")
        toks = [t for t, _ in result]
        assert COV.AUTHENTICATE in toks

    def test_component_decorator_produces_contract(self):
        result = apply_tier3("@Component({ selector: 'app-root' })")
        toks = [t for t, _ in result]
        assert COV.CONTRACT in toks

    def test_retry_decorator_produces_recover(self):
        result = apply_tier3("@Retry({ maxAttempts: 3 })")
        toks = [t for t, _ in result]
        assert COV.RECOVER in toks

    def test_transactional_decorator_produces_scope(self):
        result = apply_tier3("@Transactional()")
        toks = [t for t, _ in result]
        assert COV.SCOPE in toks


# ── Tier 4 — call targets ─────────────────────────────────────────────────────

class TestTier4CallTarget:
    def _call_node(self, src: str):
        tree = _PARSER.parse(src.encode())
        def find_call(n):
            if n.type == "call_expression":
                return n
            for c in n.children:
                r = find_call(c)
                if r: return r
            return None
        return find_call(tree.root_node)

    def test_save_produces_persist(self):
        node = self._call_node("repo.save(entity)")
        toks = [t for t, _ in apply_tier4(node)]
        assert COV.PERSIST in toks

    def test_findOne_produces_fetch(self):
        node = self._call_node("repo.findOne(id)")
        toks = [t for t, _ in apply_tier4(node)]
        assert COV.FETCH in toks

    def test_emit_produces_emit(self):
        node = self._call_node("emitter.emit('event', data)")
        toks = [t for t, _ in apply_tier4(node)]
        assert COV.EMIT in toks

    def test_console_log_produces_log(self):
        node = self._call_node("console.log('msg')")
        toks = [t for t, _ in apply_tier4(node)]
        assert COV.LOG in toks

    def test_push_produces_mutate(self):
        node = self._call_node("arr.push(item)")
        toks = [t for t, _ in apply_tier4(node)]
        assert COV.MUTATE in toks

    def test_validate_produces_validate(self):
        node = self._call_node("schema.validate(data)")
        toks = [t for t, _ in apply_tier4(node)]
        assert COV.VALIDATE in toks

    def test_map_produces_transform(self):
        node = self._call_node("arr.map(fn)")
        toks = [t for t, _ in apply_tier4(node)]
        assert COV.TRANSFORM in toks


# ── Tier 5 — class heritage ───────────────────────────────────────────────────

class TestTier5Heritage:
    def test_implements_repository_in_class_context(self):
        fps = fingerprints_for("""
            class UserRepo implements Repository {
                find(id: number) { return null; }
            }
        """)
        fp = next(fp for fp in fps if "find" in fp.unit_id)
        assert "COV.PERSIST" in class_tokens_of(fp)

    def test_extends_error_in_class_context(self):
        fps = fingerprints_for("""
            class NotFoundError extends Error {
                constructor(msg: string) { super(msg); }
            }
        """)
        fp = next(fp for fp in fps if "constructor" in fp.unit_id)
        assert "COV.RAISE" in class_tokens_of(fp)

    def test_implements_can_activate_in_class_context(self):
        fps = fingerprints_for("""
            class AuthGuard implements CanActivate {
                canActivate() { return true; }
            }
        """)
        fp = next(fp for fp in fps if "canActivate" in fp.unit_id)
        assert "COV.AUTHENTICATE" in class_tokens_of(fp)

    def test_class_context_not_in_tokens(self):
        fps = fingerprints_for("""
            class NotFoundError extends Error {
                describe() { return 'not found'; }
            }
        """)
        fp = next(fp for fp in fps if "describe" in fp.unit_id)
        assert "COV.RAISE" not in tokens_of(fp)
        assert "COV.RAISE" in class_tokens_of(fp)

    def test_injectable_class_decorator_in_context(self):
        fps = fingerprints_for("""
            @Injectable()
            class UserService {
                findUser(id: number) {}
            }
        """)
        fp = next(fp for fp in fps if "findUser" in fp.unit_id)
        assert "COV.CONTRACT" in class_tokens_of(fp)


# ── Interface as CONTRACT unit ────────────────────────────────────────────────

class TestInterfaceUnit:
    def test_interface_produces_contract_fingerprint(self):
        fps = fingerprints_for("""
            interface UserRepository {
                save(user: User): Promise<User>;
                find(id: number): Promise<User | null>;
            }
        """)
        assert len(fps) == 1
        assert "COV.CONTRACT" in tokens_of(fps[0])

    def test_interface_unit_id_contains_name(self):
        fps = fingerprints_for("""
            interface PaymentGateway {
                charge(amount: number): boolean;
            }
        """)
        assert "PaymentGateway" in fps[0].unit_id

    def test_interface_language_is_typescript(self):
        fps = fingerprints_for("interface Foo { bar(): void; }")
        assert fps[0].language == "typescript"


# ── Arrow functions ───────────────────────────────────────────────────────────

class TestArrowFunctions:
    def test_arrow_with_params_produces_intake(self):
        fps = fingerprints_for("const add = (x: number, y: number) => x + y;")
        assert len(fps) == 1
        assert "COV.INTAKE" in tokens_of(fps[0])

    def test_arrow_no_params_no_intake(self):
        fps = fingerprints_for("const greet = () => 'hello';")
        assert len(fps) == 1
        assert "COV.INTAKE" not in tokens_of(fps[0])

    def test_arrow_name_from_variable(self):
        fps = fingerprints_for("const fetchUser = async (id: number) => { await db.get(id); };")
        assert "fetchUser" in fps[0].unit_id

    def test_async_arrow_produces_async(self):
        fps = fingerprints_for("const load = async () => { await fetch('/api'); };")
        assert "COV.ASYNC" in tokens_of(fps[0])


# ── INTAKE detection ──────────────────────────────────────────────────────────

class TestIntake:
    def test_typed_params_produce_intake(self):
        toks = _single("function greet(name: string): string { return name; }")
        assert "COV.INTAKE" in toks

    def test_no_params_no_intake(self):
        toks = _single("function hello(): void {}")
        assert "COV.INTAKE" not in toks

    def test_this_param_only_no_intake(self):
        # TypeScript allows explicit `this` typing — should not count as INTAKE
        toks = _single("function f(this: Window): void {}")
        assert "COV.INTAKE" not in toks


# ── Deduplication ─────────────────────────────────────────────────────────────

class TestDeduplication:
    def test_no_duplicate_tokens(self):
        toks = _single("""
            function process(items: string[]) {
                if (items.length === 0) { throw new Error('empty'); }
                for (const item of items) {}
                return items;
            }
        """)
        assert len(toks) == len(set(toks))

    def test_multi_token_fingerprint(self):
        toks = set(_single("""
            async function fetchAndProcess(id: number) {
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
        assert "COV.FETCH" in toks


# ── Language tag ──────────────────────────────────────────────────────────────

class TestLanguageTag:
    def test_fingerprint_language_is_typescript(self):
        fps = fingerprints_for("function f() { return 1; }")
        assert fps[0].language == "typescript"

    def test_unit_id_uses_ts_extension(self):
        fps = fingerprints_for("function f() {}")
        assert fps[0].unit_id.startswith("test.ts::")


# ── Route detection ───────────────────────────────────────────────────────────

class TestRouteDetection:
    def test_express_get_route_has_route_token(self):
        fps = fingerprints_for("""
            router.get('/users', async (req: Request, res: Response) => {
                const users = await db.findAll();
                res.json(users);
            });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert len(route_fps) >= 1

    def test_express_post_route_unit_id(self):
        fps = fingerprints_for("""
            router.post('/users', async (req: Request, res: Response) => {
                const user = await db.create(req.body);
                res.json(user);
            });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert any("POST:/users" in fp.unit_id for fp in route_fps)

    def test_express_route_with_middleware_chain(self):
        fps = fingerprints_for("""
            router.put('/users/:id', authenticate, authorize, async (req, res) => {
                await db.update(req.params.id, req.body);
                res.sendStatus(204);
            });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert len(route_fps) >= 1
        assert any("PUT:/users/:id" in fp.unit_id for fp in route_fps)

    def test_app_delete_route(self):
        fps = fingerprints_for("""
            app.delete('/users/:id', async (req: Request, res: Response) => {
                await db.remove(req.params.id);
                res.sendStatus(204);
            });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert len(route_fps) >= 1

    def test_express_route_body_tokens_preserved(self):
        toks = set(tokens_of(fingerprints_for("""
            router.get('/data', async (req, res) => {
                try {
                    const data = await db.find();
                    res.json(data);
                } catch (e) {
                    throw e;
                }
            });
        """)[0]))
        assert "COV.ROUTE" in toks
        assert "COV.FETCH" in toks     # db.find()
        assert "COV.RECOVER" in toks   # catch

    def test_express_dynamic_path_placeholder(self):
        fps = fingerprints_for("""
            const PATH = '/dynamic';
            router.get(PATH, (req, res) => { res.send('ok'); });
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert len(route_fps) >= 1
        assert any("<dynamic>" in fp.unit_id for fp in route_fps)

    def test_non_route_call_not_collected(self):
        fps = fingerprints_for("""
            promise.get('/url').then(data => console.log(data));
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert len(route_fps) == 0

    def test_nestjs_get_decorator_still_works(self):
        fps = fingerprints_for("""
            @Controller('/api')
            class UserController {
                @Get('/users')
                async listUsers(): Promise<User[]> {
                    return this.userService.findAll();
                }
            }
        """)
        route_fps = [fp for fp in fps if "COV.ROUTE" in tokens_of(fp)]
        assert len(route_fps) >= 1
