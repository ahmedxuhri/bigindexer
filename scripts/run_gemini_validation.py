#!/usr/bin/env python3
"""Run Gemini TWIN validation in foreground with auto model mode.

Key behavior:
1. Sequential execution (no background shell loop).
2. Resume-safe (skips already completed prompt files).
3. Gemini model auto-selection (no -m flag).
4. Reconfigures Gemini MCP `bigindexer` server per target repo.
5. Appends/upserts rows in validation/runs.csv for generated outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "validation" / "runs"
RUNS_CSV = ROOT / "validation" / "runs.csv"
REPOS_CSV = ROOT / "validation" / "repos.csv"
ARTIFACTS_DIR = ROOT / "output" / "validation" / "mcp-ab"
REPO_BASE = Path("/tmp/bgi-ab-repos")

DEFAULT_REPOS = ["fastapi", "django", "pydantic", "prometheus", "nextjs"]
PROMPT_IDS = ["p01", "p02", "p03", "p04"]

PROMPTS = {
    "fastapi": {
        "p01": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Understand fastapi architecture and identify strong and weak points with evidence' "
            "and limit 3. Then answer: Tell me what this project is about, strong points, "
            "and weak points. Include a concise actionability checklist."
        ),
        "p02": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Assess boundary impact of editing fastapi/routing.py' and limit 3. "
            "Then answer: What architectural boundaries are touched if we edit "
            "fastapi/routing.py? Include a concise actionability checklist."
        ),
        "p03": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Estimate blast radius for solve_dependencies in fastapi/dependencies/utils.py' "
            "and limit 3. Then answer: What is the likely blast radius if we change "
            "solve_dependencies in fastapi/dependencies/utils.py? Include a concise "
            "actionability checklist."
        ),
        "p04": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'I need to add request timing middleware with x-request-timing header in FastAPI "
            "request pipeline. Give the safest implementation path with minimal "
            "cross-boundary impact.' and limit 3. Then provide the safest implementation path. "
            "Include the twin_context result fields task_cov, top twin ids/files, seam "
            "recommendation, and an explicit actionability checklist."
        ),
    },
    "django": {
        "p01": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Understand django architecture and identify strong and weak points with evidence' "
            "and limit 3. Then answer: Tell me what this project is about, strong points, "
            "and weak points. Include a concise actionability checklist."
        ),
        "p02": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Assess boundary impact of editing django/db/models/query.py' and limit 3. "
            "Then answer: What architectural boundaries are touched if we edit "
            "django/db/models/query.py? Include a concise actionability checklist."
        ),
        "p03": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Estimate blast radius for get_response in django/core/handlers/base.py' and limit 3. "
            "Then answer: What is the likely blast radius if we change get_response in "
            "django/core/handlers/base.py? Include a concise actionability checklist."
        ),
        "p04": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'I need to add per-request audit log in Django with minimal cross-boundary impact. "
            "Give the safest implementation path with minimal cross-boundary impact.' and limit 3. "
            "Then provide the safest implementation path. Include the twin_context result fields "
            "task_cov, top twin ids/files, seam recommendation, and an explicit actionability checklist."
        ),
    },
    "pydantic": {
        "p01": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Understand pydantic architecture and identify strong and weak points with evidence' "
            "and limit 3. Then answer: Tell me what this project is about, strong points, "
            "and weak points. Include a concise actionability checklist."
        ),
        "p02": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Assess boundary impact of editing pydantic/main.py' and limit 3. "
            "Then answer: What architectural boundaries are touched if we edit "
            "pydantic/main.py? Include a concise actionability checklist."
        ),
        "p03": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Estimate blast radius for changes in pydantic/fields.py' and limit 3. "
            "Then answer: What is the likely blast radius if we change pydantic/fields.py? "
            "Include a concise actionability checklist."
        ),
        "p04": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'I need to add a custom string validator in pydantic with the safest "
            "implementation path and minimal cross-boundary impact.' and limit 3. "
            "Then provide the safest implementation path. Include the twin_context result "
            "fields task_cov, top twin ids/files, seam recommendation, and an explicit "
            "actionability checklist."
        ),
    },
    "prometheus": {
        "p01": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Understand prometheus architecture and identify strong and weak points with evidence' "
            "and limit 3. Then answer: Tell me what this project is about, strong points, "
            "and weak points. Include a concise actionability checklist."
        ),
        "p02": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Assess boundary impact of editing scrape/manager.go' and limit 3. "
            "Then answer: What architectural boundaries are touched if we edit "
            "scrape/manager.go? Include a concise actionability checklist."
        ),
        "p03": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Estimate blast radius for fanout.Querier in storage/fanout.go' and limit 3. "
            "Then answer: What is the likely blast radius if we change fanout.Querier in "
            "storage/fanout.go? Include a concise actionability checklist."
        ),
        "p04": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'In prometheus/web/api/v1/api.go, add a new endpoint /api/v1/status/label_cardinality "
            "next to existing label/series handlers using storage.Querier path and minimal "
            "cross-boundary impact.' and limit 3. Then provide the safest implementation path. "
            "Include task_cov, top twin ids/files, seam recommendation, and a 5-step "
            "actionability checklist with exact file-level guidance."
        ),
    },
    "nextjs": {
        "p01": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Understand next.js architecture and identify strong and weak points with evidence' "
            "and limit 3. Then answer: Tell me what this project is about, strong points, "
            "and weak points. Include a concise actionability checklist."
        ),
        "p02": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Assess boundary impact of editing packages/next/src/server/next-server.ts' and limit 3. "
            "Then answer: What architectural boundaries are touched if we edit "
            "packages/next/src/server/next-server.ts? Include a concise actionability checklist."
        ),
        "p03": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'Estimate blast radius for BaseServer in packages/next/src/server/base-server.ts' "
            "and limit 3. Then answer: What is the likely blast radius if we change BaseServer "
            "in packages/next/src/server/base-server.ts? Include a concise actionability checklist."
        ),
        "p04": (
            "Use evidence mode. For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN "
            "and cite exact sources. Separate current state from historical context. "
            "Do not modify anything. First, call bigindexer_twin_context with task: "
            "'I need to add a per-request trace-id response header in Next.js with the safest "
            "implementation path and minimal cross-boundary impact.' and limit 3. "
            "Then provide the safest implementation path. Include the twin_context result fields "
            "task_cov, top twin ids/files, seam recommendation, and an explicit actionability checklist."
        ),
    },
}


@dataclass
class RunResult:
    repo: str
    prompt_id: str
    latency_sec: float
    output_file: Path
    time_file: Path
    mcp_invoked: bool
    returncode: int
    status: str
    timestamp_utc: str


def _load_repo_urls() -> dict[str, str]:
    urls: dict[str, str] = {}
    with REPOS_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            urls[row["repo_slug"]] = row["repo_url"]
    return urls


def _run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )


def _ensure_repo_checkout(repo: str, repo_url: str) -> Path:
    REPO_BASE.mkdir(parents=True, exist_ok=True)
    repo_dir = REPO_BASE / repo
    if repo_dir.exists() and (repo_dir / ".git").exists():
        return repo_dir

    if repo_dir.exists() and not (repo_dir / ".git").exists():
        raise RuntimeError(f"{repo_dir} exists but is not a git repo")

    clone = _run_cmd(
        ["git", "clone", "--depth", "1", repo_url, str(repo_dir)],
        cwd=REPO_BASE.parent,
        timeout=3600,
    )
    if clone.returncode != 0:
        raise RuntimeError(
            f"git clone failed for {repo}: {clone.stderr.strip() or clone.stdout.strip()}"
        )
    return repo_dir


def _configure_gemini_mcp(repo: str) -> None:
    graph = ARTIFACTS_DIR / repo / "bgi-graph.json"
    fuse = ARTIFACTS_DIR / repo / "fuse-graph.json"
    if not graph.exists() or not fuse.exists():
        raise RuntimeError(f"Missing artifacts for {repo}: {graph} / {fuse}")

    _run_cmd(["gemini", "mcp", "remove", "bigindexer"], cwd=ROOT, timeout=30)
    add = _run_cmd(
        [
            "gemini",
            "mcp",
            "add",
            "bigindexer",
            "python3",
            "-m",
            "bgi.cli",
            "mcp",
            "--graph",
            str(graph),
            "--fuse-graph",
            str(fuse),
        ],
        cwd=ROOT,
        timeout=120,
    )
    if add.returncode != 0:
        raise RuntimeError(f"gemini mcp add failed: {add.stderr.strip() or add.stdout.strip()}")

    listed = _run_cmd(["gemini", "mcp", "list"], cwd=ROOT, timeout=60)
    listing = f"{listed.stdout}\n{listed.stderr}"
    if repo not in listing:
        raise RuntimeError(f"gemini mcp list does not show repo '{repo}' in bigindexer config")


def _output_paths(repo: str, prompt_id: str) -> tuple[Path, Path]:
    repo_run_dir = RUNS_DIR / repo
    repo_run_dir.mkdir(parents=True, exist_ok=True)
    stem = f"gemini_mcp_{prompt_id}_twin_refresh_auto_r1"
    return repo_run_dir / f"{stem}.txt", repo_run_dir / f"{stem}.time"


def _already_completed(out_file: Path, time_file: Path) -> bool:
    if not out_file.exists() or not time_file.exists():
        return False
    text = out_file.read_text(errors="ignore")
    return _detect_mcp_invocation(text) and len(text.strip()) > 0


def _detect_mcp_invocation(output_text: str) -> bool:
    for line in output_text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "tool_use":
            continue
        tool_name = str(event.get("tool_name", ""))
        if tool_name.startswith("mcp_bigindexer_twin_context"):
            return True
    return False


def _run_one(repo: str, prompt_id: str, repo_dir: Path, timeout: int) -> RunResult:
    prompt = PROMPTS[repo][prompt_id]
    out_file, time_file = _output_paths(repo, prompt_id)

    if _already_completed(out_file, time_file):
        latency = float(time_file.read_text().strip())
        return RunResult(
            repo=repo,
            prompt_id=prompt_id,
            latency_sec=latency,
            output_file=out_file,
            time_file=time_file,
            mcp_invoked=True,
            returncode=0,
            status="skipped_existing",
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    cmd = [
        "gemini",
        "--approval-mode",
        "yolo",
        "--output-format",
        "stream-json",
        "--include-directories",
        str(repo_dir),
        "-p",
        prompt,
    ]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    start = time.perf_counter()
    try:
        proc = _run_cmd(cmd, cwd=ROOT, timeout=timeout)
        elapsed = time.perf_counter() - start
        combined = f"{proc.stdout}{proc.stderr}"
        out_file.write_text(combined)
        time_file.write_text(f"{elapsed:.2f}")
        mcp_invoked = _detect_mcp_invocation(combined)

        if proc.returncode != 0:
            status = "error"
        elif not mcp_invoked:
            status = "no_mcp_invocation"
        else:
            status = "ok"

        return RunResult(
            repo=repo,
            prompt_id=prompt_id,
            latency_sec=elapsed,
            output_file=out_file,
            time_file=time_file,
            mcp_invoked=mcp_invoked,
            returncode=proc.returncode,
            status=status,
            timestamp_utc=ts,
        )
    except subprocess.TimeoutExpired as e:
        elapsed = time.perf_counter() - start
        output = (e.stdout or "") + (e.stderr or "") + "\n[timeout]\n"
        out_file.write_text(output)
        time_file.write_text(f"{elapsed:.2f}")
        return RunResult(
            repo=repo,
            prompt_id=prompt_id,
            latency_sec=elapsed,
            output_file=out_file,
            time_file=time_file,
            mcp_invoked=False,
            returncode=124,
            status="timeout",
            timestamp_utc=ts,
        )


def _note_from_status(result: RunResult) -> str:
    if result.status == "ok":
        return "gemini_auto_twin_refresh_valid_mcp_invoked"
    if result.status == "no_mcp_invocation":
        return "gemini_auto_twin_refresh_invalid_no_mcp_invocation"
    if result.status == "timeout":
        return "gemini_auto_twin_refresh_timeout"
    if result.status == "skipped_existing":
        return "gemini_auto_twin_refresh_skipped_existing"
    return f"gemini_auto_twin_refresh_error_rc_{result.returncode}"


def _upsert_runs_csv(results: list[RunResult]) -> None:
    with RUNS_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    index = {row["run_id"]: i for i, row in enumerate(rows)}
    for result in results:
        run_id = f"{result.repo}-{result.prompt_id}-mcp-twin-refresh-gemini-auto-r1"
        row = {k: "" for k in fieldnames}
        row.update(
            {
                "run_id": run_id,
                "timestamp_utc": result.timestamp_utc,
                "repo_slug": result.repo,
                "repo_dir": str(REPO_BASE / result.repo),
                "cli": "gemini",
                "model": "gemini/auto",
                "mcp_mode": "mcp",
                "prompt_id": result.prompt_id,
                "latency_sec": f"{result.latency_sec:.2f}",
                "output_file": str(result.output_file.relative_to(ROOT)),
                "time_file": str(result.time_file.relative_to(ROOT)),
                "executor": "gemini_auto_runner",
                "notes": _note_from_status(result),
            }
        )
        if run_id in index:
            rows[index[run_id]] = row
        else:
            rows.append(row)

    with RUNS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini auto-model TWIN retest runner")
    parser.add_argument(
        "--repos",
        default=",".join(DEFAULT_REPOS),
        help="Comma-separated repo slugs (default: fastapi,django,pydantic,prometheus,nextjs)",
    )
    parser.add_argument("--skip-clone", action="store_true", help="Do not clone missing repos")
    parser.add_argument("--timeout", type=int, default=420, help="Per-run timeout in seconds")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N runs (0 = all)")
    args = parser.parse_args()

    if "GEMINI_API_KEY" not in os.environ:
        print("ERROR: GEMINI_API_KEY is not set in environment.")
        return 2

    repo_urls = _load_repo_urls()
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    missing_prompt_repos = [r for r in repos if r not in PROMPTS]
    if missing_prompt_repos:
        print(f"ERROR: missing prompt config for repos: {', '.join(missing_prompt_repos)}")
        return 2

    prepared: dict[str, Path] = {}
    for repo in repos:
        if args.skip_clone:
            repo_dir = REPO_BASE / repo
            if not repo_dir.exists():
                print(f"ERROR: --skip-clone set but repo missing: {repo_dir}")
                return 2
            prepared[repo] = repo_dir
            continue
        url = repo_urls.get(repo)
        if not url:
            print(f"ERROR: repo URL not found in repos.csv for {repo}")
            return 2
        prepared[repo] = _ensure_repo_checkout(repo, url)

    results: list[RunResult] = []
    run_count = 0
    total_runs = len(repos) * len(PROMPT_IDS)
    print(f"Starting Gemini auto retest: {total_runs} runs")

    for repo in repos:
        print(f"\n[{repo}] configuring MCP")
        _configure_gemini_mcp(repo)
        for prompt_id in PROMPT_IDS:
            run_count += 1
            print(f"  ({run_count}/{total_runs}) {repo}/{prompt_id} ... ", end="", flush=True)
            result = _run_one(repo, prompt_id, prepared[repo], timeout=args.timeout)
            results.append(result)
            print(f"{result.status} ({result.latency_sec:.2f}s)")

            if args.limit and run_count >= args.limit:
                _upsert_runs_csv(results)
                print("\nStopped early due to --limit.")
                return 0

    _upsert_runs_csv(results)
    ok = sum(1 for r in results if r.status in {"ok", "skipped_existing"})
    print(f"\nDone. {ok}/{len(results)} runs completed with MCP evidence or existing cached outputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
