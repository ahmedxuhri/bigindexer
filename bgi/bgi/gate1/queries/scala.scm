;; Scala COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call/method target names).
;; Scoped to a function/method/closure body.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return expressions
((return_expression) @output)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if/match expressions
((if_expression) @conditional)
((match_expression) @conditional)

;; LOOP: for/while/do-while loops and statements
((for_expression) @loop)
((while_expression) @loop)
((do_while_expression) @loop)

;; ── Error ────────────────────────────────────────────────────────────────────

;; RAISE: throw expressions
((throw_expression) @raise)

;; RECOVER: catch clauses
((catch_clause) @recover)

;; DEFER: finally clauses
((finally_clause) @defer)

;; ── Call and Method Expressions (Tier 4) ──────────────────────────────────────

;; Method call name matching
((call_expression
  [
    (identifier) @name
    (field_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((call_expression
  [
    (identifier) @name
    (field_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby)$"))
 @fetch)

((call_expression
  [
    (identifier) @name
    (field_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((call_expression
  [
    (identifier) @name
    (field_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(on|subscribe|listen|addlistener)$"))
 @subscribe)

((call_expression
  [
    (identifier) @name
    (field_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((call_expression
  [
    (identifier) @name
    (field_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((call_expression
  [
    (identifier) @name
    (field_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|assertvalid)$"))
 @validate)

((call_expression
  [
    (identifier) @name
    (field_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(Future|async)$"))
 @async)

;; Logging and telemetry based on object prefix (e.g. logger.info)
((call_expression
  (field_expression
    (identifier) @obj
    (identifier) @name
  )
  (#match? @obj "(?i)^(logger|log|console)$"))
 @log)

((call_expression
  (field_expression
    (identifier) @obj
    (identifier) @name
  )
  (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$"))
 @measure)
