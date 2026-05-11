# Scoring Rubric

Score each prompt response in both modes (`baseline`, `mcp`).

## Metrics

| metric | scale | rule |
|---|---|---|
| latency_sec | numeric | from time file |
| evidence_coverage_pct | 0-100 | VERIFIED claims / total major claims |
| evidence_tag_relaxed_pct | 0-100 | primary evidence + capped credit for unlabeled repo-anchor lines |
| boundary_accuracy | 0/1 | 1 if no obvious wrong-boundary guidance |
| actionability | 1-5 | 5 means immediately executable |
| hallucination_flags | integer | contradicted claims count |
| rework_needed | 0/1 | 1 if answer likely causes rework |

## Per-prompt net score (optional)

Use for quick ranking:

```text
net_score = (boundary_accuracy * 2) + actionability + (evidence_coverage_pct / 25) - hallucination_flags - (rework_needed * 2)
```

## Repo-level verdict

MCP wins for a repo if:

1. latency improves, and
2. either boundary_accuracy is higher OR hallucination_flags are lower.
