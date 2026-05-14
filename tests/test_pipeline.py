"""
End-to-end pipeline tests using the test fixtures directory.

Scans /tests/fixtures (12 units, auth + payment clusters) and validates
the full pipeline output: units, edges, clusters, JSON serialization.
"""
import json
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def pipeline_result(tmp_path_factory):
    """Run the full pipeline once; share result across tests in module."""
    from bgi.pipeline import run_scan

    out = tmp_path_factory.mktemp("bgi_out") / "graph.json"
    db  = tmp_path_factory.mktemp("bgi_db")  / "sep.db"

    run_scan(
        root=str(FIXTURES_DIR),
        language="python",
        output=str(out),
        db=str(db),
    )
    return json.loads(out.read_text())


class TestPipelineStats:
    def test_unit_count(self, pipeline_result):
        assert pipeline_result["stats"]["units"] == 12

    def test_edge_count_positive(self, pipeline_result):
        assert pipeline_result["stats"]["edges"] > 0

    def test_cluster_count(self, pipeline_result):
        assert pipeline_result["stats"]["clusters"] == 2

    def test_hard_cluster_count(self, pipeline_result):
        assert pipeline_result["stats"]["hard_clusters"] == 2


class TestPipelineClusters:
    def test_auth_cluster_exists(self, pipeline_result):
        files_in_clusters = [frozenset(c["files"]) for c in pipeline_result["clusters"]]
        assert any("auth_module.py" in frozenset(f) for f in files_in_clusters)

    def test_payment_cluster_exists(self, pipeline_result):
        files_in_clusters = [frozenset(c["files"]) for c in pipeline_result["clusters"]]
        assert any("sample_python.py" in frozenset(f) for f in files_in_clusters)

    def test_clusters_are_separate(self, pipeline_result):
        clusters = pipeline_result["clusters"]
        assert len(clusters) == 2
        ids = [c["id"] for c in clusters]
        assert len(set(ids)) == 2

    def test_all_units_assigned_to_cluster(self, pipeline_result):
        all_member_ids = []
        for c in pipeline_result["clusters"]:
            all_member_ids.extend(c["members"])
        assert len(all_member_ids) == 12


class TestPipelineEdges:
    def test_edges_have_required_fields(self, pipeline_result):
        for edge in pipeline_result["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "key" in edge
            assert "lock" in edge
            assert "confidence" in edge
            assert "type" in edge

    def test_fetch_persist_edges_exist(self, pipeline_result):
        pairs = {(e["key"].split(".")[-1], e["lock"].split(".")[-1])
                 for e in pipeline_result["edges"]}
        assert ("FETCH", "PERSIST") in pairs

    def test_no_ghost_edges_in_fixture(self, pipeline_result):
        # Fixture functions are deterministic (conf=1.0) — no GHOSTs expected
        ghost_edges = [e for e in pipeline_result["edges"] if e["type"] == "GHOST"]
        assert len(ghost_edges) == 0


class TestPipelineJSONSerializable:
    def test_full_graph_is_json_serializable(self, pipeline_result):
        # If we got here, json.loads already worked — just double-check round-trip
        reserialised = json.loads(json.dumps(pipeline_result))
        assert reserialised["stats"]["units"] == 12

    def test_sep_stats_present(self, pipeline_result):
        assert "sep" in pipeline_result["stats"]
        s = pipeline_result["stats"]["sep"]
        assert "total" in s
        assert "pending" in s
        assert "resolved" in s


def test_scan_writes_bigindexer_context_and_not_agents(tmp_path):
    from bgi.pipeline import run_scan

    out = tmp_path / "bgi-graph.json"
    db = tmp_path / "sep.db"

    run_scan(
        root=str(FIXTURES_DIR),
        language="python",
        output=str(out),
        db=str(db),
    )

    assert (tmp_path / "bigindexer.md").exists()
    assert not (tmp_path / "agents.md").exists()
