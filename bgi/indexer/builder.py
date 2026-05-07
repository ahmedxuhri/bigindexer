"""
BGI Index Builder — loads Gate 1-3 output into searchable indexes.

Pipeline:
1. Load Gate 1 units (162k units on kubernetes) → units table
2. Load Gate 2 edges (8.6M edges) → edges table  
3. Load Gate 3 clusters → cluster tables
4. Tokenize symbols → symbol_index (inverted)
5. Analyze clusters → cluster_type classification
6. Optimize (VACUUM + ANALYZE)

Timing on kubernetes (3.6M LOC):
- Load units: ~500ms
- Load edges: ~2s
- Load clusters: ~200ms
- Tokenize: ~1s
- Analyze: ~500ms
- Vacuum: ~500ms
Total: ~4.7s
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

from bgi.indexer.schema import IndexSchema

logger = logging.getLogger(__name__)


class IndexBuilder:
    """Builds indexes from Gate 1-3 output files."""

    def __init__(self, schema: IndexSchema):
        """
        Initialize builder.
        
        Args:
            schema: IndexSchema instance (database already initialized)
        """
        self.schema = schema
        self.conn = schema.connect()

    def build_from_pipeline_output(
        self,
        gate1_units_file: str,
        gate2_edges_file: str,
        gate3_clusters_file: str,
        gate3_fuse_graph_file: Optional[str] = None,
    ) -> Dict:
        """
        Build complete index from Gate 1-3 output files.
        
        Args:
            gate1_units_file: Path to units.jsonl from Gate 1
            gate2_edges_file: Path to edges.jsonl from Gate 2
            gate3_clusters_file: Path to clusters.jsonl from Gate 3
            gate3_fuse_graph_file: Path to fuse-graph.json (optional, for boundary detection)
        
        Returns:
            Dictionary with build statistics
        """
        stats = {}
        
        logger.info("Starting index build from Gate output...")
        
        # Load units
        units_count = self._load_units(gate1_units_file)
        stats["units_loaded"] = units_count
        logger.info(f"✓ Loaded {units_count} units")
        
        # Load edges
        edges_count = self._load_edges(gate2_edges_file)
        stats["edges_loaded"] = edges_count
        logger.info(f"✓ Loaded {edges_count} edges")
        
        # Load clusters
        clusters_count, members_count = self._load_clusters(gate3_clusters_file)
        stats["clusters_loaded"] = clusters_count
        stats["cluster_members_loaded"] = members_count
        logger.info(f"✓ Loaded {clusters_count} clusters with {members_count} members")
        
        # Detect boundary edges
        if gate3_fuse_graph_file:
            boundary_count = self._mark_boundary_clusters(gate3_fuse_graph_file)
            stats["boundary_clusters"] = boundary_count
            logger.info(f"✓ Marked {boundary_count} boundary clusters")
        
        # Build symbol index
        symbols_count = self._build_symbol_index()
        stats["symbols_indexed"] = symbols_count
        logger.info(f"✓ Built symbol index with {symbols_count} tokens")
        
        # Analyze & classify clusters
        classified_count = self._classify_clusters()
        stats["clusters_classified"] = classified_count
        logger.info(f"✓ Classified {classified_count} clusters")
        
        # Optimize database
        self.schema.vacuum()
        stats["db_size_mb"] = self.schema.get_stats().get("db_size_mb", 0)
        logger.info(f"✓ Database optimized ({stats['db_size_mb']:.1f} MB)")
        
        logger.info(f"Index build complete: {stats}")
        return stats

    def _load_units(self, units_file: str) -> int:
        """Load units from Gate 1 output (units.jsonl)."""
        cursor = self.conn.cursor()
        count = 0
        
        with open(units_file) as f:
            for line in f:
                if not line.strip():
                    continue
                
                unit = json.loads(line)
                
                # Extract fields from Gate 1 unit format
                unit_id = unit.get("id", "")
                name = unit.get("name", "")
                file_path = unit.get("file_path", "")
                language = unit.get("language", "")
                line_start = unit.get("line_start", 0)
                line_end = unit.get("line_end", 0)
                scope_type = unit.get("scope_type")
                parent_scope = unit.get("parent_scope")
                signature = unit.get("signature")
                fingerprint = unit.get("fingerprint")
                decorators = unit.get("decorators", [])
                is_exported = unit.get("is_exported", False)
                
                # Store fingerprint as JSON
                fingerprint_json = json.dumps(fingerprint) if fingerprint else None
                decorators_json = json.dumps(decorators) if decorators else None
                
                cursor.execute("""
                    INSERT OR REPLACE INTO units
                    (id, name, file_path, language, line_start, line_end,
                     scope_type, parent_scope, signature, fingerprint, decorators, is_exported)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    unit_id, name, file_path, language, line_start, line_end,
                    scope_type, parent_scope, signature, fingerprint_json, decorators_json, is_exported
                ))
                
                count += 1
        
        self.conn.commit()
        return count

    def _load_edges(self, edges_file: str) -> int:
        """Load edges from Gate 2 output (edges.jsonl)."""
        cursor = self.conn.cursor()
        count = 0
        
        with open(edges_file) as f:
            for line in f:
                if not line.strip():
                    continue
                
                edge = json.loads(line)
                
                # Extract fields from Gate 2 edge format
                edge_id = f"{edge.get('source')}→{edge.get('target')}#{edge.get('type')}"
                source_id = edge.get("source", "")
                target_id = edge.get("target", "")
                edge_type = edge.get("type", "")
                fanout = edge.get("fanout", 1.0)
                confidence = edge.get("confidence", 1.0)
                is_forward = 1  # Always forward in Gate 2 output
                
                cursor.execute("""
                    INSERT OR REPLACE INTO edges
                    (id, source_id, target_id, edge_type, fanout, is_forward, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    edge_id, source_id, target_id, edge_type, fanout, is_forward, confidence
                ))
                
                count += 1
        
        self.conn.commit()
        return count

    def _load_clusters(self, clusters_file: str) -> Tuple[int, int]:
        """Load clusters from Gate 3 output (clusters.jsonl)."""
        cursor = self.conn.cursor()
        clusters_count = 0
        members_count = 0
        
        with open(clusters_file) as f:
            for line in f:
                if not line.strip():
                    continue
                
                cluster = json.loads(line)
                
                # Extract cluster metadata
                cluster_id = cluster.get("id")
                units = cluster.get("units", [])
                size = len(units)
                max_unit_pct = cluster.get("max_unit_pct", 0)
                
                # Insert cluster
                cursor.execute("""
                    INSERT OR REPLACE INTO clusters
                    (id, size, max_unit_pct)
                    VALUES (?, ?, ?)
                """, (cluster_id, size, max_unit_pct))
                
                clusters_count += 1
                
                # Insert cluster members
                for unit_id in units:
                    cursor.execute("""
                        INSERT OR REPLACE INTO cluster_members
                        (cluster_id, unit_id)
                        VALUES (?, ?)
                    """, (cluster_id, unit_id))
                    members_count += 1
        
        self.conn.commit()
        return clusters_count, members_count

    def _mark_boundary_clusters(self, fuse_graph_file: str) -> int:
        """Mark clusters that contain boundary edges (from fuse-graph.json)."""
        cursor = self.conn.cursor()
        boundary_clusters = set()
        
        with open(fuse_graph_file) as f:
            fuse_graph = json.load(f)
        
        # Fuse graph contains edges between clusters (boundary edges)
        for edge in fuse_graph.get("edges", []):
            source_cluster = edge.get("source_cluster")
            target_cluster = edge.get("target_cluster")
            
            if source_cluster:
                boundary_clusters.add(source_cluster)
            if target_cluster:
                boundary_clusters.add(target_cluster)
        
        # Update clusters
        count = 0
        for cluster_id in boundary_clusters:
            cursor.execute(
                "UPDATE clusters SET is_boundary = 1 WHERE id = ?",
                (cluster_id,)
            )
            count += 1
        
        self.conn.commit()
        return count

    def _build_symbol_index(self) -> int:
        """Build inverted symbol index from unit names."""
        cursor = self.conn.cursor()
        count = 0
        
        # Fetch all units
        cursor.execute("SELECT id, name FROM units")
        units = cursor.fetchall()
        
        for unit_id, name in units:
            # Tokenize name: split on camelCase, snake_case, punctuation
            tokens = self._tokenize_symbol(name)
            
            for token in tokens:
                cursor.execute("""
                    INSERT OR REPLACE INTO symbol_index
                    (token, unit_id)
                    VALUES (?, ?)
                """, (token, unit_id))
                count += 1
        
        self.conn.commit()
        return count

    def _tokenize_symbol(self, symbol: str) -> List[str]:
        """
        Tokenize a symbol name into searchable tokens.
        
        Examples:
        - "fetch_user" → ["fetch", "user", "fetch_user"]
        - "FetchUser" → ["fetch", "user", "fetchuser"]
        - "get_user_by_id" → ["get", "user", "by", "id", "get_user", "user_by", "by_id", ...]
        """
        if not symbol:
            return []
        
        # First, insert space before uppercase letters (camelCase splitting)
        # Must do this BEFORE lowercasing to catch case boundaries
        with_spaces = re.sub(r'([a-z])([A-Z])', r'\1 \2', symbol)
        
        # Now convert to lowercase
        symbol_lower = with_spaces.lower()
        
        # Replace separators with spaces
        symbol_lower = re.sub(r'[_\-#.:\s]+', ' ', symbol_lower)
        
        # Split and remove empty strings
        parts = [p for p in symbol_lower.split() if p]
        
        if not parts:
            return [symbol.lower()] if symbol else []
        
        tokens = set()
        
        # Add individual parts
        tokens.update(parts)
        
        # Add full lowercased symbol (without spaces)
        tokens.add(symbol.lower())
        
        # Add bigrams of parts (for phrase search)
        for i in range(len(parts) - 1):
            tokens.add(f"{parts[i]}_{parts[i+1]}")
        
        return sorted(tokens)

    def _classify_clusters(self) -> int:
        """Analyze clusters and classify by type."""
        cursor = self.conn.cursor()
        count = 0
        
        # Fetch all clusters
        cursor.execute("SELECT id, size FROM clusters")
        clusters = cursor.fetchall()
        
        for cluster_id, size in clusters:
            cluster_type = self._infer_cluster_type(cluster_id, size)
            
            cursor.execute(
                "UPDATE clusters SET cluster_type = ? WHERE id = ?",
                (cluster_type, cluster_id)
            )
            count += 1
        
        self.conn.commit()
        return count

    def _infer_cluster_type(self, cluster_id: int, size: int) -> str:
        """
        Infer cluster type from content and size.
        
        Heuristics:
        - size < 3: "utility" (helper functions)
        - size 3-10: "component" (tightly coupled)
        - size 10-50: "module" (functional area)
        - size > 50: "subsystem" (architectural layer)
        - has FUSE boundary: "boundary" (architectural interface)
        """
        cursor = self.conn.cursor()
        
        # Check if boundary
        cursor.execute(
            "SELECT is_boundary FROM clusters WHERE id = ?",
            (cluster_id,)
        )
        result = cursor.fetchone()
        if result and result[0]:
            return "boundary"
        
        # Classify by size
        if size < 3:
            return "utility"
        elif size < 10:
            return "component"
        elif size < 50:
            return "module"
        else:
            return "subsystem"

    def get_build_stats(self) -> Dict:
        """Get statistics about built indexes."""
        stats = self.schema.get_stats()
        
        # Add insights
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(DISTINCT language) FROM units")
        stats["languages_indexed"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT edge_type) FROM edges")
        stats["edge_types"] = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT cluster_type, COUNT(*) as count 
            FROM clusters 
            WHERE cluster_type IS NOT NULL 
            GROUP BY cluster_type
        """)
        stats["cluster_distribution"] = dict(cursor.fetchall())
        
        return stats


if __name__ == "__main__":
    import sys
    
    # CLI: python3 -m bgi.indexer.builder build <gate1_units> <gate2_edges> <gate3_clusters> [<fuse_graph>]
    if len(sys.argv) > 4:
        logging.basicConfig(level=logging.INFO)
        
        schema = IndexSchema()
        schema.create_schema(overwrite=False)
        
        builder = IndexBuilder(schema)
        
        gate1_units = sys.argv[1]
        gate2_edges = sys.argv[2]
        gate3_clusters = sys.argv[3]
        fuse_graph = sys.argv[4] if len(sys.argv) > 4 else None
        
        result = builder.build_from_pipeline_output(
            gate1_units, gate2_edges, gate3_clusters, fuse_graph
        )
        
        print("\n=== Build Results ===")
        for key, value in result.items():
            print(f"{key:25} : {value}")
        
        print("\n=== Index Statistics ===")
        stats = builder.get_build_stats()
        for key, value in stats.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for k, v in value.items():
                    print(f"  {k:20} : {v}")
            else:
                print(f"{key:25} : {value}")
