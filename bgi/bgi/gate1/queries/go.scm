;; Go COV Token Query Patterns — WATER-CLOCK
;; Covers Tier 1 (AST structure) and Tier 4 (call target method names).
;; Run scoped to a function/method node.

;; ── Data Flow ────────────────────────────────────────────────────────────────

;; OUTPUT: return statements
((return_statement) @output)

;; MUTATE: slice append or delete built-ins
((call_expression
  function: (identifier) @name
  (#match? @name "(?i)^(append|delete)$"))
 @mutate)

;; TRANSFORM: range loop
((range_clause) @transform)

;; ── Control Flow ──────────────────────────────────────────────────────────────

;; CONDITIONAL: if/switch/select statements
((if_statement) @conditional)
((expression_switch_statement) @conditional)
((type_switch_statement) @conditional)
((select_statement) @conditional)

;; LOOP: for statements
((for_statement) @loop)

;; ── State ────────────────────────────────────────────────────────────────────

;; ── Communication ────────────────────────────────────────────────────────────

;; EMIT: send statement on channel (e.g. ch <- val)
((send_statement) @emit)

;; SUBSCRIBE: receive statement from channel (e.g. <-ch)
((unary_expression
  operator: "<-") @subscribe)

;; DEFER: defer statements
((defer_statement) @defer)

;; ── Async ────────────────────────────────────────────────────────────────────

;; ASYNC: go statement
((go_statement) @async)

;; ── Call Expressions (Tier 4) ────────────────────────────────────────────────

;; Method and standalone function calls
((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(save|insert|create|write|persist|add|put|store|upsert|exec|execcontext|writeto|writefile|writeall)$"))
 @persist)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(find|get|read|query|fetch|load|select|filter|findone|findall|findby|querycontext|queryrow|queryrowcontext|scan|readfile|readall|lookup|search)$"))
 @fetch)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(emit|publish|dispatch|send|broadcast|trigger|next|notify|fire)$"))
 @emit)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(on|subscribe|listen|receive|watch|observe)$"))
 @subscribe)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(map|transform|convert|serialize|deserialize|encode|decode|format|parse|marshal|unmarshal|marshaljson|unmarshaljson)$"))
 @transform)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(update|append|push|splice|pop|delete|remove|clear|set|patch)$"))
 @mutate)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(validate|check|ensure|verify|assert|ispresent|isvalid)$"))
 @validate)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(close|stop|shutdown|cancel|release|unlock|rwunlock|done|wait|wg\\.done)$"))
 @teardown)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(authenticate|login|signin|verifytoken|verifycredentials|checkpassword|verifypassword)$"))
 @authenticate)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(authorize|requireauth|requirepermission|requirerole|checkpermission|haspermission|canaccess)$"))
 @authorize)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(panic|fatal|fatalln|fatalf)$"))
 @raise)

((call_expression
  function: [
    (identifier) @name
    (selector_expression field: (field_identifier) @name)
  ]
  (#match? @name "(?i)^(recover)$"))
 @recover)

;; Logging and telemetry based on operand/package name
((call_expression
  function: (selector_expression
    operand: (identifier) @obj)
  (#match? @obj "(?i)^(log|logger|slog|klog|zap|logrus|zerolog|glog)$"))
 @log)

((call_expression
  function: (selector_expression
    operand: (identifier) @obj)
  (#match? @obj "(?i)^(metrics|statsd|counter|gauge|histogram|timer|telemetry|prometheus|meter|tracer|span|otel|observability)$"))
 @measure)

;; Route calls: HTTP router methods (e.g. router.HandleFunc)
((call_expression
  function: (selector_expression
    operand: (identifier) @obj
    field: (field_identifier) @method)
  (#match? @obj "(?i)^(http|mux|router|r|app|engine|g|api|rg|v1|v2|echo|fiber|gin|chi|mux\\.router)$")
  (#match? @method "(?i)^(handlefunc|handle|get|post|put|delete|patch|head|options|any|use|group|subrouter|pathprefix)$"))
 @route)
