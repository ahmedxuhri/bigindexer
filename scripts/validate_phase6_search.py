#!/usr/bin/env python3
"""
Phase 6 validation runner:
1) Build a kubernetes-sized search index from Gate 1 units
2) Benchmark QueryPlanner and Query API latency
3) Write JSON report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.scanner import scan_repository
from bgi.indexer.api import SearchAPI
from bgi.indexer.builder import IndexBuilder
from bgi.indexer.planner import QueryPlanner
from bgi.indexer.schema import IndexSchema


def _parse_unit_id(unit_id: str) -> tuple[str, str]:
    if "::" in unit_id:
        file_path, rest = unit_id.split("::", 1)
        name = rest.split("::")[-1].split("#")[-1]
        return file_path, name or Path(file_path).stem
    if ":" in unit_id:
        file_path, name = unit_id.rsplit(":", 1)
        return file_path, name or Path(file_path).stem
    return unit_id, Path(unit_id).stem


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * (p / 100.0)))
    return sorted_vals[max(0, min(idx, len(sorted_vals) - 1))]


def _timed_call(fn, *args, **kwargs) -> tuple[Any, float]:
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return result, elapsed_ms


def _write_gate_jsonl(
    fingerprints: list[Any],
    out_dir: Path,
    cluster_size: int = 25,
) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    units_file = out_dir / "units.jsonl"
    edges_file = out_dir / "edges.jsonl"
    clusters_file = out_dir / "clusters.jsonl"

    units: list[dict[str, Any]] = []
    with units_file.open("w", encoding="utf-8") as f:
        for fp in fingerprints:
            file_path, name = _parse_unit_id(fp.unit_id)
            line_start, line_end = (0, 0)
            if isinstance(fp.line_range, (tuple, list)) and len(fp.line_range) == 2:
                line_start, line_end = int(fp.line_range[0]), int(fp.line_range[1])
            unit = {
                "id": fp.unit_id,
                "name": name,
                "file_path": file_path,
                "language": fp.language or "unknown",
                "line_start": line_start,
                "line_end": line_end,
                "fingerprint": {"tokens": [str(t) for t in fp.tokens]},
                "is_exported": not name.startswith("_"),
            }
            units.append(unit)
            f.write(json.dumps(unit) + "\n")

    # Synthetic call edges to exercise caller/callee paths at scale.
    unit_ids = [u["id"] for u in units]
    with edges_file.open("w", encoding="utf-8") as f:
        for i in range(len(unit_ids) - 1):
            edge = {
                "source": unit_ids[i],
                "target": unit_ids[i + 1],
                "type": "call",
                "fanout": 0.5,
                "confidence": 0.8,
            }
            f.write(json.dumps(edge) + "\n")
            if i % 20 == 0 and i + 20 < len(unit_ids):
                shortcut = {
                    "source": unit_ids[i],
                    "target": unit_ids[i + 20],
                    "type": "call",
                    "fanout": 0.3,
                    "confidence": 0.6,
                }
                f.write(json.dumps(shortcut) + "\n")

    total_units = max(1, len(unit_ids))
    with clusters_file.open("w", encoding="utf-8") as f:
        cluster_id = 1
        for i in range(0, len(unit_ids), cluster_size):
            members = unit_ids[i : i + cluster_size]
            cluster = {
                "id": cluster_id,
                "units": members,
                "max_unit_pct": round((len(members) / total_units) * 100.0, 4),
            }
            f.write(json.dumps(cluster) + "\n")
            cluster_id += 1

    return units_file, edges_file, clusters_file


def _bench_planner(planner: QueryPlanner, sample_symbols: list[str], sample_contexts: list[str]) -> dict:
    lookup_times: list[float] = []
    prefix_times: list[float] = []
    callers_times: list[float] = []
    callees_times: list[float] = []

    prefixes = sorted({s[:3] for s in sample_symbols if len(s) >= 3})
    if not prefixes:
        prefixes = ["get"]

    for i, symbol in enumerate(sample_symbols):
        context = sample_contexts[i % len(sample_contexts)] if sample_contexts else None
        _, ms = _timed_call(planner.lookup_symbol, symbol, context, 10)
        lookup_times.append(ms)

    for p in prefixes[: min(300, len(prefixes))]:
        _, ms = _timed_call(planner.search_prefix, p, None, 10)
        prefix_times.append(ms)

    for symbol in sample_symbols[:200]:
        _, ms_callers = _timed_call(planner.find_callers, symbol, 10)
        _, ms_callees = _timed_call(planner.find_callees, symbol, 10)
        callers_times.append(ms_callers)
        callees_times.append(ms_callees)

    def _stats(values: list[float]) -> dict[str, float]:
        return {
            "count": len(values),
            "avg_ms": round(sum(values) / max(1, len(values)), 3),
            "p50_ms": round(_percentile(values, 50), 3),
            "p95_ms": round(_percentile(values, 95), 3),
            "max_ms": round(max(values) if values else 0.0, 3),
        }

    return {
        "lookup_symbol": _stats(lookup_times),
        "search_prefix": _stats(prefix_times),
        "find_callers": _stats(callers_times),
        "find_callees": _stats(callees_times),
    }


async def _bench_api(index_path: str, sample_symbols: list[str]) -> dict:
    api = SearchAPI(index_path)
    transport = httpx.ASGITransport(app=api.app)
    timings: dict[str, list[float]] = {
        "symbols": [],
        "search": [],
        "callers": [],
        "callees": [],
        "stats": [],
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for symbol in sample_symbols:
            t0 = time.perf_counter()
            r = await client.get(f"/api/symbols/{symbol}", params={"max_results": 10})
            r.raise_for_status()
            timings["symbols"].append((time.perf_counter() - t0) * 1000.0)

        prefixes = sorted({s[:3] for s in sample_symbols if len(s) >= 3})[:200]
        for p in prefixes:
            t0 = time.perf_counter()
            r = await client.get("/api/search", params={"q": p, "max_results": 10})
            r.raise_for_status()
            timings["search"].append((time.perf_counter() - t0) * 1000.0)

        for symbol in sample_symbols[:150]:
            t0 = time.perf_counter()
            r = await client.get(f"/api/callers/{symbol}", params={"max_results": 10})
            r.raise_for_status()
            timings["callers"].append((time.perf_counter() - t0) * 1000.0)

            t0 = time.perf_counter()
            r = await client.get(f"/api/callees/{symbol}", params={"max_results": 10})
            r.raise_for_status()
            timings["callees"].append((time.perf_counter() - t0) * 1000.0)

        for _ in range(50):
            t0 = time.perf_counter()
            r = await client.get("/api/stats")
            r.raise_for_status()
            timings["stats"].append((time.perf_counter() - t0) * 1000.0)

    api.planner.close()

    def _stats(values: list[float]) -> dict[str, float]:
        return {
            "count": len(values),
            "avg_ms": round(sum(values) / max(1, len(values)), 3),
            "p50_ms": round(_percentile(values, 50), 3),
            "p95_ms": round(_percentile(values, 95), 3),
            "max_ms": round(max(values) if values else 0.0, 3),
        }

    return {endpoint: _stats(vals) for endpoint, vals in timings.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Phase 6 search latency.")
    parser.add_argument("--repo", required=True, help="Repo root to scan (Gate 1).")
    parser.add_argument("--index-db", required=True, help="Output SQLite index path.")
    parser.add_argument("--report", required=True, help="Output JSON report path.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    repo = Path(args.repo).resolve()
    index_path = Path(args.index_db).resolve()
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[Phase6] Gate 1 scan start: {repo}")
    ai = AIFallback(enabled=False)
    t0 = time.perf_counter()
    fingerprints = scan_repository(repo, ai=ai)
    gate1_sec = time.perf_counter() - t0
    print(f"[Phase6] Gate 1 units: {len(fingerprints)} in {gate1_sec:.3f}s")

    with tempfile.TemporaryDirectory(prefix="bgi-phase6-") as tmpdir:
        units_file, edges_file, clusters_file = _write_gate_jsonl(
            fingerprints=fingerprints,
            out_dir=Path(tmpdir),
        )

        schema = IndexSchema(str(index_path))
        schema.create_schema(overwrite=True)
        builder = IndexBuilder(schema)

        print("[Phase6] Building index ...")
        t1 = time.perf_counter()
        build_stats = builder.build_from_pipeline_output(
            str(units_file),
            str(edges_file),
            str(clusters_file),
            None,
        )
        index_build_sec = time.perf_counter() - t1
        index_stats = builder.get_build_stats()
        schema.close()

    planner = QueryPlanner(str(index_path))
    symbol_rows = planner.conn.execute(
        "SELECT id, name FROM units WHERE name IS NOT NULL AND name != ''"
    ).fetchall()
    sample = [(row["id"], row["name"]) for row in symbol_rows]
    random.shuffle(sample)
    sample = sample[: min(500, len(sample))]
    sample_symbols = [name for _, name in sample]
    sample_contexts = [uid for uid, _ in sample]

    print(f"[Phase6] Benchmarking planner with {len(sample_symbols)} sample symbols ...")
    planner_stats = _bench_planner(planner, sample_symbols, sample_contexts)
    planner.close()

    print("[Phase6] Benchmarking API endpoints ...")
    api_stats = asyncio.run(_bench_api(str(index_path), sample_symbols))

    report = {
        "repo": str(repo),
        "seed": args.seed,
        "gate1_units": len(fingerprints),
        "gate1_time_sec": round(gate1_sec, 3),
        "index_build_time_sec": round(index_build_sec, 3),
        "index_db_path": str(index_path),
        "index_build_stats": build_stats,
        "index_stats": index_stats,
        "planner_latency_ms": planner_stats,
        "api_latency_ms": api_stats,
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[Phase6] Report written: {report_path}")
    print(
        f"[Phase6] Planner lookup p95={planner_stats['lookup_symbol']['p95_ms']}ms | "
        f"API /api/symbols p95={api_stats['symbols']['p95_ms']}ms"
    )


if __name__ == "__main__":
    main()
