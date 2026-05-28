;; Rust COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call/method target names).
;; Scoped to a function/method body.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return expressions
((return_expression) @output)

;; MUTATE: variable assignments (structural mutation)
((assignment_expression) @mutate)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if/match expressions
((if_expression) @conditional)
((match_expression) @conditional)

;; LOOP: for/while/loop expressions
((for_expression) @loop)
((while_expression) @loop)
((loop_expression) @loop)

;; ── Error ────────────────────────────────────────────────────────────────────

;; RECOVER: try expressions (e.g. expr?)
((try_expression) @recover)

;; ── Async ────────────────────────────────────────────────────────────────────

;; ASYNC: await expression
((await_expression) @async)

;; ── Call and Method Expressions (Tier 4) ──────────────────────────────────────

;; Method call expression (represented as call_expression on field_expression)
((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|find_one|find_all|find_by)$"))
 @fetch)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(on|subscribe|listen|poll_next)$"))
 @subscribe)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse|into|from)$"))
 @transform)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch|insert)$"))
 @mutate)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(validate|check|ensure|verify|assert)$"))
 @validate)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(panic|bail)$"))
 @raise)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(recover|or_else|unwrap_or_else)$"))
 @recover)

((call_expression
  function: (field_expression
    field: (field_identifier) @name)
  (#match? @name "(?i)^(spawn|spawn_blocking)$"))
 @async)

;; Scoped/field call/function call (identifier, scoped_identifier, field_expression)
((call_expression
  function: (identifier) @name
  (#match? @name "(?i)^(panic|bail)$"))
 @raise)

((call_expression
  function: (identifier) @name
  (#match? @name "(?i)^(spawn|spawn_blocking)$"))
 @async)

((call_expression
  function: (scoped_identifier
    name: (identifier) @name)
  (#match? @name "(?i)^(panic|bail)$"))
 @raise)

((call_expression
  function: (scoped_identifier
    name: (identifier) @name)
  (#match? @name "(?i)^(spawn|spawn_blocking)$"))
 @async)

((call_expression
  function: (generic_function
    function: (identifier) @name)
  (#match? @name "(?i)^(panic|bail)$"))
 @raise)

;; Logging and telemetry based on object prefix
((call_expression
  function: (field_expression
    value: (identifier) @obj)
  (#match? @obj "(?i)^(log|logger|tracing)$"))
 @log)

((call_expression
  function: (field_expression
    value: (identifier) @obj)
  (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$"))
 @measure)
