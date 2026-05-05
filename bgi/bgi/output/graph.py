"""
Output — serialize the BGI graph to JSON-compatible dict, cluster adjacency list,
and GraphML (for Gephi / Cytoscape / AI graph tools).
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from collections import defaultdict

from bgi.core.fingerprint import COVFingerprint
from bgi.core.edges import BGIEdge
from bgi.gate3.drs import DRSResult


def serialize_graph(
    fingerprints: list[COVFingerprint],
    edges: list[BGIEdge],
    drs: DRSResult | None = None,
    sep_stats: dict | None = None,
    forecasts: list[dict] | None = None,
) -> dict:
    result: dict = {
        "bgi_version": "0.1.0",
        "stats": {
            "units": len(fingerprints),
            "edges": len(edges),
            "hard": sum(1 for e in edges if e.edge_type == "HARD"),
            "predicted": sum(1 for e in edges if e.edge_type == "PREDICTED"),
            "ghost": sum(1 for e in edges if e.edge_type == "GHOST"),
            "sep": sep_stats or {},
        },
        "units": [
            {
                "id": fp.unit_id,
                "tokens": [str(t) for t in fp.tokens],
                "class_context": [str(t) for t in fp.class_context],
                "confidence": fp.confidence,
                "source": fp.source,
                "language": fp.language,
                "line_range": list(fp.line_range),
                "hash": fp.fingerprint_hash,
                "cluster": drs.unit_to_cluster.get(fp.unit_id) if drs else None,
                "is_seam": fp.unit_id in drs.seam_units if drs else False,
            }
            for fp in fingerprints
        ],
        "edges": [
            {
                "source": e.source_id,
                "target": e.target_id,
                "key": str(e.key_token),
                "lock": str(e.lock_token),
                "confidence": e.confidence,
                "type": e.edge_type,
                "provenance": e.provenance,
            }
            for e in edges
        ],
    }

    if drs:
        result["stats"]["clusters"] = len(drs.clusters)
        result["stats"]["hard_clusters"] = sum(1 for c in drs.clusters if c.is_hard)
        result["stats"]["seam_units"] = len(drs.seam_units)
        result["clusters"] = [
            {
                "id": c.cluster_id,
                "size": c.size,
                "probability": c.probability,
                "radar_range": c.radar_range,
                "is_hard": c.is_hard,
                "is_cross_file": c.is_cross_file,
                "files": sorted(c.files),
                "dominant_tokens": [str(t) for t in c.dominant_tokens],
                "seams": list(c.seam_unit_ids),
                "members": c.member_ids,
            }
            for c in sorted(drs.clusters, key=lambda c: -c.probability)
        ]

    if forecasts:
        result["resurrection_forecasts"] = forecasts

    return result


# ── Cluster-level adjacency graph ─────────────────────────────────────────────

def build_cluster_graph(
    edges: list[BGIEdge],
    drs: DRSResult,
) -> dict:
    """
    Collapse unit-level edges to cluster-level directed adjacency.

    Each cluster node carries: id, dominant_tokens, probability, size, files.
    Each cluster edge carries: source_cluster, target_cluster, weight (edge count),
    dominant_key/lock token pair, and the max unit-edge confidence.

    This is the primary artifact for AI agent consumption — compact enough to fit
    in a prompt but semantically rich enough to answer architectural questions.
    """
    # cluster_id → Cluster object
    cmap = {c.cluster_id: c for c in drs.clusters}

    # unit_id → cluster_id
    u2c = drs.unit_to_cluster

    # Accumulate cluster→cluster edge stats
    # key: (src_cluster_id, tgt_cluster_id)
    edge_stats: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"weight": 0, "max_confidence": 0.0, "key_tokens": [], "lock_tokens": []}
    )

    for e in edges:
        src_c = u2c.get(e.source_id)
        tgt_c = u2c.get(e.target_id)
        if src_c is None or tgt_c is None or src_c == tgt_c:
            continue
        stats = edge_stats[(src_c, tgt_c)]
        stats["weight"] += 1
        stats["max_confidence"] = max(stats["max_confidence"], e.confidence)
        stats["key_tokens"].append(str(e.key_token))
        stats["lock_tokens"].append(str(e.lock_token))

    nodes = [
        {
            "id": c.cluster_id,
            "dominant_tokens": [str(t) for t in c.dominant_tokens],
            "probability": c.probability,
            "size": c.size,
            "is_hard": c.is_hard,
            "is_cross_file": c.is_cross_file,
            "files": sorted(c.files),
            "members": c.member_ids,
        }
        for c in sorted(drs.clusters, key=lambda c: -c.probability)
    ]

    cluster_edges = []
    for (src, tgt), stats in sorted(edge_stats.items()):
        # Most frequent key token for this cluster edge
        from collections import Counter
        dominant_key  = Counter(stats["key_tokens"]).most_common(1)[0][0]
        dominant_lock = Counter(stats["lock_tokens"]).most_common(1)[0][0]
        cluster_edges.append({
            "source": src,
            "target": tgt,
            "weight": stats["weight"],
            "max_confidence": round(stats["max_confidence"], 4),
            "dominant_key": dominant_key,
            "dominant_lock": dominant_lock,
        })

    return {
        "nodes": nodes,
        "edges": cluster_edges,
        "stats": {
            "clusters": len(nodes),
            "cluster_edges": len(cluster_edges),
        },
    }


# ── GraphML export ────────────────────────────────────────────────────────────

def to_graphml(
    edges: list[BGIEdge],
    drs: DRSResult,
    *,
    cluster_level: bool = True,
) -> str:
    """
    Serialize the BGI graph as GraphML (XML).

    When cluster_level=True (default): exports the cluster graph (compact, AI-friendly).
    When cluster_level=False: exports the full unit graph (verbose, for deep inspection).

    Compatible with Gephi, Cytoscape, and networkx.read_graphml().
    """
    graphml = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/graphml")

    # Declare attribute keys
    def _key(id_, for_, name, type_):
        ET.SubElement(graphml, "key", id=id_, **{"for": for_}, **{"attr.name": name}, **{"attr.type": type_})

    if cluster_level:
        _key("probability",  "node", "probability",      "double")
        _key("size",         "node", "size",              "int")
        _key("is_hard",      "node", "is_hard",           "boolean")
        _key("tokens",       "node", "dominant_tokens",   "string")
        _key("files",        "node", "files",             "string")
        _key("weight",       "edge", "weight",            "int")
        _key("confidence",   "edge", "max_confidence",    "double")
        _key("key_token",    "edge", "dominant_key",      "string")
        _key("lock_token",   "edge", "dominant_lock",     "string")

        g = ET.SubElement(graphml, "graph", id="cluster_graph", edgedefault="directed")
        cg = build_cluster_graph(edges, drs)

        for node in cg["nodes"]:
            n = ET.SubElement(g, "node", id=node["id"])
            _data(n, "probability", str(node["probability"]))
            _data(n, "size",        str(node["size"]))
            _data(n, "is_hard",     str(node["is_hard"]).lower())
            _data(n, "tokens",      ",".join(node["dominant_tokens"]))
            _data(n, "files",       ",".join(node["files"]))

        for i, e in enumerate(cg["edges"]):
            el = ET.SubElement(g, "edge", id=f"ce{i}", source=e["source"], target=e["target"])
            _data(el, "weight",     str(e["weight"]))
            _data(el, "confidence", str(e["max_confidence"]))
            _data(el, "key_token",  e["dominant_key"])
            _data(el, "lock_token", e["dominant_lock"])

    else:
        _key("language",   "node", "language",    "string")
        _key("confidence", "node", "confidence",  "double")
        _key("tokens",     "node", "tokens",      "string")
        _key("cluster",    "node", "cluster",     "string")
        _key("edge_type",  "edge", "type",        "string")
        _key("confidence", "edge", "confidence",  "double")

        g = ET.SubElement(graphml, "graph", id="unit_graph", edgedefault="directed")
        u2c = drs.unit_to_cluster if drs else {}

        # Collect all unit ids referenced in edges
        unit_ids = {e.source_id for e in edges} | {e.target_id for e in edges}
        for uid in sorted(unit_ids):
            n = ET.SubElement(g, "node", id=uid)
            _data(n, "cluster", u2c.get(uid, ""))

        for i, e in enumerate(edges):
            el = ET.SubElement(g, "edge", id=f"e{i}", source=e.source_id, target=e.target_id)
            _data(el, "edge_type",  e.edge_type)
            _data(el, "confidence", str(e.confidence))

    ET.indent(graphml, space="  ")
    return ET.tostring(graphml, encoding="unicode", xml_declaration=True)


def write_graphml(
    edges: list[BGIEdge],
    drs: DRSResult,
    output_path: str,
    *,
    cluster_level: bool = True,
) -> None:
    """Write GraphML to a file."""
    xml = to_graphml(edges, drs, cluster_level=cluster_level)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml)


def _data(parent: ET.Element, key: str, text: str) -> None:
    el = ET.SubElement(parent, "data", key=key)
    el.text = text

