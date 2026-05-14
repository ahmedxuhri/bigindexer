"""Tests for Big Indexer MCP architecture context service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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

    (tmp_path / "auth.py").write_text(
        "\n".join(
            [
                "class AuthService:",
                "    def login(self, request):",
                "        if not request:",
                "            raise ValueError('missing request')",
                "        return {'ok': True}",
                "",
                "    def verify(self, token):",
                "        return bool(token)",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "billing.py").write_text(
        "\n".join(
            [
                "class BillingService:",
                "    def charge(self, payload):",
                "        if not payload:",
                "            raise ValueError('empty payload')",
                "        record = {'charged': True}",
                "        return record",
                "",
                "    def refund(self, payment_id):",
                "        return {'refund': payment_id}",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "api.py").write_text(
        "\n".join(
            [
                "class Routes:",
                "    def post_login(self, request):",
                "        if not request:",
                "            return {'ok': False}",
                "        return {'ok': True}",
            ]
        ),
        encoding="utf-8",
    )

    graph = {
        "units": [
            {
                "id": "auth.py::AuthService::login",
                "cluster": cid_a,
                "language": "python",
                "confidence": 0.95,
                "tokens": ["COV.AUTHENTICATE", "COV.INTAKE", "COV.VALIDATE", "COV.OUTPUT"],
                "class_context": ["COV.CONTRACT"],
                "line_range": [2, 5],
            },
            {
                "id": "auth.py::AuthService::verify",
                "cluster": cid_a,
                "language": "python",
                "confidence": 0.92,
                "tokens": ["COV.AUTHENTICATE", "COV.VALIDATE"],
                "class_context": [],
                "line_range": [7, 8],
            },
            {
                "id": "billing.py::BillingService::charge",
                "cluster": cid_b,
                "language": "python",
                "confidence": 0.93,
                "tokens": ["COV.PERSIST", "COV.VALIDATE", "COV.INTAKE", "COV.OUTPUT"],
                "class_context": ["COV.CONTRACT"],
                "line_range": [2, 6],
            },
            {
                "id": "billing.py::BillingService::refund",
                "cluster": cid_b,
                "language": "python",
                "confidence": 0.9,
                "tokens": ["COV.FETCH", "COV.OUTPUT"],
                "class_context": [],
                "line_range": [8, 9],
            },
            {
                "id": "api.py::Routes::post_login",
                "cluster": cid_c,
                "language": "python",
                "confidence": 0.88,
                "tokens": ["COV.ROUTE", "COV.INTAKE", "COV.VALIDATE", "COV.OUTPUT"],
                "class_context": [],
                "line_range": [2, 5],
            },
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


def test_response_cache_reuse_and_reload_invalidation(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    seams_before = service.high_coupling_seams("", limit=10)
    cache_size_before = len(service._response_cache)
    seams_cached = service.high_coupling_seams("", limit=10)
    cache_size_after = len(service._response_cache)

    assert seams_cached == seams_before
    assert cache_size_before == cache_size_after
    assert seams_before["seam_count"] == 2

    graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
    graph_payload["edges"].append(
        {
            "source": "api.py::Routes::post_login",
            "target": "billing.py::BillingService::charge",
            "key": "COV.ROUTE",
            "lock": "COV.PERSIST",
            "confidence": 0.9,
            "type": "HARD",
        }
    )
    _write_json(graph_path, graph_payload)

    service.reload()
    assert len(service._response_cache) == 0

    seams_after = service.high_coupling_seams("", limit=10)
    assert seams_after["seam_count"] == 3


def test_classify_prompt_defaults_to_package_scope(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    classified = service.classify_prompt("How is AuthService wired with interfaces and goroutines?")
    assert classified["scope"] == "package"
    assert classified["needs_call_graph"] is True
    assert classified["needs_interfaces"] is True
    assert "call_graph" in classified["signals"]
    assert "interfaces" in classified["signals"]


def test_guided_arch_context_stages_without_repo_escalation(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    guided = service.guided_arch_context("Trace impact of auth.py::AuthService::login across boundaries", max_items=6)
    tiers = {step["tier"] for step in guided["steps"]}
    assert 1 in tiers
    assert tiers.issubset({1, 2, 3})
    assert guided["repository_context"] == {}


def test_guided_arch_context_repo_escalates_only_when_explicit_and_high_confidence(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    guided = service.guided_arch_context(
        "For the entire repo-wide architecture and cross-package boundaries in auth.py, map goroutines and interfaces.",
        max_items=6,
    )
    assert guided["classification"]["needs_repo_scope"] is True
    assert guided["classification"]["scope"] in {"file", "repository"}
    assert guided["repository_context"] != {}


def test_task_fingerprint_derives_cov_tokens(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    fingerprint = service.task_fingerprint("Add an API endpoint that validates input and persists user data.")
    assert fingerprint["status"] in {"ok", "ambiguous"}
    assert "INTAKE" in fingerprint["tokens"]
    assert "VALIDATE" in fingerprint["tokens"]
    assert "PERSIST" in fingerprint["tokens"]


def test_behavioral_twins_returns_ranked_candidates(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    twins = service.behavioral_twins(
        "Implement validation and persistence for a request payload.",
        limit=3,
        min_score=0.2,
    )
    assert twins["twin_candidates"]
    assert twins["twin_candidates"][0]["unit"] == "billing.py::BillingService::charge"
    assert twins["twin_candidates"][0]["source_available"] is True


def test_twin_context_includes_seam_and_rubric(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    ctx = service.twin_context(
        "Implement validation and persistence for a request payload.",
        limit=3,
        include_source=True,
    )
    assert ctx["rubric"] == [
        "exact function body",
        "no TODOs",
        "exact imports",
        "explicit error handling",
        "test case included",
    ]
    assert ctx["seam"]["anchor_unit"]
    assert ctx["status"] in {"ready_for_delta_generation", "needs_more_context"}


def test_twin_context_escalates_for_vague_task(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    ctx = service.twin_context("Fix the bug.", limit=3, include_source=False, min_score=0.25)
    assert ctx["status"] == "needs_more_context"
    assert ctx["confidence_gate"]["status"] == "no_confident_twin"
    assert "escalation" in ctx


def test_service_requires_fuse_graph_artifact(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    fuse_path.unlink()

    with pytest.raises(FileNotFoundError, match="Fuse graph file not found"):
        ArchitectureContextService(str(graph_path), str(fuse_path))


def test_service_rejects_invalid_graph_json(tmp_path: Path):
    graph_path, fuse_path, _ = _build_artifacts(tmp_path)
    graph_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid graph JSON"):
        ArchitectureContextService(str(graph_path), str(fuse_path))
