"""
FUSE-MAP output writer.

Writes fuse-graph.json — a graph of clusters connected by their refused merges.
Each FuseEdge is an architectural boundary: two components that tried to merge
but were stopped by the cluster size cap. This is BGI's boundary map.
"""
from __future__ import annotations
import json
from pathlib import Path

from bgi.gate3.drs import FuseEdge


def write_fuse_graph(
    fuse_edges: list[FuseEdge],
    output_path: str | Path,
    max_cluster_size: int,
    total_units: int,
) -> None:
    """Write fuse-graph.json from a list of FuseEdges."""
    path = Path(output_path)

    nodes: dict[str, dict] = {}
    edges_out: list[dict] = []

    for fe in fuse_edges:
        for cid in (fe.from_cluster, fe.to_cluster):
            if cid not in nodes:
                nodes[cid] = {"id": cid}
        edges_out.append({
            "from": fe.from_cluster,
            "to": fe.to_cluster,
            "trigger_source": fe.trigger_source,
            "trigger_target": fe.trigger_target,
            "confidence": round(fe.trigger_confidence, 4),
            "refused_at_size": fe.refused_at_size,
        })

    payload = {
        "meta": {
            "total_units": total_units,
            "max_cluster_size": max_cluster_size,
            "fuse_event_count": len(fuse_edges),
            "boundary_cluster_count": len(nodes),
        },
        "boundary_clusters": list(nodes.values()),
        "bridges": edges_out,
    }

    path.write_text(json.dumps(payload, indent=2))
