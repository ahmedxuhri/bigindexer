# Big Indexer MCP Prompt Protocol (High-Trust Mode)

Use this protocol when you want fewer hallucinations and more verifiable answers.

## Copy-paste system instruction

```text
Use Big Indexer MCP tools as primary evidence.
For every major claim:
1) include a source citation (tool + artifact/file),
2) label claim status as VERIFIED or HYPOTHESIS,
3) if no evidence is found, say UNKNOWN.

Do not treat historical documents as current status unless explicitly confirmed.
Current status source priority:
1) README.md current status section
2) latest validation evidence under `docs/VALIDATION_EVIDENCE.md`
3) latest benchmark artifacts under output/validation/
4) historical docs only as background
```

## Copy-paste user prompt template

```text
Answer this question in evidence mode:
<QUESTION>

Constraints:
- Use Big Indexer MCP tools first.
- Return a table with columns: claim, status (VERIFIED/HYPOTHESIS/UNKNOWN), evidence.
- Evidence must include exact file/artifact paths or tool output names.
- Separate "current state" from "historical context".
```

## Recommended output format

| claim | status | evidence |
|---|---|---|
| <statement> | VERIFIED | `README.md`, `docs/VALIDATION_EVIDENCE.md`, `output/validation/...json`, `cluster_of_file(...)` |
| <statement> | HYPOTHESIS | inferred from partial signals |
| <statement> | UNKNOWN | no direct artifact evidence |

## Quick anti-drift checklist

Before accepting an answer, verify:

1. Did it explicitly mark historical vs current?
2. Did each major claim have evidence?
3. Did it avoid stating assumptions as facts?
4. Did it include any stale claims contradicted by latest artifacts?
