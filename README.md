# BGI — Bio-Gate Indexing

BGI is a language-agnostic code intelligence pipeline that fingerprints units with COV semantic tokens, builds behavioral edges, and clusters architecture boundaries for large repositories.

## Current Status

- **Phase 5 (Water-Clock) complete**: single-pass `.scm` fingerprinting + multiprocessing + incremental auto mode + language registry
- **Phase 6 Option A complete**: interactive search index, query planner, FastAPI query API, VS Code prototype
- **Tests**: `789 passed`
- **Large-repo validation**: kubernetes/kubernetes (3.6M LOC), max cluster `1.113%`

## Pipeline

```text
Source files
   ↓
Gate 1: COV fingerprinting (what units do)
   ↓
Gate 2: Key-Lock edge matching (how units connect)
   ↓
Gate 3: DRS clustering + FUSE boundaries (architecture shape)
   ↓
Outputs: graph JSON, routes, GraphML, fuse-graph, HTML, index tables
```

## Quickstart

```bash
pip install -e .

# Scan one repo
bgi scan /path/to/repo --lang auto --out bgi-graph.json

# Include optional outputs
bgi scan /path/to/repo --lang auto \
  --routes routes.json \
  --graphml graph.graphml \
  --fuse-graph fuse-graph.json \
  --html

# Incremental scan
bgi scan /path/to/repo --lang auto --incremental --cache .bgi-cache.json

# Diff two versions
bgi diff /path/before /path/after --lang auto --out diff.json

# Curate unresolved patterns
bgi curate --graph bgi-graph.json --unresolved bgi-unresolved.jsonl
```

## CLI Commands

- `bgi scan`: full pipeline (Gates 1-3) with optional outputs and parallelism
- `bgi diff`: architecture diff between two roots
- `bgi curate`: propose COV vocabulary extensions from unresolved patterns

Key `scan` options:

- `--lang auto` for mixed-language repos
- `--parallel --max-workers N` for Gate 1 multiprocessing
- `--max-cluster-pct 0.03` for FUSE-MAP cluster ceiling

## Interactive Search Index (Phase 6)

Implemented components:

- **Index schema** (`bgi.indexer.schema`): tables for units/edges/clusters/symbol index
- **Index builder** (`bgi.indexer.builder`): loads Gate outputs into index
- **Query planner** (`bgi.indexer.planner`): score-based scope narrowing
- **Query API** (`bgi.indexer.api`): FastAPI endpoints
  - `GET /api/symbols/{name}`
  - `GET /api/search?q=...`
  - `GET /api/callers/{symbol}`
  - `GET /api/callees/{symbol}`
  - `GET /api/stats`
  - `GET /api/health`
- **VS Code prototype** (`ide/vscode`): lookup symbol, prefix search, find callers

Create an app instance in Python:

```python
from bgi.indexer.api import create_search_app

app = create_search_app("index.db")
```

## Supported Languages

Python, TypeScript, JavaScript, Java, Go, Rust, Ruby, C#, PHP, Kotlin, C, Scala, Lua, Elixir, Swift, R, Dart, Bash, Nim, Zig, Haskell, OCaml, F#, Clojure, Erlang, MATLAB, VB, Crystal, COBOL, Groovy, plus generic fallback mode.

## Benchmarks / Validation Snapshot

- **kubernetes/kubernetes**
  - LOC: `3,627,208`
  - Units: `162,954`
  - Gate timings: Gate 1 `67.513s`, Gate 2 `138.869s`, Gate 3 `12.797s`
  - Total: `219.179s`
  - Max cluster: `1.113%` (under 3% bound)

## Docs

- `MEMORANDUM.md` — architecture contracts and invariants
- `TASKPLAN.md` — implementation history and phase roadmap
- `docs/LANGUAGE_SUPPORT.md` — `.scm` language support guide
- `docs/CONTRIBUTING_LANGUAGES.md` — adding new languages
- `docs/INDEX_SCHEMA.md` — index schema design
- `docs/QUERY_PLANNER.md` — planner heuristics and scoring

## Development

```bash
# run tests
python3 -m pytest tests/ -x -q

# build VS Code prototype
npm --prefix ide/vscode install
npm --prefix ide/vscode run build
```
