# Prompt Pack for A/B Validation

Use the same prompt text for baseline and MCP modes.

## Global instruction prefix (prepend to every prompt)

```text
Use evidence mode.
For each major claim, mark VERIFIED / HYPOTHESIS / UNKNOWN and cite exact sources.
Separate current state from historical context.
```

## p01 — project assessment

```text
Do not modify anything.
Tell me what this project is about, strong points, and weak points.
```

## p02 — boundary analysis

```text
Do not modify anything.
What architectural boundaries are touched if we edit <TARGET_FILE_OR_DIR>?
```

## p03 — blast radius

```text
Do not modify anything.
What is the likely blast radius if we change <TARGET_SYMBOL_OR_FILE>?
```

## p04 — safe implementation path

```text
Do not modify anything.
I need to add <FEATURE>. Give the safest implementation path with minimal cross-boundary impact.
```

## p05 — contradiction check

```text
Do not modify anything.
List 5 risk claims about this project, and for each show direct evidence path.
If evidence is missing, mark UNKNOWN.
```

## p06 — architecture summary

```text
Do not modify anything.
Give a concise architecture summary for this repo with top 3 clusters and top seams.
```
