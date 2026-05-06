# BGI — Bio-Gate Indexing

**Language-agnostic hierarchical code intelligence pipeline.**

BGI fingerprints every function and method in a codebase with COV (Canonical Operation Vocabulary) semantic tokens, then groups units into architectural clusters via confidence-scored edges — producing a living architecture graph optimized for AI agent consumption.

---

## What It Does

```
Source files  (any language)
      │
      ▼
[Gate 1]  COV Fingerprinting     — What does each unit DO?
      ▼
[Gate 2]  Key-Lock Matching      — What connects to what?
      ▼
[Gate 3]  DRS Clustering         — What are the architectural components?
      ▼
[Output]  Graph JSON + Route Manifest + GraphML + agents.md
```

28 semantic tokens. 14 key-lock relationships. Language-agnostic.

---

## Quickstart

```bash
pip install -e .

# Scan a Python project
bgi scan /path/to/project --out graph.json

# Scan a multi-language repo
bgi scan /path/to/repo --lang auto --routes routes.json --graphml graph.graphml

# Diff two commits
bgi diff /path/before /path/after --lang auto

# Exclude noisy directories
bgi scan /path/to/repo --lang auto --exclude-dirs docs_src examples benchmarks
```

---

## Benchmark Results

| Repo | Units | Total time | Clusters |
|------|-------|-----------|----------|
| FastAPI | 4,509 | 7.3s | 243 |
| VS Code | 75,131 | 144s | 1,156 |

---

## Architecture

See `MEMORANDUM.md` for full design contracts, gate contracts, COV vocabulary, and invariants.

See `TASKPLAN.md` for implementation history and future roadmap.

---

## Supported Languages

Python · TypeScript · JavaScript · Java · Go · Rust · Ruby · C# · PHP · Kotlin · C · Scala · Lua · Elixir · Swift · R · Dart · Bash · Nim · Zig · Haskell · OCaml · F# · Clojure · Erlang · MATLAB · VB · Crystal · COBOL · Groovy

---

## Project Layout

```
bgi/bgi/          Python package (pip-installable)
  core/           COV vocabulary, fingerprint, edge types
  gate1/          Language scanners (tree-sitter + generic regex)
  gate2/          Key-Lock matching engine
  gate3/          DRS clustering algorithm
  ai/             AI positions (fallback, narrator, curator, forecaster)
  delta/          Incremental scan cache + diff engine
  output/         Graph serialization, GraphML, route manifest, HTML viz
  sep/            Suspended Edge Pool (SQLite)
tests/            600+ tests
pyproject.toml    Package config
MEMORANDUM.md     Full design spec and invariants
TASKPLAN.md       Implementation roadmap
problem.md        VS Code scale benchmark report
```
