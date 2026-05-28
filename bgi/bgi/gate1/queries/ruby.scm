;; Ruby COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call/method target names).
;; Scoped to a function/method/closure body.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return statements
((return) @output)

;; EMIT: yield statements
((yield) @emit)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if, unless, case, modifier forms
((if) @conditional)
((if_modifier) @conditional)
((unless) @conditional)
((unless_modifier) @conditional)
((case) @conditional)

;; LOOP: for, while, until loops
((for) @loop)
((while) @loop)
((until) @loop)

;; ── Error ────────────────────────────────────────────────────────────────────



;; RECOVER: rescue clauses
((rescue) @recover)

;; DEFER: ensure clauses
((ensure) @defer)

;; ── Call and Method Expressions (Tier 4) ──────────────────────────────────────

;; Method call name matching
((call
  method: (identifier) @name
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert)$"))
 @persist)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|find_by|find_by\\!|find_or_create_by)$"))
 @fetch)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger)$"))
 @emit)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(subscribe|listen|on)$"))
 @subscribe)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse)$"))
 @transform)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(update|append|push|delete|remove|clear|set|merge\\!)$"))
 @mutate)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|valid\\?)$"))
 @validate)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(raise|fail)$"))
 @raise)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(recover|retry)$"))
 @recover)

((call
  method: (identifier) @name
  (#match? @name "(?i)^(perform_async|deliver_later|delay|async|enqueue_later)$"))
 @async)

;; Logging and telemetry based on object prefix (e.g. logger.info)
((call
  receiver: [(identifier) (constant)] @obj
  (#match? @obj "(?i)^(logger|log)$"))
 @log)

((call
  receiver: [(identifier) (constant)] @obj
  (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus)$"))
 @measure)

;; Call receiver (e.g. Rails.logger.info)
((call
  receiver: (call
    receiver: [(identifier) (constant)] @obj_parent
    method: (identifier) @obj_method
    (#match? @obj_parent "(?i)^rails$")
    (#match? @obj_method "(?i)^(logger|log)$"))
  )
 @log)
