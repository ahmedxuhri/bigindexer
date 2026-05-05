"""
Tests for AI Position 3 — Architecture Narrator (narrator.py).

Coverage:
  - Heuristic path: always runs, no client needed
  - _infer_role: role mapping from dominant COV tokens
  - _cluster_name: name extraction from member IDs
  - _cross_cluster_edges: cross-boundary edge detection + lifecycle filtering
  - AI enhancement: mock OpenAI-compatible client
  - AI failure: malformed JSON / exception → falls back to heuristic md
  - ArchitectureNarrator.model: configurable, defaults to deepseek-v4-flash
  - Pipeline wiring: narrator receives AI client when --ai-key provided
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from bgi.ai.narrator import (
    ArchitectureNarrator,
    NarratorResult,
    _infer_role,
    _cluster_name,
    _cross_cluster_edges,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _minimal_graph(n_clusters: int = 2) -> dict:
    """Build a minimal BGI graph dict for narrator tests."""
    units = []
    clusters = []
    edges = []

    for i in range(n_clusters):
        cid = f"c{i}"
        uid_a = f"mod_{i}.py::ClassA::method_a"
        uid_b = f"mod_{i}.py::ClassA::method_b"
        units += [
            {"id": uid_a, "tokens": ["COV.FETCH"], "cluster": cid, "is_seam": False},
            {"id": uid_b, "tokens": ["COV.PERSIST"], "cluster": cid, "is_seam": False},
        ]
        clusters.append({
            "id": cid,
            "members": [uid_a, uid_b],
            "files": [f"mod_{i}.py"],
            "dominant_tokens": ["COV.FETCH", "COV.PERSIST"],
            "probability": 0.85,
            "radar_range": 40,
            "is_hard": True,
            "is_cross_file": False,
        })

    # Cross-cluster edge between cluster 0 and cluster 1
    if n_clusters >= 2:
        edges.append({
            "source": "mod_0.py::ClassA::method_a",
            "target": "mod_1.py::ClassA::method_b",
            "key": "COV.FETCH",
            "lock": "COV.PERSIST",
            "type": "HARD",
        })

    return {
        "units": units,
        "clusters": clusters,
        "edges": edges,
        "stats": {
            "units": len(units),
            "edges": len(edges),
            "hard": len(edges),
            "predicted": 0,
            "clusters": n_clusters,
            "hard_clusters": n_clusters,
            "seam_units": 0,
            "sep": {"pending": 0, "intentional_boundary": 0},
        },
        "resurrection_forecasts": [],
    }


def _make_openai_client(response_text: str):
    """Mock OpenAI-compatible client."""
    message = MagicMock()
    message.content = response_text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


# ── _infer_role ───────────────────────────────────────────────────────────────

class TestInferRole:
    def test_auth_and_authz(self):
        assert _infer_role(["COV.AUTHENTICATE", "COV.AUTHORIZE"]) == "Authentication & Authorization"

    def test_authenticate_only(self):
        assert _infer_role(["COV.AUTHENTICATE"]) == "Authentication"

    def test_data_access(self):
        assert _infer_role(["COV.PERSIST", "COV.FETCH"]) == "Data Access / Repository"

    def test_data_reader(self):
        assert _infer_role(["COV.FETCH"]) == "Data Reader"

    def test_data_writer(self):
        assert _infer_role(["COV.PERSIST"]) == "Data Writer"

    def test_event_bus(self):
        assert _infer_role(["COV.EMIT", "COV.SUBSCRIBE"]) == "Event Bus / Pub-Sub"

    def test_lifecycle(self):
        assert _infer_role(["COV.INIT", "COV.TEARDOWN"]) == "Lifecycle Manager"

    def test_validator(self):
        assert _infer_role(["COV.VALIDATE"]) == "Validator"

    def test_transformer(self):
        assert _infer_role(["COV.TRANSFORM"]) == "Data Transformer"

    def test_general_logic_fallback(self):
        assert _infer_role(["COV.ASYNC"]) == "General Logic"

    def test_empty_tokens(self):
        assert _infer_role([]) == "General Logic"

    def test_test_suite(self):
        assert _infer_role(["COV.TEST"]) == "Test Suite"


# ── _cluster_name ─────────────────────────────────────────────────────────────

class TestClusterName:
    def test_class_name_wins(self):
        cluster = {
            "id": "c0",
            "members": [
                "models.py::UserService::create",
                "models.py::UserService::delete",
                "models.py::UserService::get",
            ],
            "files": ["models.py"],
        }
        assert _cluster_name(cluster) == "UserService"

    def test_file_stem_fallback(self):
        cluster = {
            "id": "c0",
            "members": ["auth_utils.py::helper"],
            "files": ["auth_utils.py"],
        }
        assert _cluster_name(cluster) == "Auth Utils"

    def test_id_fallback(self):
        cluster = {"id": "c0", "members": [], "files": []}
        assert _cluster_name(cluster) == "c0"


# ── _cross_cluster_edges ──────────────────────────────────────────────────────

class TestCrossClusterEdges:
    def test_finds_cross_cluster_edge(self):
        unit_to_cluster = {"a.py::f": "c0", "b.py::g": "c1"}
        edges = [{"source": "a.py::f", "target": "b.py::g", "key": "COV.FETCH", "lock": "COV.PERSIST", "type": "HARD"}]
        result = _cross_cluster_edges(edges, unit_to_cluster)
        assert len(result) == 1
        assert result[0]["from_cluster"] == "c0"
        assert result[0]["to_cluster"] == "c1"

    def test_ignores_same_cluster(self):
        unit_to_cluster = {"a.py::f": "c0", "a.py::g": "c0"}
        edges = [{"source": "a.py::f", "target": "a.py::g", "key": "COV.FETCH", "lock": "COV.PERSIST", "type": "HARD"}]
        result = _cross_cluster_edges(edges, unit_to_cluster)
        assert result == []

    def test_filters_lifecycle_noise(self):
        unit_to_cluster = {"a.py::init": "c0", "b.py::teardown": "c1"}
        edges = [{"source": "a.py::init", "target": "b.py::teardown",
                  "key": "COV.INIT", "lock": "COV.TEARDOWN", "type": "HARD"}]
        result = _cross_cluster_edges(edges, unit_to_cluster)
        assert result == []

    def test_deduplicates(self):
        unit_to_cluster = {"a.py::f": "c0", "b.py::g": "c1"}
        edge = {"source": "a.py::f", "target": "b.py::g", "key": "COV.FETCH", "lock": "COV.PERSIST", "type": "HARD"}
        result = _cross_cluster_edges([edge, edge], unit_to_cluster)
        assert len(result) == 1


# ── Heuristic path ────────────────────────────────────────────────────────────

class TestNarratorHeuristic:
    def test_returns_narrator_result(self):
        graph = _minimal_graph()
        narrator = ArchitectureNarrator(enabled=False)
        result = narrator.narrate(graph, root="/my/service")
        assert isinstance(result, NarratorResult)
        assert not result.ai_enhanced

    def test_agents_md_contains_cluster_section(self):
        graph = _minimal_graph()
        narrator = ArchitectureNarrator(enabled=False)
        result = narrator.narrate(graph, root="/my/service")
        assert "## Clusters" in result.agents_md
        assert "## Overview" in result.agents_md

    def test_agents_md_contains_role(self):
        graph = _minimal_graph()
        narrator = ArchitectureNarrator(enabled=False)
        result = narrator.narrate(graph, root="/my/service")
        assert "Data Access / Repository" in result.agents_md

    def test_cross_cluster_section_present(self):
        graph = _minimal_graph(n_clusters=2)
        narrator = ArchitectureNarrator(enabled=False)
        result = narrator.narrate(graph, root="/svc")
        assert "Cross-Cluster Relationships" in result.agents_md

    def test_empty_graph(self):
        graph = {"units": [], "clusters": [], "edges": [], "stats": {
            "units": 0, "edges": 0, "hard": 0, "predicted": 0,
            "clusters": 0, "hard_clusters": 0, "seam_units": 0,
            "sep": {"pending": 0, "intentional_boundary": 0},
        }, "resurrection_forecasts": []}
        narrator = ArchitectureNarrator(enabled=False)
        result = narrator.narrate(graph, root="/empty")
        assert "# BGI Architecture" in result.agents_md


# ── AI enhancement ────────────────────────────────────────────────────────────

class TestNarratorAI:
    def test_ai_enhanced_flag_set(self):
        ai_response = json.dumps({
            "cluster_names": {"c0": "Auth Gateway", "c1": "Data Engine"},
            "concerns": [],
        })
        client = _make_openai_client(ai_response)
        narrator = ArchitectureNarrator(enabled=True, client=client, model="deepseek-v4-flash")
        graph = _minimal_graph()
        result = narrator.narrate(graph, root="/svc")
        assert result.ai_enhanced is True

    def test_ai_enriches_cluster_names(self):
        ai_response = json.dumps({
            "cluster_names": {"c0": "User Repository", "c1": "Event Dispatcher"},
            "concerns": [],
        })
        client = _make_openai_client(ai_response)
        narrator = ArchitectureNarrator(enabled=True, client=client)
        graph = _minimal_graph()
        result = narrator.narrate(graph, root="/svc")
        assert "User Repository" in result.agents_md
        assert result.cluster_names["c0"] == "User Repository"

    def test_ai_appends_concerns(self):
        ai_response = json.dumps({
            "cluster_names": {},
            "concerns": ["Suspicious bidirectional FETCH↔PERSIST between c0 and c1"],
        })
        client = _make_openai_client(ai_response)
        narrator = ArchitectureNarrator(enabled=True, client=client)
        graph = _minimal_graph()
        result = narrator.narrate(graph, root="/svc")
        assert "Architectural Concerns (AI)" in result.agents_md
        assert "Suspicious bidirectional" in result.agents_md

    def test_ai_malformed_json_falls_back(self):
        client = _make_openai_client("this is not json at all")
        narrator = ArchitectureNarrator(enabled=True, client=client)
        graph = _minimal_graph()
        result = narrator.narrate(graph, root="/svc")
        assert result.ai_enhanced is False
        assert "AI enhancement failed" in result.agents_md

    def test_ai_exception_falls_back(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("network error")
        narrator = ArchitectureNarrator(enabled=True, client=client)
        graph = _minimal_graph()
        result = narrator.narrate(graph, root="/svc")
        assert result.ai_enhanced is False
        assert "## Clusters" in result.agents_md  # heuristic md still present

    def test_model_passed_to_client(self):
        ai_response = json.dumps({"cluster_names": {}, "concerns": []})
        client = _make_openai_client(ai_response)
        narrator = ArchitectureNarrator(enabled=True, client=client, model="deepseek-v4-pro")
        graph = _minimal_graph()
        narrator.narrate(graph, root="/svc")
        call_kwargs = client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("model") == "deepseek-v4-pro"

    def test_no_client_disabled(self):
        narrator = ArchitectureNarrator(enabled=True, client=None)
        graph = _minimal_graph()
        result = narrator.narrate(graph, root="/svc")
        assert result.ai_enhanced is False

    def test_default_model_is_deepseek(self):
        narrator = ArchitectureNarrator()
        assert narrator.model == "deepseek-v4-flash"

    def test_ai_empty_concerns_no_section(self):
        ai_response = json.dumps({"cluster_names": {}, "concerns": []})
        client = _make_openai_client(ai_response)
        narrator = ArchitectureNarrator(enabled=True, client=client)
        graph = _minimal_graph()
        result = narrator.narrate(graph, root="/svc")
        assert "Architectural Concerns (AI)" not in result.agents_md

    def test_ai_code_block_stripped(self):
        """LLMs sometimes wrap JSON in ```json...```."""
        ai_response = '```json\n{"cluster_names": {"c0": "MyService"}, "concerns": []}\n```'
        client = _make_openai_client(ai_response)
        narrator = ArchitectureNarrator(enabled=True, client=client)
        graph = _minimal_graph()
        result = narrator.narrate(graph, root="/svc")
        assert result.ai_enhanced is True
        assert "MyService" in result.agents_md
