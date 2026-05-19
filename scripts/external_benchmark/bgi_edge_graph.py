"""Project BGI unit-level edges to file-level edges.

BGI's bgi-graph.json contains edges between code units (functions/methods).
For clustering at the file level, we aggregate: every unit→unit edge becomes
a file→file edge with weight = number of underlying unit edges.

Self-loops (edges where both units live in the same file) are dropped — they
don't influence inter-file clustering.

We also offer a HARD-only filter: BGI marks edges as HARD or SUSPENDED. HARD
edges passed all gate-2 scope checks; SUSPENDED ones did not. Using HARD-only
isolates BGI's confident claims.
"""
from __future__ import annotations

import json
from collections import defaultdict

import networkx as nx
from networkx.algorithms.community import louvain_communities


def _file_of_unit(unit_id: str) -> str:
    return unit_id.split("::", 1)[0] if "::" in unit_id else unit_id


def file_graph_from_bgi_edges(
    graph_path: str,
    files: list[str] | None = None,
    hard_only: bool = True,
) -> nx.Graph:
    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    file_set = set(files) if files is not None else None
    edge_weights: dict[tuple[str, str], int] = defaultdict(int)

    for edge in graph.get("edges", []):
        if hard_only and edge.get("type") != "HARD":
            continue
        src_file = _file_of_unit(edge.get("source", ""))
        tgt_file = _file_of_unit(edge.get("target", ""))
        if src_file == tgt_file or not src_file or not tgt_file:
            continue
        if file_set is not None and (src_file not in file_set or tgt_file not in file_set):
            continue
        u, v = sorted([src_file, tgt_file])
        edge_weights[(u, v)] += 1

    g = nx.Graph()
    nodes = files if files is not None else (
        {_file_of_unit(u.get("id", "")) for u in graph.get("units", [])}
    )
    g.add_nodes_from(nodes)
    for (u, v), w in edge_weights.items():
        g.add_edge(u, v, weight=w)
    return g


def louvain_clusters_from_graph(graph: nx.Graph, seed: int = 42) -> dict[str, str]:
    communities = louvain_communities(graph, weight="weight", seed=seed)
    out: dict[str, str] = {}
    for i, comm in enumerate(communities):
        for node in comm:
            out[node] = f"louvain_{i:03d}"
    return out


if __name__ == "__main__":
    import sys
    from collections import Counter
    g = file_graph_from_bgi_edges(sys.argv[1])
    print(f"file graph from BGI edges: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    weights = [d.get("weight", 1) for _, _, d in g.edges(data=True)]
    if weights:
        print(f"edge weights: min={min(weights)} med={sorted(weights)[len(weights)//2]} max={max(weights)}")
    clusters = louvain_clusters_from_graph(g)
    sizes = Counter(clusters.values())
    print(f"Louvain on BGI edges: {len(sizes)} communities, top: {sizes.most_common(5)}")
