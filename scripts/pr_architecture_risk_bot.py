#!/usr/bin/env python3
"""PR Architecture Risk Bot for Big Indexer GitHub Action."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bgi.mcp.context import ArchitectureContextService

COMMENT_MARKER = "<!-- bgi-pr-architecture-risk-bot -->"


@dataclass
class FileRisk:
    file_path: str
    score: int
    risk_level: str
    cluster_count: int
    seam_count: int
    max_seam_edges: int
    impacted_count: int
    top_cluster: str


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def risk_level(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def _score_file(
    *,
    cluster_count: int,
    seam_count: int,
    max_seam_edges: int,
    impacted_count: int,
    found_cluster: bool,
) -> int:
    score = 0
    score += min(35, max_seam_edges * 4)
    score += min(35, impacted_count)
    score += min(15, seam_count * 3)
    if not found_cluster:
        score += 10
    score += min(5, cluster_count)
    return _clamp(score, 0, 100)


def _git_changed_files(repo_root: Path, base_sha: str, head_sha: str) -> list[str]:
    cmd = [
        "git",
        "--no-pager",
        "-C",
        str(repo_root),
        "diff",
        "--name-only",
        f"{base_sha}..{head_sha}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _load_event(event_path: str) -> dict[str, Any]:
    if not event_path:
        return {}
    p = Path(event_path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _extract_pr(event: dict[str, Any]) -> tuple[int | None, str, str]:
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        return None, "", ""
    number = pr.get("number") or event.get("number")
    base_sha = ((pr.get("base") or {}).get("sha") or "").strip()
    head_sha = ((pr.get("head") or {}).get("sha") or "").strip()
    return int(number) if number else None, base_sha, head_sha


def _normalize_paths(raw: str) -> list[str]:
    if not raw.strip():
        return []
    parts = raw.replace(",", "\n").splitlines()
    return [p.strip() for p in parts if p.strip()]


def compute_risk_report(
    *,
    service: Any,
    changed_files: list[str],
    max_files: int,
    max_seams: int,
    impact_depth: int,
    max_neighbors: int,
    task_prompt: str,
) -> dict[str, Any]:
    files = changed_files[: _clamp(max_files, 1, 500)]
    file_risks: list[FileRisk] = []
    skipped: list[str] = []

    for file_path in files:
        if file_path.endswith("/") or file_path.startswith(".git/"):
            skipped.append(file_path)
            continue
        cluster = service.cluster_of_file(file_path)
        seams = service.high_coupling_seams(file_path, limit=_clamp(max_seams, 1, 30))
        impact = service.impact_neighbors(
            file_path,
            depth=_clamp(impact_depth, 1, 4),
            limit=_clamp(max_neighbors, 1, 200),
        )

        clusters = cluster.get("clusters", []) if isinstance(cluster, dict) else []
        seam_rows = seams.get("seams", []) if isinstance(seams, dict) else []
        max_edges = max((int(s.get("edge_count", 0)) for s in seam_rows), default=0)
        impacted_count = int(impact.get("impacted_count", 0)) if isinstance(impact, dict) else 0
        cluster_count = int(cluster.get("cluster_count", 0)) if isinstance(cluster, dict) else 0
        found_cluster = bool(cluster.get("found")) if isinstance(cluster, dict) else False
        top_cluster = clusters[0].get("id", "") if clusters else ""
        score = _score_file(
            cluster_count=cluster_count,
            seam_count=len(seam_rows),
            max_seam_edges=max_edges,
            impacted_count=impacted_count,
            found_cluster=found_cluster,
        )
        file_risks.append(
            FileRisk(
                file_path=file_path,
                score=score,
                risk_level=risk_level(score),
                cluster_count=cluster_count,
                seam_count=int(seams.get("seam_count", len(seam_rows))) if isinstance(seams, dict) else len(seam_rows),
                max_seam_edges=max_edges,
                impacted_count=impacted_count,
                top_cluster=top_cluster,
            )
        )

    file_risks.sort(key=lambda x: (x.score, x.max_seam_edges, x.impacted_count), reverse=True)
    overall_score = max((f.score for f in file_risks), default=0)
    overall_level = risk_level(overall_score)

    twin = {}
    if task_prompt.strip():
        twin = service.twin_context(task_prompt, limit=3, include_source=False, min_score=0.25)

    return {
        "overall_score": overall_score,
        "overall_level": overall_level,
        "changed_files_count": len(changed_files),
        "analyzed_files_count": len(file_risks),
        "top_files": [f.__dict__ for f in file_risks[:10]],
        "skipped_files": skipped,
        "twin_context": twin,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = [
        COMMENT_MARKER,
        "## BGI PR Architecture Risk Report",
        "",
        f"- **Overall risk**: `{report.get('overall_level', 'LOW')}` ({report.get('overall_score', 0)}/100)",
        f"- **Changed files**: `{report.get('changed_files_count', 0)}`",
        f"- **Analyzed files**: `{report.get('analyzed_files_count', 0)}`",
        "",
    ]

    top_files = report.get("top_files", []) or []
    if top_files:
        lines.extend(
            [
                "### Top risk files",
                "",
                "| File | Risk | Impacted units | Max seam edges | Top cluster |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for row in top_files:
            lines.append(
                f"| `{row.get('file_path', '')}` | {row.get('score', 0)} ({row.get('risk_level', 'LOW')}) "
                f"| {row.get('impacted_count', 0)} | {row.get('max_seam_edges', 0)} | `{row.get('top_cluster', '')}` |"
            )
        lines.append("")
    else:
        lines.extend(["No analyzable changed files were detected.", ""])

    twin = report.get("twin_context") or {}
    if twin:
        lines.append("### Twin context (optional task prompt)")
        lines.append("")
        lines.append(f"- **Status**: `{twin.get('status', 'n/a')}`")
        candidates = twin.get("twin_candidates", []) or []
        if candidates:
            top = candidates[0]
            lines.append(
                f"- **Top twin**: `{top.get('unit', '')}` "
                f"(score `{top.get('score', 0)}`, overlap `{', '.join(top.get('overlap_tokens', []))}`)"
            )
        seam = twin.get("seam") or {}
        if seam:
            lines.append(f"- **Suggested seam anchor**: `{seam.get('suggestion', '')}`")
        lines.append("")

    lines.append("_Generated by Big Indexer PR Architecture Risk Bot._")
    return "\n".join(lines).strip() + "\n"


def _github_request(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "bigindexer-pr-risk-bot",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def upsert_pr_comment(*, token: str, repository: str, pr_number: int, body: str) -> str:
    if not token:
        return ""
    owner_repo = repository.strip()
    if "/" not in owner_repo or pr_number <= 0:
        return ""
    base = f"https://api.github.com/repos/{owner_repo}"
    comments_url = f"{base}/issues/{pr_number}/comments?per_page=100"

    try:
        comments = _github_request("GET", comments_url, token)
        existing_id = None
        for c in comments:
            if COMMENT_MARKER in (c.get("body") or ""):
                existing_id = c.get("id")
                break
        if existing_id:
            updated = _github_request("PATCH", f"{base}/issues/comments/{existing_id}", token, {"body": body})
            return str(updated.get("html_url") or "")
        created = _github_request("POST", f"{base}/issues/{pr_number}/comments", token, {"body": body})
        return str(created.get("html_url") or "")
    except urllib.error.HTTPError as exc:
        print(f"[BGI] Warning: failed to post PR comment ({exc.code}): {exc.reason}", file=sys.stderr)
    except urllib.error.URLError as exc:
        print(f"[BGI] Warning: failed to post PR comment: {exc.reason}", file=sys.stderr)
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PR architecture risk report from BGI artifacts.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--graph-path", required=True)
    parser.add_argument("--fuse-graph-path", required=True)
    parser.add_argument("--index-db-path", default="")
    parser.add_argument("--changed-files", default="")
    parser.add_argument("--task-prompt", default="")
    parser.add_argument("--max-files", type=int, default=40)
    parser.add_argument("--max-seams", type=int, default=8)
    parser.add_argument("--impact-depth", type=int, default=2)
    parser.add_argument("--max-neighbors", type=int, default=40)
    parser.add_argument("--post-comment", default="true")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    event = _load_event(os.environ.get("GITHUB_EVENT_PATH", ""))
    pr_number, base_sha, head_sha = _extract_pr(event)
    manual_files = _normalize_paths(args.changed_files)
    changed_files: list[str] = manual_files

    if not changed_files and base_sha and head_sha:
        try:
            changed_files = _git_changed_files(repo_root, base_sha, head_sha)
        except RuntimeError as exc:
            print(f"[BGI] Warning: unable to diff PR range {base_sha}..{head_sha}: {exc}", file=sys.stderr)

    service = ArchitectureContextService(
        graph_path=args.graph_path,
        fuse_graph_path=args.fuse_graph_path,
        index_db_path=args.index_db_path or None,
    )
    report = compute_risk_report(
        service=service,
        changed_files=changed_files,
        max_files=args.max_files,
        max_seams=args.max_seams,
        impact_depth=args.impact_depth,
        max_neighbors=args.max_neighbors,
        task_prompt=args.task_prompt,
    )
    markdown = render_markdown(report)

    output_md = Path(args.output_markdown)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown, encoding="utf-8")

    comment_url = ""
    if _parse_bool(args.post_comment) and pr_number:
        comment_url = upsert_pr_comment(
            token=os.environ.get("GITHUB_TOKEN", ""),
            repository=os.environ.get("GITHUB_REPOSITORY", ""),
            pr_number=pr_number,
            body=markdown,
        )

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "risk_score": report.get("overall_score", 0),
        "risk_level": report.get("overall_level", "LOW"),
        "changed_files_count": report.get("changed_files_count", 0),
        "report_path": str(output_md),
        "comment_url": comment_url,
    }
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
