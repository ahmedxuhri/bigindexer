"""
BGI Interactive Search Index Schema

Manages SQLite index database creation, migrations, and schema operations.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = "1.0"


class IndexSchema:
    """Manages index database schema creation and migrations."""

    def __init__(self, db_path: str = "bgi/index.db"):
        """
        Initialize schema manager.
        
        Args:
            db_path: Path to SQLite index database
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Connect to index database."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def create_schema(self, overwrite: bool = False) -> None:
        """
        Create or verify index schema.
        
        Args:
            overwrite: If True, drop existing tables and recreate
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        if overwrite:
            logger.info("Dropping existing index tables...")
            self._drop_all_tables(cursor)
        
        logger.info("Creating index schema...")
        
        # Metadata table (first, for version tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS index_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Units table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS units (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                language TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                scope_type TEXT,
                parent_scope TEXT,
                signature TEXT,
                fingerprint JSON,
                decorators JSON,
                is_exported BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_units_file ON units(file_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_units_name ON units(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_units_language ON units(language)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_units_exported ON units(is_exported)")
        
        # Edges table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                fanout REAL DEFAULT 1.0,
                is_forward BOOLEAN DEFAULT 1,
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY (source_id) REFERENCES units(id),
                FOREIGN KEY (target_id) REFERENCES units(id)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_forward ON edges(is_forward)")
        
        # Clusters table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clusters (
                id INTEGER PRIMARY KEY,
                size INTEGER NOT NULL,
                max_unit_pct REAL,
                cluster_type TEXT,
                is_boundary BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_clusters_size ON clusters(size)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_clusters_boundary ON clusters(is_boundary)")
        
        # Cluster membership table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cluster_members (
                cluster_id INTEGER NOT NULL,
                unit_id TEXT NOT NULL,
                PRIMARY KEY (cluster_id, unit_id),
                FOREIGN KEY (cluster_id) REFERENCES clusters(id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_unit ON cluster_members(unit_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_cluster ON cluster_members(cluster_id)")
        
        # Symbol index (inverted)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_index (
                token TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                PRIMARY KEY (token, unit_id),
                FOREIGN KEY (unit_id) REFERENCES units(id)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_token ON symbol_index(token)")
        
        # Store schema version
        cursor.execute(
            "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION)
        )
        
        conn.commit()
        logger.info(f"Index schema created (version {SCHEMA_VERSION})")

    def _drop_all_tables(self, cursor: sqlite3.Cursor) -> None:
        """Drop all index tables."""
        tables = [
            "symbol_index",
            "cluster_members",
            "clusters",
            "edges",
            "units",
            "index_meta",
        ]
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        logger.info("Dropped all index tables")

    def verify_schema(self) -> bool:
        """
        Verify that schema is valid and complete.
        
        Returns: True if schema is valid
        """
        conn = self.connect()
        cursor = conn.cursor()
        
        required_tables = {
            "units",
            "edges",
            "clusters",
            "cluster_members",
            "symbol_index",
            "index_meta",
        }
        
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing = {row[0] for row in cursor.fetchall()}
        
        missing = required_tables - existing
        if missing:
            logger.error(f"Missing tables: {missing}")
            return False
        
        logger.info(f"Schema verification passed ({len(required_tables)} tables)")
        return True

    def get_stats(self) -> dict:
        """Get index statistics."""
        conn = self.connect()
        cursor = conn.cursor()
        
        stats = {}
        
        for table in ["units", "edges", "clusters", "cluster_members", "symbol_index"]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            stats[table] = count
        
        # Get DB file size
        db_path = Path(self.db_path)
        if db_path.exists():
            stats["db_size_mb"] = db_path.stat().st_size / (1024 * 1024)
        
        return stats

    def vacuum(self) -> None:
        """Optimize database (VACUUM + ANALYZE)."""
        conn = self.connect()
        cursor = conn.cursor()
        
        logger.info("Vacuuming index database...")
        cursor.execute("VACUUM")
        cursor.execute("ANALYZE")
        conn.commit()
        logger.info("Index vacuumed")

    def print_schema(self) -> None:
        """Print schema information."""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name")
        
        print("\n=== Index Schema ===\n")
        for row in cursor.fetchall():
            if row[0]:
                print(row[0] + ";\n")


def init_index(db_path: str = "bgi/index.db", overwrite: bool = False) -> IndexSchema:
    """
    Initialize index schema and return manager.
    
    Args:
        db_path: Path to index database
        overwrite: If True, recreate schema
    
    Returns: IndexSchema instance
    """
    schema = IndexSchema(db_path)
    schema.create_schema(overwrite=overwrite)
    return schema


if __name__ == "__main__":
    import sys
    
    # CLI: python3 -m bgi.indexer.schema [init|verify|stats|print]
    if len(sys.argv) > 1:
        command = sys.argv[1]
        schema = IndexSchema()
        
        if command == "init":
            schema.create_schema(overwrite=False)
            print("✓ Index schema initialized")
        elif command == "verify":
            if schema.verify_schema():
                print("✓ Schema is valid")
            else:
                print("✗ Schema is invalid")
        elif command == "stats":
            stats = schema.get_stats()
            print("\n=== Index Statistics ===")
            for key, value in stats.items():
                print(f"{key:20} : {value}")
        elif command == "print":
            schema.print_schema()
        elif command == "vacuum":
            schema.vacuum()
            print("✓ Index vacuumed")
        else:
            print(f"Unknown command: {command}")
            print("Usage: python3 -m bgi.indexer.schema [init|verify|stats|print|vacuum]")
    else:
        print("Usage: python3 -m bgi.indexer.schema [init|verify|stats|print|vacuum]")
