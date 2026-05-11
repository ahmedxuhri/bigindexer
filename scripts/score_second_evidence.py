#!/usr/bin/env python3
"""Compute and publish a second (tag-relaxed) evidence score.

The primary evidence metric in runs.csv is checklist recall from strict verified claims.
This script adds a secondary score that credits repo-anchored evidence lines even when
they are not explicitly tagged as VERIFIED/HYPOTHESIS/UNKNOWN.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
RUNS_CSV = ROOT / "validation" / "runs.csv"
AGGREGATE_CSV = ROOT / "output" / "validation" / "mcp-ab" / "aggregate.csv"
PER_REPO_CSV = ROOT / "output" / "validation" / "mcp-ab" / "per_repo.csv"

SECOND_METRIC = "evidence_tag_relaxed_pct"

CHECKLIST_COUNTS = {
    ("fastapi", "p01"): 7,
    ("django", "p01"): 7,
    ("pydantic", "p01"): 6,
    ("prometheus", "p01"): 7,
    ("nextjs", "p01"): 7,
    ("fastapi", "p02"): 5,
    ("django", "p02"): 5,
    ("pydantic", "p02"): 5,
    ("prometheus", "p02"): 5,
    ("nextjs", "p02"): 8,
    ("fastapi", "p03"): 6,
    ("django", "p03"): 5,
    ("pydantic", "p03"): 5,
    ("prometheus", "p03"): 5,
    ("nextjs", "p03"): 5,
    ("fastapi", "p04"): 5,
    ("django", "p04"): 5,
    ("pydantic", "p04"): 5,
    ("prometheus", "p04"): 5,
    ("nextjs", "p04"): 5,
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LABEL_RE = re.compile(r"\b(?:VERIFIED|HYPOTHESIS|UNKNOWN)\b", re.IGNORECASE)
ANCHOR_RE = re.compile(r"\b[a-zA-Z0-9_./-]+\.(?:py|go|ts|tsx|rs|js|jsx|md)\b")


def _is_scored(row: dict[str, str]) -> bool:
    return bool((row.get("evidence_coverage_pct") or "").strip())


def _iter_clean_lines(output_file: str):
    text = (ROOT / output_file).read_text(errors="ignore")
    for raw in text.splitlines():
        line = ANSI_RE.sub("", raw)
        if line.startswith(("INFO", "WARN", "ERROR")):
            continue
        if line.startswith("> build ·"):
            continue
        yield line


def _second_score(row: dict[str, str]) -> str:
    key = (row["repo_slug"], row["prompt_id"])
    denom = CHECKLIST_COUNTS.get(key)
    if not denom:
        return ""

    base = float(row["evidence_coverage_pct"])
    unlabeled_anchor_lines = 0
    for line in _iter_clean_lines(row["output_file"]):
        if ANCHOR_RE.search(line) and not LABEL_RE.search(line):
            unlabeled_anchor_lines += 1

    # Conservative tag-relaxed credit:
    #  - scale by checklist size
    #  - apply low weight (0.15)
    #  - cap at +25 points to keep the primary metric dominant
    bonus = min(25.0, (unlabeled_anchor_lines / denom) * 100.0 * 0.15)
    score = min(100.0, base + bonus)
    return f"{score:.1f}"


def _load_csv(path: Path):
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return rows, fieldnames


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _mean(rows: list[dict[str, str]], key: str) -> float:
    vals = [float(r[key]) for r in rows if (r.get(key) or "").strip()]
    return sum(vals) / len(vals)


def _median(rows: list[dict[str, str]], key: str) -> float:
    vals = [float(r[key]) for r in rows if (r.get(key) or "").strip()]
    return float(median(vals))


def _slice_rows(runs: list[dict[str, str]], mode: str, repo_slug: str | None = None):
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
        ]
    if mode == "mcp_twin_refresh_p04":
        return [
            r
            for r in scored
            if "mcp-twin-refresh" in r["run_id"]
            and "gpt4o" not in r["run_id"]
            and r["prompt_id"] == "p04"
        ]
    if mode == "mcp_twin_refresh_full":
        return [
            r
            for r in scored
            if "mcp-twin-refresh" in r["run_id"] and "gpt4o" not in r["run_id"]
        ]
    if mode == "mcp_twin_refresh_gpt4o":
        return [r for r in scored if "mcp-twin-refresh-gpt4o" in r["run_id"]]
    return []


def _refresh_rollups(runs: list[dict[str, str]]):
    agg_rows, agg_fields = _load_csv(AGGREGATE_CSV)
    if SECOND_METRIC not in agg_fields:
        agg_fields.append(SECOND_METRIC)
    for row in agg_rows:
        subset = _slice_rows(runs, row["mcp_mode"])
        row[SECOND_METRIC] = f"{_mean(subset, SECOND_METRIC):.2f}" if subset else ""

    per_rows, per_fields = _load_csv(PER_REPO_CSV)
    if SECOND_METRIC not in per_fields:
        per_fields.append(SECOND_METRIC)
    for row in per_rows:
        subset = _slice_rows(runs, row["mcp_mode"], row["repo_slug"])
        row[SECOND_METRIC] = f"{_mean(subset, SECOND_METRIC):.2f}" if subset else ""

    _write_csv(AGGREGATE_CSV, agg_fields, agg_rows)
    _write_csv(PER_REPO_CSV, per_fields, per_rows)


def main():
    runs, run_fields = _load_csv(RUNS_CSV)
    if SECOND_METRIC not in run_fields:
        run_fields.append(SECOND_METRIC)

    for row in runs:
        row[SECOND_METRIC] = _second_score(row) if _is_scored(row) else ""

    _write_csv(RUNS_CSV, run_fields, runs)
    _refresh_rollups(runs)
    print("Updated second evidence score in runs/aggregate/per_repo CSVs.")


if __name__ == "__main__":
    main()
