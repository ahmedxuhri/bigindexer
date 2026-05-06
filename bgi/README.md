# BGI — Bio-Gate Indexing

**Language-agnostic, hierarchical code intelligence pipeline producing a living, confidence-scored architecture graph optimized for AI agent consumption.**

BGI does not parse semantics. It fingerprints *behavioral intent* — what a code unit **does**, not what it **is**. The result is a compact, queryable graph that any AI agent can consume to understand a codebase's architecture before editing it.

---

## How it works

```
Source files
     │
     ▼
┌─────────────┐
│   Gate 1    │  COV Fingerprinting
│             │  Parse every function/method with tree-sitter.
│             │  Assign behavioral tokens from a 29-token vocabulary (COV).
│             │  5 tiers: AST nodes → function names → decorators → call targets → class heritage
└──────┬──────┘
       │  list[COVFingerprint]
       ▼
┌─────────────┐
│   Gate 2    │  Key-Lock Matching
│             │  Match fingerprints whose tokens complement each other (INTAKE↔OUTPUT,
│             │  FETCH↔PERSIST, RAISE↔RECOVER, etc.).
│             │  Produces HARD / PREDICTED / GHOST edges.
│             │  Unresolved outward tokens → Suspended Edge Pool (SEP).
└──────┬──────┘
       │  list[BGIEdge]
       ▼
┌─────────────┐
│   Gate 3    │  Dynamic Radar Scope (DRS) Clustering
│             │  Groups units into architectural clusters using a 4-pass algorithm:
│             │  Pass 1: within-file proximity (radar window)
│             │  Pass 1.5: namespace clustering (same subdirectory, shared high-prior tokens)
│             │  Pass 2: cross-file merging via HARD edges
│             │  Pass 3: probability scoring + cluster hardening
│             │  Pass 4: seam finalization (auto-detected module boundaries)
└──────┬──────┘
       │
       ▼
  bgi-graph.json  +  agents.md
```

### Suspended Edge Pool (SEP)

Unresolved outward references (DELEGATE, FETCH, EMIT, PERSIST, ROUTE with no partner) are stored in a SQLite database. On subsequent scans they are resurrected if a matching fingerprint appears. Edges that remain unresolved past 7 days are promoted to `INTENTIONAL_BOUNDARY` — signalling a deliberate external seam.

### AI Positions

Four optional AI positions are embedded in the pipeline. All default to `enabled=False` — the pipeline produces a complete graph without them.

| Position | Where | Role |
|----------|-------|------|
| 1 | Gate 1 | Token Fallback — LLM assigns COV when no tier fires |
| 2 | SEP | Resurrection Forecaster — predicts which suspended edges will resolve |
| 3 | Gate 3 | Architecture Narrator — writes human-readable `agents.md` cluster descriptions |
| 4 | Gate 3 | Seam Validator — confirms or rejects auto-detected architectural seams |

---

## Canonical Operation Vocabulary (COV)

29 tokens split into **edge-forming** (participate in key-lock matching) and **characterization** (enrich clustering and scoring only).

| Group | Tokens |
|-------|--------|
| Data Flow | `INTAKE` `OUTPUT` `TRANSFORM` `MUTATE` `SANITIZE` |
| Control Flow | `CONDITIONAL` `LOOP` `GUARD` `ROUTE` `SCOPE` |
| State | `FETCH` `PERSIST` |
| Communication | `EMIT` `SUBSCRIBE` `DELEGATE` |
| Structure | `CONTRACT` `COMPOSE` `INIT` `TEARDOWN` |
| Error | `RAISE` `RECOVER` `DEFER` |
| Cross-cutting | `AUTHENTICATE` `AUTHORIZE` `VALIDATE` `LOG` `MEASURE` `ASYNC` |
| Testing | `TEST` |

Key-lock pairs (edges form when one unit has the KEY token and another has the LOCK):

```
INTAKE ↔ OUTPUT        FETCH ↔ PERSIST        EMIT ↔ SUBSCRIBE
RAISE ↔ RECOVER        INIT ↔ TEARDOWN         INIT ↔ DEFER
TEST ↔ CONTRACT        VALIDATE ↔ INTAKE       SANITIZE ↔ INTAKE
GUARD ↔ CONTRACT       GUARD ↔ INTAKE          AUTHENTICATE ↔ ROUTE
AUTHORIZE ↔ ROUTE      DELEGATE ↔ CONTRACT
```

---

## Output

### `bgi-graph.json`

```json
{
  "units": [
    {
      "id": "auth/guards.py::JwtGuard::can_activate",
      "tokens": ["COV.AUTHENTICATE", "COV.INTAKE", "COV.OUTPUT"],
      "class_context": ["COV.CONTRACT"],
      "confidence": 0.95,
      "language": "python",
      "line_range": [12, 28]
    }
  ],
  "edges": [
    {
      "source": "auth/guards.py::JwtGuard::can_activate",
      "target": "routes/users.py::get_user",
      "key_token": "COV.AUTHENTICATE",
      "lock_token": "COV.ROUTE",
      "confidence": 0.90,
      "type": "HARD"
    }
  ],
  "clusters": [
    {
      "id": "cluster_auth_guards_py_JwtGuard_can",
      "size": 6,
      "probability": 0.95,
      "is_hard": true,
      "is_cross_file": false,
      "dominant_tokens": ["COV.AUTHENTICATE", "COV.INTAKE", "COV.OUTPUT"],
      "members": ["auth/guards.py::JwtGuard::can_activate", "..."]
    }
  ]
}
```

### `agents.md`

Markdown architecture narration written by AI Position 3. One section per cluster. Designed to be dropped into an AI agent's context window before it edits code.

---

## Benchmarks

| Codebase | Language | Units | Edges | Edge/unit | Clusters |
|----------|----------|-------|-------|-----------|----------|
| Flask core | Python | 383 | 7,675 | 20.0 | 20 |
| FastAPI core | Python | 280 | 3,655 | 13.1 | 21 |
| NestJS packages/core | TypeScript | 881 | 9,129 | 10.4 | 85 |

---

## Installation

```bash
pip install -e .
```

**Dependencies:** `tree-sitter`, `tree-sitter-python`, `tree-sitter-typescript`

---

## Usage

```bash
# Scan a Python project
bgi scan ./my-project --lang python --out graph.json

# Scan a TypeScript project
bgi scan ./my-ts-project --lang typescript --out graph.json

# Scan TSX files
bgi scan ./my-react-app --lang tsx --out graph.json

# Curate vocabulary extension candidates
bgi curate --graph graph.json --db bgi-sep.db --out candidates.json
```

---

## Project structure

```
bgi/
├── bgi/
│   ├── core/
│   │   ├── cov.py          # COV enum, KEY_LOCK_PAIRS, LOCK_MAP
│   │   ├── fingerprint.py  # COVFingerprint dataclass
│   │   └── edges.py        # BGIEdge dataclass
│   ├── gate1/
│   │   ├── scanner.py          # Python scanner + scan_directory dispatch
│   │   ├── python_rules.py     # Tier 1–5 rules for Python AST
│   │   ├── ts_scanner.py       # TypeScript/TSX scanner
│   │   ├── typescript_rules.py # Tier 1–5 rules for TypeScript AST
│   │   ├── rules.py            # Shared rule helpers
│   │   └── ai_fallback.py      # AI Position 1
│   ├── gate2/
│   │   └── keylock.py      # Key-lock matching, scope gate, suspended edges
│   ├── gate3/
│   │   ├── drs.py          # DRS clustering (4 passes + Pass 1.5)
│   │   └── narrator.py     # AI Position 3 — agents.md generation
│   ├── sep/
│   │   └── pool.py         # Suspended Edge Pool (SQLite)
│   ├── ai/
│   │   └── curator.py      # Vocabulary Curator (bgi curate)
│   ├── pipeline.py         # Orchestrates Gates 1→2→3→SEP→output
│   └── cli.py              # CLI entry point
├── tests/                  # 173 tests (pytest)
├── MEMORANDUM.md           # Formal design spec — all invariants and contracts
├── TASKPLAN.md             # Roadmap
└── pyproject.toml
```

---

## Tests

```bash
pytest                          # 173 tests
pytest --cov=bgi --cov-report=term-missing   # with coverage
```

---

## Design spec

See [`MEMORANDUM.md`](MEMORANDUM.md) for the full formal specification: COV vocabulary contracts, gate invariants, scope gate rationale, DRS algorithm details, SEP lifecycle, and extension zone.
