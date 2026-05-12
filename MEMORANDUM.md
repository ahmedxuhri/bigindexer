# BGI — Memorandum of Acts

**Version:** 1.0  
**Date:** 2026-05-05  
**Status:** Ratified  
**Scope:** All design decisions, vocabulary contracts, gate contracts, and invariants for the Big Indexer system.

**Current status note:** this is the design-contract memo. For current project state, use `README.md`, `TASKPLAN.md`, and `docs/VALIDATION_EVIDENCE.md`. The public repo now reflects the 100-run, 3-model validation set; commercialization notes remain local-only.

---

## 1. System Statement

BGI is a **language-agnostic, hierarchical code intelligence pipeline** that produces a living, confidence-scored architecture graph optimized for AI agent consumption. It does not parse semantics; it fingerprints *behavioral intent* — what a code unit *does*, not what it *is*.

The pipeline consists of three gates, four embedded AI positions, and one persistent pool:

```
Source files
    │
    ▼
[Gate 1] COV Fingerprinting
    │  881 units (NestJS core benchmark)
    ▼
[Gate 2] Key-Lock Matching
    │  9,129 edges (HARD + PREDICTED), 0 suspended
    ▼
[Gate 3] DRS Clustering
    │  85 clusters (41 hard, 16 cross-file)
    ▼
Architecture Graph (JSON) + agents.md narration

               ┌──────────────────────────┐
               │  Suspended Edge Pool     │
               │  (SEP — SQLite)          │
               │  Gate 2 → SEP → Gate 2'  │
               └──────────────────────────┘
```

---

## 2. Canonical Operation Vocabulary (COV)

COV is a **closed, 29-token vocabulary** that represents the behavioral fingerprint of a code unit. Every token is a `str` enum member. The set is closed — no runtime extension without a formal curation proposal.

### 2.1 Token Table

| Token | Group | Meaning | Forming edges? |
|-------|-------|---------|----------------|
| `INTAKE` | Data Flow | Unit accepts external input (parameters) | ✅ |
| `OUTPUT` | Data Flow | Unit produces a return value | ✅ |
| `TRANSFORM` | Data Flow | Maps one data shape to another | ❌ characterization |
| `MUTATE` | Data Flow | Modifies state (in-place, attribute write, augmented assign) | ❌ characterization |
| `SANITIZE` | Data Flow | Cleans/normalizes input (composite: GUARD + TRANSFORM) | ✅ |
| `CONDITIONAL` | Control Flow | Branching (if/switch/match/ternary) | ❌ characterization |
| `LOOP` | Control Flow | Iteration (for/while) | ❌ characterization |
| `GUARD` | Control Flow | Assertion / precondition check | ✅ |
| `ROUTE` | Control Flow | HTTP/RPC endpoint dispatch | ✅ |
| `SCOPE` | Control Flow | Explicit resource scope (with/transaction) | ❌ characterization |
| `FETCH` | State | Reads from persistent storage | ✅ |
| `PERSIST` | State | Writes to persistent storage | ✅ |
| `EMIT` | Communication | Fires an event / publishes a message | ✅ |
| `SUBSCRIBE` | Communication | Listens for an event / consumes a message | ✅ |
| `DELEGATE` | Communication | Hands off to a known contract | ✅ |
| `CONTRACT` | Structure | Defines an interface / abstract type | ✅ |
| `COMPOSE` | Structure | Constructs a composite from parts | ❌ characterization |
| `INIT` | Structure | Constructs/initializes a resource | ✅ |
| `TEARDOWN` | Structure | Destructs/shuts down a resource | ✅ |
| `RAISE` | Error | Throws or signals an error | ✅ |
| `RECOVER` | Error | Catches or handles an error | ✅ |
| `DEFER` | Error | Finally / cleanup after try | ✅ |
| `AUTHENTICATE` | Cross-cutting | Verifies identity | ✅ |
| `AUTHORIZE` | Cross-cutting | Checks permissions | ✅ |
| `VALIDATE` | Cross-cutting | Validates data shape/constraints | ✅ |
| `LOG` | Cross-cutting | Emits a log record | ❌ characterization |
| `MEASURE` | Cross-cutting | Emits a metric/trace | ❌ characterization |
| `ASYNC` | Cross-cutting | Involves async/await/promises | ❌ characterization |
| `TEST` | Testing | A test function or test class | ✅ |

### 2.2 Key-Lock Pairs

Edge formation rule: **an edge exists iff one unit carries the KEY token and another carries the LOCK token.** Both directions are checked; the edge is directed by the `KEY_LOCK_PAIRS` definition.

```python
KEY_LOCK_PAIRS = [
    (INTAKE,       OUTPUT),       # data flows in → data flows out
    (FETCH,        PERSIST),      # read complements write
    (EMIT,         SUBSCRIBE),    # event producer ↔ consumer
    (RAISE,        RECOVER),      # error thrown ↔ handled
    (INIT,         TEARDOWN),     # lifecycle open ↔ close
    (INIT,         DEFER),        # initialized resource needs cleanup
    (TEST,         CONTRACT),     # test covers a contract
    (VALIDATE,     INTAKE),       # validation guards intake
    (SANITIZE,     INTAKE),       # sanitization guards intake
    (GUARD,        CONTRACT),     # assertion enforces a contract  (multi-pair)
    (GUARD,        INTAKE),       # assertion gates input          (multi-pair)
    (AUTHENTICATE, ROUTE),        # auth gate on a route
    (AUTHORIZE,    ROUTE),        # authz gate on a route
    (DELEGATE,     CONTRACT),     # delegation to a defined contract
]
```

**Invariant:** Every non-characterization token must appear in at least one key-lock pair.

### 2.3 Characterization Tokens

These tokens do NOT form edges. They enrich Gate 3 clustering, cluster role narration, and probability scoring:

`TRANSFORM · MUTATE · SCOPE · CONDITIONAL · LOOP · ASYNC · COMPOSE · LOG · MEASURE`

---

## 3. Gate 1 — COV Fingerprinting

**Purpose:** Parse source files with tree-sitter; assign COV tokens to each code unit.

**Contract:**
- Input: a directory path + language tag
- Output: `list[COVFingerprint]`
- One `COVFingerprint` per *behavioral unit* (function, method, arrow function, interface)
- Decorators and class heritage are **not** separate units; their tokens go into the fingerprint of the enclosed unit
- Class-level tokens go into `class_context` (separate from `tokens`), never into `tokens` directly

### 3.1 COVFingerprint schema

```python
@dataclass
class COVFingerprint:
    unit_id:       str          # "file.py::ClassName::method_name"
    tokens:        list[COV]    # own tokens (deduplicated)
    class_context: list[COV]    # tokens from the enclosing class
    confidence:    float        # 0.0–1.0; weighted average of tier confidences
    line_range:    tuple[int,int]
    language:      str          # "python" | "typescript" | "tsx"
    source:        str          # provenance string for debugging
```

### 3.2 Unit ID format

```
<relative_file_path>::<ClassName>::<method_name>   # class method
<relative_file_path>::<function_name>              # module-level function
<relative_file_path>::<InterfaceName>              # interface (TS only)
```

### 3.3 Five-Tier Fingerprinting Cascade

Each tier fires independently. Tokens from all tiers are merged, then **deduplicated** into the final fingerprint. Confidence = weighted average.

| Tier | Input | Signal | Confidence |
|------|-------|--------|------------|
| 1 | AST node type | Deterministic: `return_statement → OUTPUT` | 1.0 |
| 2 | Function name | Heuristic: `__init__ → INIT`, `test_* → TEST` | 0.95 |
| 3 | Decorator text | Pattern: `@login_required → AUTHENTICATE` | 0.9 |
| 4 | Call target | Heuristic: `.save() → PERSIST`, `.query() → FETCH` | 0.75 |
| 5 | Class heritage | Heuristic: `extends Error → RAISE`, `implements Repository → PERSIST` | 0.9 |

**Tier 5 tokens always go into `class_context`, never into `tokens`.**  
Exception: interfaces — the interface itself gets `CONTRACT` in `tokens`.

### 3.4 Python-specific AST nodes

| node type | COV |
|-----------|-----|
| `return_statement` | OUTPUT |
| `yield` / `yield_from` | EMIT |
| `raise_statement` | RAISE |
| `assert_statement` | GUARD |
| `except_clause` | RECOVER |
| `finally_clause` | DEFER |
| `for_statement` / `while_statement` | LOOP |
| `if_statement` / `elif_clause` / `match_statement` | CONDITIONAL |
| `with_statement` | SCOPE |
| `await` | ASYNC |
| `augmented_assignment` | MUTATE |
| `assignment` with attribute/subscript LHS | MUTATE |
| `list_comprehension` / `dictionary_comprehension` / `set_comprehension` / `generator_expression` | TRANSFORM |

**Bug fixed:** tree-sitter Python uses `dictionary_comprehension` (not `dict_comprehension`).

### 3.5 TypeScript-specific AST nodes

| node type / condition | COV |
|-----------------------|-----|
| `return_statement` | OUTPUT |
| `throw_statement` | RAISE |
| `catch_clause` | RECOVER |
| `finally_clause` | DEFER |
| `for_in_statement` (covers both for-of and for-in) | LOOP |
| `for_statement` / `while_statement` | LOOP |
| `if_statement` / `switch_statement` | CONDITIONAL |
| `await_expression` | ASYNC |
| `yield_expression` | EMIT |
| `augmented_assignment_expression` | MUTATE |
| `assignment_expression` with `member_expression` LHS | MUTATE |
| `interface_declaration` | CONTRACT (unit-level) |

**TypeScript quirks (tree-sitter-typescript):**
- `for-of` and `for-in` both produce `for_in_statement` — no separate types
- `yield` produces `yield_expression`, not `yield` like Python
- `throw` produces `throw_statement`, not `raise_statement`
- Async detection: check for `async` child token on `function_declaration` or `arrow_function`
- Arrow functions: `arrow_function` node; body can be expression or `statement_block`
- `this` parameter in TypeScript formal_parameters must be **skipped** — it is not a real parameter and must not produce INTAKE
- `.d.ts` declaration files are **excluded** from all TypeScript scans
- Decorators are direct children of `class_declaration` or `method_definition` (not wrapped in `decorated_definition` like Python)

### 3.6 INTAKE detection rules

**Python:** INTAKE if the function has ≥1 parameter excluding `self` / `cls`.

**TypeScript:** INTAKE if the function has ≥1 parameter excluding the `this` parameter. Arrow functions with empty `()` do not get INTAKE.

### 3.7 Language dispatch

```python
scan_directory(path, language):
    if language in ("typescript", "tsx", "ts"):
        dispatch to ts_scanner.scan_file_ts()
        skip files ending in ".d.ts"
        use tsts.language_tsx() for .tsx files
        use tsts.language_typescript() for .ts files
    else:  # python (default)
        dispatch to scanner.scan_file()
```

---

## 4. Gate 2 — Key-Lock Matching

**Purpose:** Find edges between fingerprints whose tokens form a key-lock pair.

**Contract:**
- Input: `list[COVFingerprint]`
- Output: `(list[BGIEdge], list[SuspendedEdge])`

### 4.1 Algorithm

```
1. Build token index: COV → [fingerprints containing this token]
   (uses all_tokens() so class_context participates in matching)

2. For each fingerprint fp_a:
   For each edge-forming token in fp_a.all_tokens():
     Look up complement tokens from LOCK_MAP
     For each complement token → for each fp_b in index:
       - Skip if fp_a == fp_b
       - Apply scope gate (see §4.2)
       - Mark matched_any = True  ← MUST be before dedup check
       - Dedup (frozenset of unit_ids + key/lock token pair)
       - Compute confidence → classify edge type
       - Append BGIEdge

   If matched_any is still False after all complements:
     If token is in _OUTWARD: emit SuspendedEdge to SEP
```

**Bug fixed:** `matched_any = True` must be set **before** the dedup `continue` check. If set after, the second occurrence of a matched pair incorrectly finds `matched_any=False` and generates a spurious suspended edge.

### 4.2 Scope Gate

High-frequency token pairs that produce O(N²) noise when matched globally are restricted by scope:

| Pair | Constraint |
|------|-----------|
| `INTAKE ↔ OUTPUT` | Same class (for methods) or same file (for module-level) |
| `GUARD ↔ INTAKE` | Same class or same file |
| `GUARD ↔ CONTRACT` | Same class or same file |

**Rationale:** `INTAKE` and `OUTPUT` appear in ≈75% of all functions. Without the scope gate, a 383-unit codebase would produce ~146k edges instead of ~7k.

**Cross-file rule:** Units from different files are never scope-compatible for class-scoped pairs. Units in the same file but different classes (one or both module-level) are scope-compatible.

### 4.3 Edge Confidence

```
base = min(fp_a.confidence, fp_b.confidence)
if same file:         base += 0.05
if same class:        base += 0.05   (only for class methods)
confidence = min(1.0, base)
```

### 4.4 Edge Types

| Type | Confidence threshold |
|------|---------------------|
| `HARD` | ≥ 0.85 |
| `PREDICTED` | ≥ 0.50 |
| `GHOST` | < 0.50 |

### 4.5 Suspended Edges

A `SuspendedEdge` is emitted when an **outward** token finds no partner in the current scan:

```python
_OUTWARD = {DELEGATE, FETCH, EMIT, PERSIST, ROUTE}
```

Only outward tokens are suspended. `RECOVER`, `SUBSCRIBE` etc. are inward and do not suspend (the lack of a partner is normal).

### 4.6 BGIEdge schema

```python
@dataclass
class BGIEdge:
    source_id:  str       # unit_id of the KEY-token unit
    target_id:  str       # unit_id of the LOCK-token unit
    key_token:  COV
    lock_token: COV
    confidence: float
    edge_type:  EdgeType  # "HARD" | "PREDICTED" | "GHOST"
    provenance: str       # "gate2:tier1-5:source_a/source_b"
```

---

## 5. Gate 3 — Dynamic Radar Scope (DRS) Clustering

**Purpose:** Group fingerprints into architectural clusters using a 4-pass algorithm.

**Contract:**
- Input: `list[COVFingerprint]`, `list[BGIEdge]`
- Output: `DRSResult` (clusters, unit→cluster map, seam units)

### 5.1 Pass 1 — Within-file proximity grouping

For each file (units sorted by line number):
- Each unit opens a "radar window" of `_radar_range(token_prior)` lines
- If no open cluster's window covers the unit: start a new cluster
- If exactly one cluster covers it: join that cluster
- If two or more clusters cover it: mark as **seam candidate**, merge clusters

```
_BASE_RADAR     = 400 lines
_MAX_MULTIPLIER = 3.0
_RADAR_CEILING  = 8,000 lines
radar_range(p)  = min(8000, int(400 × (1 + 2p)))
```

### 5.2 Pass 1.5 — Namespace clustering

Units in the **same subdirectory** (non-root) that share ≥1 high-prior token (prior ≥ 0.7) are cross-file merged.

```
_NAMESPACE_THRESHOLD = 0.7
_NAMESPACE_MIN_SHARED = 1
```

**Rationale:** Files in `security/`, `middleware/`, `hooks/` are architecturally co-located even if not proximity-connected within a file. This pass fixed the FastAPI `security/*` fragmentation (4 files → 1 AUTHENTICATE cluster).

**Excluded:** Root-level files (empty subdir string) are not namespace-merged.

### 5.3 Pass 2 — Cross-file merging via HARD edges

Only HARD edges (confidence ≥ 0.85) trigger cross-file cluster merging, and only for specific token pairs:

```python
_CROSS_FILE_MERGE_PAIRS = {
    (DELEGATE,     CONTRACT),   # explicit delegation
    (TEST,         CONTRACT),   # test ↔ contract
    (EMIT,         SUBSCRIBE),  # event bus cross-service
    (AUTHENTICATE, ROUTE),      # auth gate on route
    (AUTHORIZE,    ROUTE),      # authz gate on route
}
```

**Rationale:** `INIT↔TEARDOWN` and `INTAKE↔OUTPUT` must NOT trigger cross-file merges — they appear everywhere and would collapse all components into one mega-cluster.

### 5.4 Pass 3 — Probability and radar computation

```
probability = max_token_prior + velocity_boost + cross_file_boost + size_boost

where:
  velocity_boost    = min(0.3,  edge_count × 0.05)
  cross_file_boost  = 0.1 if is_cross_file else 0.0
  size_boost        = min(0.1,  cluster.size × 0.01)
```

### 5.5 COV Token Priors

Used in probability computation and Pass 1 radar sizing:

| Prior | Tokens |
|-------|--------|
| 1.0 | CONTRACT, ROUTE, AUTHENTICATE, AUTHORIZE |
| 0.9 | PERSIST |
| 0.8 | FETCH, EMIT, SUBSCRIBE |
| 0.7 | INIT, TEARDOWN, VALIDATE, TEST |
| 0.6 | RAISE, RECOVER |
| 0.5 | INTAKE, OUTPUT, GUARD, DELEGATE, SANITIZE, DEFER |
| 0.4 | TRANSFORM, MUTATE, SCOPE, ASYNC, COMPOSE |
| 0.3 | CONDITIONAL, LOOP, LOG, MEASURE |

### 5.6 Pass 4 — Seam finalization

Units that fell within two clusters' radar in Pass 1 (seam candidates) are confirmed as **architectural seams** — auto-detected module boundaries.

### 5.7 Cluster hardening

A cluster is `is_hard = True` if:
- `probability ≥ 0.85` AND
- `size ≥ 2`

### 5.8 Cluster schema

```python
@dataclass
class Cluster:
    cluster_id:      str
    member_ids:      list[str]
    dominant_tokens: list[COV]    # top-5 by frequency
    probability:     float
    radar_range:     int
    is_hard:         bool
    files:           set[str]
    seam_unit_ids:   set[str]
```

---

## 6. Suspended Edge Pool (SEP)

**Purpose:** Persist unresolved outward references across scan runs, detect intentional boundaries, and surface Odd Groups for AI Position 2.

### 6.1 Schema

```sql
CREATE TABLE suspended_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT    NOT NULL,
    token       TEXT    NOT NULL,      -- COV token name
    raw_callee  TEXT    NOT NULL,      -- best-effort callee name
    ingested_at REAL    NOT NULL,      -- unix timestamp
    resolved    INTEGER NOT NULL DEFAULT 0,
    resolved_at REAL,
    boundary    INTEGER NOT NULL DEFAULT 0,   -- 1 = INTENTIONAL_BOUNDARY
    scan_run    TEXT                           -- batch ID
);
```

### 6.2 Lifecycle

```
Gate 2 produces SuspendedEdge list
    → SEP.ingest()       -- write new (skips existing unresolved duplicates)
    → SEP.resurrect()    -- given new fingerprints, resolve matching edges
    → SEP.odd_groups()   -- cluster by token/pattern for AI Position 2
    → SEP.scan_boundaries() -- promote stale (>7 days) to INTENTIONAL_BOUNDARY
```

### 6.3 Odd Groups

An `OddGroup` is a cluster of suspended edges sharing the same COV token. It is the input to **AI Position 2** (Resurrection Forecaster).

```python
@dataclass
class OddGroup:
    token:       COV
    pattern:     str          # dominant raw_callee pattern
    member_ids:  list[str]
    count:       int
    oldest_age_s: float
    is_boundary: bool
```

### 6.4 Boundary promotion

Default age threshold: **7 days**. An edge that remains unresolved for longer is promoted to `boundary=1` (INTENTIONAL_BOUNDARY). This signals that the missing partner is not missing — it is intentionally external (a 3rd-party service, a separate repo, a deliberate seam).

---

## 7. AI Positions

Four AI positions are embedded in the pipeline. All positions default to `enabled=False` (no API calls during normal scans). Each is independently opt-in.

| Position | Location | Role | Input | Output |
|----------|----------|------|-------|--------|
| 1 | Gate 1, unit level | Token Fallback — assign COV when no tier fires | AST subtree text, context | `list[(COV, confidence)]` |
| 2 | SEP | Resurrection Forecaster — predict which suspended edges will resolve | `OddGroup` list | Prediction scores |
| 3 | Gate 3, post-DRS | Architecture Narrator — write `agents.md` cluster descriptions | `DRSResult` + fingerprints | Markdown narration |
| 4 | Gate 3, post-DRS | Seam Validator — confirm or reject auto-detected seam candidates | Seam unit list + context | Accept/reject signals |

**Invariant:** BGI must produce a complete, valid graph with `AIFallback(enabled=False)`. AI positions are *enhancements*, not requirements.

---

## 8. Output Contract

### 8.1 `bgi-graph.json`

```json
{
  "units": [
    {
      "id":            "file.py::Class::method",
      "tokens":        ["COV.INTAKE", "COV.OUTPUT"],
      "class_context": ["COV.CONTRACT"],
      "confidence":    0.95,
      "language":      "python",
      "line_range":    [10, 25]
    }
  ],
  "edges": [
    {
      "source":     "file.py::Class::method",
      "target":     "file.py::Class::other",
      "key_token":  "COV.INTAKE",
      "lock_token": "COV.OUTPUT",
      "confidence": 0.95,
      "type":       "HARD"
    }
  ],
  "clusters": [
    {
      "id":              "cluster_...",
      "size":            12,
      "probability":     0.95,
      "radar_range":     1200,
      "is_hard":         true,
      "is_cross_file":   false,
      "files":           ["file.py"],
      "dominant_tokens": ["COV.OUTPUT", "COV.INTAKE"],
      "seams":           [],
      "members":         ["file.py::Class::method", "..."]
    }
  ]
}
```

### 8.2 `agents.md`

Human- and AI-readable architecture narration. One section per cluster. Written by AI Position 3. Includes:
- Cluster role (Lifecycle Manager / Data Access / Interface Contract / etc.)
- Probability + radar range
- Dominant tokens
- Member unit list
- File list

### 8.3 CLI

```
bgi scan <path> [--lang python|typescript|tsx|ts] [--out bgi-graph.json] [--db bgi-sep.db]
bgi curate [--unresolved bgi-unresolved.jsonl] [--db bgi-sep.db] [--graph bgi-graph.json] [--out cov-extension-candidates.json]
```

---

## 9. Known Invariants and Constraints

| # | Invariant |
|---|-----------|
| I1 | COV is closed. No token is added without a curation proposal and key-lock pair definition. |
| I2 | All tokens are deduplicated within a single fingerprint (list, not multiset). |
| I3 | Tier 5 tokens always go into `class_context`, never directly into `tokens`. |
| I4 | Gate 2 `matched_any` flag must be set **before** the dedup `continue`. |
| I5 | `INTAKE↔OUTPUT` and all `GUARD` pairs are class-scoped — never matched globally. |
| I6 | `.d.ts` files are always excluded from TypeScript scans. |
| I7 | TypeScript `this` parameters do not produce INTAKE. |
| I8 | Cross-file cluster merges require a HARD edge AND the pair must be in `_CROSS_FILE_MERGE_PAIRS`. |
| I9 | AI positions default to `enabled=False`. The pipeline must be complete without them. |
| I10 | SEP skips duplicate ingestion (same `source_id` + `token` already unresolved). |

---

## 10. Validated Benchmarks

| Codebase | Units | Edges | Edge/unit | Clusters | Suspended | Notes |
|----------|-------|-------|-----------|----------|-----------|-------|
| Flask (core) | 383 | 7,675 | 20.0 | 20 | 0 | After INTAKE↔OUTPUT scope gate |
| FastAPI (core) | 280 | 3,655 | 13.1 | 21 | 0 | After GUARD scope gate + namespace clustering |
| NestJS (packages/core) | 881 | 9,129 | 10.4 | 85 | 0 | TypeScript; 16 cross-file clusters |

Edge/unit ratios below 30 are considered healthy. Above 50 indicates a scope gate may be missing.

---

## 11. Extension Zone

Tokens known to be desirable but not yet formalized:

| Candidate | Likely group | Notes |
|-----------|-------------|-------|
| `MEMOIZE` | State | Currently mapped to FETCH (cache read). Needs own key-lock pair. |
| `PATTERN_MATCH` | Control Flow | `match_statement` currently maps to CONDITIONAL. Distinct semantics. |
| `AMBIENT` | Structure | TypeScript `declare module` / `.d.ts` — excluded today, may need representation |
| `BATCH` | Data Flow | Bulk operations distinct from PERSIST/FETCH |

Extension process: raise a curation proposal via `bgi curate`, review candidates in `cov-extension-candidates.json`, then add token + key-lock pair + tier rules + tests before ratification.
