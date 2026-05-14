"""Tests for MCP server startup artifact guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from bgi.mcp.server import _require_json_artifact, _resolve_fuse_path, _scan_hint


def test_resolve_fuse_path_defaults_next_to_graph():
    graph = "tmp/bgi-graph.json"
    assert _resolve_fuse_path(graph, None) == Path("tmp/fuse-graph.json")


def test_require_json_artifact_fails_when_missing(tmp_path: Path):
    missing = tmp_path / "missing.json"
    hint = _scan_hint("bgi-graph.json", tmp_path / "fuse-graph.json")

    with pytest.raises(RuntimeError, match="Missing required graph file"):
        _require_json_artifact(missing, "graph", hint)


def test_require_json_artifact_fails_when_invalid_json(tmp_path: Path):
    broken = tmp_path / "broken.json"
    broken.write_text("{nope", encoding="utf-8")
    hint = _scan_hint("bgi-graph.json", tmp_path / "fuse-graph.json")

    with pytest.raises(RuntimeError, match="Invalid JSON in required graph file"):
        _require_json_artifact(broken, "graph", hint)
