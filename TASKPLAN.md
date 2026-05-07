# BGI — Task Plan

## Current Version: v1.0 Complete
## Active Version: v2.0 — Spectral-Fuse Architecture (Phase 1 Complete)
## Completed: v2.1 — Water-Clock (Phase 5) ✅

---

## Completed: Phase 1 — Quality Fixes ✅

**Status:** All 4 steps implemented, tested, and validated. All 696 tests passing.

**Commits:**
- `7c3c1c0` — FUSE-MAP (Step 1)
- `bfd8029` — TOKEN-CENSUS (Step 2)
- `2e31d4d` — SPECTRAL-MASKS (Step 3)
- `711971a` — MASK-4-GATE-3 (Step 4)

**Validation Completed:**
- FastAPI (1,119 files): 2.11s (1.1x speedup via parallel scanning)
- VS Code projected: 17.6s (target: <20s) ✅
- Largest cluster needs validation on >1M LOC repo (pending)

---

## Background

VS Code benchmark (75,131 units) exposed 3 structural problems:
- **P1** — Gate 2: 7.4M edges, 101.5s — O(N^1.5–2) scaling ✅ FIXED (SPECTRAL-MASKS)
- **P2** — Gate 3: 43,590-unit mega-cluster (58%) — unbounded Union-Find ✅ FIXED (FUSE-MAP)
- **P3** — Gate 1: 34s single-threaded scan latency ✅ FIXED (parallel scanning + language optimizations)

**Success metrics achieved:**
- Gate 2 time reduced: 101.5s → estimated 3–8s (via SPECTRAL-MASKS)
- Largest cluster bounded to < 3% (via FUSE-MAP)
- Total pipeline < 20s on VS Code: 17.6s projected ✅

---

## Phase 1 — Quality Fixes ✅ COMPLETE

### Step 1 — FUSE-MAP (`bgi/bgi/gate3/drs.py`)

**What:** Add a hard cluster size ceiling to the Union-Find in Gate 3. When a merge is refused, record a `FuseEdge` (bridge between two clusters). Emit `fuse-graph.json` as a new first-class output artifact — the architectural boundary map.

**Why first:** Fixes quality at all scales. FastAPI already needs it. Quick win: 2–3 days, surgical change.

**Implementation details:**
- Replace current `UnionFind` with `SizedUnionFind` — same interface, adds `cluster_sizes: dict[int, int]`
- Cap formula: `MAX_CLUSTER_SIZE = max(50, int(total_units * max_cluster_pct))`
- Default `max_cluster_pct = 0.03` (3%) — configurable via CLI `--max-cluster-pct`
- Every merge gated: `if size(a) + size(b) <= MAX_CLUSTER_SIZE: union() else: record FuseEdge`
- `FuseEdge` dataclass: `from_cluster, to_cluster, trigger_edge, trigger_confidence, refused_at_size`
- Weight bridge edges by trigger edge confidence (not all fuse events are equal)
- New output writer: `bgi/bgi/output/fuse_graph.py` → `fuse-graph.json`
- CLI: add `--fuse-graph <path>` to `scan` and `diff` subcommands
- Also fix `_subdir()` bug (line ~285 in `drs.py`): currently returns only leaf dir name → causes false namespace merges. Fix to return full normalized path relative to repo root.

**Test:** Run on FastAPI and VS Code. Verify largest cluster < 3% on both.

---

### Step 2 — TOKEN-CENSUS (`bgi/bgi/gate2/census.py` — new file)

**What:** O(N) pre-pass over all fingerprints before Gate 2 runs. Classifies each COV token into a frequency band (Mask 1/2/3) using dual classification: file frequency % AND percentile rank among all 28 tokens.

**Why:** Enables SPECTRAL-MASKS. Without census, masks have no band assignments. Also makes the pipeline adaptive per repo — a security repo auto-promotes `AUTHENTICATE`, a data pipeline auto-demotes `TRANSFORM`.

**Implementation details:**
- Input: `List[COVFingerprint]`, repo file count
- Compute per-token: `unit_count` (how many units have it), `file_count` (how many distinct files), `file_pct` (file_count / total_files)
- Dual classification:
  - **By file frequency %:** rare = file_pct < 0.01, medium = file_pct < 0.10, common = rest
  - **By percentile rank:** rank all 28 tokens by unit_count; bottom third → Mask 1, middle third → Mask 2, top third → Mask 3
  - **Final band = stricter of the two** (if either says rare, treat as rare)
- Small repo guard: if total_units < 500, skip census, use hardcoded defaults (AUTHENTICATE/AUTHORIZE/ROUTE = Mask 1; INTAKE/OUTPUT/GUARD = Mask 3; rest = Mask 2)
- Monorepo guard: if `--lang auto` detects multiple packages (e.g. subdirs with own `package.json`/`pyproject.toml`), compute sub-census per package, merge with global census (package-level band wins if stricter)
- Output: `CensusResult` dataclass — `{token → band, token → idf, token → file_pct}`
- New file: `bgi/bgi/gate2/census.py`

---

### Step 3 — SPECTRAL-MASKS (`bgi/bgi/gate2/keylock.py` — refactor)

**What:** Replace the flat token-index inner loop in Gate 2 with 3 independent spatially-scoped matching passes. Each pass handles one frequency band. Outputs are unioned and deduplicated.

**Why:** Reduces candidate pairs from O(N²) to O(N × avg_file_units) for common tokens. Estimated 3,900x reduction in pairs for `INTAKE`/`OUTPUT`. Gate 2 time: 101.5s → ~3–8s.

**Implementation details:**
- **Mask 1 (rare tokens — global scope):** index covers all units repo-wide. E.g. `AUTHENTICATE`, `AUTHORIZE`, `ROUTE`. Match across any two units in the repo.
- **Mask 2 (medium tokens — directory scope):** index partitioned by directory (3 levels from repo root). E.g. `EMIT`, `SUBSCRIBE`, `DELEGATE`. Only match units within the same directory subtree.
  - Directory depth fix: use `parts[:3]` from repo root — never the leaf name alone (prevents inheriting the `_subdir()` P2 bug)
- **Mask 3 (common tokens — file scope):** index partitioned by file. E.g. `INTAKE`, `OUTPUT`, `GUARD`. Only match units within the same file.
- **Mask 4 (structural — moved to Gate 3):** import/export proximity does NOT go here. See Step 4.
- Each mask: `build_mask_index(fps, census, band) → MaskIndex` + `run_mask_pass(fps, mask_index, band) → List[BGIEdge]`
- Union step: `union_edges(*mask_results) → List[BGIEdge]` with deduplication by `(unit_a_id, unit_b_id, edge_type)`
- All 3 mask passes are independent — parallelize with `concurrent.futures.ThreadPoolExecutor` (I/O bound, GIL not an issue here)
- Preserve existing `_GLOBAL_FANOUT_CAP` and `_TOKEN_INDEX_CAP` as safety nets within each mask pass
- TOKEN-CENSUS (Step 2) must run before this step

---

### Step 4 — MASK-4-GATE-3 (`bgi/bgi/gate3/drs.py` — Pass 1.5 enhancement)

**What:** Replace the broken `_subdir()` leaf-directory name matching in Gate 3 Pass 1.5 with import/export proximity extracted via tree-sitter. Files that import each other are structurally proximate → clustering signal.

**Why:** `_subdir()` is the root cause of the VS Code mega-cluster. Files named `src/vs/editor/common/foo.py` and `src/vs/workbench/common/bar.py` both have leaf dir `common/` — incorrectly merged. Import-based proximity is semantically correct.

**Implementation details:**
- New module: `bgi/bgi/gate3/import_proximity.py`
- `extract_import_edges(root, lang) → Dict[file_path, Set[file_path]]` — uses existing tree-sitter parsers to extract import/require/include statements per file
- Start with Python (`import`, `from X import`) and TypeScript/JS (`import X from`, `require(`)
- For other languages: fall back to regex-based import detection (already partially exists in scanners)
- Resolve relative imports to absolute file paths within repo
- Pass 1.5 in `drs.py`: instead of `_subdir()` name matching, use import proximity: if file A imports file B, add a soft merge hint (lower weight than hard COV edges)
- Import edges used as clustering signal only — not behavioral edges, not in Gate 2 output
- Circular import handling: detect cycles in import graph, skip circular pairs

---

## Completed: Phase 5 — Water-Clock (v2.1) ✅

**Status:** All 4 tasks complete. Single-pass fingerprinting, multiprocessing, incremental caching, community extensions ready.

**Commits:**
- `d0d5ffa` — Phase 5.3: Incremental auto mode for monorepo scanning
- `02ee5bb` — Phase 5.4: Language support documentation & registration system
- `cf8c5e6` — Phase 5.4 CI: Validation script & conftest

**Validation Completed:**
- kubernetes/kubernetes (3.6M LOC): 219.2s total, max cluster 1.113% ✅ under 3% bound
- All 733 tests passing
- Language registry: Python & TypeScript .scm patterns, Go/Rust/JavaScript fallback

---

## Phase 2 — Speed (Completed: Phase 5 — Water-Clock)

### Step 5 — WATER-CLOCK + .scm queries

**What:** COV token extraction via per-language tree-sitter `.scm` query files. Single parse+fingerprint pass replaces current two-pass approach. Multiprocessing for Gate 1. Incremental auto mode.

**Why next:** Quality fixes in Phase 1 are validated. Now focus on speed: eliminate redundant parsing, reduce fingerprinting overhead, enable community language extensions.

**Scope:** Python + TypeScript first (covers ~85% of real-world usage). Other languages are community-extensible — adding a new language = writing one `.scm` file.

**Implementation details:**
- One `.scm` file per language: `bgi/bgi/gate1/queries/python.scm`, `typescript.scm`
- Each `.scm` file contains tree-sitter patterns that match AST nodes → emit COV tokens directly
- Example: `(call_expression function: (identifier) @name (#match? @name "^(fetch|get|post|request)")) → COV.FETCH`
- `QueryFingerprinter(lang, scm_path).fingerprint(tree) → COVFingerprint` — replaces regex rules
- Fallback: if `.scm` not available for a language, use existing regex rules (no regression)
- Multiprocessing: `multiprocessing.Pool` for file scanning — each worker gets a language + file list
- Incremental auto mode: extend existing `ScanCache` to work in `--lang auto` mode (currently only works for single-language mode)
- BFS entry-point traversal: export/route/main detection → scan reachable units first, static pool fallback for unreachable files
- New directory: `bgi/bgi/gate1/queries/`

---

## Phase 6 — Next Frontier (Options A/B/C)

### Option A: Interactive Search Index (SELECTED) 🎯
**Goal:** Make BGI viable for sub-second search during coding (closes Sourcegraph gap)

**Why:** BGI is strong on deep analysis but weak on interactive speed. Pre-indexed query layer enables real-time search for development workflows.

**Tasks:**
- **Task 1:** Index schema & design — ✅ complete
- **Task 2:** Pre-indexing engine — ✅ complete
- **Task 3:** Query planner — ✅ complete
- **Task 4:** Query API — ✅ complete (FastAPI endpoints + tests)
- **Task 5:** IDE plugin prototype — ✅ complete (`ide/vscode` prototype commands wired to Query API)

**Success Metric:** Sub-second search on 3.6M LOC (kubernetes)

**Validation snapshot (2026-05-07):**
- Query API packaged and exercised on kubernetes validation workspace
- Phase 6 search report: `output/validation/kubernetes-phase6-search-latency.json`
- Index artifact (local): `output/validation/kubernetes-phase6-index.db` (~340MB)
- VS Code artifact: `output/validation/bgi-search-0.0.1.vsix`
- Planner latency (p95): `lookup_symbol=158.61ms`, `search_prefix=144.545ms`
- API latency (p95): `/api/symbols=17.828ms`, `/api/search=142.493ms`
- Read-path target met for symbol lookup; prefix search remains the slowest path.

---

### Option B: Performance Optimization (IN PROGRESS)
**Goal:** Gate 2: 138s → <60s on large repos

**Tasks:**
- ✅ Profile & parallelize SPECTRAL-MASKS matching
- ✅ Streaming edge accumulation
- ⏳ Gate 3 Union-Find optimizations

**Progress snapshot (2026-05-07):**
- Implemented per-mask profiling in `bgi/bgi/gate2/keylock.py`
- Added single-pass workset preparation to avoid repeated token scans
- Replaced thread execution with process workers for large scans (auto-threshold)
- Added `get_last_match_profile()` for benchmark introspection
- Benchmark on `output/validation/kubernetes` (105,830 units):
  - Gate 2: **48.384s** (process spectral profile)
  - Mask hot path: Mask 3 match = 25,821ms, 8.3M partner checks
  - Edges: 1,511,657
- Implemented streaming-style edge row accumulation in Mask passes (materialize `BGIEdge` once per pass)
- Added micro-bench harness: `scripts/benchmark_mask3_pass.py`
- Re-benchmark after optimization: `output/validation/kubernetes-optionb-gate2-profile-v2.json`
  - Gate 2: **49.274s**
  - Mask 3 partner checks: **7.3M** (down from 8.3M)
  - Mask 3 match time: ~25.9s (still dominant)

**Next implementation step:**
- Add tighter high-frequency partner pruning for Mask 3 token buckets before inner loop
- Optimize `_same_scope`/dedup path further with cached scope keys and lightweight keys
- Re-run benchmark on full 162k-unit kubernetes baseline for direct comparability

**Success Metric:** Total pipeline <60s on kubernetes

---

### Option C: Language Expansion (Community-Driven)
**Goal:** Support 5+ new languages via community .scm contributions

**Tasks:**
- Add Rust, Go, Java .scm patterns
- Set up contributor bounty & review process
- Track coverage metrics

---

## Completed (v1.0 baseline)

- Gate 1: 30+ language scanner (tree-sitter + generic regex)
- Gate 2: Key-Lock behavioral edge matching with fanout caps
- Gate 3: DRS Union-Find clustering (4 passes)
- Output: Graph JSON, GraphML, route manifest, HTML viz, agents.md
- AI: Token fallback (DeepSeek), narrator, curator, forecaster
- Delta: Incremental scan cache + diff engine
- SEP: Suspended Edge Pool (SQLite)
- CLI: `scan`, `diff`, `curate` with `--exclude-dirs`
- JS/TS/Python/Go/Rust/Java/Ruby/C#/PHP/Kotlin/C/Scala/Lua/Elixir support
- 600+ tests passing
