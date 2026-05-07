;; Python COV Token Query Patterns — WATER-CLOCK (single-pass fingerprinting)
;; Covers Tier 1 (AST structure) and Tier 4 (call target method names).
;; Run scoped to a function_definition node for function-level fingerprinting.
;; Tier 2 (func name), Tier 3 (decorators), Tier 5 (class context) handled separately.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return statements
((return_statement) @output)

;; EMIT: yield and yield_from (generator emission)
((yield) @emit)

;; TRANSFORM: comprehensions and generator expressions
((list_comprehension) @transform)
((dictionary_comprehension) @transform)
((set_comprehension) @transform)
((generator_expression) @transform)

;; MUTATE: augmented assignment (+=, -=, etc.) — always MUTATE
((augmented_assignment) @mutate)

;; MUTATE: regular assignment where LHS is attribute or subscript
((assignment
  left: (attribute) @_lhs) @mutate)

((assignment
  left: (subscript) @_lhs) @mutate)

;; MUTATE: via method calls (obj.update/append/pop etc.)
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(update|append|extend|remove|pop|delete|clear|setdefault|discard|insert)$"))
 @mutate)

;; SANITIZE: sanitization/encoding functions
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(sanitize|escape|clean|strip)$"))
 @sanitize)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if/elif/match statements
((if_statement) @conditional)
((elif_clause) @conditional)
((match_statement) @conditional)

;; LOOP: for and while loops
((for_statement) @loop)
((while_statement) @loop)

;; GUARD: assert statements
((assert_statement) @guard)

;; SCOPE: with statements (resource/transaction scope)
((with_statement) @scope)

;; ── State ────────────────────────────────────────────────────────────────────

;; FETCH: obj.get/find/read/query/fetch/load/retrieve/filter/select/all etc.
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(find|get|read|query|fetch|load|select|filter|all|first|last|retrieve|list)$"))
 @fetch)

;; PERSIST: obj.save/write/create/insert/put/store/dump/export etc.
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(save|insert|create|write|persist|add|put|store|dump|export)$"))
 @persist)

;; ── Communication ────────────────────────────────────────────────────────────

;; EMIT: obj.emit/send/publish/dispatch/broadcast/trigger
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(emit|publish|dispatch|send|broadcast|trigger)$"))
 @emit)

;; SUBSCRIBE: obj.on/subscribe/listen/attach/connect/register
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(on|subscribe|listen|attach|connect|register)$"))
 @subscribe)

;; ── Cross-cutting ────────────────────────────────────────────────────────────

;; VALIDATE: obj.validate/check/ensure/verify
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(validate|check|ensure|verify|assert_valid)$"))
 @validate)

;; TRANSFORM: obj.map/transform/convert/serialize/deserialize/encode/decode
((call
  function: (attribute
    attribute: (identifier) @name)
  (#match? @name "^(map|transform|convert|project|serialize|deserialize|encode|decode)$"))
 @transform)

;; LOG: logger.info/debug/warning/error/critical
((call
  function: (attribute
    object: (identifier) @obj
    attribute: (identifier) @method)
  (#match? @obj "^(logging|logger|log|LOG)$"))
 @log)

;; MEASURE: metrics.record/gauge/counter/histogram etc.
((call
  function: (attribute
    object: (identifier) @obj
    attribute: (identifier) @method)
  (#match? @obj "^(metrics|statsd|counter|gauge|histogram|timer|telemetry)$"))
 @measure)

;; ── Error ────────────────────────────────────────────────────────────────────

;; RAISE: raise statements
((raise_statement) @raise)

;; RECOVER: except clauses
((except_clause) @recover)

;; DEFER: finally blocks
((finally_clause) @defer)

;; ── Async ────────────────────────────────────────────────────────────────────

;; ASYNC: await expressions inside function body
((await) @async)

