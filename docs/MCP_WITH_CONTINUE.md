# Big Indexer × Continue — 5-minute setup

> The fastest path from `pip install bigindexer` to your AI coding
> assistant having real architecture context, with no per-token-pricing
> service in the middle.

This guide walks through wiring [Big Indexer](https://github.com/ahmedxuhri/bigindexer) into [Continue](https://continue.dev) — a popular open-source coding assistant that runs locally and uses your own API keys.

The same MCP server works with Claude Desktop, Cursor, Cline, Aider, and any other MCP-capable client. Continue is the example here because it's free, BYO-API-key, and ships a clean MCP integration.

## What you get

- Continue continues to do what it does — chat, code edit, autocomplete.
- BGI runs as a local MCP server alongside it.
- When Continue needs architectural context (cluster a file belongs to, blast radius of a change, behavioral twins for a task), it asks BGI's MCP server.
- Result: less file-reading by the AI, fewer wrong-boundary suggestions, lower input-token cost on big repos.

## Prerequisites

- Python 3.10+
- VS Code with the [Continue extension](https://marketplace.visualstudio.com/items?itemName=Continue.continue) installed
- An API key for whichever model you use with Continue (Anthropic, OpenAI, DeepSeek, local Ollama, etc.)

## Step 1 — Install Big Indexer

```bash
pip install bigindexer
```

Verify:

```bash
bgi --help
```

## Step 2 — Scan your repo

```bash
cd /path/to/your/repo
bgi scan . --lang auto --out bgi-graph.json --fuse-graph fuse-graph.json
```

This produces three files:

- `bgi-graph.json` — the behavioral graph (edges, units, clusters)
- `fuse-graph.json` — architectural boundary signal
- `bigindexer.md` — human-readable architecture summary (great for sharing in PRs)

Scan time scales with repo size:

| Repo size | Roughly |
|---|---|
| <500 files | a few seconds |
| 500–5,000 files | 10–60 seconds |
| 5,000–50,000 files | 1–5 minutes |
| 50,000+ files | use `--incremental` and a cache file |

## Step 3 — Add BGI to Continue's MCP config

Open Continue's config file (`~/.continue/config.json` on macOS/Linux, `%USERPROFILE%\.continue\config.json` on Windows). Add a `mcpServers` block:

```jsonc
{
  // ... your existing config (models, providers, etc.) ...
  "experimental": {
    "modelContextProtocolServers": [
      {
        "name": "bgi",
        "transport": {
          "type": "stdio",
          "command": "bgi",
          "args": [
            "mcp",
            "--graph", "/absolute/path/to/your/repo/bgi-graph.json",
            "--fuse-graph", "/absolute/path/to/your/repo/fuse-graph.json"
          ]
        }
      }
    ]
  }
}
```

Replace `/absolute/path/to/your/repo/` with the actual paths to the files you scanned in step 2.

> Continue's MCP support sits under `experimental` at the time of writing. If your Continue version uses a different key, check [Continue's MCP docs](https://docs.continue.dev/customization/mcp).

## Step 4 — Reload Continue

Restart VS Code, or run "Continue: Reload Window" from the command palette.

In Continue's chat, type:

```
What architectural cluster does my-file.py belong to?
```

Continue should now invoke BGI's MCP `cluster_of_file` tool and return a real architectural answer instead of guessing from filenames.

## Step 5 — Use the right BGI tools for the right tasks

BGI exposes 12 MCP tools. The three most useful in practice:

| Tool | When to use |
|---|---|
| `task_fingerprint(task)` | Convert a natural-language task into BGI's behavioral token vocabulary |
| `behavioral_twins(task)` | Find the top-3 in-repo code units doing similar work |
| `twin_context(task)` | Combined: task fingerprint + twins + seam + rubric — the full implementation brief |

Try this prompt in Continue:

```
Use the BGI twin_context MCP tool for this task:
"Add a caching layer to the auth middleware that respects per-user TTLs."

Return the top twin candidate, the seam suggestion, and the rubric checklist.
```

The model receives concrete file references, behavioral analogues from your codebase, and a 5-point safety rubric — all derived from your scan, not invented.

## Refresh the index after big changes

BGI scans are static. After a big refactor or merge:

```bash
bgi scan . --lang auto --incremental --cache .bgi-cache.json \
  --out bgi-graph.json --fuse-graph fuse-graph.json
```

`--incremental` only re-scans files that changed since the cache, so refreshes are seconds rather than minutes.

## What BGI is not

- **Not an AI coding assistant.** Continue/Cursor/Claude do that part.
- **Not a symbol indexer.** LSP does that, better.
- **Not a vector embedding service.** Different mechanism, different tradeoffs.

BGI is the architecture-aware context layer underneath whichever AI coding assistant you've already picked. It runs locally, costs you nothing per token, and stays out of your inference loop.

## Validation

Across 100 scored runs on 5 production open-source repos (django, fastapi, prometheus, pydantic-core, next.js) with three different models (deepseek-v4-flash, GPT-4o, Gemini auto), MCP context cut median agent latency from 133.8s to 66.2s and dropped boundary mistakes to zero. Full evidence with raw run artifacts: [bigindexer.com/validation](https://bigindexer.com/validation).

## Troubleshooting

**"command not found: bgi"** — the install didn't put `bgi` on your PATH. Try `python -m bgi.cli` instead, or check `pip show bigindexer` to confirm install location.

**Continue isn't invoking BGI tools** — check the Continue logs (View → Output → Continue) for MCP startup errors. Common causes: absolute paths required for `--graph`/`--fuse-graph`; the JSON config must be valid (trailing comma errors silently break MCP loading).

**Scan is slow on a large repo** — first scan is full; subsequent scans should use `--incremental`. For monorepos, scan only the directory you care about (`bgi scan packages/web/ ...`).

**MCP server crashes on startup with "Missing required graph file"** — run `bgi scan` first; the MCP server doesn't auto-scan.

## Other clients

The same `bgi mcp` command works with:

- **Claude Desktop** — add to `claude_desktop_config.json`'s `mcpServers`
- **Cursor** — add to `~/.cursor/mcp.json`
- **Cline (VS Code)** — add to `cline_mcp_settings.json`
- **Aider** — invoke via Aider's tool extension hooks (see `docs/MCP_REAL_TRANSCRIPT.md` for an unedited example)

Detailed config snippets in [`docs/MCP_SETUP.md`](MCP_SETUP.md).

## Telemetry

Off by default. If you want to help us see which BGI versions are actually getting used, set `BGI_TELEMETRY=1` in your environment. Full schema and what we never collect: [`docs/TELEMETRY.md`](TELEMETRY.md).

---

Issues, questions, ideas: [github.com/ahmedxuhri/bigindexer/issues](https://github.com/ahmedxuhri/bigindexer/issues).
