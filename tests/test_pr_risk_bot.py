"""Tests for the PR Architecture Risk Bot script."""

from __future__ import annotations

import json
from pathlib import Path

from bgi.mcp.context import ArchitectureContextService, cluster_id_from_rep
from scripts.pr_architecture_risk_bot import (
    COMMENT_MARKER,
    _normalize_paths,
    compute_risk_report,
    render_markdown,
    risk_level,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    rep_a = "src/auth.py::AuthService::login"
    rep_b = "src/payments.py::PaymentsService::charge"
    rep_c = "src/api.py::Routes::post_login"

    cid_a = cluster_id_from_rep(rep_a)
    cid_b = cluster_id_from_rep(rep_b)
    cid_c = cluster_id_from_rep(rep_c)

    graph = {
        "units": [
            {
                "id": rep_a,
                "cluster": cid_a,
                "language": "python",
                "confidence": 0.95,
                "tokens": ["COV.AUTHENTICATE", "COV.INTAKE", "COV.VALIDATE"],
                "class_context": ["COV.CONTRACT"],
                "line_range": [1, 8],
            },
            {
                "id": rep_b,
                "cluster": cid_b,
                "language": "python",
                "confidence": 0.93,
                "tokens": ["COV.PERSIST", "COV.OUTPUT"],
                "class_context": ["COV.CONTRACT"],
                "line_range": [1, 8],
            },
            {
                "id": rep_c,
                "cluster": cid_c,
                "language": "python",
                "confidence": 0.9,
                "tokens": ["COV.ROUTE", "COV.INTAKE"],
                "class_context": [],
                "line_range": [1, 8],
            },
        ],
        "edges": [
            {
                "source": rep_a,
                "target": rep_b,
                "key": "COV.AUTHENTICATE",
                "lock": "COV.PERSIST",
                "confidence": 0.91,
                "type": "HARD",
            },
            {
                "source": rep_b,
                "target": rep_c,
                "key": "COV.PERSIST",
                "lock": "COV.ROUTE",
                "confidence": 0.89,
                "type": "HARD",
            },
        ],
        "clusters": [
            {
                "id": cid_a,
                "size": 1,
                "probability": 0.98,
                "is_hard": True,
                "is_cross_file": False,
                "files": ["src/auth.py"],
                "dominant_tokens": ["COV.AUTHENTICATE"],
                "members": [rep_a],
            },
            {
                "id": cid_b,
                "size": 1,
                "probability": 0.97,
                "is_hard": True,
                "is_cross_file": False,
                "files": ["src/payments.py"],
                "dominant_tokens": ["COV.PERSIST"],
                "members": [rep_b],
            },
            {
                "id": cid_c,
                "size": 1,
                "probability": 0.96,
                "is_hard": True,
                "is_cross_file": False,
                "files": ["src/api.py"],
                "dominant_tokens": ["COV.ROUTE"],
                "members": [rep_c],
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
                "refused_at_size": 200,
            }
        ],
    }

    graph_path = tmp_path / "bgi-graph.json"
    fuse_path = tmp_path / "fuse-graph.json"
    _write_json(graph_path, graph)
    _write_json(fuse_path, fuse)
    return graph_path, fuse_path


def test_risk_level_thresholds():
    assert risk_level(10) == "LOW"
    assert risk_level(40) == "MEDIUM"
    assert risk_level(70) == "HIGH"


def test_normalize_paths_handles_commas_and_newlines():
    assert _normalize_paths("a.py, b.py\nc.py") == ["a.py", "b.py", "c.py"]


def test_compute_risk_report_and_markdown(tmp_path: Path):
    graph_path, fuse_path = _build_artifacts(tmp_path)
    service = ArchitectureContextService(str(graph_path), str(fuse_path))

    report = compute_risk_report(
        service=service,
        changed_files=["src/auth.py", "src/payments.py"],
        max_files=10,
        max_seams=8,
        impact_depth=2,
        max_neighbors=20,
        task_prompt="validate input and persist data",
    )

    assert report["changed_files_count"] == 2
    assert report["analyzed_files_count"] == 2
    assert report["top_files"]
    assert report["overall_score"] >= report["top_files"][0]["score"]
    assert report["twin_context"] == {} or "status" in report["twin_context"]

    markdown = render_markdown(report)
    assert COMMENT_MARKER in markdown
    assert "## BGI PR Architecture Risk Report" in markdown
    assert "Top risk files" in markdown
