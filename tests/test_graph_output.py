"""
Tests for output/graph.py — cluster adjacency graph and GraphML export.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET

import pytest

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.core.edges import BGIEdge
from bgi.gate2.keylock import match_fingerprints
from bgi.gate3.drs import run_drs
from bgi.output.graph import (
    serialize_graph,
    build_cluster_graph,
    to_graphml,
    write_graphml,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fp(unit_id: str, tokens: list[COV], line_range=(1, 10)) -> COVFingerprint:
    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=[],
        confidence=0.95,
        source="deterministic",
        language="python",
        line_range=line_range,
    )


def _edge(src: str, tgt: str, key=COV.FETCH, lock=COV.PERSIST, confidence=0.9, etype="HARD") -> BGIEdge:
    return BGIEdge(
        source_id=src,
        target_id=tgt,
        key_token=key,
        lock_token=lock,
        confidence=confidence,
        edge_type=etype,
        provenance="test",
    )


def _build_small_graph():
    """Two-cluster setup: auth cluster and data cluster linked by a FETCH→PERSIST edge."""
    fps = [
        _fp("auth.py::login",    [COV.AUTHENTICATE, COV.ROUTE], line_range=(1, 20)),
        _fp("auth.py::logout",   [COV.AUTHENTICATE],            line_range=(25, 40)),
        _fp("data.py::save",     [COV.PERSIST],                 line_range=(1, 15)),
        _fp("data.py::load",     [COV.FETCH],                   line_range=(20, 35)),
    ]
    edges, _ = match_fingerprints(fps)
    drs, _fuse = run_drs(fps, edges)
    return fps, edges, drs


# ── build_cluster_graph ───────────────────────────────────────────────────────

class TestBuildClusterGraph:
    def test_returns_nodes_and_edges_keys(self):
        fps, edges, drs = _build_small_graph()
        cg = build_cluster_graph(edges, drs)
        assert "nodes" in cg
        assert "edges" in cg
        assert "stats" in cg

    def test_node_count_matches_drs_clusters(self):
        fps, edges, drs = _build_small_graph()
        cg = build_cluster_graph(edges, drs)
        assert cg["stats"]["clusters"] == len(drs.clusters)

    def test_node_has_required_fields(self):
        fps, edges, drs = _build_small_graph()
        cg = build_cluster_graph(edges, drs)
        for node in cg["nodes"]:
            assert "id"               in node
            assert "dominant_tokens"  in node
            assert "probability"      in node
            assert "size"             in node
            assert "is_hard"          in node
            assert "files"            in node
            assert "members"          in node

    def test_cluster_edge_has_required_fields(self):
        fps, edges, drs = _build_small_graph()
        cg = build_cluster_graph(edges, drs)
        for e in cg["edges"]:
            assert "source"         in e
            assert "target"         in e
            assert "weight"         in e
            assert "max_confidence" in e
            assert "dominant_key"   in e
            assert "dominant_lock"  in e

    def test_no_self_loop_cluster_edges(self):
        fps, edges, drs = _build_small_graph()
        cg = build_cluster_graph(edges, drs)
        for e in cg["edges"]:
            assert e["source"] != e["target"]

    def test_cross_cluster_edge_weight_positive(self):
        fps, edges, drs = _build_small_graph()
        cg = build_cluster_graph(edges, drs)
        for e in cg["edges"]:
            assert e["weight"] >= 1

    def test_explicit_cross_cluster_edge_captured(self):
        """Two disjoint clusters joined only by a synthetic HARD edge."""
        fps = [
            _fp("a.py::foo", [COV.ROUTE],   line_range=(1, 5)),
            _fp("b.py::bar", [COV.PERSIST],  line_range=(1, 5)),
        ]
        cross_edge = _edge("a.py::foo", "b.py::bar", key=COV.ROUTE, lock=COV.PERSIST)
        drs, _fuse = run_drs(fps, [cross_edge])
        cg = build_cluster_graph([cross_edge], drs)
        # a and b are in different clusters; there must be at least one cluster edge
        assert cg["stats"]["cluster_edges"] >= 1

    def test_empty_edges_produces_no_cluster_edges(self):
        fps = [_fp("a.py::foo", [COV.FETCH])]
        drs, _fuse = run_drs(fps, [])
        cg = build_cluster_graph([], drs)
        assert cg["edges"] == []

    def test_nodes_sorted_by_probability_desc(self):
        fps, edges, drs = _build_small_graph()
        cg = build_cluster_graph(edges, drs)
        probs = [n["probability"] for n in cg["nodes"]]
        assert probs == sorted(probs, reverse=True)


# ── to_graphml ────────────────────────────────────────────────────────────────

class TestToGraphml:
    def test_produces_valid_xml(self):
        fps, edges, drs = _build_small_graph()
        xml_str = to_graphml(edges, drs, cluster_level=True)
        root = ET.fromstring(xml_str)
        assert root.tag.endswith("graphml")

    def test_cluster_level_graph_node_count(self):
        fps, edges, drs = _build_small_graph()
        xml_str = to_graphml(edges, drs, cluster_level=True)
        root = ET.fromstring(xml_str)
        ns = {"g": "http://graphml.graphdrawing.org/graphml"}
        nodes = root.findall(".//g:node", ns)
        assert len(nodes) == len(drs.clusters)

    def test_cluster_level_directed_graph(self):
        fps, edges, drs = _build_small_graph()
        xml_str = to_graphml(edges, drs, cluster_level=True)
        root = ET.fromstring(xml_str)
        ns = {"g": "http://graphml.graphdrawing.org/graphml"}
        graph_el = root.find("g:graph", ns)
        assert graph_el.attrib.get("edgedefault") == "directed"

    def test_unit_level_graph_has_unit_ids(self):
        fps, edges, drs = _build_small_graph()
        xml_str = to_graphml(edges, drs, cluster_level=False)
        # Every unit referenced by an edge should appear as a node
        root = ET.fromstring(xml_str)
        ns = {"g": "http://graphml.graphdrawing.org/graphml"}
        node_ids = {n.attrib["id"] for n in root.findall(".//g:node", ns)}
        for e in edges:
            assert e.source_id in node_ids
            assert e.target_id in node_ids

    def test_graphml_has_key_declarations(self):
        fps, edges, drs = _build_small_graph()
        xml_str = to_graphml(edges, drs, cluster_level=True)
        assert 'attr.name="probability"'  in xml_str
        assert 'attr.name="dominant_key"' in xml_str

    def test_write_graphml_creates_file(self, tmp_path):
        fps, edges, drs = _build_small_graph()
        out = str(tmp_path / "graph.graphml")
        write_graphml(edges, drs, out, cluster_level=True)
        content = (tmp_path / "graph.graphml").read_text()
        assert "<graphml" in content
        assert len(content) > 100


# ── serialize_graph integration ───────────────────────────────────────────────

class TestSerializeGraphWithClusters:
    def test_cluster_graph_in_serialize_output(self):
        fps, edges, drs = _build_small_graph()
        result = serialize_graph(fps, edges, drs=drs)
        assert "clusters" in result
        assert result["stats"]["clusters"] == len(drs.clusters)

    def test_unit_cluster_assignment_present(self):
        fps, edges, drs = _build_small_graph()
        result = serialize_graph(fps, edges, drs=drs)
        for unit in result["units"]:
            # Every unit should have a cluster assignment
            assert "cluster" in unit
