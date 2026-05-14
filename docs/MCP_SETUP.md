# Big Indexer MCP Setup

This guide explains how to run the Big Indexer MCP server and connect it to MCP-capable clients.

> Current state: the public validation set is 100 scored runs across deepseek, GPT-4o, and Gemini auto (`docs/VALIDATION_EVIDENCE.md`). For implementation tasks, prefer `twin_context` first, then `behavioral_twins` and `task_fingerprint`.

## 1) Generate architecture artifacts

Run a scan first so MCP tools have data:

```bash
bgi scan /path/to/repo --lang auto --out bgi-graph.json --fuse-graph fuse-graph.json
```

This generates required MCP artifacts (`bgi-graph.json`, `fuse-graph.json`) and an optional context note file (`bigindexer.md`).

Optional: build a query index DB if you want ranked symbol search:

```bash
# Existing index workflow in this repo can produce index.db artifacts.
# Pass that DB path to MCP with --index-db.
```

## 2) Run MCP server (stdio)

From repository root:

```bash
bgi mcp --graph bgi-graph.json --fuse-graph fuse-graph.json --index-db index.db
```

If you do not use index DB, omit `--index-db`. MCP now fails fast with a clear "run bgi scan first" message when either required graph artifact is missing or invalid JSON.

## 3) MCP tools exposed

1. `cluster_of_file(file_path)`
2. `boundary_edges(file_or_cluster, limit=20)`
3. `high_coupling_seams(file_or_cluster="", limit=20)`
4. `impact_neighbors(symbol_or_file, depth=2, limit=50)`
5. `search_symbols(query, limit=10, context_unit_id="")`
6. `architecture_summary(path_scope="", top_clusters=5, seam_limit=10)`
7. `classify_prompt(prompt)`
8. `guided_arch_context(prompt, max_items=8)`
9. `task_fingerprint(task, max_tokens=8)`
10. `behavioral_twins(task, limit=3, min_score=0.25, include_source=true)`
11. `twin_context(task, limit=3, include_source=true, min_score=0.25)`
12. `reload_artifacts()`

Current recommended path for AI assistance:

1. `task_fingerprint` for deterministic task normalization
2. `behavioral_twins` for concrete in-repo analogs
3. `twin_context` for the full implementation brief with seam and rubric

## 4) Client configuration pattern

Most MCP clients accept a stdio command config. Use:

- command: `bgi`
- args: `["mcp", "--graph", "/absolute/path/bgi-graph.json", "--fuse-graph", "/absolute/path/fuse-graph.json"]`

If your client supports environment variables, set them as needed for your workspace.

## 5) Example prompts

1. "What cluster does `src/payments/service.py` belong to and why?"
2. "Show boundary edges touching `src/auth`."
3. "What is the blast radius if I change `auth.py::AuthService::login`?"
4. "Give me top coupling seams in this repo."
5. "For task: `add endpoint that validates input and persists data`, call `twin_context` and return the top twin and seam."

## 6) Notes

- Big Indexer MCP is static-analysis based; it does not use runtime traces.
- `search_symbols` is stronger with `--index-db`; otherwise it falls back to graph scanning.
- `bigindexer.md` is optional metadata for human/agent context and is not required to start MCP.

## 7) High-trust prompting (recommended)

Use `docs/MCP_PROMPT_PROTOCOL.md` to force evidence-backed responses.

It gives:

1. copy-paste system instruction for evidence mode
2. user prompt template with strict constraints
3. output format requiring `VERIFIED` / `HYPOTHESIS` / `UNKNOWN`
4. anti-drift checklist to catch stale historical claims
