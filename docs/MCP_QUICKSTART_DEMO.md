# Big Indexer MCP Quick Start Demo

Get MCP architecture analysis working in under 5 minutes.

> Current-state note: the published validation evidence now includes BGI-TWIN and three-model replication (`docs/VALIDATION_EVIDENCE.md`). For real work, use `twin_context` first.

## Prerequisites

- `bgi` installed (via `pip install bigindexer`)
- OpenCode CLI, GitHub Copilot CLI, or Gemini CLI
- A Git repository to analyze

## 1-Minute Setup

```bash
# Clone a test repository
git clone https://github.com/pallets/flask /tmp/demo-repo
cd /tmp/demo-repo

# Scan it with Big Indexer
bgi scan . --lang auto --out bgi-graph.json --fuse-graph fuse-graph.json
# Optional human-readable context is also generated as bigindexer.md

# Create MCP config (copy-paste this into your CLI directory or use --additional-mcp-config)
cat > mcp-config.json << EOF
{
  "mcpServers": {
    "bigindexer": {
      "command": "python3",
      "args": [
        "-m", "bgi.cli", "mcp",
        "--graph", "$(pwd)/bgi-graph.json",
        "--fuse-graph", "$(pwd)/fuse-graph.json"
      ]
    }
  }
}
EOF
```

## 2-Minute Test: OpenCode CLI

```bash
# Run a query that uses the MCP tool
opencode run --agent build --dir /tmp/demo-repo \
  "Use MCP tool bigindexer_get_architecture_summary to describe the architecture in 3 bullet points."
```

**Expected output**: The tool invokes BigIndexer's MCP server, retrieves the architecture summary, and synthesizes a response.

## 2-Minute Test: BGI-TWIN (recommended)

```bash
opencode run --dir /tmp/demo-repo \
  "Use MCP tool twin_context for this change and return the top twin candidate, seam suggestion, and rubric checklist."
```

**Expected output**: The tool invokes `twin_context`, returns behavioral twins, a seam suggestion, and an actionability rubric that maps directly to the current validation workflow.

## 2-Minute Test: GitHub Copilot CLI

```bash
# Ensure ~/.copilot/mcp-config.json is set up (see docs/MCP_SETUP.md)
copilot --add-dir /tmp/demo-repo -C /tmp/demo-repo \
  -p "What are the main architectural clusters in this repo? Use the MCP tool bigindexer_get_architecture_summary." \
  --allow-all
```

**Expected output**: The MCP tool `architecture_summary` is called in real-time during agent reasoning.

## Automated Demo Script

For a fully automated walk-through:

```bash
./scripts/mcp-demo.sh fastapi opencode
./scripts/mcp-demo.sh django copilot
./scripts/mcp-demo.sh pydantic opencode
```

Each demo:
1. Scans the repository
2. Sets up the MCP server
3. Runs a guided architecture analysis
4. Prints the MCP tool response and AI synthesis
5. Shows latency metrics

---

## What You'll See

### MCP Tool Invocation (logged output)

```
CallToolRequest
  Tool: bigindexer_get_architecture_summary
  Parameters: { path_scope: "", top_clusters: 5 }
```

### MCP Response (structured JSON)

```json
{
  "scope": "repository",
  "cluster_count": 127,
  "top_clusters": [
    {
      "id": "flask:core",
      "label": "Core HTTP framework",
      "unit_count": 89,
      "description": "Request/response handling, routing, WSGI integration"
    },
    ...
  ]
}
```

### AI Synthesis

```
Flask's architecture centers around three core areas:

• **HTTP Framework**: Request routing, middleware, WSGI integration, 
  response formatting.

• **Templating & Rendering**: Jinja2 integration, template context, 
  auto-escaping for security.

• **CLI & Development Tools**: Development server, debugger, shell context, 
  command registration.
```

---

## Troubleshooting

### "MCP server exits at startup"

```bash
# Make sure required scan artifacts exist and are valid JSON:
bgi scan /path/to/repo --out bgi-graph.json --fuse-graph fuse-graph.json

# Then run MCP with absolute artifact paths in your config.
```

### "No MCP tool invocation in response"

Add explicit tool reference to your prompt:

```bash
# Bad (generic):
"Tell me about the architecture"

# Good (explicit):
"Use MCP tool bigindexer_get_architecture_summary to analyze the architecture"
```

### Latency is high

First run may include artifact loading. Subsequent runs are faster as buffers warm up.

---

## Live Examples

Real MCP invocation transcripts and latency measurements are in `docs/MCP_EXAMPLE_TRANSCRIPTS.md`.

---

## Next: Explore Other MCP Tools

Beyond `architecture_summary`, try:

```bash
# Find which cluster owns a file
opencode run --dir /tmp/demo-repo \
  "Which cluster does 'flask/app.py' belong to? Use bigindexer_cluster_of_file."

# Find high-coupling integration seams
opencode run --dir /tmp/demo-repo \
  "Show the high_coupling_seams in the flask:core cluster."

# Impact analysis
opencode run --dir /tmp/demo-repo \
  "If I change the request handler in flask/app.py, which other files might break? Use impact_neighbors."
```

See `docs/MCP_SETUP.md` for full tool documentation.
