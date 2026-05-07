"""Tests for Phase 6 Task 4 Query API endpoints."""

import json
import tempfile
from pathlib import Path

import httpx
import pytest

from bgi.indexer.api import SearchAPI
from bgi.indexer.schema import IndexSchema


def _seed_index_data(db_path: str) -> None:
    schema = IndexSchema(db_path)
    schema.create_schema()

    cursor = schema.conn.cursor()

    units = [
        (
            "auth.py:fetch_user",
            "fetch_user",
            "auth/auth.py",
            "python",
            10,
            20,
            json.dumps({"tokens": ["FETCH", "OUTPUT"]}),
            1,
        ),
        (
            "auth.py:verify_token",
            "verify_token",
            "auth/auth.py",
            "python",
            22,
            35,
            json.dumps({"tokens": ["VALIDATE", "OUTPUT"]}),
            1,
        ),
        (
            "utils.py:helper",
            "helper",
            "utils/utils.py",
            "python",
            1,
            5,
            json.dumps({"tokens": ["OUTPUT"]}),
            0,
        ),
        (
            "app.py:main",
            "main",
            "app/app.py",
            "python",
            50,
            100,
            json.dumps({"tokens": ["FETCH", "VALIDATE"]}),
            1,
        ),
    ]
    cursor.executemany(
        """
        INSERT INTO units
        (id, name, file_path, language, line_start, line_end, fingerprint, is_exported)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        units,
    )

    edges = [
        ("app.py:main", "auth.py:fetch_user", "call", 0.9),
        ("app.py:main", "auth.py:verify_token", "call", 0.8),
        ("auth.py:fetch_user", "utils.py:helper", "call", 0.7),
    ]
    cursor.executemany(
        """
        INSERT INTO edges (source_id, target_id, edge_type, fanout)
        VALUES (?, ?, ?, ?)
        """,
        edges,
    )

    symbol_tokens = [
        ("auth.py:fetch_user", "fetch"),
        ("auth.py:fetch_user", "user"),
        ("auth.py:fetch_user", "fetch_user"),
        ("auth.py:verify_token", "verify"),
        ("auth.py:verify_token", "token"),
        ("auth.py:verify_token", "verify_token"),
        ("utils.py:helper", "helper"),
        ("app.py:main", "main"),
    ]
    cursor.executemany(
        "INSERT INTO symbol_index (unit_id, token) VALUES (?, ?)",
        symbol_tokens,
    )

    schema.conn.commit()
    schema.conn.close()


@pytest.fixture
def seeded_db_path() -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "api-test.db")
        _seed_index_data(db_path)
        yield db_path


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def api_client(seeded_db_path: str):
    search_api = SearchAPI(seeded_db_path)
    transport = httpx.ASGITransport(app=search_api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    search_api.planner.close()


@pytest.mark.anyio
async def test_lookup_symbol_endpoint(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/symbols/fetch_user")
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "fetch_user"
    assert body["count"] == 1
    assert body["results"][0]["unit_id"] == "auth.py:fetch_user"
    assert isinstance(body["results"][0]["is_exported"], bool)


@pytest.mark.anyio
async def test_lookup_symbol_respects_max_results(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/symbols/fetch", params={"max_results": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] <= 1


@pytest.mark.anyio
async def test_search_prefix_endpoint(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/search", params={"q": "ver"})
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "ver"
    assert body["count"] >= 1
    assert body["results"][0]["name"] == "verify_token"


@pytest.mark.anyio
async def test_search_prefix_requires_q(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/search")
    assert response.status_code == 422


@pytest.mark.anyio
async def test_callers_endpoint(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/callers/fetch_user")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    unit_ids = {result["unit_id"] for result in body["results"]}
    assert "app.py:main" in unit_ids


@pytest.mark.anyio
async def test_callees_endpoint(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/callees/main")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    unit_ids = {result["unit_id"] for result in body["results"]}
    assert "auth.py:fetch_user" in unit_ids


@pytest.mark.anyio
async def test_stats_endpoint(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["db_path"].endswith("api-test.db")
    assert body["unique_units"] == 4
    assert body["token_count"] >= 1


@pytest.mark.anyio
async def test_health_endpoint(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
