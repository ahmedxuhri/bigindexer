# MCP Real-World Demo Transcript

This is a real, unedited transcript from running Big Indexer's MCP `architecture_summary` tool on the FastAPI repository using GitHub Copilot CLI.

## Setup

```bash
# Repository: FastAPI (https://github.com/pallets/fastapi)
# Client: GitHub Copilot CLI (gpt-5.3-codex)
# MCP Server: Big Indexer (bgi mcp --graph ... --fuse-graph ...)
# Timestamp: 2026-05-09T19:52:56Z

# Scanned 2,511 units across 14,370 files
# Generated architecture graph with 333 detected clusters
```

## User Query

```
"Use MCP tool bigindexer_get_architecture_summary to answer: 
What are the main architectural clusters in this repo? 
Provide 3 bullet points."
```

## MCP Tool Invocation

```
Running the architecture summarizer across the repository to extract 
the top clusters; will use its output to condense the main architectural 
areas into three bullets. Calling tools now.

● architecture_summary (MCP: bigindexer) · path_scope: "", top_clusters: 8, seam_limit: 10
  └ {"scope":"repository","cluster_count":333,"unit_count":2511,"top_cluster...
```

*(Tool response truncated in display; full JSON available to agent)*

## AI Agent Response

```
- Core framework: FastAPI runtime (applications, routing, request/response 
  handling, datastructures, encoders, OpenAPI generation).

- Dependency, security & concurrency: dependency-injection utilities, 
  background/concurrency helpers, and security (HTTP/OAuth) modules.

- Tests, docs & tooling: large test suites, documentation examples, and 
  scripts (doc/translation tooling and test harness).
```

## Performance Metrics

```
Changes   +0 -0
Requests  0 Premium (29s latency)
Tokens    ↑ 37.4k (sent) • ↓ 2.2k (received) • 18.4k (cached) • 2.0k (reasoning)
```

**Interpretation**:
- **Latency**: 29 seconds (includes MCP server startup, graph loading, LLM reasoning)
- **Token cost**: 37.4k tokens sent (full repository context + MCP tool result)
- **Cache reuse**: 18.4k cached tokens (Copilot CLI reused prior context)
- **Reasoning overhead**: 2.0k reasoning tokens (agent thought process)
- **Premium requests**: 0 (uses standard quota)

---

## What Happened Behind the Scenes

1. **Client received query**: "Use MCP tool bigindexer_get_architecture_summary..."
2. **MCP resolution**: Copilot CLI found `architecture_summary` in configured MCP servers
3. **Tool execution**: Invoked Big Indexer MCP server:
   ```
   python3 -m bgi.cli mcp --graph ... --fuse-graph ...
   ```
4. **Graph analysis**: Server loaded architecture graph (~627MB bgi-graph.json)
5. **Cluster extraction**: Computed top 8 clusters by centrality and coupling
6. **Tool response**: Returned structured JSON with cluster definitions
7. **LLM reasoning**: Agent synthesized response using MCP data
8. **Response delivery**: Streamed natural language summary to user

---

## Reproducibility

This transcript is reproducible. Running the same query on FastAPI again produces consistent architectural summaries. To reproduce:

```bash
# Clone FastAPI
git clone https://github.com/pallets/fastapi /tmp/fastapi

# Scan
cd /tmp/fastapi
bgi scan . --lang auto --out bgi-graph.json --fuse-graph fuse-graph.json

# Configure MCP (create ~/.copilot/mcp-config.json with bigindexer server)
# See docs/MCP_SETUP.md for instructions

# Run same query
copilot \
  -C /tmp/fastapi \
  -p "Use MCP tool bigindexer_get_architecture_summary to answer: What are the main architectural clusters in this repo? Provide 3 bullet points." \
  --allow-all
```

---

## Why This Matters

1. **Real tool use**: This demonstrates actual MCP tool invocation, not hallucination
2. **Multi-client**: Same MCP server works across OpenCode, Copilot, and Gemini CLIs
3. **Production ready**: Latencies are reasonable for interactive use
4. **Reproducible**: Results are deterministic based on code structure, not training data
5. **Architecture-aware**: Uses actual call graphs and import dependencies, not guesses

---

## Further Examples

See `docs/MCP_EXAMPLE_TRANSCRIPTS.md` for additional transcripts:
- Django repository analysis
- Multi-client latency comparison
- Impact analysis and coupling seams
- Symbol search integration

