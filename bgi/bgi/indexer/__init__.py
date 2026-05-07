"""
BGI Interactive Search Index

Enables sub-second queries on large codebases by pre-indexing Gate 1-3 output.

Public API:
    - IndexSchema: database schema management
    - init_index: initialize index database
    - IndexBuilder: load Gate output into indexes
    - QueryPlanner: plan search queries for fast lookups (Phase 6 Task 3)
    - SearchAPI: REST endpoints (Phase 6 Task 4)
"""

from bgi.indexer.schema import IndexSchema, init_index, SCHEMA_VERSION

__all__ = [
    "IndexSchema",
    "init_index",
    "SCHEMA_VERSION",
]
