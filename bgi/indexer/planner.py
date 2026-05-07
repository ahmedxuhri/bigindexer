"""
BGI Query Planner: Scope narrowing for fast symbol lookup.

Implements ranking heuristics for sub-100ms searches on pre-indexed code graph:
1. Frequency score - rare symbols ranked higher
2. Callee/caller bias - popular exports ranked higher
3. Locality bias - nearby units ranked higher
4. Fingerprint matching - COV token overlap
5. Package proximity - same-package units ranked higher
"""

import json
import math
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass, field
from collections import defaultdict
import sqlite3


@dataclass
class QueryResult:
    """Result of a query planner lookup."""
    unit_id: str
    name: str
    file_path: str
    score: float
    reasoning: str
    is_exported: bool = False


@dataclass
class QueryStats:
    """Statistics about query planner performance."""
    db_path: str
    token_count: int = 0
    unique_units: int = 0
    packages: int = 0
    cache_hit_rate: float = 0.0
    avg_query_time_ms: float = 0.0
    total_queries: int = 0


class QueryPlanner:
    """
    Query planner for efficient symbol lookup on pre-indexed code graph.
    
    Narrowing strategies:
    1. Token frequency: rare symbols rated higher
    2. Call graph topology: high-fanin exports rated higher
    3. Locality: nearby units rated higher
    4. Fingerprint overlap: COV token matching
    5. Package proximity: same-package units rated higher
    """
    
    def __init__(self, db_path: str):
        """Initialize query planner with index database."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        
        # Load metadata and build caches
        self._token_frequencies: Dict[str, int] = {}
        self._in_degrees: Dict[str, int] = {}
        self._packages: Dict[str, str] = {}
        self._unit_cache: Dict[str, dict] = {}
        
        # Stats tracking (initialize BEFORE _load_caches)
        self.stats = QueryStats(db_path=db_path)
        
        self._load_caches()
    
    def _load_caches(self):
        """Load token frequencies, in-degrees, and package map."""
        cursor = self.conn.cursor()
        
        # Load token frequencies
        cursor.execute("""
            SELECT token, COUNT(*) as freq 
            FROM symbol_index 
            GROUP BY token
        """)
        for row in cursor.fetchall():
            self._token_frequencies[row["token"]] = row["freq"]
        
        self.stats.token_count = len(self._token_frequencies)
        
        # Load in-degrees (call graph)
        cursor.execute("""
            SELECT target_id, COUNT(*) as in_degree 
            FROM edges 
            WHERE edge_type = 'call' 
            GROUP BY target_id
        """)
        for row in cursor.fetchall():
            self._in_degrees[row["target_id"]] = row["in_degree"]
        
        # Load unit cache and compute package map
        cursor.execute("SELECT id, name, file_path, is_exported FROM units")
        unique_packages = set()
        for row in cursor.fetchall():
            unit_id = row["id"]
            file_path = row["file_path"]
            self._unit_cache[unit_id] = dict(row)
            
            # Extract package
            pkg = self._extract_package(file_path)
            self._packages[unit_id] = pkg
            unique_packages.add(pkg)
        
        self.stats.unique_units = len(self._unit_cache)
        self.stats.packages = len(unique_packages)
    
    def _extract_package(self, file_path: str) -> str:
        """
        Extract package identifier from file path.
        
        Heuristics:
        - Python: directory containing __init__.py
        - JavaScript: directory containing package.json
        - Go: directory containing go.mod
        - Default: first 2 path components
        """
        path = Path(file_path)
        parts = path.parts
        
        if len(parts) < 2:
            return parts[0] if parts else "root"
        
        # Check for common package markers
        parent = path.parent
        
        # Python: look for __init__.py
        if (parent / "__init__.py").exists():
            return str(parent)
        
        # JavaScript: look for package.json
        for potential_root in [parent, parent.parent, parent.parent.parent]:
            if (potential_root / "package.json").exists():
                return str(potential_root)
            if (potential_root / "go.mod").exists():
                return str(potential_root)
            if (potential_root / "Cargo.toml").exists():
                return str(potential_root)
        
        # Default: first two path components
        return "/".join(parts[:2])
    
    def _compute_frequency_score(self, token: str, unit_id: str) -> float:
        """
        Compute frequency score: rare symbols ranked higher.
        
        Formula: 1.0 / (1.0 + log10(frequency))
        - "fetch" (500 occurrences) → ~0.33
        - "rare_func" (2 occurrences) → ~0.80
        """
        freq = self._token_frequencies.get(token, 1)
        # Avoid log(0), handle single occurrence
        score = 1.0 / (1.0 + math.log10(max(freq, 1)))
        return min(score, 1.0)
    
    def _compute_callee_score(self, unit_id: str) -> float:
        """
        Compute callee score: high-fanin exports ranked higher.
        
        Exported units with many callers are likely targets.
        Formula: min(in_degree / 10.0, 1.0) * export_boost
        """
        in_degree = self._in_degrees.get(unit_id, 0)
        is_exported = self._unit_cache.get(unit_id, {}).get("is_exported", False)
        
        export_boost = 1.5 if is_exported else 1.0
        score = min(in_degree / 10.0, 1.0) * export_boost
        
        return min(score, 1.0)
    
    def _compute_locality_score(self, context_unit_id: Optional[str], candidate_id: str) -> float:
        """
        Compute locality score: nearby units ranked higher.
        
        Distance levels:
        - Same file → 1.0
        - Same package → 0.8
        - Same directory → 0.6
        - Transitively reachable (1–2 hops) → 0.4
        - Remote → 0.1
        """
        if not context_unit_id:
            return 0.5  # No context, neutral score
        
        context_unit = self._unit_cache.get(context_unit_id, {})
        candidate_unit = self._unit_cache.get(candidate_id, {})
        
        if not context_unit or not candidate_unit:
            return 0.1
        
        context_file = context_unit.get("file_path", "")
        candidate_file = candidate_unit.get("file_path", "")
        
        # Same file
        if context_file == candidate_file:
            return 1.0
        
        # Same package
        context_pkg = self._packages.get(context_unit_id, "")
        candidate_pkg = self._packages.get(candidate_id, "")
        if context_pkg and context_pkg == candidate_pkg:
            return 0.8
        
        # Same directory
        context_dir = str(Path(context_file).parent)
        candidate_dir = str(Path(candidate_file).parent)
        if context_dir == candidate_dir:
            return 0.6
        
        # Same parent directory
        if str(Path(context_dir).parent) == str(Path(candidate_dir).parent):
            return 0.5
        
        # Remote
        return 0.1
    
    def _compute_fingerprint_score(self, context_unit_id: Optional[str], candidate_id: str) -> float:
        """
        Compute fingerprint overlap score.
        
        Units with matching COV tokens likely have related behavior.
        Formula: overlap / union (Jaccard similarity)
        Threshold: require >20% overlap to avoid noise
        """
        if not context_unit_id:
            return 0.0
        
        cursor = self.conn.cursor()
        
        # Get fingerprints (stored as JSON)
        cursor.execute("SELECT fingerprint FROM units WHERE id = ?", (context_unit_id,))
        context_row = cursor.fetchone()
        if not context_row or not context_row["fingerprint"]:
            return 0.0
        
        cursor.execute("SELECT fingerprint FROM units WHERE id = ?", (candidate_id,))
        candidate_row = cursor.fetchone()
        if not candidate_row or not candidate_row["fingerprint"]:
            return 0.0
        
        try:
            context_fp = json.loads(context_row["fingerprint"])
            candidate_fp = json.loads(candidate_row["fingerprint"])
            
            context_tokens = set(context_fp.get("tokens", []))
            candidate_tokens = set(candidate_fp.get("tokens", []))
            
            if not context_tokens or not candidate_tokens:
                return 0.0
            
            overlap = len(context_tokens & candidate_tokens)
            union = len(context_tokens | candidate_tokens)
            
            if union == 0:
                return 0.0
            
            jaccard = overlap / union
            
            # Threshold: require >20% overlap
            if jaccard < 0.2:
                return 0.0
            
            return min(jaccard, 1.0)
        
        except (json.JSONDecodeError, KeyError, TypeError):
            return 0.0
    
    def _compute_package_score(self, context_unit_id: Optional[str], candidate_id: str) -> float:
        """
        Compute package proximity score.
        
        Same-package units get boost.
        """
        if not context_unit_id:
            return 0.5
        
        context_pkg = self._packages.get(context_unit_id, "")
        candidate_pkg = self._packages.get(candidate_id, "")
        
        if not context_pkg or not candidate_pkg:
            return 0.5
        
        if context_pkg == candidate_pkg:
            return 1.2
        
        # Sibling package (same parent)
        context_parent = str(Path(context_pkg).parent)
        candidate_parent = str(Path(candidate_pkg).parent)
        if context_parent == candidate_parent:
            return 0.8
        
        return 0.5
    
    def _rank_candidates(
        self,
        query_token: str,
        context_unit_id: Optional[str],
        candidates: List[str],
        max_results: int = 10,
    ) -> List[QueryResult]:
        """
        Rank candidates by combined score.
        
        Weights:
        - Frequency: 0.25
        - Callee score: 0.20
        - Locality: 0.25
        - Fingerprint: 0.15
        - Package: 0.15
        """
        scores = []
        
        for candidate_id in candidates:
            # Skip if not in cache
            if candidate_id not in self._unit_cache:
                continue
            
            unit = self._unit_cache[candidate_id]
            
            # Individual scores (0–1 scale)
            freq_score = self._compute_frequency_score(query_token, candidate_id)
            callee_score = self._compute_callee_score(candidate_id)
            locality_score = self._compute_locality_score(context_unit_id, candidate_id)
            fingerprint_score = self._compute_fingerprint_score(context_unit_id, candidate_id)
            package_score = self._compute_package_score(context_unit_id, candidate_id)
            
            # Weighted combination
            combined = (
                freq_score * 0.25 +
                callee_score * 0.20 +
                locality_score * 0.25 +
                fingerprint_score * 0.15 +
                package_score * 0.15
            )
            
            # Build reasoning
            reasons = []
            if freq_score > 0.7:
                reasons.append("rare symbol")
            if callee_score > 0.7:
                reasons.append("popular export")
            if locality_score > 0.8:
                reasons.append("nearby unit")
            if fingerprint_score > 0.5:
                reasons.append("matching behavior")
            
            reasoning = ", ".join(reasons) if reasons else "general match"
            
            scores.append((
                QueryResult(
                    unit_id=candidate_id,
                    name=unit.get("name", ""),
                    file_path=unit.get("file_path", ""),
                    score=combined,
                    reasoning=reasoning,
                    is_exported=unit.get("is_exported", False),
                ),
                combined,
            ))
        
        # Sort descending by score
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # Threshold and limit
        threshold = 0.2
        results = [r for r, s in scores if s >= threshold]
        
        return results[:max_results]
    
    def lookup_symbol(
        self,
        symbol: str,
        context_unit_id: Optional[str] = None,
        max_results: int = 10,
    ) -> List[QueryResult]:
        """
        Look up a symbol by exact token match.
        
        Returns ranked list of matching units.
        """
        cursor = self.conn.cursor()
        
        # Find all units with this token
        cursor.execute(
            "SELECT DISTINCT unit_id FROM symbol_index WHERE token = ?",
            (symbol.lower(),)
        )
        candidates = [row["unit_id"] for row in cursor.fetchall()]
        
        # Rank
        results = self._rank_candidates(symbol.lower(), context_unit_id, candidates, max_results)
        
        # Update stats
        self.stats.total_queries += 1
        
        return results
    
    def search_prefix(
        self,
        prefix: str,
        context_unit_id: Optional[str] = None,
        max_results: int = 10,
    ) -> List[QueryResult]:
        """
        Search for symbols by prefix.
        
        Returns ranked list of matching units.
        """
        cursor = self.conn.cursor()
        
        # Find all tokens starting with prefix
        cursor.execute(
            "SELECT DISTINCT token FROM symbol_index WHERE token LIKE ?",
            (f"{prefix.lower()}%",)
        )
        tokens = [row["token"] for row in cursor.fetchall()]
        
        # Aggregate candidates from all matching tokens
        candidates = set()
        for token in tokens:
            cursor.execute(
                "SELECT DISTINCT unit_id FROM symbol_index WHERE token = ?",
                (token,)
            )
            candidates.update([row["unit_id"] for row in cursor.fetchall()])
        
        # Rank
        results = self._rank_candidates(prefix.lower(), context_unit_id, list(candidates), max_results)
        
        # Update stats
        self.stats.total_queries += 1
        
        return results
    
    def find_callers(
        self,
        symbol: str,
        max_results: int = 10,
    ) -> List[QueryResult]:
        """
        Find units that call the given symbol.
        
        Returns ranked list of callers.
        """
        cursor = self.conn.cursor()
        
        # Find target unit
        cursor.execute(
            "SELECT id FROM units WHERE name = ?",
            (symbol,)
        )
        target_rows = cursor.fetchall()
        
        if not target_rows:
            return []
        
        results = []
        
        for target_row in target_rows:
            target_id = target_row["id"]
            
            # Find incoming edges (callers)
            cursor.execute(
                "SELECT DISTINCT source_id FROM edges WHERE target_id = ? AND edge_type = ?",
                (target_id, "call")
            )
            callers = [row["source_id"] for row in cursor.fetchall()]
            
            # Rank by locality (no context, so all get neutral score)
            for caller_id in callers[:max_results]:
                if caller_id in self._unit_cache:
                    unit = self._unit_cache[caller_id]
                    results.append(QueryResult(
                        unit_id=caller_id,
                        name=unit.get("name", ""),
                        file_path=unit.get("file_path", ""),
                        score=0.5,
                        reasoning="direct caller",
                        is_exported=unit.get("is_exported", False),
                    ))
        
        self.stats.total_queries += 1
        
        return results[:max_results]
    
    def find_callees(
        self,
        symbol: str,
        max_results: int = 10,
    ) -> List[QueryResult]:
        """
        Find units called by the given symbol.
        
        Returns ranked list of callees.
        """
        cursor = self.conn.cursor()
        
        # Find target unit
        cursor.execute(
            "SELECT id FROM units WHERE name = ?",
            (symbol,)
        )
        target_rows = cursor.fetchall()
        
        if not target_rows:
            return []
        
        results = []
        
        for target_row in target_rows:
            target_id = target_row["id"]
            
            # Find outgoing edges (callees)
            cursor.execute(
                "SELECT DISTINCT target_id FROM edges WHERE source_id = ? AND edge_type = ?",
                (target_id, "call")
            )
            callees = [row["target_id"] for row in cursor.fetchall()]
            
            # Return top callees by in-degree (popularity)
            callee_scores = [(c, self._in_degrees.get(c, 0)) for c in callees]
            callee_scores.sort(key=lambda x: x[1], reverse=True)
            
            for callee_id, _ in callee_scores[:max_results]:
                if callee_id in self._unit_cache:
                    unit = self._unit_cache[callee_id]
                    results.append(QueryResult(
                        unit_id=callee_id,
                        name=unit.get("name", ""),
                        file_path=unit.get("file_path", ""),
                        score=min(self._in_degrees.get(callee_id, 0) / 10.0, 1.0),
                        reasoning="popular callee",
                        is_exported=unit.get("is_exported", False),
                    ))
        
        self.stats.total_queries += 1
        
        return results[:max_results]
    
    def get_stats(self) -> QueryStats:
        """Get query planner statistics."""
        return self.stats
    
    def close(self):
        """Close database connection."""
        self.conn.close()
