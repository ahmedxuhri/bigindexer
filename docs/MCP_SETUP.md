# Big Indexer MCP Setup

This guide explains how to run the Big Indexer MCP server and connect it to MCP-capable clients.

## 1) Generate architecture artifacts

Run a scan first so MCP tools have data:

```bash
bgi scan /path/to/repo --lang auto --out bgi-graph.json --fuse-graph fuse-graph.json
```

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

If you do not use index DB, omit `--index-db`.

## 3) MCP tools exposed

1. `cluster_of_file(file_path)`
2. `boundary_edges(file_or_cluster, limit=20)`
3. `high_coupling_seams(file_or_cluster="", limit=20)`
4. `impact_neighbors(symbol_or_file, depth=2, limit=50)`
5. `search_symbols(query, limit=10, context_unit_id="")`
6. `architecture_summary(path_scope="", top_clusters=5, seam_limit=10)`
7. `reload_artifacts()`

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

## 6) Notes

- Big Indexer MCP is static-analysis based; it does not use runtime traces.
- `search_symbols` is stronger with `--index-db`; otherwise it falls back to graph scanning.
