;; Kotlin COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call/method target names).
;; Scoped to a function/method/closure body.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return expressions
((return_expression) @output)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if/when expressions
((if_expression) @conditional)
((when_expression) @conditional)

;; LOOP: for/while/do-while loops
((for_statement) @loop)
((while_statement) @loop)
((do_while_statement) @loop)

;; ── Error ────────────────────────────────────────────────────────────────────

;; RAISE: throw expressions
((throw_expression) @raise)

;; RECOVER: catch blocks
((catch_block) @recover)

;; DEFER: finally blocks
((finally_block) @defer)

;; ── Call and Method Expressions (Tier 4) ──────────────────────────────────────

;; Method call name matching
((call_expression
  [
    (identifier) @name
    (navigation_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((call_expression
  [
    (identifier) @name
    (navigation_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby)$"))
 @fetch)

((call_expression
  [
    (identifier) @name
    (navigation_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next)$"))
 @emit)

((call_expression
  [
    (identifier) @name
    (navigation_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(on|subscribe|listen|addlistener)$"))
 @subscribe)

((call_expression
  [
    (identifier) @name
    (navigation_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((call_expression
  [
    (identifier) @name
    (navigation_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((call_expression
  [
    (identifier) @name
    (navigation_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|assertvalid)$"))
 @validate)

((call_expression
  [
    (identifier) @name
    (navigation_expression
      (identifier) @obj
      (identifier) @name
    )
  ]
  (#match? @name "(?i)^(launch|async)$"))
 @async)

;; Logging and telemetry based on object prefix (e.g. logger.info)
((call_expression
  (navigation_expression
    (identifier) @obj
    (identifier) @name
  )
  (#match? @obj "(?i)^(logger|log|console)$"))
 @log)

((call_expression
  (navigation_expression
    (identifier) @obj
    (identifier) @name
  )
  (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$"))
 @measure)
