# Public Validation Summary (Template)

## Scope

- Repos tested: <N>
- CLIs tested: <list>
- Models tested: <list>
- Prompt IDs used: <list>

## Key results

1. Median latency baseline vs MCP: <value> vs <value>
2. Boundary error rate baseline vs MCP: <value> vs <value>
3. Hallucination flags baseline vs MCP: <value> vs <value>
4. Actionability average baseline vs MCP: <value> vs <value>

## Repo-by-repo outcomes

| repo | cli | model | baseline_latency | mcp_latency | baseline_hallucinations | mcp_hallucinations | verdict |
|---|---|---|---:|---:|---:|---:|---|
| <repo> | <cli> | <model> | <x> | <y> | <a> | <b> | MCP better / neutral / worse |

## Representative transcript excerpts

### Example 1 (speed + quality)
- baseline: <summary>
- mcp: <summary>
- why it matters: <note>

### Example 2 (boundary safety)
- baseline: <summary>
- mcp: <summary>
- why it matters: <note>

## Honest limitations

1. <limitation>
2. <limitation>

## Reproducibility

- Raw outputs: `validation/runs/`
- Run manifest: `validation/runs.csv`
- Prompt pack: `validation/prompts.md`
