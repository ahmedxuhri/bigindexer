"""
Output — serialize the BGI graph to a JSON-compatible dict.
"""
from __future__ import annotations

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
