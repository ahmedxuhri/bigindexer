;; C# COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call/method target names).
;; Scoped to a function/method/constructor body.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return statements
((return_statement) @output)

;; EMIT: yield statements
((yield_statement) @emit)

;; MUTATE: assignments where LHS is member access (obj.prop = x)
((assignment_expression
  left: (member_access_expression)) @mutate)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if/switch statements
((if_statement) @conditional)
((switch_statement) @conditional)

;; LOOP: while, for, foreach, do/while statements
((while_statement) @loop)
((for_statement) @loop)
((foreach_statement) @loop)
((do_statement) @loop)

;; ── Error ────────────────────────────────────────────────────────────────────

;; RAISE: throw statements
((throw_statement) @raise)

;; RECOVER: catch clauses
((catch_clause) @recover)

;; DEFER: finally clauses
((finally_clause) @defer)

;; ── Async ────────────────────────────────────────────────────────────────────

;; ASYNC: await expression
((await_expression) @async)

;; ── Call and Method Expressions (Tier 4) ──────────────────────────────────────

;; Standard function calls (identifier)
((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby)$"))
 @fetch)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(on|subscribe|listen|addlistener)$"))
 @subscribe)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|assertvalid)$"))
 @validate)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(panic|fail|error)$"))
 @raise)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(recover|retry)$"))
 @recover)

((invocation_expression
  function: (identifier) @name
  (#match? @name "(?i)^(runasync|supplyasync|thenapplyasync|thencomposeasync)$"))
 @async)

;; Method calls (member_access_expression)
((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby)$"))
 @fetch)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(on|subscribe|listen|addlistener)$"))
 @subscribe)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|assertvalid)$"))
 @validate)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(panic|fail|error)$"))
 @raise)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(recover|retry)$"))
 @recover)

((invocation_expression
  function: (member_access_expression
    name: (identifier) @name)
  (#match? @name "(?i)^(runasync|supplyasync|thenapplyasync|thencomposeasync)$"))
 @async)

;; Logging and telemetry based on object prefix
((invocation_expression
  function: (member_access_expression
    expression: (identifier) @obj
    (#match? @obj "(?i)^(console|logger|log)$")))
 @log)

((invocation_expression
  function: (member_access_expression
    expression: (identifier) @obj
    (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$")))
 @measure)
