"""MCP server entrypoint for Big Indexer architecture context.

Copyright (c) 2026 Ahmed F A Abuzuhri
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse

from bgi.mcp.context import ArchitectureContextService


def create_mcp_server(
    graph_path: str = "bgi-graph.json",
    fuse_graph_path: str | None = None,
    index_db_path: str | None = None,
):
    """Create FastMCP server and register tools."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "The 'mcp' package is required to run the MCP server. "
            "Install it with: pip install mcp"
        ) from exc

    service = ArchitectureContextService(
        graph_path=graph_path,
        fuse_graph_path=fuse_graph_path,
        index_db_path=index_db_path,
    )
    mcp = FastMCP("Big Indexer MCP")

    @mcp.tool()
    def cluster_of_file(file_path: str):
        """Get architectural cluster data for a file path."""
        return service.cluster_of_file(file_path)

    @mcp.tool()
    def boundary_edges(file_or_cluster: str, limit: int = 12):
        """Get fuse boundary edges touching a file or cluster."""
        return service.boundary_edges(file_or_cluster=file_or_cluster, limit=limit)

    @mcp.tool()
    def high_coupling_seams(file_or_cluster: str = "", limit: int = 12):
        """Get strongest cross-cluster seams for a file/cluster or whole repo."""
        return service.high_coupling_seams(file_or_cluster=file_or_cluster, limit=limit)

    @mcp.tool()
    def impact_neighbors(symbol_or_file: str, depth: int = 2, limit: int = 30):
        """Get likely architectural blast radius from symbol/file."""
        return service.impact_neighbors(symbol_or_file=symbol_or_file, depth=depth, limit=limit)

    @mcp.tool()
    def search_symbols(query: str, limit: int = 8, context_unit_id: str = ""):
        """Search symbols via index DB if available, else graph fallback."""
        ctx = context_unit_id or None
        return service.search_symbols(query=query, limit=limit, context_unit_id=ctx)

    @mcp.tool()
    def architecture_summary(path_scope: str = "", top_clusters: int = 4, seam_limit: int = 6):
        """Get compact architecture summary for context injection."""
        return service.architecture_summary(path_scope=path_scope, top_clusters=top_clusters, seam_limit=seam_limit)

    @mcp.tool()
    def reload_artifacts():
        """Reload graph and fuse artifacts from disk."""
        return service.reload()

    return mcp


def run_server(
    graph_path: str = "bgi-graph.json",
    fuse_graph_path: str | None = None,
    index_db_path: str | None = None,
) -> None:
    mcp = create_mcp_server(
        graph_path=graph_path,
        fuse_graph_path=fuse_graph_path,
        index_db_path=index_db_path,
    )
    mcp.run()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bgi-mcp",
        description="Big Indexer MCP server",
    )
    parser.add_argument("--graph", default="bgi-graph.json", help="Path to bgi-graph.json")
    parser.add_argument("--fuse-graph", default=None, help="Path to fuse-graph.json")
    parser.add_argument("--index-db", default=None, help="Path to index SQLite DB (optional)")
    args = parser.parse_args()
    run_server(graph_path=args.graph, fuse_graph_path=args.fuse_graph, index_db_path=args.index_db)


if __name__ == "__main__":
    main()
