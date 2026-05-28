;; PHP COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call/method target names).
;; Scoped to a function/method/closure body.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return statements
((return_statement) @output)

;; EMIT: yield expressions
((yield_expression) @emit)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if/switch/match statements
((if_statement) @conditional)
((switch_statement) @conditional)
((match_expression) @conditional)

;; LOOP: while, for, foreach, do/while statements
((while_statement) @loop)
((for_statement) @loop)
((foreach_statement) @loop)
((do_statement) @loop)

;; ── Error ────────────────────────────────────────────────────────────────────

;; RAISE: throw expressions
((throw_expression) @raise)

;; RECOVER: catch clauses
((catch_clause) @recover)

;; DEFER: finally clauses
((finally_clause) @defer)

;; ── Call and Method Expressions (Tier 4) ──────────────────────────────────────

;; Function call expression (standalone function call)
((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby)$"))
 @fetch)

((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(on|subscribe|listen|addlistener)$"))
 @subscribe)

((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|assertvalid)$"))
 @validate)

((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(panic|fail|error)$"))
 @raise)

((function_call_expression
  function: (name) @name
  (#match? @name "(?i)^(recover|retry)$"))
 @recover)

;; Member call expression ($obj->method())
((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby)$"))
 @fetch)

((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(on|subscribe|listen|addlistener)$"))
 @subscribe)

((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|assertvalid)$"))
 @validate)

((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(panic|fail|error)$"))
 @raise)

((member_call_expression
  name: (name) @name
  (#match? @name "(?i)^(recover|retry)$"))
 @recover)

;; Scoped call expression (Class::method())
((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby)$"))
 @fetch)

((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(on|subscribe|listen|addlistener)$"))
 @subscribe)

((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|assertvalid)$"))
 @validate)

((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(panic|fail|error)$"))
 @raise)

((scoped_call_expression
  name: (name) @name
  (#match? @name "(?i)^(recover|retry)$"))
 @recover)

;; Logging and telemetry based on object/scope prefix
((member_call_expression
  object: (variable_name
    (name) @obj)
  (#match? @obj "(?i)^(console|logger|log)$"))
 @log)

((member_call_expression
  object: (variable_name
    (name) @obj)
  (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$"))
 @measure)

((scoped_call_expression
  scope: (name) @obj
  (#match? @obj "(?i)^(console|logger|log)$"))
 @log)

((scoped_call_expression
  scope: (name) @obj
  (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$"))
 @measure)
