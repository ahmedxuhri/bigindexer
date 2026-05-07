# BGI — Bio-Gate Indexing

**BGI is architecture cartography for codebases.**  
It fingerprints behavioral intent (COV tokens), builds behavioral edges, and clusters units into architectural components with explicit boundary signals.

---

## Why BGI Exists

BGI was redesigned around one core insight from `bgi2.md`:

> The original failure mode was not “bugs” — it was missing **scale constraints**.

At scale, unconstrained matching and unconstrained clustering create edge explosions and mega-clusters.  
BGI’s answer is the **Spectral-Fuse Architecture**: constrain both edge generation and cluster growth so quality stays stable as repos grow.

---

## Spectral-Fuse Architecture (Adopted)

This is the project’s current direction and implemented baseline:

1. **TOKEN-CENSUS**: classify COV token frequency per repo (adaptive bands).
2. **SPECTRAL-MASKS (Gate 2)**: scoped matching by token band:
   - rare tokens → global scope
   - medium tokens → directory scope
   - common tokens (`INTAKE`, `OUTPUT`, `GUARD`) → file scope
3. **FUSE-MAP (Gate 3)**: hard cluster-size ceiling; refused merges become **FuseEdges**.
4. **MASK-4-GATE-3**: import/export proximity as clustering signal (not behavioral edge signal).
5. **WATER-CLOCK + `.scm`**: single-pass tree-sitter query fingerprinting + multiprocessing + incremental mode.

### Core Philosophy

- **Quality-first over raw speed** (accurate clusters > fast noisy output)
- Architectural boundaries are first-class outputs (`fuse-graph.json`)
- Scale constraints are design primitives, not afterthoughts

---

## Pipeline

```text
Source files
   ↓
Gate 1: COV fingerprinting
  - single-pass .scm query extraction
  - multiprocessing + incremental cache support
   ↓
Gate 2: Key-Lock edge generation
  - spectral masks by frequency/scope
   ↓
Gate 3: DRS clustering
  - fuse-capped merges + boundary graph
  - import-proximity signal for structural cohesion
   ↓
Outputs
  - bgi-graph.json
  - routes.json (optional)
  - graph.graphml (optional)
  - fuse-graph.json
  - HTML viz (optional)
```

---

## Current Project Status

- **Phase 5 complete**: Water-Clock + `.scm` + multiprocessing + incremental auto + language registry
- **Phase 6 Option A complete**:
  - index schema
  - index builder
  - query planner
  - FastAPI query API
  - VS Code prototype
- **Tests**: `789 passed`
- **Large-repo validation**: `kubernetes/kubernetes` (3.6M LOC), max cluster `1.113%`

---

## Quickstart

```bash
pip install -e .

# Scan a repo (auto language detection)
bgi scan /path/to/repo --lang auto --out bgi-graph.json

# Add optional outputs
bgi scan /path/to/repo --lang auto \
  --routes routes.json \
  --graphml graph.graphml \
  --fuse-graph fuse-graph.json \
  --html

# Incremental scan
bgi scan /path/to/repo --lang auto --incremental --cache .bgi-cache.json

# Diff two trees
bgi diff /path/before /path/after --lang auto --out diff.json

# Curate unresolved behavior patterns
bgi curate --graph bgi-graph.json --unresolved bgi-unresolved.jsonl
```

---

## CLI Commands

- `bgi scan` — full Gate 1→3 pipeline
- `bgi diff` — architecture diff between two roots
- `bgi curate` — propose COV token extensions from unresolved patterns

Common scan flags:

- `--lang auto`
- `--parallel --max-workers N`
- `--max-cluster-pct 0.03`
- `--fuse-graph fuse-graph.json`
- `--incremental --cache .bgi-cache.json`

---

## Interactive Search Stack (Phase 6)

BGI now includes an interactive index/query layer:

- `bgi.indexer.schema` — SQLite schema management
- `bgi.indexer.builder` — load Gate artifacts into index
- `bgi.indexer.planner` — ranked scope narrowing
- `bgi.indexer.api` — FastAPI endpoints:
  - `GET /api/symbols/{name}`
  - `GET /api/search?q=...`
  - `GET /api/callers/{symbol}`
  - `GET /api/callees/{symbol}`
  - `GET /api/stats`
  - `GET /api/health`
- `ide/vscode` — VS Code prototype (lookup symbol / prefix / callers)

App factory:

```python
from bgi.indexer.api import create_search_app

app = create_search_app("index.db")
```

---

## Benchmarks / Calibration Notes

Historical stress signals (from architecture cycle):

- FastAPI (4,509 units): largest cluster ~35%
- VS Code (75,131 units): 7.4M edges, largest cluster ~58%

These findings drove Spectral-Fuse adoption and quality-first prioritization.

Latest large validation:

- Kubernetes LOC: `3,627,208`
- Units: `162,954`
- Gate timings: Gate 1 `67.513s`, Gate 2 `138.869s`, Gate 3 `12.797s`
- Total: `219.179s`
- Max cluster: `1.113%`

---

## Supported Languages

Python, TypeScript, JavaScript, Java, Go, Rust, Ruby, C#, PHP, Kotlin, C, Scala, Lua, Elixir, Swift, R, Dart, Bash, Nim, Zig, Haskell, OCaml, F#, Clojure, Erlang, MATLAB, VB, Crystal, COBOL, Groovy, plus generic fallback mode.

---

## Documentation

- `MEMORANDUM.md` — design contracts and invariants
- `TASKPLAN.md` — implementation phases and status
- `bgi2.md` — convergence log for Spectral-Fuse architecture
- `docs/LANGUAGE_SUPPORT.md` — `.scm` language support guide
- `docs/CONTRIBUTING_LANGUAGES.md` — adding new languages
- `docs/INDEX_SCHEMA.md` — index schema design
- `docs/QUERY_PLANNER.md` — planner heuristics and scoring

---

## Development

```bash
# test suite
python3 -m pytest tests/ -x -q

# build VS Code prototype
npm --prefix ide/vscode install
npm --prefix ide/vscode run build
```
