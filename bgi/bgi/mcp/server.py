"""MCP server entrypoint for Big Indexer architecture context.

Copyright (c) 2026 bigindexer.com
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bgi.mcp.context import ArchitectureContextService


def _resolve_fuse_path(graph_path: str, fuse_graph_path: str | None) -> Path:
    if fuse_graph_path:
        return Path(fuse_graph_path)
    return Path(graph_path).with_name("fuse-graph.json")


def _scan_hint(graph_path: str, fuse_path: Path) -> str:
    return (
        "Run a scan first, for example:\n"
        f"  bgi scan /path/to/repo --out {graph_path} --fuse-graph {fuse_path}"
    )


def _require_json_artifact(path: Path, label: str, hint: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Missing required {label} file: {path}\n{hint}")
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in required {label} file: {path}\n"
            f"JSON error: {exc.msg} (line {exc.lineno}, column {exc.colno})\n"
            f"{hint}"
        ) from exc


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
        """Return the architectural cluster that contains a given source file.

        Use this when you need to know which module boundary or subsystem a file
        belongs to before making changes, so you avoid cross-cluster side effects.
        Do NOT use this for symbol lookup — use search_symbols instead.

        Args:
            file_path: Relative or absolute path to the source file (e.g. "src/auth/login.py").

        Returns:
            A dict with cluster_id, cluster_label, member file list, and size.
            Returns null if the file is not present in the indexed graph.
        """
        return service.cluster_of_file(file_path)

    @mcp.tool()
    def boundary_edges(file_or_cluster: str, limit: int = 12):
        """Return cross-cluster dependency edges that touch a file or cluster.

        Use this to identify architectural seams — places where two modules are
        tightly coupled across a boundary. Call this before refactoring or extracting
        a subsystem to understand what depends on it and what it depends on.
        Prefer high_coupling_seams when you want the strongest seams repo-wide.

        Args:
            file_or_cluster: A file path or cluster ID whose boundary edges you want.
            limit: Maximum number of edges to return (default 12).

        Returns:
            A list of edge dicts, each with source, target, weight, and cluster labels.
        """
        return service.boundary_edges(file_or_cluster=file_or_cluster, limit=limit)

    @mcp.tool()
    def high_coupling_seams(file_or_cluster: str = "", limit: int = 12):
        """Return the strongest cross-cluster coupling seams in the repo or around a focal point.

        Use this to find the highest-risk architectural boundaries — pairs of clusters
        with the most inter-cluster dependencies. Call with no arguments for a repo-wide
        hotspot list. Pass a file or cluster to scope the result to its neighbourhood.
        Use boundary_edges when you already know the focal file/cluster.

        Args:
            file_or_cluster: Optional file path or cluster ID to scope results. Empty = repo-wide.
            limit: Maximum number of seams to return (default 12).

        Returns:
            A ranked list of seam dicts with cluster_a, cluster_b, edge_count, and weight.
        """
        return service.high_coupling_seams(file_or_cluster=file_or_cluster, limit=limit)

    @mcp.tool()
    def impact_neighbors(symbol_or_file: str, depth: int = 2, limit: int = 30):
        """Return the architectural blast radius of a symbol or file change.

        Use this before editing a function, class, or module to understand which
        other files and clusters are likely to be affected. Depth controls how many
        hops away from the focal point to traverse. Prefer depth=1 for quick checks
        and depth=2–3 for larger refactors.

        Args:
            symbol_or_file: A symbol name (e.g. "AuthService.login") or file path.
            depth: Traversal depth in the dependency graph (default 2, max recommended 3).
            limit: Maximum number of neighbour units to return (default 30).

        Returns:
            A list of impacted units with file path, cluster, and distance from focal point.
        """
        return service.impact_neighbors(symbol_or_file=symbol_or_file, depth=depth, limit=limit)

    @mcp.tool()
    def search_symbols(query: str, limit: int = 8, context_unit_id: str = ""):
        """Search for symbols (functions, classes, methods) by name or description.

        Use this to locate a specific function or class before navigating to it or
        understanding its context. Requires an index DB for ranked semantic results;
        falls back to graph name-matching when no DB is present. Prefer this over
        grep when you want architecture-aware ranking. Do NOT use for cluster lookup —
        use cluster_of_file instead.

        Args:
            query: Symbol name fragment or natural-language description (e.g. "parse headers").
            limit: Maximum number of results to return (default 8).
            context_unit_id: Optional unit ID to bias results toward a specific module scope.

        Returns:
            A ranked list of symbol dicts with name, file, cluster, and relevance score.
        """
        ctx = context_unit_id or None
        return service.search_symbols(query=query, limit=limit, context_unit_id=ctx)

    @mcp.tool()
    def architecture_summary(path_scope: str = "", top_clusters: int = 4, seam_limit: int = 6):
        """Return a compact architecture summary suitable for injecting into an AI context window.

        Use this at the start of a session to orient the agent on the repo's major
        modules, their sizes, and the strongest coupling seams. Pass a path_scope to
        restrict the summary to a subdirectory. Avoid calling this repeatedly in a
        single session — cache the result and use targeted tools (cluster_of_file,
        impact_neighbors) for follow-up queries.

        Args:
            path_scope: Optional subdirectory path to restrict the summary (e.g. "src/api").
            top_clusters: Number of largest clusters to include (default 4).
            seam_limit: Number of strongest seams to include (default 6).

        Returns:
            A dict with cluster list, seam list, unit count, and file count.
        """
        return service.architecture_summary(path_scope=path_scope, top_clusters=top_clusters, seam_limit=seam_limit)

    @mcp.tool()
    def classify_prompt(prompt: str):
        """Classify a user prompt into architectural scope and retrieval strategy.

        Use this as the first step when you receive a free-text task and are unsure
        which Big Indexer tools to call next. It maps the prompt to a scope type
        (symbol / file / cluster / repo) and a suggested retrieval sequence.
        Do NOT use this if you already know the target file or symbol — call the
        targeted tools directly.

        Args:
            prompt: The raw user task or question (e.g. "refactor the payment module").

        Returns:
            A dict with scope_type, confidence, and a suggested list of follow-up tool calls.
        """
        return service.classify_prompt(prompt=prompt)

    @mcp.tool()
    def guided_arch_context(prompt: str, max_items: int = 8):
        """Return staged architecture context for a task prompt using scope-first escalation.

        Use this as a one-shot alternative to chaining classify_prompt → cluster_of_file
        → impact_neighbors manually. It internally escalates from symbol → file → cluster
        → repo scope and stops as soon as enough context is gathered. Prefer this for
        general task prompts. Use individual tools when you need fine-grained control.

        Args:
            prompt: The user task description (e.g. "add rate limiting to the API gateway").
            max_items: Maximum total context units to return across all escalation stages (default 8).

        Returns:
            A dict with scope, matched units, cluster info, seams, and retrieval metadata.
        """
        return service.guided_arch_context(prompt=prompt, max_items=max_items)

    @mcp.tool()
    def task_fingerprint(task: str, max_tokens: int = 8):
        """Convert a natural-language task description into COV (code-operation vocabulary) tokens.

        Use this to extract the structured intent of a task before searching for
        behavioral twins. COV tokens represent the canonical operations implied by
        the task (e.g. "validate", "persist", "emit-event"). Do NOT use this for
        symbol search — use search_symbols instead.

        Args:
            task: Natural-language task description (e.g. "add retry logic to the HTTP client").
            max_tokens: Maximum number of COV tokens to return (default 8).

        Returns:
            A list of COV token strings ranked by relevance to the task.
        """
        return service.task_fingerprint(task=task, max_tokens=max_tokens)

    @mcp.tool()
    def behavioral_twins(task: str, limit: int = 3, min_score: float = 0.25, include_source: bool = True):
        """Find existing code units in the repo that implement behavior similar to a given task.

        Use this to discover prior art before writing new code — if a twin exists,
        you can follow its pattern rather than inventing from scratch. Twins are ranked
        by COV overlap (shared operation vocabulary). Use twin_context instead when you
        also need seam and rubric data for implementation guidance.

        Args:
            task: Natural-language description of the behavior you want to implement.
            limit: Maximum number of twin candidates to return (default 3).
            min_score: Minimum COV overlap score to include a candidate (default 0.25, range 0–1).
            include_source: Whether to include source code snippets in results (default True).

        Returns:
            A ranked list of twin dicts with unit_id, file, score, shared COV tokens, and source.
        """
        return service.behavioral_twins(
            task=task,
            limit=limit,
            min_score=min_score,
            include_source=include_source,
        )

    @mcp.tool()
    def twin_context(task: str, limit: int = 3, include_source: bool = True, min_score: float = 0.25):
        """Return full implementation context for a task: COV fingerprint, behavioral twins, seam, and rubric.

        Use this as the primary tool when starting implementation of a new feature or
        change. It bundles task_fingerprint + behavioral_twins + boundary_edges + a
        quality rubric into a single response optimised for context injection. Prefer
        this over calling those tools individually unless you need only one component.

        Args:
            task: Natural-language description of the task to implement.
            limit: Maximum number of behavioral twins to include (default 3).
            include_source: Whether to include source snippets for each twin (default True).
            min_score: Minimum COV overlap score for twin inclusion (default 0.25, range 0–1).

        Returns:
            A dict with cov_tokens, twins (ranked), nearest seam, and implementation rubric.
        """
        return service.twin_context(
            task=task,
            limit=limit,
            include_source=include_source,
            min_score=min_score,
        )

    @mcp.tool()
    def reload_artifacts():
        """Reload the BGI graph and fuse-graph artifacts from disk without restarting the server.

        Use this after running 'bgi scan' on the repo to pick up updated index data
        in the same MCP session. Do NOT call this during normal query workflows —
        only call it when you know the index files have been regenerated.

        Returns:
            A status dict confirming which artifacts were reloaded and their file sizes.
        """
        return service.reload()

    return mcp


def _telemetry_mcp_start(graph_path: str) -> None:
    """Fire opt-in mcp_start telemetry event. No-op unless BGI_TELEMETRY=1."""
    try:
        from bgi import telemetry
    except ImportError:
        return
    if not telemetry.is_enabled():
        return
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            bgi_version = version("bigindexer")
        except PackageNotFoundError:
            bgi_version = "unknown"
        repo_id = telemetry.compute_repo_id(Path.cwd())
        bucket = None
        try:
            graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
            distinct_files = {
                u["id"].split("::", 1)[0]
                for u in graph.get("units", [])
                if isinstance(u.get("id"), str)
            }
            bucket = telemetry.repo_size_bucket(len(distinct_files))
        except Exception:
            pass
        telemetry.report_event(
            "mcp_start",
            version=bgi_version,
            repo_id=repo_id,
            repo_size_bucket=bucket,
        )
    except Exception:
        # Telemetry must never break MCP startup
        pass


def run_server(
    graph_path: str = "bgi-graph.json",
    fuse_graph_path: str | None = None,
    index_db_path: str | None = None,
) -> None:
    resolved_fuse_path = _resolve_fuse_path(graph_path, fuse_graph_path)
    hint = _scan_hint(graph_path, resolved_fuse_path)
    _require_json_artifact(Path(graph_path), "graph", hint)
    _require_json_artifact(resolved_fuse_path, "fuse-graph", hint)

    metadata_path = Path(graph_path).with_name("bigindexer.md")
    if metadata_path.exists():
        print(f"[BGI] Optional context file detected: {metadata_path}")
    else:
        print(
            "[BGI] Optional context file not found: "
            f"{metadata_path} (scan can generate it for human-readable architecture notes)."
        )

    if index_db_path:
        if Path(index_db_path).exists():
            print(f"[BGI] Optional index DB enabled: {index_db_path} (ranked symbol search active).")
        else:
            print(
                "[BGI] Optional index DB path not found: "
                f"{index_db_path} (continuing with graph-based symbol fallback)."
            )
    else:
        print("[BGI] Optional index DB not provided (using graph-based symbol fallback).")

    _telemetry_mcp_start(graph_path)

    mcp = create_mcp_server(
        graph_path=graph_path,
        fuse_graph_path=str(resolved_fuse_path),
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
