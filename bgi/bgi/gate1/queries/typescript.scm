;; TypeScript/JavaScript COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call target method names).
;; Run scoped to a function/method/arrow node for function-level fingerprinting.
;; Tier 2 (func name), Tier 3 (decorators), Tier 5 (class context) handled separately.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return statements
((return_statement) @output)

;; EMIT: yield expressions (generator emission)
((yield_expression) @emit)

;; TRANSFORM: array/object spread, map/filter/reduce calls
((call_expression
  function: (member_expression
    property: (property_identifier) @name)
  (#match? @name "^(map|filter|reduce|flatMap|forEach|transform|convert|serialize|deserialize)$"))
 @transform)

;; MUTATE: augmented assignment (+=, -=, etc.)
((augmented_assignment_expression) @mutate)

;; MUTATE: assignment where LHS is member_expression (obj.prop = x)
((assignment_expression
  left: (member_expression) @_lhs) @mutate)

;; MUTATE: via method calls
((call_expression
  function: (member_expression
    property: (property_identifier) @name)
  (#match? @name "^(push|pop|shift|unshift|splice|set|delete|clear|update|assign)$"))
 @mutate)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if/else statements, ternary, switch
((if_statement) @conditional)
((ternary_expression) @conditional)
((switch_statement) @conditional)

;; LOOP: all loop forms
((for_statement) @loop)
((for_in_statement) @loop)
((while_statement) @loop)
((do_statement) @loop)

;; GUARD: type assertion/guard function calls
((call_expression
  function: (identifier) @name
  (#match? @name "^(assert|invariant|ok)$"))
 @guard)

;; SCOPE: try/catch/finally blocks
((try_statement) @scope)

;; ── State ────────────────────────────────────────────────────────────────────

;; FETCH: obj.get/find/read/query/fetch/load/retrieve/filter/select
((call_expression
  function: (member_expression
    property: (property_identifier) @name)
  (#match? @name "^(find|findById|findOne|get|read|query|fetch|load|select|filter|all|first|last|retrieve|list|search)$"))
 @fetch)

;; FETCH: standalone fetch() call
((call_expression
  function: (identifier) @name
  (#match? @name "^(fetch|axios)$"))
 @fetch)

;; PERSIST: obj.save/write/create/insert/put/store/upsert/post
((call_expression
  function: (member_expression
    property: (property_identifier) @name)
  (#match? @name "^(save|insert|create|write|persist|store|put|upsert|add|post)$"))
 @persist)

;; ── Communication ────────────────────────────────────────────────────────────

;; EMIT: obj.emit/publish/dispatch/send/broadcast/trigger
((call_expression
  function: (member_expression
    property: (property_identifier) @name)
  (#match? @name "^(emit|publish|dispatch|send|broadcast|trigger|notify)$"))
 @emit)

;; SUBSCRIBE: obj.on/subscribe/listen/addEventListener/register
((call_expression
  function: (member_expression
    property: (property_identifier) @name)
  (#match? @name "^(on|subscribe|listen|addEventListener|addListener|register|watch|observe)$"))
 @subscribe)

;; ── Cross-cutting ────────────────────────────────────────────────────────────

;; VALIDATE: obj.validate/check/verify
((call_expression
  function: (member_expression
    property: (property_identifier) @name)
  (#match? @name "^(validate|check|verify|assert|isValid)$"))
 @validate)

;; LOG: console.log/debug/info/warn/error
((call_expression
  function: (member_expression
    object: (identifier) @obj
    property: (property_identifier) @method)
  (#match? @obj "^(console|logger|log)$"))
 @log)

;; MEASURE: performance.mark/measure, metrics.record etc.
((call_expression
  function: (member_expression
    object: (identifier) @obj
    property: (property_identifier) @method)
  (#match? @obj "^(performance|metrics|statsd|counter|gauge|histogram|telemetry)$"))
 @measure)

;; ── Error ────────────────────────────────────────────────────────────────────

;; RAISE: throw statements
((throw_statement) @raise)

;; RECOVER: catch clauses
((catch_clause) @recover)

;; DEFER: finally clauses
((finally_clause) @defer)

;; ── Async ────────────────────────────────────────────────────────────────────

;; ASYNC: await expressions inside function body
((await_expression) @async)

