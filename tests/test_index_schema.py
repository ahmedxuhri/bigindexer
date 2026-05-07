"""
Tests for BGI index schema.

Validates:
1. Schema creation and table structure
2. Index verification
3. Statistics gathering
4. Schema completeness
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from bgi.indexer.schema import IndexSchema, SCHEMA_VERSION


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


class TestIndexSchemaCreation:
    """Test schema creation and initialization."""

    def test_schema_creation(self, temp_db):
        """Test that schema creates all required tables."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        assert Path(temp_db).exists()
        assert schema.verify_schema()

    def test_schema_creates_required_tables(self, temp_db):
        """Test that all required tables are created."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        required = {"units", "edges", "clusters", "cluster_members", "symbol_index", "index_meta"}
        assert required.issubset(tables), f"Missing tables: {required - tables}"
        
        conn.close()

    def test_schema_creates_indexes(self, temp_db):
        """Test that all indexes are created."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
        indexes = {row[0] for row in cursor.fetchall()}
        
        expected_indexes = {
            "idx_units_file",
            "idx_units_name",
            "idx_units_language",
            "idx_units_exported",
            "idx_edges_source",
            "idx_edges_target",
            "idx_edges_type",
            "idx_edges_forward",
            "idx_clusters_size",
            "idx_clusters_boundary",
            "idx_members_unit",
            "idx_members_cluster",
            "idx_symbols_token",
        }
        
        assert expected_indexes.issubset(indexes), f"Missing indexes: {expected_indexes - indexes}"
        
        conn.close()

    def test_schema_version_stored(self, temp_db):
        """Test that schema version is stored in metadata."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM index_meta WHERE key = ?", ("schema_version",))
        result = cursor.fetchone()
        
        assert result is not None
        assert result[0] == SCHEMA_VERSION
        
        conn.close()

    def test_schema_overwrite(self, temp_db):
        """Test that schema can be overwritten."""
        schema = IndexSchema(temp_db)
        
        # Create initial schema
        schema.create_schema()
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO index_meta (key, value) VALUES (?, ?)", ("test_key", "test_value"))
        conn.commit()
        conn.close()
        
        # Verify data exists
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM index_meta WHERE key = ?", ("test_key",))
        assert cursor.fetchone() is not None
        conn.close()
        
        # Overwrite schema
        schema.create_schema(overwrite=True)
        
        # Verify data is gone
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM index_meta WHERE key = ?", ("test_key",))
        assert cursor.fetchone() is None
        conn.close()


class TestIndexSchemaVerification:
    """Test schema verification and validation."""

    def test_verify_valid_schema(self, temp_db):
        """Test verification of valid schema."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        assert schema.verify_schema() is True

    def test_verify_detects_missing_tables(self, temp_db):
        """Test that verification detects missing tables."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        # Drop a table
        conn = schema.connect()
        cursor = conn.cursor()
        cursor.execute("DROP TABLE units")
        conn.commit()
        
        # Verification should fail
        assert schema.verify_schema() is False

    def test_get_stats_empty_index(self, temp_db):
        """Test statistics for empty index."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        stats = schema.get_stats()
        
        assert stats["units"] == 0
        assert stats["edges"] == 0
        assert stats["clusters"] == 0
        assert stats["cluster_members"] == 0
        assert stats["symbol_index"] == 0
        assert "db_size_mb" in stats


class TestIndexSchemaStructure:
    """Test specific table structures."""

    def test_units_table_structure(self, temp_db):
        """Test units table has correct columns."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(units)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_cols = {
            "id", "name", "file_path", "language",
            "line_start", "line_end", "scope_type", "parent_scope",
            "signature", "fingerprint", "decorators", "is_exported",
            "created_at", "updated_at"
        }
        
        assert required_cols.issubset(columns), f"Missing columns: {required_cols - columns}"
        conn.close()

    def test_edges_table_structure(self, temp_db):
        """Test edges table has correct columns."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(edges)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_cols = {
            "id", "source_id", "target_id", "edge_type",
            "fanout", "is_forward", "confidence"
        }
        
        assert required_cols.issubset(columns), f"Missing columns: {required_cols - columns}"
        conn.close()

    def test_clusters_table_structure(self, temp_db):
        """Test clusters table has correct columns."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(clusters)")
        columns = {row[1] for row in cursor.fetchall()}
        
        required_cols = {"id", "size", "max_unit_pct", "cluster_type", "is_boundary", "created_at"}
        
        assert required_cols.issubset(columns), f"Missing columns: {required_cols - columns}"
        conn.close()


class TestIndexSchemaInsertion:
    """Test insertion and data validation."""

    def test_insert_unit(self, temp_db):
        """Test inserting a unit."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        conn = schema.connect()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO units (id, name, file_path, language, line_start, line_end, is_exported)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("file.py:foo", "foo", "file.py", "python", 10, 20, 1))
        
        conn.commit()
        
        # Verify insertion
        cursor.execute("SELECT * FROM units WHERE id = ?", ("file.py:foo",))
        result = cursor.fetchone()
        assert result is not None
        assert result["name"] == "foo"

    def test_insert_edge_with_foreign_key(self, temp_db):
        """Test inserting edges respects foreign keys."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        conn = schema.connect()
        cursor = conn.cursor()
        
        # Insert units first
        cursor.execute("""
            INSERT INTO units (id, name, file_path, language, line_start, line_end)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("file.py:a", "a", "file.py", "python", 1, 5))
        
        cursor.execute("""
            INSERT INTO units (id, name, file_path, language, line_start, line_end)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("file.py:b", "b", "file.py", "python", 6, 10))
        
        # Insert edge
        cursor.execute("""
            INSERT INTO edges (id, source_id, target_id, edge_type)
            VALUES (?, ?, ?, ?)
        """, ("file.py:a→b#call", "file.py:a", "file.py:b", "call"))
        
        conn.commit()
        
        # Verify insertion
        cursor.execute("SELECT * FROM edges WHERE id = ?", ("file.py:a→b#call",))
        result = cursor.fetchone()
        assert result is not None
        assert result["source_id"] == "file.py:a"
        assert result["target_id"] == "file.py:b"


class TestIndexSchemaVacuum:
    """Test index optimization."""

    def test_vacuum_runs_without_error(self, temp_db):
        """Test that vacuum runs without error."""
        schema = IndexSchema(temp_db)
        schema.create_schema()
        
        # Should not raise
        schema.vacuum()
        
        # Verify schema still valid after vacuum
        assert schema.verify_schema()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
