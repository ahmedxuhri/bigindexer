# Big Indexer Validation Workspace

This directory is the operational workspace for MCP A/B validation runs.

## Objective

Measure whether MCP context improves answer quality and speed across public repos.

## Roles

1. **You (manual executor):**
   - run commands
   - copy/paste prompts
   - save outputs
   - record observed issues
2. **Me (manager/analyst):**
   - define protocol
   - score outputs
   - detect hallucinations/stale claims
   - generate public evidence summary

## Directory structure

```text
validation/
  README.md
  CLI_MATRIX.md
  repos.csv
  prompts.md
  scoring.md
  runs.csv
  summary-template.md
  runs/
    .gitkeep
  evidence/
    .gitkeep
```

## Standard run flow

1. Pick one repo from `repos.csv`.
2. Build BGI artifacts for that repo.
3. Run the same prompt pack in:
   - baseline mode (MCP OFF)
   - MCP mode (MCP ON)
4. Verify MCP invocation evidence in MCP mode output (tool trace or MCP-only architectural data).
5. Save outputs into `validation/runs/<repo_slug>/`.
6. Record metadata in `validation/runs.csv`.
7. Score with rubric in `validation/scoring.md`.

## Run validity gates

Before comparing baseline vs MCP latency/quality, confirm:

1. MCP mode output actually used MCP tools.
2. Both runs used the same model.
3. Prompt text is identical except MCP mode.

If gate 1 fails, mark notes as `invalid_no_mcp_invocation` and rerun.

## Naming convention

- Output text: `validation/runs/<repo_slug>/<cli>_<mode>_<prompt_id>.txt`
- Time file: `validation/runs/<repo_slug>/<cli>_<mode>_<prompt_id>.time`

Where:

- `cli`: `opencode`, `gemini`, `copilot-cli`
- `mode`: `baseline`, `mcp`
- `prompt_id`: `p01`, `p02`, ...

## First execution target

Start with `fastapi` from `repos.csv` using prompts `p01..p04`.
