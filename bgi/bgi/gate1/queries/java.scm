;; Java COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call/method target names).
;; Scoped to a function/method/constructor body.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return statements
((return_statement) @output)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if and switch expressions
((if_statement) @conditional)
((switch_expression) @conditional)

;; LOOP: while, for, enhanced for, do/while statements
((while_statement) @loop)
((for_statement) @loop)
((enhanced_for_statement) @loop)
((do_statement) @loop)

;; SCOPE: synchronized block/statement
((synchronized_statement) @scope)

;; ── Error ────────────────────────────────────────────────────────────────────

;; RAISE: throw statements
((throw_statement) @raise)

;; RECOVER: catch clauses
((catch_clause) @recover)

;; DEFER: finally clauses
((finally_clause) @defer)

;; ── Method Invocations (Tier 4) ──────────────────────────────────────────────

;; Method call expression (including standalone call)
((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby)$"))
 @fetch)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(on|subscribe|listen|addlistener|pipe)$"))
 @subscribe)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|assertvalid)$"))
 @validate)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(panic|fail|error)$"))
 @raise)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(recover|retry)$"))
 @recover)

((method_invocation
  name: (identifier) @name
  (#match? @name "(?i)^(runasync|supplyasync|thenapplyasync|thencomposeasync)$"))
 @async)

;; Logging and telemetry based on object prefix
((method_invocation
  object: (identifier) @obj
  (#match? @obj "(?i)^(console|logger|log)$"))
 @log)

((method_invocation
  object: (identifier) @obj
  (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$"))
 @measure)
