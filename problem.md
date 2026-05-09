# BGI — Scale Problems: VS Code Benchmark Report

**Prepared by:** BGI Development Team  
**Date:** 2026-05-06  
**Benchmark target:** Microsoft VS Code (`github.com/microsoft/vscode`, shallow clone)  
**Submitted to:** Google Engineering Review  

---

## Executive Summary

BGI (Big Indexer) is a language-agnostic hierarchical code intelligence pipeline. When run against VS Code — approximately 1 million lines of TypeScript across 9,792 source files — three critical scalability problems emerged:

| Problem | Symptom | Impact |
|---------|---------|--------|
| **P1** | Gate 2 produces 7.4 million edges in 101 seconds | Unacceptable CI latency for large repos |
| **P2** | Largest cluster contains 43,590 of 75,131 units (58%) | Cluster is too coarse for architectural signal |
| **P3** | Gate 1 scans 75,131 units in 34 seconds | Acceptable today, will bottleneck beyond 200k units |

This document explains what BGI does at each stage, then deeply analyses each problem with current code pointers, root cause, and suggested solution directions.

---

## Part 1 — What BGI Does (System Overview)

### 1.1 Purpose

BGI does not parse code semantics. It fingerprints **behavioral intent** — what a code unit *does*, not what it *is*. The output is a confidence-scored architecture graph optimized for AI agent consumption: cluster summaries, route manifests, event graphs, and cross-boundary seam detection.

### 1.2 The Pipeline

```
Source files  (any language)
      │
      ▼
[Gate 1]  COV Fingerprinting
      │    Reads each function/method using a language-specific AST scanner
      │    (tree-sitter for Python/TS/JS; regex+heuristic for 15+ other languages)
      │    Assigns 1–5 COV tokens per unit from a fixed vocabulary of 28 tokens
      │    Output: List[COVFingerprint]
      │
      ▼
[Gate 2]  Key-Lock Matching
      │    Pairs fingerprints whose tokens form complementary relationships
      │    (e.g. FETCH ↔ PERSIST, EMIT ↔ SUBSCRIBE, AUTHENTICATE ↔ ROUTE)
      │    Output: List[BGIEdge] (typed HARD / PREDICTED / GHOST)
      │             + List[SuspendedEdge] (unresolved outward references)
      │
      ▼
[Gate 3]  DRS — Dynamic Radar Scope clustering
      │    Groups units into clusters via 4-pass algorithm:
      │      Pass 1: within-file proximity (radar line window)
      │      Pass 1.5: cross-file namespace merge (shared directory + tokens)
      │      Pass 2: cross-file merge via HARD edges
      │      Pass 3: probability scoring + cluster hardening
      │      Pass 4: seam finalization (architectural boundary detection)
      │    Output: DRSResult (clusters, unit→cluster map, seam units)
      │
      ▼
[SEP]     Suspended Edge Pool  (SQLite)
          Stores unresolved references across scan runs; attempts resurrection
          when new scans bring in missing lock counterparts
      
      ▼
[Output]  Graph JSON + optional Route Manifest + GraphML + HTML visualization
          agents.md: natural-language architecture narration for AI agents
```

### 1.3 The COV Vocabulary

BGI uses exactly **28 tokens** (Canonical Operation Vocabulary). Every code unit is assigned a subset of these based on what it does:

| Category | Tokens |
|----------|--------|
| Data Flow | `INTAKE` `OUTPUT` `TRANSFORM` `MUTATE` `SANITIZE` |
| Control Flow | `CONDITIONAL` `LOOP` `GUARD` `ROUTE` `SCOPE` |
| State | `FETCH` `PERSIST` |
| Communication | `EMIT` `SUBSCRIBE` `DELEGATE` |
| Structure | `CONTRACT` `COMPOSE` `INIT` `TEARDOWN` |
| Error | `RAISE` `RECOVER` `DEFER` |
| Cross-cutting | `AUTHENTICATE` `AUTHORIZE` `VALIDATE` `LOG` `MEASURE` `ASYNC` |
| Testing | `TEST` |

**Edge-forming tokens** (14 of 28) participate in Gate 2 matching. The rest are **characterization tokens** used only in Gate 3 probability scoring.

**Key-Lock pairs** (the 14 edge-forming relationships):

```
INTAKE     ↔  OUTPUT
FETCH      ↔  PERSIST
EMIT       ↔  SUBSCRIBE
RAISE      ↔  RECOVER
INIT       ↔  TEARDOWN
INIT       ↔  DEFER
TEST       ↔  CONTRACT
VALIDATE   →  INTAKE
SANITIZE   →  INTAKE
GUARD      →  CONTRACT  (multi-pair)
GUARD      →  INTAKE    (multi-pair)
AUTHENTICATE → ROUTE
AUTHORIZE    → ROUTE
DELEGATE   →  CONTRACT
```

### 1.4 Benchmark Numbers

| Metric | FastAPI (4,509 units) | VS Code (75,131 units) |
|--------|----------------------|------------------------|
| Gate 1 | 1.8s | 34.0s |
| Gate 2 | 5.4s | 101.5s |
| Gate 3 | 0.2s | 8.9s |
| **Total** | **7.4s** | **144.4s** |
| Edges | 197k | 7.4 million |
| Clusters | 243 | 1,156 |
| Largest cluster | 1,580 (35%) | **43,590 (58%)** |

---

## Part 2 — Problem 1: Gate 2 Edge Explosion

### 2.1 What Gate 2 Does

Gate 2 builds a **token index** — a dictionary mapping each COV token to all fingerprints that contain it — then emits edges by checking each fingerprint's tokens against the index of their complementary tokens.

**Simplified pseudocode (current implementation, `bgi/gate2/keylock.py`):**

```python
# Step 1: Build index
token_index: dict[COV, list[COVFingerprint]] = {}
for fp in fingerprints:
    for token in fp.all_tokens():
        if is_edge_forming(token):
            token_index[token].append(fp)

# Step 2: Match
for fp_a in fingerprints:              # O(N)
    for token_a in fp_a.all_tokens():  # O(T) — small constant
        for lock_token in LOCK_MAP[token_a]:
            for fp_b in token_index[lock_token]:  # O(M) — the problem
                emit_edge(fp_a, fp_b)
```

**Stated complexity:** `O(N × T × M)` where T = avg tokens/unit, M = avg matches/token.

**The claim that T and M are "small constants" breaks at scale.**

### 2.2 Root Cause

In VS Code, certain COV tokens are **extremely high-frequency**:

| Token | Estimated units in VS Code | Notes |
|-------|--------------------------|-------|
| `INTAKE` | ~50,000+ | Nearly every function takes a parameter |
| `OUTPUT` | ~45,000+ | Nearly every function returns a value |
| `ASYNC` | ~15,000+ | VS Code is heavily async/event-driven |
| `GUARD` | ~20,000+ | Validation/null-checks everywhere |
| `CONTRACT` | ~10,000+ | Interfaces and type contracts pervasive |

When `INTAKE` appears in 50,000 units and `OUTPUT` appears in 45,000 units, the inner loop tries to produce **50,000 × 45,000 = 2.25 billion** candidate pairs for just this one token pair alone.

### 2.3 Current Mitigations (Not Enough at This Scale)

Two caps were added after the FastAPI benchmark:

```python
_GLOBAL_FANOUT_CAP = 100   # per (unit, token) combo: stop emitting after 100 partners
_TOKEN_INDEX_CAP   = 500   # if a token has >500 entries, trim bucket (keep same-file first)
```

Additionally, **scope-constrained pairs** skip the inner loop for cross-scope units:

```python
_CLASS_SCOPED_PAIRS = {
    (COV.INTAKE, COV.OUTPUT),   # only match within same class or same file
    (COV.GUARD, COV.INTAKE),
    ...
}
```

**Why it's still not enough at 75k units:**

Even with the 500-entry cap on token buckets and the 100-partner fan-out cap, the number of *surviving* pairs is still proportional to:

```
N_files × 500 (capped bucket) × 100 (fanout cap) = O(N × 50,000) candidate evaluations
```

At 75k units this produces ~7.4 million edges and 100 seconds of compute. The cap is architecturally wrong: it truncates the bucket to the first 500 file-groups rather than the 500 *most semantically similar* units. This means edge quality degrades arbitrarily.

### 2.4 Suggested Solution Directions

**Option A — Locality-hash bucketing (preferred)**

Instead of a flat token index, build a **two-level index**: `token → {file_hash_bucket → list[fp]}`. When emitting edges, only match within the same or adjacent bucket. A bucket is a content-addressable hash of the file's directory path (e.g. `src/vs/workbench/` hashes to the same bucket). This gives O(1) local lookups and eliminates global fan-out entirely for `INTAKE`/`OUTPUT`.

```
token_index[INTAKE]["src/vs/workbench"] = [fp1, fp2, ...]
token_index[INTAKE]["src/vs/platform"]  = [fp3, fp4, ...]
# When matching fp_a (in workbench): only look at workbench bucket, not all 50k
```

**Option B — MinHash / LSH similarity pre-filter**

Before Gate 2, compute a MinHash sketch of each fingerprint's token set. Use Locality Sensitive Hashing to partition fingerprints into similarity bands. Gate 2 only matches within bands, guaranteeing that the inner loop size is bounded by the band width regardless of repo size.

**Option C — Sparse edge sampling with importance weighting**

Treat the token index as a sparse bipartite graph. Use a weighted sampling strategy: emit the top-K edges by confidence score (weighted by token rarity — rare tokens like `AUTHENTICATE` get higher weight than ubiquitous `INTAKE`). K is fixed (e.g. 20 per unit), giving O(N × K) total edges regardless of scale.

**Option D — Inverted frequency weighting (TF-IDF analogy)**

Borrow from information retrieval. A token that appears in 90% of all units has near-zero discriminative value (like "the" in a document). Weight each token by `log(N / df)` where `df` is the document frequency of that token. Only emit edges for token pairs whose combined weight exceeds a threshold. `INTAKE ↔ OUTPUT` effectively drops out; `AUTHENTICATE ↔ ROUTE` remains.

**Recommended approach:** Combine A + D. Locality bucketing for the inner loop bound, plus IDF weighting to suppress universally-common token pairs entirely at the matching phase.

### 2.5 Desired Outcome

| Metric | Current (75k units) | Target |
|--------|-------------------|--------|
| Gate 2 time | 101.5s | < 10s |
| Edge count | 7.4 million | 500k–1M (meaningful only) |
| Edge quality | Degraded by arbitrary truncation | Preserved by semantic weighting |

---

## Part 3 — Problem 2: Gate 3 Mega-Cluster

### 3.1 What Gate 3 Does

Gate 3 runs **DRS — Dynamic Radar Scope** clustering. It groups code units into architectural clusters through 4 passes:

**Pass 1 (within-file proximity):** For each file, units are sorted by line number. A "radar window" of N lines rolls forward. Units within the window are merged into the same cluster. The window size is proportional to the unit's COV token prior (high-signal tokens like `ROUTE`, `CONTRACT` get a larger radar than `LOOP` or `LOG`).

**Pass 1.5 (namespace merge):** Units in the same subdirectory that share a high-prior COV token (prior ≥ 0.7) are merged cross-file. This correctly groups `auth/login.py`, `auth/middleware.py`, `auth/tokens.py` together.

**Pass 2 (HARD edge merge):** Units connected by HARD-confidence edges are merged cross-file, but only for specific token pairs that justify cross-boundary merging: `DELEGATE↔CONTRACT`, `EMIT↔SUBSCRIBE`, `AUTHENTICATE↔ROUTE`, `AUTHORIZE↔ROUTE`.

**Pass 3 (probability scoring):** Each cluster gets a probability score 0.0–1.0 based on its dominant COV token priors, edge count (velocity), cross-file span, and size. Clusters scoring ≥ 0.85 with ≥ 2 members are "hard" clusters.

**Pass 4 (seam finalization):** Units that scored equally between two clusters during Pass 1 are confirmed as architectural seams — boundary points auto-detected without human labeling.

### 3.2 Root Cause of the Mega-Cluster

VS Code's result: **1 cluster containing 43,590 units (58% of all units)**.

This is caused by a **transitive closure explosion** in the Union-Find structure used across all passes.

The problem is not a single bad merge — it is a chain reaction:

1. **Pass 1 (within-file):** VS Code's `src/vs/workbench/` contains files with thousands of lines. Within a single large file, all units get merged into one cluster (correct behavior).

2. **Pass 1.5 (namespace):** `src/vs/workbench/` is a single subdirectory name. All files in it share the same `subdir` key. Hundreds of workbench files all have `CONTRACT` or `INIT` tokens (prior ≥ 0.7). All their representatives are merged together. This is the first explosion.

3. **Pass 2 (HARD edges):** The now-giant workbench cluster has units with `DELEGATE` and `CONTRACT` tokens. Any other part of the codebase (`platform/`, `editor/`) that emits or receives these tokens gets merged into the same Union-Find root.

4. **Result:** The Union-Find transitively connects most of the codebase through a sequence of individually-reasonable merges.

**The core algorithmic flaw:** Union-Find with no size ceiling. Once a cluster is large, it becomes a "gravity well" — every subsequent merge candidate with any shared token gets pulled in, making the cluster exponentially more likely to absorb the next unit.

**Secondary cause:** Pass 1.5 uses only the **immediate parent directory name** (`_subdir` returns `parts[-2]`). For VS Code, `src/vs/workbench/browser/parts/editor/` all return `editor` as their subdir — but so does `src/vs/workbench/contrib/editor/`. Different architectural components share the same directory leaf name and incorrectly merge.

```python
# Current (broken for deep trees):
def _subdir(unit_id: str) -> str:
    parts = unit_id.split("::")[0].split("/")
    return parts[-2] if len(parts) >= 2 else ""
# Returns "editor" for both:
#   src/vs/workbench/browser/parts/editor/editorPane.ts
#   src/vs/workbench/contrib/editor/browser/editorInput.ts
```

### 3.3 Suggested Solution Directions

**Option A — Cluster size cap with sub-clustering (preferred)**

Impose a maximum cluster size `MAX_CLUSTER_SIZE` (e.g. 500 units). When a Union-Find merge would exceed this limit, instead of merging:
1. Record the edge as a "bridge edge" between two clusters
2. Emit a cross-cluster edge in the output graph
3. Never merge; keep the clusters separate

This gives predictable output size regardless of repo scale. For the architecture graph, bridge edges are more useful than a mega-cluster anyway.

**Option B — Full path hash for namespace matching**

Replace the leaf-directory subdir key with the **full normalized path up to depth K** from the repo root:

```python
def _subdir_path(unit_id: str, depth: int = 3) -> str:
    parts = unit_id.split("::")[0].split("/")
    return "/".join(parts[:depth]) if len(parts) >= depth else "/".join(parts[:-1])
# Returns "src/vs/workbench" for both files above — correct grouping
# Returns "src/vs/platform" for platform files — no spurious merge
```

This immediately eliminates the Pass 1.5 explosion for deep-tree repos.

**Option C — Hierarchical clustering (two-level DRS)**

Run DRS in two passes at different granularities:
- **Level 1 (micro):** Cluster within each file (current Pass 1)
- **Level 2 (macro):** Cluster micro-clusters by directory and token similarity

The Level 2 graph has O(files) nodes instead of O(units) nodes, making the namespace merge problem tractable even for 10,000 files.

**Option D — Merge probability threshold**

Before every Union-Find merge in Pass 2, compute whether the merge is "worth it" using a score:

```
merge_score = edge.confidence × (1 / (cluster_a.size + cluster_b.size))
```

Only merge if `merge_score > THRESHOLD`. This naturally prevents small clusters from being absorbed into already-giant ones, because the size penalty increases with cluster size.

**Option E — Anchor-based clustering**

Identify "anchor" units — units with architecturally rare/high-signal tokens like `AUTHENTICATE`, `AUTHORIZE`, `ROUTE`, `CONTRACT`. Build clusters outward from anchors, never merging two clusters that have different anchors (they represent different architectural components).

**Recommended approach:** B + A. Fix the subdir hash immediately (trivial, high impact). Then add a cluster size cap with bridge-edge output for the remaining cases.

### 3.4 Desired Outcome

| Metric | Current (75k units) | Target |
|--------|-------------------|--------|
| Largest cluster | 43,590 (58%) | < 2,000 (< 3%) |
| Cluster count | 1,156 | 3,000–8,000 (meaningful granularity) |
| Gate 3 time | 8.9s | < 5s |
| Seam detection | Partially functional | Fully functional (obscured by mega-cluster) |

---

## Part 4 — Problem 3: Gate 1 Scan Latency

### 4.1 What Gate 1 Does

Gate 1 reads every source file in the repository and produces a `COVFingerprint` for each function/method. For Python and TypeScript/JavaScript, it uses a **tree-sitter AST parser**. For 15+ other languages (Go, Java, Rust, C, Ruby, etc.), it uses a **hybrid generic scanner** — regex patterns to locate function boundaries, then heuristic rules to detect COV tokens from keyword patterns and API call signatures.

For each function, Gate 1:
1. Extracts the function signature, parameter list, decorators, and body
2. Applies 5 rule tiers in order (Tier 1: decorator patterns, Tier 2: function name patterns, Tier 3: body call patterns, Tier 4: return type patterns, Tier 5: class inheritance context)
3. Assigns confidence 0.0–1.0 to each token
4. If no tier assigns a token with confidence ≥ 0.6, hands off to AI fallback (Position 1)
5. Returns a `COVFingerprint` with unit_id, tokens, confidence, line range, and source

### 4.2 Current Performance

VS Code Gate 1: **75,131 units in 34 seconds** = ~2,200 units/second.

For comparison:

| Repo scale | Units | Estimated time |
|------------|-------|----------------|
| FastAPI | 4,509 | 1.8s ✅ |
| VS Code | 75,131 | 34s ✅ (borderline) |
| Django | ~200,000 | ~90s ⚠️ |
| Linux kernel (C) | ~500,000 | ~225s ❌ |
| Kubernetes | ~1,500,000 | ~680s ❌ |

At 34s, Gate 1 is currently acceptable for a one-time scan. It becomes a CI bottleneck for incremental workflows if file change detection doesn't work or the repo is very large.

### 4.3 Root Causes

**Cause A — Single-threaded sequential scan**

`scan_repository()` is a single-threaded loop over all files:

```python
for dirpath, dirnames, filenames in root.walk():
    for fname in sorted(filenames):
        fps = _scan_file_auto(file_path, root, ai)  # blocking, sequential
        fingerprints.extend(fps)
```

Each file scan is independent. There is no shared state between file scans. This is embarrassingly parallel.

**Cause B — Tree-sitter parser instantiation overhead**

For Python, the tree-sitter parser is a module-level singleton:

```python
_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)
```

But for TypeScript and JavaScript (called via `_scan_file_auto`), the scanner modules are **lazily imported per call**:

```python
if language == "typescript":
    from bgi.gate1.ts_scanner import scan_file_ts   # imported fresh each time
    return scan_file_ts(file_path, root, ai)
```

Python caches module imports, so this is only a cost on first call. However, if Gate 1 is parallelized (see below), each worker process would re-import and re-initialize parsers, multiplying this overhead.

**Cause C — No file-level parallelism**

The incremental scan (`--incremental` flag) handles re-scan avoidance via file hash caching, but it only operates on a per-language basis. In `--lang auto` (multi-language) mode, incremental scanning is not available:

```python
if incremental and not auto_mode:   # incremental ONLY works in single-language mode
    ...
elif auto_mode:
    fingerprints = scan_repository(root_path, ai=ai, scan_run=scan_run)
```

This means every `--lang auto` scan (the most useful mode for large repos) is always a full cold scan.

### 4.4 Suggested Solution Directions

**Option A — Multiprocessing worker pool (high impact, medium complexity)**

Partition files into N chunks (one per CPU core). Each worker process receives a chunk of file paths, imports its own parser instances, scans its files, and returns fingerprints. Use Python's `multiprocessing.Pool` with `starmap`.

```python
from multiprocessing import Pool, cpu_count

def _scan_worker(file_paths, root, lang):
    ai = AIFallback(enabled=False)
    result = []
    for fp in file_paths:
        result.extend(_scan_file_auto(fp, root, ai))
    return result

chunks = partition(all_files, cpu_count())
with Pool(cpu_count()) as pool:
    batches = pool.starmap(_scan_worker, [(chunk, root, lang) for chunk in chunks])
fingerprints = [fp for batch in batches for fp in batch]
```

Expected speedup: 4–8x on a typical machine (4–8 cores). VS Code Gate 1: 34s → ~5–8s.

**Option B — Incremental scan in auto mode (high impact, low risk)**

Extend the existing `ScanCache` (already implemented for single-language mode) to work in `--lang auto` mode. The cache stores per-file hashes and cached fingerprints. On re-scan, only dirty files are re-processed.

For a CI pipeline checking a PR with 20 changed files out of 9,792, this reduces Gate 1 to near-zero (only the 20 changed files are scanned).

**Option C — Async I/O with `asyncio` / `concurrent.futures`**

For I/O-bound file reading (especially on network filesystems), use `concurrent.futures.ThreadPoolExecutor`. Tree-sitter parsing is CPU-bound (not helped by GIL-releasing threads), but file reading is I/O-bound and would benefit.

**Option D — Pre-compiled COV rule cache**

The rule application logic (Tiers 1–5) recompiles regex patterns on every scan run. Pre-compile all patterns once at module load time and cache the compiled objects. This is a low-effort, low-risk ~10–15% speedup.

**Recommended approach:** B immediately (fixes CI use case without any architectural change), then A for full cold-scan speed.

### 4.5 Desired Outcome

| Metric | Current (75k units) | Target |
|--------|-------------------|--------|
| Cold scan | 34s | < 8s (multiprocessing) |
| Incremental scan (20 changed files) | 34s (full rescan) | < 2s |
| 500k-unit repo (cold) | ~225s (estimated) | < 30s |

---

## Part 5 — Interaction Between Problems

The three problems are coupled:

```
P1 (edge explosion)
    │
    └──► feeds P2 (mega-cluster)
         More edges = more Union-Find merges = larger clusters
         Capping edges incorrectly = wrong cluster boundaries
         
P3 (scan latency)
    │
    └──► multiplies with P1
         Slower Gate 1 means full-repo rescans stay expensive
         Without incremental scan in auto mode, every CI run hits P3 + P1 + P2
```

**Fix ordering recommendation:**

1. **P2-B first** (full path subdir fix) — 2-line code change, immediate impact, eliminates most of the mega-cluster
2. **P2-A** (cluster size cap) — adds the ceiling guarantee
3. **P3-B** (incremental auto mode) — eliminates CI rescan cost
4. **P1-D** (IDF token weighting) — reduces edge count by eliminating low-signal pairs
5. **P1-A** (locality bucketing) — final edge quality + speed fix
6. **P3-A** (multiprocessing Gate 1) — only needed for >200k unit repos

---

## Part 6 — Code Pointers

| Problem | File | Key Lines |
|---------|------|-----------|
| P1 fan-out caps | `bgi/gate2/keylock.py` | Lines 98–99 (`_GLOBAL_FANOUT_CAP`, `_TOKEN_INDEX_CAP`) |
| P1 inner loop | `bgi/gate2/keylock.py` | Lines 174–230 (nested for loops) |
| P1 scope-constrained pairs | `bgi/gate2/keylock.py` | Lines 79–88 (`_CLASS_SCOPED_PAIRS`) |
| P2 subdir hash (broken) | `bgi/gate3/drs.py` | Lines 283–286 (`_subdir()` function) |
| P2 namespace merge | `bgi/gate3/drs.py` | Lines 275–320 (Pass 1.5) |
| P2 Union-Find merge | `bgi/gate3/drs.py` | Lines 350–369 (Pass 2) |
| P2 no size ceiling | `bgi/gate3/drs.py` | Lines 371–410 (Pass 3, Cluster construction) |
| P3 sequential file scan | `bgi/gate1/scanner.py` | Lines 534–546 (`scan_repository` inner loop) |
| P3 no incremental auto | `bgi/pipeline.py` | Lines 36–37 (`if incremental and not auto_mode`) |
| COV vocabulary | `bgi/core/cov.py` | Full file (28 tokens + KEY_LOCK_PAIRS) |

---

## Part 7 — Benchmark Reproduction

To reproduce the VS Code benchmark:

```bash
# Clone VS Code (shallow)
git clone --depth=1 https://github.com/microsoft/vscode.git /tmp/vscode

# Install BGI
cd /path/to/bgi && pip install -e .

# Run full pipeline benchmark
python3 -c "
import time, sys
from pathlib import Path
from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.scanner import scan_repository
from bgi.gate2.keylock import match_fingerprints
from bgi.gate3.drs import run_drs

root = Path('/tmp/vscode')
ai = AIFallback(enabled=False)

t0 = time.time()
fps = scan_repository(root, ai=ai, exclude_dirs={'node_modules', '.build', 'out'})
t1 = time.time()
edges, _ = match_fingerprints(fps)
t2 = time.time()
drs = run_drs(fps, edges)
t3 = time.time()

sizes = sorted([c.size for c in drs.clusters], reverse=True)
print(f'Units: {len(fps)}, Edges: {len(edges)}, Clusters: {len(drs.clusters)}')
print(f'Gate 1: {t1-t0:.1f}s, Gate 2: {t2-t1:.1f}s, Gate 3: {t3-t2:.1f}s')
print(f'Largest 5 clusters: {sizes[:5]}')
"
```

Expected output (current code):
```
[BGI] scan_repository: 75131 units [bash:52, javascript:334, rust:755, typescript:73990]
Units: 75131, Edges: 7412628, Clusters: 1156
Gate 1: 34.0s, Gate 2: 101.5s, Gate 3: 8.9s
Largest 5 clusters: [43590, 1153, 932, 808, 764]
```

---

## Appendix — BGI Repository

- **Repository:** `https://github.com/ahmedxuhri/bigindexer`
- **Language:** Python 3.10+
- **Dependencies:** tree-sitter, tree-sitter-python, tree-sitter-typescript, tree-sitter-javascript
- **Test suite:** `python3 -m pytest tests/ -x -q` (600 tests, 1.9s)
- **Architecture doc:** `bgi/memorandum-of-acts.md` (full design contracts and invariants)
