# BGI Query Planner — Scope Narrowing for Real-Time Search

## Overview

The Query Planner enables **sub-100ms lookups** on pre-indexed code graph by narrowing search scope intelligently. Instead of scanning all 160K+ units on large repos, it prunes the candidate set using:

1. **Token frequency heuristics** — symbols are not equally common
2. **Caller/callee patterns** — call graph topology predicts relevance
3. **Locality bias** — nearby units more likely to be relevant
4. **Fingerprint matching** — COV token overlap filters false matches
5. **File proximity** — same package/directory → higher rank

## Architecture

```
Query: "fetch_user"
  ↓
[Token Analyzer]        → Detect language, split tokens
  ↓
[Candidate Filter]      → Symbol index returns matching units (N=50–200 typical)
  ↓
[Scope Narrower]        → Apply ranking & pruning heuristics
  ├─ Frequency score (how common is this symbol?)
  ├─ Caller/callee bias (edges in call graph)
  ├─ Locality score (distance from context)
  ├─ Fingerprint overlap (COV token match)
  └─ Package boundary (same directory?)
  ↓
[Ranking]               → Sort by combined score, return top-K
  ↓
Result: [unit_id, score, reasoning]
```

## Heuristics & Scoring

### 1. Frequency Score
Rare symbols are more likely to be what user is searching for.

```python
# Token frequency across all units
freq = count(units with token)
frequency_score = 1.0 / (1.0 + log(freq))

# Example:
# "fetch" appears in 500 units → score ≈ 0.33
# "obscure_function_xyz" appears in 2 units → score ≈ 0.95
```

**Impact:** ×2–3 boost for rare symbols

### 2. Caller/Callee Bias
If a unit is frequently called in the codebase, it's more likely the target.

```python
# In-degree (how many units call this one?)
in_degree = len(incoming_edges)

# Out-degree (how many units does this call?)
out_degree = len(outgoing_edges)

# Exported symbols get boost
export_boost = 1.5 if is_exported else 1.0

# Callee score: popular exports are usually targets
callee_score = min(in_degree / 10.0, 1.0) * export_boost
```

**Impact:** ×1.5–2.0 for exported high-fanin units

### 3. Locality Bias
Units in same file/package as context are more relevant.

```python
# Distance scoring (lower is better)
distance = tree_distance(context_unit, candidate_unit)

# Scores:
# - Same file → 1.0
# - Same package → 0.8
# - Same directory → 0.6
# - Transitively reachable (1–2 hops) → 0.4
# - Remote → 0.1

locality_score = locality_map.get(distance, 0.1)
```

**Impact:** ×1.5–2.0 boost for same-file/package units

### 4. Fingerprint Matching (COV Tokens)
Units with matching COV tokens likely have related behavior.

```python
# Overlap of fingerprints
query_tokens = fingerprint(query_unit).tokens
candidate_tokens = fingerprint(candidate_unit).tokens

overlap = len(query_tokens ∩ candidate_tokens)
overlap_score = overlap / len(query_tokens ∪ candidate_tokens)

# Require minimum overlap to avoid noise
if overlap_score < 0.2:
    return 0
```

**Impact:** ×1.2–1.5 boost for fingerprint-matching units

### 5. Package/Directory Proximity
Units in same package.json/setup.py scope as user.

```python
# Extract package root for each unit
pkg_a = extract_package(context_unit.file_path)
pkg_b = extract_package(candidate_unit.file_path)

if pkg_a == pkg_b:
    package_score = 1.2
elif is_sibling_package(pkg_a, pkg_b):
    package_score = 0.8
else:
    package_score = 0.5
```

**Impact:** ×1.2 boost for same-package

## Ranking Algorithm

```python
def rank_candidates(query: str, context: UnitContext, candidates: List[Unit]) -> List[Tuple[Unit, float]]:
    """
    Narrow search scope and rank candidates.
    
    Args:
        query: Symbol name or partial name
        context: Current unit (for locality)
        candidates: Units matching query token (from symbol_index)
    
    Returns:
        Sorted list of (unit, combined_score) tuples
    """
    
    scores = []
    
    for candidate in candidates:
        # Individual scores (0–1)
        freq_score = compute_frequency_score(query, candidate)
        callee_score = compute_callee_score(candidate)
        locality_score = compute_locality_score(context, candidate)
        fingerprint_score = compute_fingerprint_score(context, candidate)
        package_score = compute_package_score(context, candidate)
        
        # Weighted combination
        combined = (
            freq_score * 0.25 +
            callee_score * 0.20 +
            locality_score * 0.25 +
            fingerprint_score * 0.15 +
            package_score * 0.15
        )
        
        scores.append((candidate, combined))
    
    # Sort descending by score
    scores.sort(key=lambda x: x[1], reverse=True)
    
    # Prune: return top-K, or all if combined > threshold
    K = 10  # Return top 10
    threshold = 0.3  # Minimum score to include
    
    return [(u, s) for u, s in scores[:K] if s >= threshold]
```

## Query Types & Strategies

### 1. Direct Symbol Lookup
**User Query:** "fetch_user"  
**Strategy:** Exact token match + locality bias

```python
# Find all units with token "fetch_user"
candidates = symbol_index.lookup("fetch_user")
ranked = rank_candidates("fetch_user", context_unit, candidates)
return ranked[:5]
```

**Performance:** <50ms (symbol_index is O(1) lookup)

### 2. Partial Name Search
**User Query:** "fetch"  
**Strategy:** Token prefix match + frequency filtering

```python
# Find all tokens starting with "fetch"
tokens = symbol_index.prefix_search("fetch")  # ["fetch", "fetch_user", "fetcher", ...]

# Aggregate by unit
candidates = set()
for token in tokens:
    candidates.update(symbol_index.lookup(token))

ranked = rank_candidates("fetch", context_unit, candidates)
return ranked[:5]
```

**Performance:** <100ms (prefix search + aggregation)

### 3. Type/Pattern-Based Search
**User Query:** "export:fetch"  
**Strategy:** Call graph + fingerprint matching

```python
# Find exported units with token "fetch"
candidates = symbol_index.lookup("fetch")
candidates = [u for u in candidates if u.is_exported]

# Boost by in-degree (popular exports)
ranked = rank_candidates("fetch", context_unit, candidates)
return ranked[:5]
```

**Performance:** <100ms (filtering + ranking)

### 4. Callee Search
**User Query:** "who calls fetch_user?"  
**Strategy:** Reverse graph traversal + locality

```python
# Find target unit
target = symbol_index.lookup_exact("fetch_user")[0]

# Get incoming edges
callers = edges.select(target_id=target.id, reverse=True)

# Rank by locality to context
ranked = [(c, locality_score(context, c)) for c in callers]
ranked.sort(reverse=True)
return ranked[:10]
```

**Performance:** <100ms (edge lookup + sorting)

## Data Structures & Indexes

### Required Indexes (from INDEX_SCHEMA.md)
```sql
-- Symbol tokenization index
CREATE INDEX idx_symbol_index_token ON symbol_index(token);
CREATE INDEX idx_symbol_index_unit_token ON symbol_index(unit_id, token);

-- Call graph for locality
CREATE INDEX idx_edges_source_type ON edges(source_id, edge_type);
CREATE INDEX idx_edges_target_type ON edges(target_id, edge_type);

-- Cluster membership for package detection
CREATE INDEX idx_cluster_members_cluster ON cluster_members(cluster_id);

-- Frequency stats
CREATE INDEX idx_units_language ON units(language);
```

### Runtime Caches
```python
# Pre-compute token frequencies on index build
token_frequencies = {
    "fetch": 150,
    "user": 800,
    "fetch_user": 12,
    # ...
}

# Pre-compute package boundaries
packages = {
    "/app/src/auth.py": "auth",
    "/app/src/utils/fetch.py": "utils",
    # ...
}

# Cache call graph in-degrees
in_degrees = {
    "app.py:fetch_user": 25,
    "lib.py:helper": 3,
    # ...
}
```

## Performance Targets

| Operation | Target | Assumptions |
|-----------|--------|-------------|
| Symbol lookup | <50ms | SQLite index on symbol_index(token) |
| Prefix search | <100ms | ~50 tokens match |
| Ranking (50 candidates) | <30ms | Python scoring loop |
| Callee search | <100ms | Edge lookup + sorting |
| Full query pipeline | <200ms | Includes all steps |

**Cache warming:** First query after DB open → ~500ms (load frequencies, package map, in-degrees)

## Implementation Roadmap

### Phase 6 Task 3a: Core Planner
- [ ] QueryPlanner class: rank_candidates(), compute_*_score() methods
- [ ] Frequency cache: load from index_meta during init
- [ ] Package detector: extract_package() for all supported languages
- [ ] Tests: 20+ test cases for scoring, ranking, edge cases

### Phase 6 Task 3b: Query Strategies
- [ ] Direct symbol lookup
- [ ] Partial name search (prefix matching)
- [ ] Type-based filtering
- [ ] Callee/caller traversal

### Phase 6 Task 3c: Integration Tests
- [ ] Full pipeline on 3.6M LOC (kubernetes)
- [ ] Latency profiling: <200ms target
- [ ] Cache effectiveness: hit rate >80%

## Example Usage

```python
from bgi.indexer.planner import QueryPlanner

# Initialize with index
planner = QueryPlanner(db_path="index.db")

# Query type 1: Direct lookup
results = planner.lookup_symbol("fetch_user", context_unit_id="app.py:main")
# [
#   (Unit(id="auth.py:fetch_user", score=0.92), "Exact match + exported + frequent caller"),
#   (Unit(id="lib.py:fetch_user_cached", score=0.78), "Similar name + local package"),
# ]

# Query type 2: Prefix search
results = planner.search_prefix("fetch", context_unit_id="app.py:main")
# [
#   (Unit(id="auth.py:fetch_user", score=0.92), ...),
#   (Unit(id="auth.py:fetch_data", score=0.81), ...),
#   (Unit(id="cache.py:fetch_cached", score=0.65), ...),
# ]

# Query type 3: Find callers
results = planner.find_callers("fetch_user", max_results=10)
# [
#   (Unit(id="app.py:main", score=0.9), "Direct caller, same file"),
#   (Unit(id="app.py:process", score=0.8), "Indirect via main"),
# ]

# Stats
print(planner.get_stats())
# {
#     "db_path": "index.db",
#     "token_count": 8342,
#     "unique_units": 162954,
#     "packages": 1450,
#     "cache_hit_rate": 0.87,
#     "avg_query_time_ms": 45,
# }
```

## Future Enhancements

1. **Learning to Rank:** Train on user click patterns (which result users actually clicked)
2. **Semantic Similarity:** Use embeddings of unit bodies to find related units
3. **Context Awareness:** Track user's recent views, prioritize related code
4. **Fuzzy Matching:** Handle typos (e.g., "fetch_usr" → "fetch_user")
5. **Multi-language Support:** Cross-language dependencies (Python imports TS modules, etc.)

## References

- Query planner design inspired by Sourcegraph's precise code navigation (https://sourcegraph.com/blog/precise-code-intelligence)
- Ranking inspired by BM25 (frequency-based IR model)
- Locality heuristics based on software architecture research (Conway's Law, package cohesion)
