"""Weekly combined adoption rollup.

Reads the optional server-side telemetry JSONL log + the GitHub traffic
snapshot and produces one consolidated markdown summary in
output/rollups/weekly.md.

Telemetry log path defaults to website/data/telemetry.jsonl. Override with
--telemetry-log. If the file is missing or empty, the section is rendered
as 'no telemetry data yet' rather than failing.

GitHub data is read from the file written by github_traffic.py. Run that
first if you want fresh numbers, or pass --skip-github to just summarize
telemetry.

Usage:
    python3 scripts/rollups/github_traffic.py
    python3 scripts/rollups/weekly.py
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _load_telemetry(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    events: list[dict] = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _summarize_telemetry(events: list[dict]) -> str:
    if not events:
        return (
            "## Telemetry (opt-in MCP startup pings)\n\n"
            "_No telemetry events recorded yet. Either no users have enabled "
            "`BGI_TELEMETRY=1`, or the server hasn't received any requests yet._\n"
        )
    total = len(events)
    distinct_repos = {e.get("repo_id") for e in events if e.get("repo_id")}
    by_kind = Counter(e.get("event_kind", "unknown") for e in events)
    by_os = Counter(e.get("os", "unknown") for e in events)
    by_bucket = Counter(e.get("repo_size_bucket") or "?" for e in events)
    by_version = Counter(e.get("version") or "?" for e in events)
    by_tool = Counter(
        e.get("tool_name") for e in events
        if e.get("event_kind") == "tool_call" and e.get("tool_name")
    )

    lines = [
        "## Telemetry (opt-in MCP startup pings)",
        "",
        f"- Events: **{total}**",
        f"- Distinct repos: **{len(distinct_repos)}**",
        "",
        "### By event kind",
        "",
    ]
    for kind, count in by_kind.most_common():
        lines.append(f"- `{kind}`: {count}")
    lines += ["", "### By OS", ""]
    for osn, count in by_os.most_common():
        lines.append(f"- `{osn}`: {count}")
    lines += ["", "### By repo size bucket", ""]
    for bucket, count in by_bucket.most_common():
        lines.append(f"- `{bucket}`: {count}")
    lines += ["", "### By BGI version", ""]
    for version, count in by_version.most_common():
        lines.append(f"- `{version}`: {count}")
    if by_tool:
        lines += ["", "### Top MCP tools called", ""]
        for tool, count in by_tool.most_common(10):
            lines.append(f"- `{tool}`: {count}")
    lines.append("")
    return "\n".join(lines)


def _read_github(path: Path) -> str:
    if not path.exists():
        return (
            "## GitHub traffic\n\n"
            f"_No snapshot at `{path}`. Run "
            "`python3 scripts/rollups/github_traffic.py` first._\n"
        )
    body = path.read_text(encoding="utf-8")
    # Strip the file's own H1 since this rollup has its own
    lines = body.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        # also drop any blank line right after the title
        while lines and not lines[0].strip():
            lines = lines[1:]
    # Reformat any H2s as H3s under our H2 header
    out = ["## GitHub traffic", ""]
    for line in lines:
        if line.startswith("## "):
            out.append("### " + line[3:])
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--telemetry-log",
        default="website/data/telemetry.jsonl",
        help="Path to JSONL telemetry log written by the website server.",
    )
    ap.add_argument(
        "--github-snapshot",
        default="output/rollups/github_traffic.md",
        help="Path to GitHub traffic snapshot from github_traffic.py.",
    )
    ap.add_argument(
        "--out",
        default="output/rollups/weekly.md",
        help="Output markdown path.",
    )
    args = ap.parse_args()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    telemetry_events = _load_telemetry(Path(args.telemetry_log))
    telemetry_block = _summarize_telemetry(telemetry_events)
    github_block = _read_github(Path(args.github_snapshot))

    md = (
        "# BGI Adoption — weekly rollup\n"
        "\n"
        f"_Snapshot generated {now}._\n"
        "\n"
        "Internal artifact. Aggregated from public GitHub traffic API and "
        "(if enabled) opt-in MCP startup telemetry. No user identity, no "
        "repo identity, no source code is captured.\n"
        "\n"
        + telemetry_block
        + "\n"
        + github_block
        + "\n"
        "---\n"
        "\n"
        "_Generated by `scripts/rollups/weekly.py`. To refresh GitHub numbers "
        "run `scripts/rollups/github_traffic.py` first._\n"
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"  → wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
