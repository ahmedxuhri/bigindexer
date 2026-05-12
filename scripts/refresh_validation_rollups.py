#!/usr/bin/env python3
"""Recompute aggregate/per-repo validation rollups from validation/runs.csv."""

from __future__ import annotations

import csv
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
RUNS_CSV = ROOT / "validation" / "runs.csv"
AGGREGATE_CSV = ROOT / "output" / "validation" / "mcp-ab" / "aggregate.csv"
PER_REPO_CSV = ROOT / "output" / "validation" / "mcp-ab" / "per_repo.csv"

MODES = [
    "baseline",
    "mcp",
    "mcp_twin_refresh_p04",
    "mcp_twin_refresh_full",
    "mcp_twin_refresh_gpt4o",
    "mcp_twin_refresh_gemini_auto",
]

REPO_ORDER = ["django", "fastapi", "nextjs", "prometheus", "pydantic"]


def _is_scored(row: dict[str, str]) -> bool:
    return bool((row.get("evidence_coverage_pct") or "").strip())


def _slice_rows(runs: list[dict[str, str]], mode: str, repo_slug: str | None = None) -> list[dict[str, str]]:
    def repo_ok(r: dict[str, str]) -> bool:
        return repo_slug is None or r["repo_slug"] == repo_slug

    scored = [r for r in runs if _is_scored(r) and repo_ok(r)]
    if mode == "baseline":
        return [r for r in scored if r["mcp_mode"] == "baseline"]
    if mode == "mcp":
        return [
            r
            for r in scored
            if r["mcp_mode"] == "mcp"
            and "twin-refresh" not in r["run_id"]
            and "gpt4o" not in r["run_id"]
            and "gemini-auto" not in r["run_id"]
        ]
    if mode == "mcp_twin_refresh_p04":
        return [
            r
            for r in scored
            if "mcp-twin-refresh" in r["run_id"]
            and "gpt4o" not in r["run_id"]
            and "gemini-auto" not in r["run_id"]
            and r["prompt_id"] == "p04"
        ]
    if mode == "mcp_twin_refresh_full":
        return [
            r
            for r in scored
            if "mcp-twin-refresh" in r["run_id"]
            and "gpt4o" not in r["run_id"]
            and "gemini-auto" not in r["run_id"]
        ]
    if mode == "mcp_twin_refresh_gpt4o":
        return [r for r in scored if "mcp-twin-refresh-gpt4o" in r["run_id"]]
    if mode == "mcp_twin_refresh_gemini_auto":
        return [r for r in scored if "mcp-twin-refresh-gemini-auto" in r["run_id"]]
    return []


def _mean(rows: list[dict[str, str]], key: str) -> float:
    vals = [float(r[key]) for r in rows if (r.get(key) or "").strip()]
    return sum(vals) / len(vals)


def _median(rows: list[dict[str, str]], key: str) -> float:
    vals = [float(r[key]) for r in rows if (r.get(key) or "").strip()]
    return float(median(vals))


def _fmt2(value: float) -> str:
    return f"{value:.2f}"


def _load_runs() -> list[dict[str, str]]:
    with RUNS_CSV.open(newline="") as f:
        return list(csv.DictReader(f))


def _write_aggregate(runs: list[dict[str, str]]) -> None:
    fields = [
        "mcp_mode",
        "prompts",
        "evidence_coverage_pct",
        "boundary_accuracy",
        "actionability",
        "hallucination_flags",
        "median_latency_sec",
        "evidence_tag_relaxed_pct",
    ]
    out: list[dict[str, str]] = []
    for mode in MODES:
        subset = _slice_rows(runs, mode)
        if not subset:
            continue
        out.append(
            {
                "mcp_mode": mode,
                "prompts": str(len(subset)),
                "evidence_coverage_pct": _fmt2(_mean(subset, "evidence_coverage_pct")),
                "boundary_accuracy": _fmt2(_mean(subset, "boundary_accuracy")),
                "actionability": _fmt2(_mean(subset, "actionability")),
                "hallucination_flags": _fmt2(_mean(subset, "hallucination_flags")),
                "median_latency_sec": _fmt2(_median(subset, "latency_sec")),
                "evidence_tag_relaxed_pct": (
                    _fmt2(_mean(subset, "evidence_tag_relaxed_pct"))
                    if any((r.get("evidence_tag_relaxed_pct") or "").strip() for r in subset)
                    else ""
                ),
            }
        )

    with AGGREGATE_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out)


def _write_per_repo(runs: list[dict[str, str]]) -> None:
    fields = [
        "repo_slug",
        "mcp_mode",
        "prompts",
        "median_latency_sec",
        "evidence_coverage_pct",
        "boundary_accuracy",
        "actionability",
        "hallucination_flags",
        "evidence_tag_relaxed_pct",
    ]
    out: list[dict[str, str]] = []
    for mode in MODES:
        for repo in REPO_ORDER:
            subset = _slice_rows(runs, mode, repo)
            if not subset:
                continue
            out.append(
                {
                    "repo_slug": repo,
                    "mcp_mode": mode,
                    "prompts": str(len(subset)),
                    "median_latency_sec": _fmt2(_median(subset, "latency_sec")),
                    "evidence_coverage_pct": _fmt2(_mean(subset, "evidence_coverage_pct")),
                    "boundary_accuracy": _fmt2(_mean(subset, "boundary_accuracy")),
                    "actionability": _fmt2(_mean(subset, "actionability")),
                    "hallucination_flags": _fmt2(_mean(subset, "hallucination_flags")),
                    "evidence_tag_relaxed_pct": (
                        _fmt2(_mean(subset, "evidence_tag_relaxed_pct"))
                        if any((r.get("evidence_tag_relaxed_pct") or "").strip() for r in subset)
                        else ""
                    ),
                }
            )

    with PER_REPO_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out)


def main() -> None:
    runs = _load_runs()
    _write_aggregate(runs)
    _write_per_repo(runs)
    print("Refreshed aggregate.csv and per_repo.csv from runs.csv")


if __name__ == "__main__":
    main()
