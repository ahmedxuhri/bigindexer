"""Integration tests for incremental --lang auto caching."""
from __future__ import annotations

import json
import time
from pathlib import Path

from bgi.pipeline import run_scan


def _create_mixed_repo(root: Path) -> None:
    (root / "app.py").write_text(
        "def auth_user(token):\n"
        "    return token\n",
        encoding="utf-8",
    )
    (root / "web.ts").write_text(
        "export function fetchData(id: string) {\n"
        "  return id;\n"
        "}\n",
        encoding="utf-8",
    )


def test_incremental_auto_caches_languages_and_reuses_entries(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_mixed_repo(repo)

    out = tmp_path / "graph.json"
    db = tmp_path / "sep.db"
    cache_name = ".bgi-auto-cache.json"

    run_scan(
        root=str(repo),
        language="auto",
        output=str(out),
        db=str(db),
        incremental=True,
        cache_file=cache_name,
    )

    cache_path = tmp_path / cache_name
    cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
    entries = cache_data["entries"]
    assert entries["app.py"]["language"] == "python"
    assert entries["web.ts"]["language"] == "typescript"

    capsys.readouterr()
    run_scan(
        root=str(repo),
        language="auto",
        output=str(out),
        db=str(db),
        incremental=True,
        cache_file=cache_name,
    )
    second_run = capsys.readouterr().out
    assert "Incremental auto scan — 0 dirty / 2 cached" in second_run

    time.sleep(0.02)
    (repo / "web.ts").write_text(
        "export function fetchData(id: string) {\n"
        "  console.log(id);\n"
        "  return id;\n"
        "}\n",
        encoding="utf-8",
    )

    run_scan(
        root=str(repo),
        language="auto",
        output=str(out),
        db=str(db),
        incremental=True,
        cache_file=cache_name,
    )
    third_run = capsys.readouterr().out
    assert "Incremental auto scan — 1 dirty / 1 cached" in third_run
