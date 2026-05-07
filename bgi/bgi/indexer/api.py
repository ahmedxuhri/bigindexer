"""
BGI Search API for interactive symbol lookup.

Phase 6 Task 4: exposes QueryPlanner over FastAPI.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query

from bgi.indexer.planner import QueryPlanner, QueryResult


class SearchAPI:
    """FastAPI wrapper for index search endpoints."""

    def __init__(self, db_path: str):
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Index database not found: {db_path}")

        self.db_path = db_path
        self.planner = QueryPlanner(db_path)
        self.app = FastAPI(
            title="BGI Search API",
            version="0.1.0",
            description="Interactive query API over pre-indexed BGI data.",
        )
        self._register_routes()

    @staticmethod
    def _serialize_result(result: QueryResult) -> dict:
        payload = asdict(result)
        payload["is_exported"] = bool(payload["is_exported"])
        return payload

    def _register_routes(self) -> None:
        @self.app.get("/api/symbols/{name}")
        def lookup_symbol(
            name: str,
            context_unit_id: Optional[str] = None,
            max_results: int = Query(default=10, ge=1, le=100),
        ) -> dict:
            results = self.planner.lookup_symbol(
                symbol=name,
                context_unit_id=context_unit_id,
                max_results=max_results,
            )
            return {
                "query": name,
                "context_unit_id": context_unit_id,
                "count": len(results),
                "results": [self._serialize_result(r) for r in results],
            }

        @self.app.get("/api/search")
        def search_prefix(
            q: str = Query(min_length=1),
            context_unit_id: Optional[str] = None,
            max_results: int = Query(default=10, ge=1, le=100),
        ) -> dict:
            results = self.planner.search_prefix(
                prefix=q,
                context_unit_id=context_unit_id,
                max_results=max_results,
            )
            return {
                "query": q,
                "context_unit_id": context_unit_id,
                "count": len(results),
                "results": [self._serialize_result(r) for r in results],
            }

        @self.app.get("/api/callers/{symbol}")
        def callers(symbol: str, max_results: int = Query(default=10, ge=1, le=100)) -> dict:
            results = self.planner.find_callers(symbol=symbol, max_results=max_results)
            return {
                "query": symbol,
                "count": len(results),
                "results": [self._serialize_result(r) for r in results],
            }

        @self.app.get("/api/callees/{symbol}")
        def callees(symbol: str, max_results: int = Query(default=10, ge=1, le=100)) -> dict:
            results = self.planner.find_callees(symbol=symbol, max_results=max_results)
            return {
                "query": symbol,
                "count": len(results),
                "results": [self._serialize_result(r) for r in results],
            }

        @self.app.get("/api/stats")
        def stats() -> dict:
            return asdict(self.planner.get_stats())

        @self.app.get("/api/health")
        def health() -> dict:
            return {"status": "ok", "db_path": self.db_path}

        @self.app.on_event("shutdown")
        def shutdown() -> None:
            self.planner.close()


def create_search_app(db_path: str) -> FastAPI:
    """Create a FastAPI app bound to a BGI index database."""
    return SearchAPI(db_path).app
