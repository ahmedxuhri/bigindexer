# CLI Matrix and Model Tracking

This matrix defines how each CLI is used and how model identity is recorded.

## 1) OpenCode CLI

- Binary: `opencode`
- Model flag: `-m provider/model`
- Prompt mode: `opencode run "<prompt>"`
- MCP capability: configured via `opencode mcp ...`, but `opencode run` can complete without invoking MCP tools
- Recommended for quantitative A/B timing: **baseline yes, MCP only if invocation is proven**
- Important path rule: when using `--dir <repo_dir>`, OpenCode resolves MCP config from that project context; keep a valid `opencode.json` in `<repo_dir>` (use absolute artifact paths when artifacts live elsewhere).

Command template:

```bash
/usr/bin/time -f "%e" -o <time_file> \
  opencode run --dir <repo_dir> -m <provider/model> "<prompt>" \
  > <output_file>
```

Validity gate for MCP-mode runs:

1. Output must show MCP tool usage evidence (tool trace or MCP-only architectural fields tied to `fuse-graph.json`/`bgi-graph.json`).
2. If MCP is enabled but no MCP evidence appears, mark the run `invalid_no_mcp_invocation` in `runs.csv` notes and do not use it for latency claims.

## 2) Gemini CLI

- Binary: `gemini`
- Model flag: `-m <model>`
- Prompt mode: `gemini -p "<prompt>"`
- MCP capability: yes (`gemini mcp ...`)
- Recommended for quantitative A/B timing: **yes**

Command template:

```bash
/usr/bin/time -f "%e" -o <time_file> \
  gemini -m <model> --include-directories <repo_dir> -p "<prompt>" \
  > <output_file>
```

## 3) GitHub Copilot CLI

Two different tools may be called "copilot":

1. This coding-agent CLI session (the one you are using now)  
2. Local `copilot` binary from `gh-copilot` plugin (shell suggest/explain oriented)

For architecture Q/A validation, use **this coding-agent CLI** as `copilot-cli`.

- Model in this session: `gpt-5.3-codex`
- Timing: manual stopwatch or shell timing around CLI invocation path if available
- MCP capability: handled through this agent session and configured MCP tools

## Required run metadata (must record each run)

In `runs.csv`, always fill:

1. `cli`
2. `model`
3. `mcp_mode` (`baseline` or `mcp`)
4. `prompt_id`
5. `latency_sec`
6. `output_file`
7. `repo_slug`
