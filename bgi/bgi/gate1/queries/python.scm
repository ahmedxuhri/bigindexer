;; Python COV Token Query Patterns
;; Tree-sitter query file for extracting COV tokens from Python AST
;; Format: (pattern) @capture_name
;; Captured names are mapped to COV tokens

;; ── Data Flow ────────────────────────────────────────────────────────────────
;; INTAKE: function parameters, argument unpacking
((parameters) @intake)

;; OUTPUT: return statements, yield expressions
((return_statement) @output)
((yield_expression) @output)

;; TRANSFORM: comprehensions, map/filter/reduce calls
((list_comprehension) @transform)
((dict_comprehension) @transform)
((set_comprehension) @transform)
((generator_expression) @transform)

;; MUTATE: assignment to variables or object attributes
((assignment) @mutate)

;; SANITIZE: calls to sanitize, strip, encode, decode functions
((call
  function: (identifier) @name
  (#match? @name "^(sanitize|strip|encode|decode|escape|clean|filter)"))
 @sanitize)

;; ── Control Flow ──────────────────────────────────────────────────────────────
;; CONDITIONAL: if/else statements and ternary
((if_statement) @conditional)

;; LOOP: for/while loops
((for_statement) @loop)
((while_statement) @loop)

;; GUARD: assert statements
((assert_statement) @guard)

;; ROUTE: decorators like @app.route, @router.get, etc.
((decorator
  (call
    function: (attribute
      object: (identifier) @obj
      attribute: (identifier) @attr)
    (#match? @attr "^(route|get|post|put|delete|patch|head|options)$")))
 @route)

;; SCOPE: try/except/finally blocks
((try_statement) @scope)

;; ── State ────────────────────────────────────────────────────────────────────
;; FETCH: calls to get, retrieve, fetch, find, select functions
((call
  function: (identifier) @name
  (#match? @name "^(fetch|get|retrieve|find|select|query|load|read)"))
 @fetch)

;; PERSIST: calls to save, write, create, insert, update, delete functions
((call
  function: (identifier) @name
  (#match? @name "^(save|write|create|insert|update|delete|remove|persist|store)"))
 @persist)

;; ── Communication ────────────────────────────────────────────────────────────
;; EMIT: calls to send, publish, dispatch, emit functions
((call
  function: (identifier) @name
  (#match? @name "^(emit|send|publish|dispatch|broadcast|post|notify)"))
 @emit)

;; SUBSCRIBE: calls to listen, subscribe, register, on, watch functions
((call
  function: (identifier) @name
  (#match? @name "^(subscribe|listen|register|on|watch|observe|handle)"))
 @subscribe)

;; DELEGATE: calls to call, invoke, execute, run functions
((call
  function: (identifier) @name
  (#match? @name "^(delegate|call|invoke|execute|run|do|perform)"))
 @delegate)

;; ── Structure ────────────────────────────────────────────────────────────────
;; CONTRACT: decorators, type hints, assertions
((type_hint) @contract)

;; COMPOSE: function calls chaining or decorators
((decorator) @compose)

;; INIT: __init__ methods and initialization functions
((function_definition
  name: (identifier) @name
  (#match? @name "^(__init__|initialize|init|setup|configure)"))
 @init)

;; TEARDOWN: __del__ methods and cleanup functions
((function_definition
  name: (identifier) @name
  (#match? @name "^(__del__|teardown|cleanup|finalize|dispose)"))
 @teardown)

;; ── Error ────────────────────────────────────────────────────────────────────
;; RAISE: raise statements
((raise_statement) @raise)

;; RECOVER: except clauses
((except_clause) @recover)

;; DEFER: finally blocks
((finally_clause) @defer)

;; ── Cross-cutting ───────────────────────────────────────────────────────────
;; AUTHENTICATE: function/class names with auth-related keywords
((function_definition
  name: (identifier) @name
  (#match? @name "^(authenticate|auth|login|verify|validate_token)"))
 @authenticate)

;; AUTHORIZE: function/class names with authorization keywords
((function_definition
  name: (identifier) @name
  (#match? @name "^(authorize|check_permission|has_role|is_admin)"))
 @authorize)

;; VALIDATE: validation function calls
((call
  function: (identifier) @name
  (#match? @name "^(validate|check|verify|assert_valid)"))
 @validate)

;; LOG: logging function calls
((call
  function: (identifier) @name
  (#match? @name "^(log|print|debug|info|warning|error)"))
 @log)

;; MEASURE: performance/metrics functions
((call
  function: (identifier) @name
  (#match? @name "^(time|measure|profile|metric|benchmark|record)"))
 @measure)

;; ASYNC: async/await keywords
((await_expression) @async)

;; ── Testing ──────────────────────────────────────────────────────────────────
;; TEST: test function definitions
((function_definition
  name: (identifier) @name
  (#match? @name "^test_"))
 @test)
