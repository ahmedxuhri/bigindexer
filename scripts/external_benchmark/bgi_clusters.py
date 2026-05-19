"""Extract a {file_path: cluster_id} mapping from a bgi-graph.json.

BGI clusters at unit (function) granularity. We aggregate to file level
by majority vote: each file is assigned the cluster that owns the most
units in that file. Ties are broken by lexicographic cluster id (stable).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict


def file_clusters_from_graph(graph_path: str) -> dict[str, str]:
    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    file_unit_clusters: dict[str, list[str]] = defaultdict(list)
    for unit in graph.get("units", []):
        uid = unit.get("id", "")
        cluster = unit.get("cluster")
        if not cluster:
            continue
        file_path = uid.split("::", 1)[0] if "::" in uid else uid
        file_unit_clusters[file_path].append(cluster)

    out: dict[str, str] = {}
    for file_path, clusters in file_unit_clusters.items():
        counts = Counter(clusters)
        max_count = max(counts.values())
        candidates = sorted(c for c, n in counts.items() if n == max_count)
        out[file_path] = candidates[0]
    return out


if __name__ == "__main__":
    import sys
    from collections import Counter as C
    fc = file_clusters_from_graph(sys.argv[1])
    sizes = C(fc.values())
    print(f"files with clusters: {len(fc)}, distinct clusters: {len(sizes)}")
    print(f"top 5 sizes: {sizes.most_common(5)}")
