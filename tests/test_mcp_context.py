"""Tests for Big Indexer MCP architecture context service."""

from __future__ import annotations

import json
from pathlib import Path

from bgi.mcp.context import ArchitectureContextService, cluster_id_from_rep


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_artifacts(tmp_path: Path) -> tuple[Path, Path, dict]:
    rep_a = "auth.py::AuthService::login"
    rep_b = "billing.py::BillingService::charge"
    rep_c = "api.py::Routes::post_login"

    cid_a = cluster_id_from_rep(rep_a)
    cid_b = cluster_id_from_rep(rep_b)
    cid_c = cluster_id_from_rep(rep_c)

    graph = {
        "units": [
            {"id": "auth.py::AuthService::login", "cluster": cid_a, "language": "python"},
            {"id": "auth.py::AuthService::verify", "cluster": cid_a, "language": "python"},
            {"id": "billing.py::BillingService::charge", "cluster": cid_b, "language": "python"},
            {"id": "billing.py::BillingService::refund", "cluster": cid_b, "language": "python"},
            {"id": "api.py::Routes::post_login", "cluster": cid_c, "language": "python"},
        ],
        "edges": [
            {
                "source": "auth.py::AuthService::login",
                "target": "billing.py::BillingService::charge",
                "key": "COV.AUTHENTICATE",
                "lock": "COV.ROUTE",
                "confidence": 0.93,
                "type": "HARD",
            },
            {
                "source": "auth.py::AuthService::verify",
                "target": "api.py::Routes::post_login",
                "key": "COV.AUTHENTICATE",
                "lock": "COV.ROUTE",
                "confidence": 0.91,
                "type": "HARD",
            },
            {
                "source": "billing.py::BillingService::charge",
                "target": "billing.py::BillingService::refund",
                "key": "COV.FETCH",
                "lock": "COV.PERSIST",
                "confidence": 0.88,
                "type": "HARD",
            },
        ],
        "clusters": [
            {
                "id": cid_a,
                "size": 2,
                "probability": 0.98,
                "is_hard": True,
                "is_cross_file": False,
                "files": ["auth.py"],
                "dominant_tokens": ["COV.AUTHENTICATE", "COV.INTAKE"],
                "members": ["auth.py::AuthService::login", "auth.py::AuthService::verify"],
            },
            {
                "id": cid_b,
                "size": 2,
                "probability": 0.96,
                "is_hard": True,
                "is_cross_file": False,
                "files": ["billing.py"],
                "dominant_tokens": ["COV.FETCH", "COV.PERSIST"],
                "members": ["billing.py::BillingService::charge", "billing.py::BillingService::refund"],
            },
            {
                "id": cid_c,
                "size": 1,
                "probability": 0.9,
                "is_hard": True,
                "is_cross_file": False,
                "files": ["api.py"],
                "dominant_tokens": ["COV.ROUTE"],
                "members": ["api.py::Routes::post_login"],
            },
        ],
    }

    fuse = {
        "meta": {"fuse_event_count": 1},
        "boundary_clusters": [{"id": rep_a}, {"id": rep_b}],
        "bridges": [
            {
                "from": rep_a,
                "to": rep_b,
                "trigger_source": rep_a,
                "trigger_target": rep_b,
                "confidence": 0.95,
                "refused_at_size": 300,
            }
        ],
    }

    graph_path = tmp_path / "bgi-graph.json"
    fuse_path = tmp_path / "fuse-graph.json"
    _write_json(graph_path, graph)
    _write_json(fuse_path, fuse)
    return graph_path, fuse_path, {"cid_a": cid_a, "cid_b": cid_b, "cid_c": cid_c}


def test_cluster_of_file_and_summary(tmp_path: Path):
    graph_path, fuse_path, ids = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    by_file = service.cluster_of_file("auth.py")
    assert by_file["found"] is True
    assert by_file["clusters"][0]["id"] == ids["cid_a"]

    summary = service.architecture_summary("auth.py")
    assert summary["cluster_count"] >= 1
    assert summary["top_clusters"][0]["id"] == ids["cid_a"]


def test_boundary_edges_maps_fuse_representatives(tmp_path: Path):
    graph_path, fuse_path, ids = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    boundaries = service.boundary_edges("auth.py")
    assert boundaries["found"] is True
    assert boundaries["bridge_count"] == 1
    bridge = boundaries["bridges"][0]
    assert bridge["from_cluster"] == ids["cid_a"]
    assert bridge["to_cluster"] == ids["cid_b"]


def test_high_coupling_seams_for_file_scope(tmp_path: Path):
    graph_path, fuse_path, ids = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    seams = service.high_coupling_seams("auth.py")
    assert seams["seam_count"] >= 1
    seam_pairs = {(s["source_cluster"], s["target_cluster"]) for s in seams["seams"]}
    assert (ids["cid_a"], ids["cid_b"]) in seam_pairs


def test_impact_neighbors_and_symbol_fallback_search(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    impact = service.impact_neighbors("auth.py", depth=1)
    assert impact["found"] is True
    impacted_units = {u["unit_id"] for u in impact["impacted_units"]}
    assert "auth.py::AuthService::login" in impacted_units
    assert "billing.py::BillingService::charge" in impacted_units

    search = service.search_symbols("login", limit=5)
    assert search["count"] >= 1
    assert search["results"][0]["name"] in {"login", "post_login"}
