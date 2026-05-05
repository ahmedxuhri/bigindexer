"""Tests for bgi.output.html_viz — graph HTML visualizer."""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from bgi.output.html_viz import (
    _build_vis_data,
    _dominant_token,
    _node_colour,
    _TOKEN_COLOURS,
    generate_html,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _unit(uid: str, tokens: list[str], confidence: float = 0.8,
          cluster: str | None = None, is_seam: bool = False) -> dict:
    return {
        "id": uid,
        "tokens": tokens,
        "class_context": [],
        "confidence": confidence,
        "source": f"src/{uid.split('.')[0]}.py",
        "language": "python",
        "line_range": [1, 10],
        "hash": "abc",
        "cluster": cluster,
        "is_seam": is_seam,
    }


def _edge(src: str, tgt: str, etype: str = "HARD", confidence: float = 0.9) -> dict:
    return {"source": src, "target": tgt, "key": "COV.FETCH", "lock": "COV.PERSIST",
            "confidence": confidence, "type": etype, "provenance": "gate2"}


def _minimal_graph() -> dict:
    units = [
        _unit("auth.login",   ["COV.AUTHENTICATE"], 0.9, cluster="C0"),
        _unit("auth.logout",  ["COV.AUTHENTICATE"], 0.7, cluster="C0"),
        _unit("db.save",      ["COV.PERSIST"],      0.85, cluster="C1"),
        _unit("db.fetch",     ["COV.FETCH"],        0.6,  cluster="C1"),
        _unit("utils.helper", ["COV.ASYNC"],        0.5),
    ]
    edges = [
        _edge("auth.login",  "db.save",   "HARD",      0.95),
        _edge("auth.logout", "db.fetch",  "PREDICTED", 0.6),
        _edge("db.save",     "db.fetch",  "GHOST",     0.3),
    ]
    clusters = [
        {"id": "C0", "size": 2, "probability": 0.9, "is_hard": True,
         "dominant_tokens": ["COV.AUTHENTICATE"], "members": ["auth.login", "auth.logout"],
         "seams": [], "files": ["src/auth.py"]},
        {"id": "C1", "size": 2, "probability": 0.75, "is_hard": False,
         "dominant_tokens": ["COV.PERSIST"], "members": ["db.save", "db.fetch"],
         "seams": [], "files": ["src/db.py"]},
    ]
    return {
        "bgi_version": "0.1.0",
        "stats": {"units": 5, "edges": 3, "hard": 1, "predicted": 1, "ghost": 1, "clusters": 2, "hard_clusters": 1},
        "units": units,
        "edges": edges,
        "clusters": clusters,
    }


# ── _dominant_token ────────────────────────────────────────────────────────────

class TestDominantToken:
    def test_returns_first_non_structural(self):
        u = _unit("x", ["COV.ASYNC", "COV.FETCH"])
        assert _dominant_token(u) == "FETCH"

    def test_structural_only_returns_unknown(self):
        u = _unit("x", ["COV.ASYNC", "COV.INTAKE"])
        assert _dominant_token(u) == "UNKNOWN"

    def test_empty_tokens_returns_unknown(self):
        u = _unit("x", [])
        assert _dominant_token(u) == "UNKNOWN"

    def test_non_structural_first(self):
        u = _unit("x", ["COV.PERSIST"])
        assert _dominant_token(u) == "PERSIST"

    def test_multiple_non_structural_returns_first(self):
        u = _unit("x", ["COV.FETCH", "COV.PERSIST"])
        assert _dominant_token(u) == "FETCH"


# ── _node_colour ───────────────────────────────────────────────────────────────

class TestNodeColour:
    def test_known_token_returns_palette_colour(self):
        u = _unit("x", ["COV.FETCH"])
        assert _node_colour(u) == _TOKEN_COLOURS["FETCH"]

    def test_unknown_token_returns_grey(self):
        u = _unit("x", [])
        assert _node_colour(u) == "#cccccc"

    def test_authenticate_colour(self):
        u = _unit("x", ["COV.AUTHENTICATE"])
        assert _node_colour(u) == _TOKEN_COLOURS["AUTHENTICATE"]


# ── _build_vis_data ────────────────────────────────────────────────────────────

class TestBuildVisData:
    def setup_method(self):
        self.graph = _minimal_graph()
        self.vis = _build_vis_data(self.graph)

    def test_returns_required_keys(self):
        assert set(self.vis.keys()) == {"nodes", "links", "clusters", "legend", "stats"}

    def test_node_count(self):
        assert len(self.vis["nodes"]) == 5

    def test_node_has_required_fields(self):
        n = self.vis["nodes"][0]
        for f in ("id", "label", "full_id", "tokens", "confidence", "source",
                  "language", "line_range", "cluster", "is_seam",
                  "dominant_token", "colour", "radius"):
            assert f in n, f"missing field: {f}"

    def test_node_label_is_last_segment(self):
        n = next(n for n in self.vis["nodes"] if n["full_id"] == "auth.login")
        assert n["label"] == "login"

    def test_node_colour_assigned(self):
        n = next(n for n in self.vis["nodes"] if n["full_id"] == "auth.login")
        assert n["colour"] == _TOKEN_COLOURS["AUTHENTICATE"]

    def test_structural_only_node_gets_grey(self):
        n = next(n for n in self.vis["nodes"] if n["full_id"] == "utils.helper")
        assert n["colour"] == "#cccccc"

    def test_radius_clamped(self):
        for n in self.vis["nodes"]:
            assert 6 <= n["radius"] <= 18

    def test_link_count_matches_valid_edges(self):
        # 3 edges, all sources/targets are in units → 3 links
        assert len(self.vis["links"]) == 3

    def test_invalid_edge_source_dropped(self):
        graph = _minimal_graph()
        graph["edges"].append(_edge("nonexistent.fn", "db.save"))
        vis = _build_vis_data(graph)
        assert len(vis["links"]) == 3  # still 3, ghost was dropped

    def test_link_fields(self):
        lnk = self.vis["links"][0]
        for f in ("source", "target", "source_id", "target_id", "type", "confidence", "colour"):
            assert f in lnk

    def test_link_colour_by_type(self):
        hard_link = next(l for l in self.vis["links"] if l["type"] == "HARD")
        assert hard_link["colour"] == _TOKEN_COLOURS.get("HARD", "#e15759") or hard_link["colour"] == "#e15759"

    def test_cluster_count(self):
        assert len(self.vis["clusters"]) == 2

    def test_cluster_has_members(self):
        c0 = next(c for c in self.vis["clusters"] if c["id"] == "C0")
        assert "auth.login" in c0["members"]

    def test_cluster_colour(self):
        c0 = next(c for c in self.vis["clusters"] if c["id"] == "C0")
        assert c0["colour"] == _TOKEN_COLOURS["AUTHENTICATE"]

    def test_legend_excludes_structural(self):
        tokens_in_legend = {l["token"] for l in self.vis["legend"]}
        assert "ASYNC" not in tokens_in_legend
        assert "INTAKE" not in tokens_in_legend

    def test_legend_includes_common_tokens(self):
        tokens_in_legend = {l["token"] for l in self.vis["legend"]}
        for t in ("FETCH", "PERSIST", "VALIDATE", "AUTHENTICATE"):
            assert t in tokens_in_legend

    def test_stats_forwarded(self):
        assert self.vis["stats"]["units"] == 5
        assert self.vis["stats"]["edges"] == 3

    def test_empty_graph(self):
        vis = _build_vis_data({"units": [], "edges": [], "clusters": [], "stats": {}})
        assert vis["nodes"] == []
        assert vis["links"] == []
        assert vis["clusters"] == []


# ── generate_html ──────────────────────────────────────────────────────────────

class TestGenerateHtml:
    def _gen(self, tmp_path, inline: bool = True, graph: dict | None = None) -> str:
        g = graph or _minimal_graph()
        out = str(tmp_path / "out.html")
        with patch("bgi.output.html_viz._fetch_d3", return_value="/* d3-stub */"):
            generate_html(g, out, inline_d3=inline, title="Test BGI")
        return Path(out).read_text(encoding="utf-8")

    def test_creates_file(self, tmp_path):
        out = str(tmp_path / "out.html")
        with patch("bgi.output.html_viz._fetch_d3", return_value="/* d3 */"):
            generate_html(_minimal_graph(), out)
        assert Path(out).exists()

    def test_html_structure(self, tmp_path):
        html = self._gen(tmp_path)
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_title_in_html(self, tmp_path):
        html = self._gen(tmp_path)
        assert "Test BGI" in html

    def test_vis_data_embedded(self, tmp_path):
        html = self._gen(tmp_path)
        assert "const DATA = " in html

    def test_nodes_in_embedded_data(self, tmp_path):
        html = self._gen(tmp_path)
        # JSON data contains node ids
        assert "auth.login" in html
        assert "db.save" in html

    def test_d3_stub_inlined(self, tmp_path):
        html = self._gen(tmp_path)
        assert "d3-stub" in html

    def test_cdn_fallback_when_no_d3(self, tmp_path):
        g = _minimal_graph()
        out = str(tmp_path / "cdn.html")
        with patch("bgi.output.html_viz._fetch_d3", return_value=None):
            generate_html(g, out, inline_d3=True)
        html = Path(out).read_text()
        assert "cdn.jsdelivr.net" in html

    def test_no_fetch_when_inline_false(self, tmp_path):
        g = _minimal_graph()
        out = str(tmp_path / "nofetch.html")
        with patch("bgi.output.html_viz._fetch_d3") as mock_fetch:
            generate_html(g, out, inline_d3=False)
            mock_fetch.assert_not_called()
        html = Path(out).read_text()
        assert "cdn.jsdelivr.net" in html

    def test_legend_tokens_in_html(self, tmp_path):
        html = self._gen(tmp_path)
        assert "AUTHENTICATE" in html

    def test_edge_filter_checkboxes(self, tmp_path):
        html = self._gen(tmp_path)
        for etype in ("HARD", "PREDICTED", "GHOST", "RESURRECTED"):
            assert etype in html

    def test_empty_graph_renders(self, tmp_path):
        html = self._gen(tmp_path, graph={"units": [], "edges": [], "clusters": [], "stats": {}})
        assert "<!DOCTYPE html>" in html

    def test_valid_json_embedded(self, tmp_path):
        html = self._gen(tmp_path)
        # Extract JSON between "const DATA = " and first ";\n"
        m = re.search(r"const DATA = (\{.*?\});", html, re.DOTALL)
        assert m is not None, "DATA JSON not found"
        data = json.loads(m.group(1))
        assert "nodes" in data
        assert "links" in data

    def test_graph_area_and_sidebar_present(self, tmp_path):
        html = self._gen(tmp_path)
        assert "graph-area" in html
        assert "sidebar" in html
        assert "info-panel" in html
