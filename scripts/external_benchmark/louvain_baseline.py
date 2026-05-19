"""Python import-graph Louvain baseline.

Parses Python files with the stdlib AST module, builds a directed graph
of file-to-file import edges, then runs Louvain community detection on
the undirected projection.

This is the standard 'syntax-only call/import graph + generic community
detection' approach — the exact alternative the README's comparison
table claims BGI improves on.
"""
from __future__ import annotations

import ast
import os
from collections import defaultdict
from pathlib import Path
from typing import Mapping

import networkx as nx
from networkx.algorithms.community import louvain_communities


def _module_to_file_index(repo_root: str, files: list[str]) -> dict[str, str]:
    """Map dotted module path to file path (relative to repo_root).

    For each .py file, register it under the module path implied by its
    location (e.g. django/db/models/query.py -> django.db.models.query
    and django.db.models.query.__init__ etc).
    """
    idx: dict[str, str] = {}
    for f in files:
        if not f.endswith(".py"):
            continue
        no_ext = f[:-3]
        parts = no_ext.split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        dotted = ".".join(parts)
        idx[dotted] = f
    return idx


def _resolve_relative(current_module: str, level: int, name: str | None) -> str | None:
    if level == 0:
        return name
    parts = current_module.split(".")
    if level > len(parts):
        return None
    base = parts[:len(parts) - level + 1] if name else parts[:len(parts) - level]
    if name:
        base = parts[:len(parts) - (level - 1)]
        return ".".join([*base, name]) if base else name
    return ".".join(base) if base else None


def _file_to_module(file_path: str) -> str:
    no_ext = file_path[:-3]
    parts = no_ext.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_target(target_dotted: str, module_index: Mapping[str, str]) -> str | None:
    """Find the file in module_index whose module path is the longest
    matching prefix of target_dotted.
    """
    if target_dotted in module_index:
        return module_index[target_dotted]
    parts = target_dotted.split(".")
    while parts:
        parts.pop()
        candidate = ".".join(parts)
        if candidate in module_index:
            return module_index[candidate]
    return None


def build_import_graph(repo_root: str, files: list[str]) -> nx.Graph:
    module_index = _module_to_file_index(repo_root, files)
    edges: dict[tuple[str, str], int] = defaultdict(int)

    for f in files:
        if not f.endswith(".py"):
            continue
        full = os.path.join(repo_root, f)
        try:
            with open(full, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=full)
        except (SyntaxError, UnicodeDecodeError):
            continue

        current_module = _file_to_module(f)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target_file = _resolve_target(alias.name, module_index)
                    if target_file and target_file != f:
                        edges[(f, target_file)] += 1
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    target_dotted = _resolve_relative(current_module, node.level, node.module)
                else:
                    target_dotted = node.module
                if not target_dotted:
                    continue
                target_file = _resolve_target(target_dotted, module_index)
                if target_file and target_file != f:
                    edges[(f, target_file)] += 1
                for alias in node.names:
                    sub = f"{target_dotted}.{alias.name}" if target_dotted else alias.name
                    sub_file = _resolve_target(sub, module_index)
                    if sub_file and sub_file != f:
                        edges[(f, sub_file)] += 1

    g = nx.Graph()
    g.add_nodes_from(files)
    for (u, v), w in edges.items():
        if g.has_edge(u, v):
            g[u][v]["weight"] += w
        else:
            g.add_edge(u, v, weight=w)
    return g


def louvain_clusters(graph: nx.Graph, seed: int = 42) -> dict[str, str]:
    communities = louvain_communities(graph, weight="weight", seed=seed)
    out: dict[str, str] = {}
    for i, comm in enumerate(communities):
        for node in comm:
            out[node] = f"louvain_{i:03d}"
    return out


if __name__ == "__main__":
    import sys
    from ground_truth import collect_files
    repo, pkg = sys.argv[1], sys.argv[2]
    files = collect_files(repo, pkg, ["py"])
    g = build_import_graph(repo, files)
    print(f"graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    clusters = louvain_clusters(g)
    from collections import Counter
    sizes = Counter(clusters.values())
    print(f"louvain communities: {len(sizes)}, largest: {sizes.most_common(5)}")
