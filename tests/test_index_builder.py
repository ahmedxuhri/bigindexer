"""
Tests for BGI index builder.

Validates:
1. Loading Gate 1-3 output into indexes
2. Symbol tokenization
3. Cluster classification
4. Build statistics
"""

import pytest
import tempfile
import json
from pathlib import Path
from bgi.indexer.schema import IndexSchema
from bgi.indexer.builder import IndexBuilder


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


@pytest.fixture
def temp_gate_files():
    """Create temporary Gate output files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create Gate 1 units file
        units_file = Path(tmpdir) / "units.jsonl"
        units = [
            {
                "id": "file.py:fetch_user",
                "name": "fetch_user",
                "file_path": "file.py",
                "language": "python",
                "line_start": 10,
                "line_end": 20,
                "signature": "def fetch_user(id):",
                "fingerprint": {"tokens": ["FETCH", "OUTPUT"]},
                "is_exported": True,
            },
            {
                "id": "file.py:process_data",
                "name": "process_data",
                "file_path": "file.py",
                "language": "python",
                "line_start": 22,
                "line_end": 35,
                "signature": "def process_data(data):",
                "fingerprint": {"tokens": ["TRANSFORM", "MUTATE"]},
                "is_exported": True,
            },
            {
                "id": "lib.py:helper",
                "name": "helper",
                "file_path": "lib.py",
                "language": "python",
                "line_start": 1,
                "line_end": 5,
                "fingerprint": {"tokens": ["OUTPUT"]},
            },
        ]
        with open(units_file, "w") as f:
            for unit in units:
                f.write(json.dumps(unit) + "\n")
        
        # Create Gate 2 edges file
        edges_file = Path(tmpdir) / "edges.jsonl"
        edges = [
            {
                "source": "file.py:fetch_user",
                "target": "file.py:process_data",
                "type": "call",
                "fanout": 0.9,
                "confidence": 0.95,
            },
            {
                "source": "file.py:process_data",
                "target": "lib.py:helper",
                "type": "call",
                "fanout": 0.7,
                "confidence": 0.8,
            },
        ]
        with open(edges_file, "w") as f:
            for edge in edges:
                f.write(json.dumps(edge) + "\n")
        
        # Create Gate 3 clusters file
        clusters_file = Path(tmpdir) / "clusters.jsonl"
        clusters = [
            {
                "id": 1,
                "units": ["file.py:fetch_user", "file.py:process_data"],
                "max_unit_pct": 50.0,
            },
            {
                "id": 2,
                "units": ["lib.py:helper"],
                "max_unit_pct": 100.0,
            },
        ]
        with open(clusters_file, "w") as f:
            for cluster in clusters:
                f.write(json.dumps(cluster) + "\n")
        
        # Create fuse graph
        fuse_graph_file = Path(tmpdir) / "fuse-graph.json"
        fuse_graph = {
            "edges": [
                {"source_cluster": 1, "target_cluster": 2},
            ]
        }
        with open(fuse_graph_file, "w") as f:
            json.dump(fuse_graph, f)
        
        yield {
            "units": str(units_file),
            "edges": str(edges_file),
            "clusters": str(clusters_file),
            "fuse_graph": str(fuse_graph_file),
        }


class TestIndexBuilder:
    """Test index builder functionality."""

    def test_builder_initialization(self, temp_db):
        """Test builder initializes correctly."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        assert builder.schema is schema
        assert builder.conn is not None

    def test_load_units(self, temp_db, temp_gate_files):
        """Test loading units from Gate 1 output."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        count = builder._load_units(temp_gate_files["units"])
        
        assert count == 3
        
        # Verify data
        cursor = builder.conn.cursor()
        cursor.execute("SELECT * FROM units WHERE id = ?", ("file.py:fetch_user",))
        unit = cursor.fetchone()
        
        assert unit is not None
        assert unit["name"] == "fetch_user"
        assert unit["language"] == "python"
        assert unit["is_exported"] == 1  # SQLite stores bool as 0/1

    def test_load_edges(self, temp_db, temp_gate_files):
        """Test loading edges from Gate 2 output."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        builder._load_units(temp_gate_files["units"])
        count = builder._load_edges(temp_gate_files["edges"])
        
        assert count == 2
        
        # Verify data
        cursor = builder.conn.cursor()
        cursor.execute("SELECT * FROM edges WHERE edge_type = ?", ("call",))
        edges = cursor.fetchall()
        
        assert len(edges) == 2
        assert edges[0]["fanout"] == 0.9

    def test_load_clusters(self, temp_db, temp_gate_files):
        """Test loading clusters from Gate 3 output."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        builder._load_units(temp_gate_files["units"])
        clusters_count, members_count = builder._load_clusters(temp_gate_files["clusters"])
        
        assert clusters_count == 2
        assert members_count == 3  # 2 units in cluster 1, 1 in cluster 2
        
        # Verify cluster 1
        cursor = builder.conn.cursor()
        cursor.execute("SELECT * FROM cluster_members WHERE cluster_id = ?", (1,))
        members = cursor.fetchall()
        assert len(members) == 2

    def test_mark_boundary_clusters(self, temp_db, temp_gate_files):
        """Test marking boundary clusters from fuse graph."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        builder._load_clusters(temp_gate_files["clusters"])
        count = builder._mark_boundary_clusters(temp_gate_files["fuse_graph"])
        
        assert count == 2  # Both cluster 1 and 2 are boundary
        
        # Verify
        cursor = builder.conn.cursor()
        cursor.execute("SELECT is_boundary FROM clusters WHERE id = ?", (1,))
        result = cursor.fetchone()
        assert result["is_boundary"] == 1  # SQLite stores bool as 0/1

    def test_tokenize_symbol(self, temp_db):
        """Test symbol tokenization."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        builder = IndexBuilder(schema)
        
        # Test snake_case
        tokens = builder._tokenize_symbol("fetch_user")
        assert "fetch" in tokens
        assert "user" in tokens
        assert "fetch_user" in tokens
        
        # Test camelCase
        tokens = builder._tokenize_symbol("FetchUser")
        assert "fetch" in tokens
        assert "user" in tokens
        
        # Test mixed
        tokens = builder._tokenize_symbol("get_user_by_id")
        assert "get" in tokens
        assert "user" in tokens
        assert "by" in tokens
        assert "id" in tokens
        
        # Test single word
        tokens = builder._tokenize_symbol("fetch")
        assert "fetch" in tokens

    def test_build_symbol_index(self, temp_db, temp_gate_files):
        """Test building inverted symbol index."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        builder._load_units(temp_gate_files["units"])
        count = builder._build_symbol_index()
        
        assert count > 0
        
        # Verify we can find symbols
        cursor = builder.conn.cursor()
        cursor.execute("SELECT unit_id FROM symbol_index WHERE token = ?", ("fetch",))
        results = cursor.fetchall()
        
        assert len(results) > 0

    def test_infer_cluster_type(self, temp_db):
        """Test cluster type inference."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        builder = IndexBuilder(schema)
        
        # Populate clusters for testing
        cursor = builder.conn.cursor()
        cursor.execute("INSERT INTO clusters (id, size) VALUES (?, ?)", (1, 1))
        cursor.execute("INSERT INTO clusters (id, size) VALUES (?, ?)", (2, 5))
        cursor.execute("INSERT INTO clusters (id, size) VALUES (?, ?)", (3, 25))
        cursor.execute("INSERT INTO clusters (id, size) VALUES (?, ?)", (4, 100))
        builder.conn.commit()
        
        # Test inference
        assert builder._infer_cluster_type(1, 1) == "utility"
        assert builder._infer_cluster_type(2, 5) == "component"
        assert builder._infer_cluster_type(3, 25) == "module"
        assert builder._infer_cluster_type(4, 100) == "subsystem"

    def test_classify_clusters(self, temp_db, temp_gate_files):
        """Test cluster classification."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        builder._load_clusters(temp_gate_files["clusters"])
        count = builder._classify_clusters()
        
        assert count == 2
        
        # Verify classification
        cursor = builder.conn.cursor()
        cursor.execute("SELECT cluster_type FROM clusters WHERE id = ?", (1,))
        result = cursor.fetchone()
        assert result["cluster_type"] is not None

    def test_full_build_pipeline(self, temp_db, temp_gate_files):
        """Test complete build pipeline."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        stats = builder.build_from_pipeline_output(
            temp_gate_files["units"],
            temp_gate_files["edges"],
            temp_gate_files["clusters"],
            temp_gate_files["fuse_graph"],
        )
        
        assert stats["units_loaded"] == 3
        assert stats["edges_loaded"] == 2
        assert stats["clusters_loaded"] == 2
        assert stats["cluster_members_loaded"] == 3
        assert stats["boundary_clusters"] == 2
        assert stats["symbols_indexed"] > 0
        assert stats["clusters_classified"] == 2
        assert "db_size_mb" in stats

    def test_get_build_stats(self, temp_db, temp_gate_files):
        """Test getting build statistics."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        builder = IndexBuilder(schema)
        builder.build_from_pipeline_output(
            temp_gate_files["units"],
            temp_gate_files["edges"],
            temp_gate_files["clusters"],
            temp_gate_files["fuse_graph"],
        )
        
        stats = builder.get_build_stats()
        
        assert "units" in stats
        assert "edges" in stats
        assert "clusters" in stats
        assert "languages_indexed" in stats
        assert "edge_types" in stats
        assert "cluster_distribution" in stats
        
        assert stats["languages_indexed"] == 1  # Only Python
        assert stats["edge_types"] == 1  # Only "call"


class TestIndexBuilderEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_symbol(self, temp_db):
        """Test tokenizing empty symbol."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        builder = IndexBuilder(schema)
        
        tokens = builder._tokenize_symbol("")
        assert len(tokens) == 0

    def test_symbol_with_special_chars(self, temp_db):
        """Test tokenizing symbol with special characters."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        builder = IndexBuilder(schema)
        
        tokens = builder._tokenize_symbol("get::user_by-id.foo")
        assert "get" in tokens
        assert "user" in tokens
        assert "by" in tokens
        assert "id" in tokens
        assert "foo" in tokens


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
