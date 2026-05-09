#!/bin/bash
# Big Indexer MCP Demo
# Showcases architecture analysis across multiple real-world repositories
# Usage: ./mcp-demo.sh <repo_slug> [client]
# Clients: opencode (default), copilot, gemini

set -e

REPO_SLUG="${1:-fastapi}"
CLIENT="${2:-opencode}"
REPO_DIR="/tmp/bgi-ab-repos/${REPO_SLUG}"

# Validate repo exists
if [ ! -d "$REPO_DIR" ]; then
  echo "Error: Repository not found at $REPO_DIR"
  echo "Available repos: fastapi, django, pydantic"
  exit 1
fi

echo "=========================================="
echo "Big Indexer MCP Demo"
echo "=========================================="
echo "Repository: $REPO_SLUG"
echo "Client: $CLIENT"
echo "Demo working directory: $REPO_DIR"
echo ""

# Generate fresh architecture analysis
echo "[1/3] Scanning repository for architecture..."
BGI_OUTPUT_DIR="/tmp/bgi-demo-${REPO_SLUG}"
mkdir -p "$BGI_OUTPUT_DIR"

bgi scan "$REPO_DIR" \
  --lang auto \
  --out "$BGI_OUTPUT_DIR/bgi-graph.json" \
  --fuse-graph "$BGI_OUTPUT_DIR/fuse-graph.json" \
  > /dev/null 2>&1

echo "      ✓ Scanned $(find $REPO_DIR -type f | wc -l) files"
echo "      ✓ Generated architecture graph"
echo ""

# Create MCP config in repo
echo "[2/3] Configuring MCP client..."
cat > "$REPO_DIR/opencode.json" << EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "mcp": {
    "bigindexer": {
      "type": "local",
      "command": [
        "python3",
        "-m",
        "bgi.cli",
        "mcp",
        "--graph",
        "$BGI_OUTPUT_DIR/bgi-graph.json",
        "--fuse-graph",
        "$BGI_OUTPUT_DIR/fuse-graph.json"
      ]
    }
  }
}
EOF
echo "      ✓ MCP server configured"
echo ""

# Run demo query
echo "[3/3] Running architecture analysis via MCP..."
echo ""
echo "Query: Use MCP tool bigindexer_get_architecture_summary to analyze this repo"
echo "Then provide: (1) Core functionality clusters, (2) Cross-cutting concerns, (3) Quality gates"
echo ""
echo "──────────────────────────────────────────"

DEMO_PROMPT="Use MCP tool bigindexer_get_architecture_summary with top_clusters=5 to analyze the architecture. Then provide a 3-point summary of: (1) main functional areas, (2) architectural boundaries, (3) integration seams."

case "$CLIENT" in
  opencode)
    /usr/bin/time -f "Completed in %es\n" opencode run --agent build \
      --dir "$REPO_DIR" \
      "$DEMO_PROMPT" \
      2>&1 | tail -40
    ;;
  copilot)
    /usr/bin/time -f "Completed in %es\n" copilot \
      --add-dir "$REPO_DIR" \
      -C "$REPO_DIR" \
      -p "$DEMO_PROMPT" \
      --allow-all 2>&1 | tail -40
    ;;
  gemini)
    /usr/bin/time -f "Completed in %es\n" gemini \
      -m gemini-2.0-flash \
      -p "$DEMO_PROMPT" \
      --yolo 2>&1 | tail -40
    ;;
  *)
    echo "Error: Unknown client '$CLIENT'"
    echo "Supported clients: opencode, copilot, gemini"
    exit 1
    ;;
esac

echo "──────────────────────────────────────────"
echo ""
echo "✓ Demo complete!"
echo ""
echo "MCP tools available:"
echo "  • cluster_of_file(file_path)"
echo "  • boundary_edges(file_or_cluster, limit=20)"
echo "  • high_coupling_seams(file_or_cluster, limit=20)"
echo "  • impact_neighbors(symbol_or_file, depth=2, limit=50)"
echo "  • search_symbols(query, limit=10, context_unit_id)"
echo "  • architecture_summary(path_scope, top_clusters=5)"
echo "  • reload_artifacts()"
echo ""
echo "Artifacts:"
echo "  Graph: $BGI_OUTPUT_DIR/bgi-graph.json"
echo "  Fuse:  $BGI_OUTPUT_DIR/fuse-graph.json"
