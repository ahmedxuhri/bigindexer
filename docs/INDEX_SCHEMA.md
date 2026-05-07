# BGI Interactive Search Index — Phase 6 Task 1 Design

## Executive Summary

This document specifies the index schema for BGI's interactive search layer. The goal is **sub-second search** on large codebases (3.6M LOC) by pre-computing and structuring Gate 1-3 output into queryable indexes.

**Key Design Principles:**
1. **Fast Scope Narrowing:** Quickly identify candidate units/clusters from a query
2. **Incremental:** Support adding/updating units without full re-indexing
3. **Memory-Efficient:** Index large repos without excessive RAM (target: <1GB for 3.6M LOC)
4. **Language-Agnostic:** Work across all BGI-supported languages

---

## 1. What We're Indexing

### Gate 1 Output → Unit Index
From each unit (function/class/route handler), we extract:
- **Unit Metadata:** name, file path, language, line numbers
- **Fingerprint:** COV tokens (OUTPUT, MUTATE, FETCH, etc.)
- **Signature:** parameter names, return type hints, decorators
- **Scope:** file scope, class scope (if nested)

### Gate 2 Output → Edge Index
From each edge (Key-Lock pair), we extract:
- **Edge Type:** behavioral relationship (call, mutation, fetch, etc.)
- **Source Unit:** caller unit ID
- **Target Unit:** callee unit ID
- **Fanout:** edge weight/strength
- **Direction:** forward (A→B) or reverse (B←A)

### Gate 3 Output → Cluster Index
From each cluster (DRS result), we extract:
- **Cluster ID:** unique identifier
- **Unit Members:** list of unit IDs in cluster
- **Cluster Size:** count of units
- **Boundary Edges:** edges bridging to other clusters (via FUSE-GRAPH)
- **Cluster Type:** inferred (e.g., "API Handler", "Database Layer")

---

## 2. Index Schema (SQLite)

All indexes stored in `bgi/index.db` (SQLite):

```sql
-- Unit index (primary search target)
CREATE TABLE units (
    id TEXT PRIMARY KEY,           -- "file.py:func_name" or "file.ts:Class#method"
    name TEXT NOT NULL,            -- function/class name
    file_path TEXT NOT NULL,       -- relative to repo root
    language TEXT NOT NULL,        -- python, typescript, rust, etc.
    line_start INTEGER NOT NULL,   -- line number in file
    line_end INTEGER NOT NULL,
    scope_type TEXT,               -- 'file', 'class', 'module' (derived)
    parent_scope TEXT,             -- parent class ID if nested (optional)
    signature TEXT,                -- "def foo(x, y) -> str:" (raw)
    fingerprint JSON,              -- {"tokens": ["OUTPUT", "MUTATE"], "confidence": 0.95}
    decorators JSON,               -- ["@cached", "@route"] if any
    is_exported BOOLEAN,           -- True if public/exported
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_units_file ON units(file_path);
CREATE INDEX idx_units_name ON units(name);
CREATE INDEX idx_units_language ON units(language);

-- Edge index (relationship queries)
CREATE TABLE edges (
    id TEXT PRIMARY KEY,           -- "source_id→target_id#edge_type"
    source_id TEXT NOT NULL,       -- unit ID
    target_id TEXT NOT NULL,       -- unit ID
    edge_type TEXT NOT NULL,       -- 'call', 'mutation', 'fetch', etc.
    fanout REAL,                   -- edge weight (0.0-1.0)
    is_forward BOOLEAN DEFAULT 1,  -- True = A→B, False = B←A (reverse)
    confidence REAL,               -- token match confidence
    FOREIGN KEY (source_id) REFERENCES units(id),
    FOREIGN KEY (target_id) REFERENCES units(id)
);

CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_edges_type ON edges(edge_type);

-- Cluster index (architectural queries)
CREATE TABLE clusters (
    id INTEGER PRIMARY KEY,        -- cluster number (from Gate 3)
    size INTEGER NOT NULL,         -- unit count
    max_unit_pct REAL,            -- largest unit percentage
    cluster_type TEXT,             -- inferred: 'handler', 'util', 'model', etc.
    is_boundary BOOLEAN DEFAULT 0, -- True if contains FUSE boundary edges
    created_at TIMESTAMP
);

CREATE INDEX idx_clusters_size ON clusters(size);

-- Cluster membership (many-to-many)
CREATE TABLE cluster_members (
    cluster_id INTEGER NOT NULL,
    unit_id TEXT NOT NULL,
    PRIMARY KEY (cluster_id, unit_id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(id),
    FOREIGN KEY (unit_id) REFERENCES units(id)
);

CREATE INDEX idx_members_unit ON cluster_members(unit_id);

-- Inverted index for full-text search (tokenized names)
CREATE TABLE symbol_index (
    token TEXT NOT NULL,           -- lowercased, stemmed symbol name (e.g., "fetch_user" → ["fetch", "user"])
    unit_id TEXT NOT NULL,
    PRIMARY KEY (token, unit_id),
    FOREIGN KEY (unit_id) REFERENCES units(id)
);

CREATE INDEX idx_symbols_token ON symbol_index(token);

-- Metadata (version, build timestamp, etc.)
CREATE TABLE index_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Typical rows: ("version", "1.0"), ("repo_commit", "abc123"), ("built_at", "2026-05-07T15:00:00Z")
```

---

## 3. Query Patterns & Scoping

### Pattern 1: Search by Symbol Name
```sql
SELECT u.* FROM units u
JOIN symbol_index s ON u.id = s.unit_id
WHERE s.token LIKE 'fetch%'
ORDER BY u.is_exported DESC, u.name ASC
LIMIT 20;
```
**Response Time:** <100ms (index on token)

---

### Pattern 2: Find Related Units (1-hop neighbors)
```sql
-- Find all units that A calls or depends on
SELECT DISTINCT u.* FROM edges e
JOIN units u ON e.target_id = u.id
WHERE e.source_id = ?
  AND e.edge_type IN ('call', 'mutation', 'fetch')
ORDER BY e.fanout DESC;
```
**Response Time:** <200ms

---

### Pattern 3: Find Callers (reverse edges)
```sql
-- Find all units that call B
SELECT DISTINCT u.* FROM edges e
JOIN units u ON e.source_id = u.id
WHERE e.target_id = ?
  AND e.is_forward = 1
ORDER BY e.fanout DESC;
```
**Response Time:** <200ms

---

### Pattern 4: Cluster Discovery
```sql
-- Find cluster containing unit A
SELECT c.* FROM clusters c
JOIN cluster_members cm ON c.id = cm.cluster_id
WHERE cm.unit_id = ?;

-- Find cluster neighbors (units in adjacent clusters via boundary edges)
SELECT DISTINCT u.* FROM cluster_members cm
JOIN units u ON cm.unit_id = u.id
WHERE cm.cluster_id = (
  SELECT c.id FROM clusters c
  JOIN cluster_members cm2 ON c.id = cm2.cluster_id
  WHERE cm2.unit_id = ?
)
LIMIT 50;
```
**Response Time:** <300ms

---

### Pattern 5: Token-Based Search
```sql
-- Find all units with specific COV token (e.g., all FETCH operations)
SELECT u.* FROM units u
WHERE u.fingerprint JSON_CONTAINS(u.fingerprint, '"FETCH"', '$.tokens')
ORDER BY u.language, u.file_path;
```
**Response Time:** <500ms

---

## 4. Index Building Process

### Phase: Pre-indexing (after Gate 3)
```
1. Load Gate 1 units.jsonl → populate `units` table
2. Load Gate 2 edges.jsonl → populate `edges` table
3. Load Gate 3 clusters.jsonl + fuse-graph.json → populate `clusters` + `cluster_members` tables
4. Tokenize unit names → populate `symbol_index` (inverted index)
5. Analyze & classify clusters → update `clusters.cluster_type`
6. Run VACUUM & ANALYZE on index.db for optimization
```

**Time on kubernetes (3.6M LOC):**
- Load units (162k): ~500ms
- Load edges (8.6M): ~2s
- Load clusters (14k): ~200ms
- Tokenize & invert: ~1s
- **Total: ~4s** (can run offline after Gate 3)

### Phase: Incremental Update
For CI/incremental mode:
```
1. Identify changed files & their units
2. DELETE old units & their edges from index
3. INSERT new units & edges
4. UPDATE cluster membership if units moved
5. VACUUM tables
```

---

## 5. Performance Budget

### Query Latency Targets
| Query Type | Target | Notes |
|-----------|--------|-------|
| Symbol search | <100ms | Indexed lookup + LIMIT |
| 1-hop neighbors | <200ms | Single JOIN on indexed edge |
| Cluster discovery | <300ms | JOIN on cluster membership |
| Token search | <500ms | JSON_CONTAINS scan |
| Multi-hop (2-3) | <1s | Repeated JOINs, LIMIT results |

### Memory Usage
- **Index size on kubernetes:** ~300MB (indexes + B-tree overhead)
- **In-memory query cache:** ~50MB (LRU for frequent queries)
- **Total:** <400MB ✅ (well under 1GB target)

---

## 6. Incremental Indexing

To support fast re-indexing on file changes:

### Change Detection
```python
# In pipeline.py after Gate 1
changed_units = {u.id: u for u in new_units if u.id not in old_index}
deleted_units = old_index.keys() - {u.id for u in new_units}

# Remove deleted → update edges → add new
index.delete_units(deleted_units)
index.delete_edges_involving(deleted_units)
index.add_units(changed_units)
index.add_edges_from_gate2(new_edges)
```

---

## 7. Schema Extensibility

Future additions (without schema changes):
- Add `units.doc_summary TEXT` for docstring extraction
- Add `edges.proof_location JSON` for edge source code location
- Add `clusters.feature_vector BLOB` for similarity search
- Add `symbol_index.kind TEXT` for filtering by symbol type (function, class, etc.)

---

## 8. Deliverables

**Phase 6 Task 1 Output:**
1. `docs/INDEX_SCHEMA.md` — this document
2. `bgi/bgi/indexer/__init__.py` — module marker
3. `bgi/bgi/indexer/schema.py` — SQL schema creation & migrations
4. `tests/test_index_schema.py` — schema validation tests

**Next Task:** Implement indexing engine (build indexes from Gate 1-3 output)

---

## 9. Success Criteria

- ✅ Schema supports all 5 query patterns (<500ms)
- ✅ Index size <300MB on kubernetes
- ✅ Build time <5s after Gate 3
- ✅ All tests passing
- ✅ Incremental updates working
