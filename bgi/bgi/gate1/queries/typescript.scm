;; TypeScript/JavaScript COV Token Query Patterns
;; Tree-sitter query file for extracting COV tokens from TypeScript/JavaScript AST

;; ── Data Flow ────────────────────────────────────────────────────────────────
;; INTAKE: function parameters
((formal_parameters) @intake)

;; OUTPUT: return statements
((return_statement) @output)

;; TRANSFORM: array/object destructuring, map/filter/reduce
((array_pattern) @transform)
((object_pattern) @transform)
((call_expression
  function: (identifier) @name
  (#match? @name "^(map|filter|reduce|flatMap)$"))
 @transform)

;; MUTATE: variable/property assignments
((assignment_expression) @mutate)

;; SANITIZE: sanitization/encoding functions
((call_expression
  function: (identifier) @name
  (#match? @name "^(sanitize|escape|encode|decode|clean|filter)$"))
 @sanitize)

;; ── Control Flow ──────────────────────────────────────────────────────────────
;; CONDITIONAL: if/else statements and ternary
((if_statement) @conditional)
((ternary_expression) @conditional)

;; LOOP: for/while/do-while loops
((for_statement) @loop)
((for_in_statement) @loop)
((for_of_statement) @loop)
((while_statement) @loop)
((do_statement) @loop)

;; GUARD: type guards and assertions
((call_expression
  function: (identifier) @name
  (#match? @name "^(assert|check)"))
 @guard)

;; ROUTE: decorators and method names for routing
((decorator
  (identifier) @name
  (#match? @name "^(route|get|post|put|delete|patch)$"))
 @route)

;; SCOPE: try/catch/finally blocks
((try_statement) @scope)

;; ── State ────────────────────────────────────────────────────────────────────
;; FETCH: fetch/get/retrieve calls
((call_expression
  function: (identifier) @name
  (#match? @name "^(fetch|get|retrieve|find|select|query|load|read)$"))
 @fetch)

;; PERSIST: save/write/create calls
((call_expression
  function: (identifier) @name
  (#match? @name "^(save|write|create|insert|update|delete|remove|store)$"))
 @persist)

;; ── Communication ────────────────────────────────────────────────────────────
;; EMIT: event emission and publishing
((call_expression
  function: (identifier) @name
  (#match? @name "^(emit|send|publish|dispatch|broadcast|notify)$"))
 @emit)

;; SUBSCRIBE: event subscription and listening
((call_expression
  function: (identifier) @name
  (#match? @name "^(subscribe|listen|register|on|watch|observe)$"))
 @subscribe)

;; DELEGATE: function delegation and invocation
((call_expression
  function: (identifier) @name
  (#match? @name "^(delegate|call|invoke|execute|run|perform)$"))
 @delegate)

;; ── Structure ────────────────────────────────────────────────────────────────
;; CONTRACT: type annotations and interfaces
((type_annotation) @contract)
((interface_declaration) @contract)

;; COMPOSE: higher-order functions and decorators
((decorator) @compose)

;; INIT: constructor methods and initialization
((method_definition
  name: (property_identifier) @name
  (#match? @name "^(constructor|initialize|init|setup)$"))
 @init)

;; TEARDOWN: cleanup methods
((method_definition
  name: (property_identifier) @name
  (#match? @name "^(teardown|cleanup|finalize|destroy)$"))
 @teardown)

;; ── Error ────────────────────────────────────────────────────────────────────
;; RAISE: throw statements
((throw_statement) @raise)

;; RECOVER: catch clauses
((catch_clause) @recover)

;; DEFER: finally clauses
((finally_clause) @defer)

;; ── Cross-cutting ───────────────────────────────────────────────────────────
;; AUTHENTICATE: authentication-related functions
((function_declaration
  name: (identifier) @name
  (#match? @name "^(authenticate|auth|login|verify)$"))
 @authenticate)

;; AUTHORIZE: authorization-related functions
((function_declaration
  name: (identifier) @name
  (#match? @name "^(authorize|checkPermission|hasRole|isAdmin)$"))
 @authorize)

;; VALIDATE: validation functions
((call_expression
  function: (identifier) @name
  (#match? @name "^(validate|check|verify)$"))
 @validate)

;; LOG: logging functions
((call_expression
  function: (identifier) @name
  (#match? @name "^(log|debug|info|warn|error)$"))
 @log)

;; MEASURE: performance measurement
((call_expression
  function: (identifier) @name
  (#match? @name "^(time|measure|profile|benchmark|record)$"))
 @measure)

;; ASYNC: async/await
((await_expression) @async)
((async_function_declaration) @async)

;; ── Testing ──────────────────────────────────────────────────────────────────
;; TEST: test definitions
((call_expression
  function: (identifier) @name
  (#match? @name "^(test|it|describe)$"))
 @test)
