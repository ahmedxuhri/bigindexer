# Big Indexer MCP Validation Plan (A/B on 10 Public Repos)

This file defines a reproducible validation protocol for **manual + publishable** evidence.

Goal: prove whether MCP context materially improves engineering outcomes vs non-MCP usage.

---

## 1) Success criteria (decision rule)

MCP is considered valuable if, across 10 repos:

1. **Median response latency** improves by >= 30%.
2. **Boundary mistakes** decrease (fewer wrong cross-component suggestions).
3. **Evidence quality** improves (more claims backed by artifacts).
4. **Actionability** improves (answers lead to clearer next code action).
5. At least **7/10 repos** show net positive score.

---

## 2) Standard A/B protocol (use for every repo)

## A) Prepare workspace

```bash
mkdir -p /tmp/bgi-ab-repos
mkdir -p output/validation/mcp-ab
```

## B) Build artifacts for repo under test

```bash
bgi scan <REPO_PATH> --lang <LANG> \
  --out output/validation/mcp-ab/<SLUG>/bgi-graph.json \
  --fuse-graph output/validation/mcp-ab/<SLUG>/fuse-graph.json
```

## C) Run baseline (MCP OFF)

Temporarily disable project MCP config:

```bash
cd /root/mad/sessions/bgi
mv opencode.json opencode.off.json
```

Run prompts with `opencode run`, capture output + time:

```bash
/usr/bin/time -f "%e" -o output/validation/mcp-ab/<SLUG>/baseline_p01.time \
  opencode run -m <MODEL> "<PROMPT>" \
  > output/validation/mcp-ab/<SLUG>/baseline_p01.txt
```

## D) Run MCP mode (MCP ON)

Restore MCP config:

```bash
cd /root/mad/sessions/bgi
mv opencode.off.json opencode.json
```

Point MCP command to this repo’s artifacts (edit `opencode.json` command args to use):

- `output/validation/mcp-ab/<SLUG>/bgi-graph.json`
- `output/validation/mcp-ab/<SLUG>/fuse-graph.json`

Then run the same prompts:

```bash
/usr/bin/time -f "%e" -o output/validation/mcp-ab/<SLUG>/mcp_p01.time \
  opencode run -m <MODEL> "<PROMPT>" \
  > output/validation/mcp-ab/<SLUG>/mcp_p01.txt
```

## E) Keep prompt quality strict

For both baseline and MCP runs, prepend this instruction:

> Use evidence mode: for each major claim, label VERIFIED/HYPOTHESIS/UNKNOWN and cite exact artifact/file.

(Reference: `docs/MCP_PROMPT_PROTOCOL.md`)

---

## 3) Scoring rubric (per prompt, both modes)

Score each response with this table:

| Metric | Scale | How to score |
|---|---|---|
| latency_sec | numeric | value from `.time` file |
| evidence_coverage | 0-100% | VERIFIED claims / total major claims |
| boundary_accuracy | 0/1 | 1 if no obvious wrong-boundary guidance |
| actionability | 1-5 | 5 = directly executable guidance |
| hallucination_flags | integer | count factual errors contradicted by artifacts |
| rework_needed | 0/1 | 1 if answer would likely cause correction/rework |

Per-repo result = average of prompt scores (MCP vs baseline).

---

## 4) Record format (for public evidence)

Create:

- `output/validation/mcp-ab/<SLUG>/baseline_pXX.txt`
- `output/validation/mcp-ab/<SLUG>/mcp_pXX.txt`
- `output/validation/mcp-ab/<SLUG>/scores.csv`
- `output/validation/mcp-ab/<SLUG>/summary.md`

CSV schema (`scores.csv`):

```csv
repo,mode,prompt_id,latency_sec,evidence_coverage,boundary_accuracy,actionability,hallucination_flags,rework_needed,notes
fastapi,baseline,p01,131.0,55,0,3,2,1,"stale claim about tests"
fastapi,mcp,p01,36.0,78,1,4,1,0,"better structure and faster"
```

Top-level aggregate:

- `output/validation/mcp-ab/aggregate.csv`
- `output/validation/mcp-ab/public-summary.md`

In `public-summary.md`, publish:

1. median latency baseline vs MCP
2. boundary error rate baseline vs MCP
3. hallucination rate baseline vs MCP
4. 3 concrete before/after transcript snippets

---

## 5) 10 public repos and test setup

## 1. fastapi/fastapi

- URL: `https://github.com/fastapi/fastapi`
- Language: `python`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/fastapi/fastapi /tmp/bgi-ab-repos/fastapi
  ```
- Scan:
  ```bash
  bgi scan /tmp/bgi-ab-repos/fastapi --lang python --out output/validation/mcp-ab/fastapi/bgi-graph.json --fuse-graph output/validation/mcp-ab/fastapi/fuse-graph.json
  ```
- Prompt pack:
  1. “What is this project about, strong points, weak points? Use evidence mode.”
  2. “What boundaries are touched if we edit `fastapi/routing.py`?”
  3. “Blast radius for changes in `fastapi/dependencies/utils.py`.”
  4. “Give a safe refactor plan for routing/dependency interaction.”

## 2. django/django

- URL: `https://github.com/django/django`
- Language: `python`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/django/django /tmp/bgi-ab-repos/django
  ```
- Scan: same pattern with slug `django`
- Prompt pack:
  1. project summary + strengths/weaknesses (evidence mode)
  2. boundary impact for `django/db/models/query.py`
  3. blast radius for `django/core/handlers/base.py`
  4. safest place to add query logging without cross-layer leakage

## 3. pydantic/pydantic

- URL: `https://github.com/pydantic/pydantic`
- Language: `python`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/pydantic/pydantic /tmp/bgi-ab-repos/pydantic
  ```
- Scan: slug `pydantic`
- Prompt pack:
  1. architectural summary with risks
  2. boundary edges around `pydantic/main.py`
  3. impact neighbors for `pydantic/fields.py`
  4. safe path to add validation feature with minimal blast radius

## 4. microsoft/vscode

- URL: `https://github.com/microsoft/vscode`
- Language: `typescript`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/microsoft/vscode /tmp/bgi-ab-repos/vscode
  ```
- Scan: slug `vscode` (if full scan is too heavy, start with `src/vs`)
- Prompt pack:
  1. project architectural summary (current vs historical)
  2. boundaries around `src/vs/workbench/workbench.desktop.main.ts`
  3. blast radius for `src/vs/platform/files/common/files.ts`
  4. safest location for new workspace-file telemetry hook

## 5. vercel/next.js

- URL: `https://github.com/vercel/next.js`
- Language: `typescript`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/vercel/next.js /tmp/bgi-ab-repos/nextjs
  ```
- Scan: slug `nextjs`
- Prompt pack:
  1. architectural summary + weak points
  2. boundaries around `packages/next/src/server/next-server.ts`
  3. blast radius for `packages/next/src/build/index.ts`
  4. safe plan to add server-side request metric

## 6. angular/angular

- URL: `https://github.com/angular/angular`
- Language: `typescript`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/angular/angular /tmp/bgi-ab-repos/angular
  ```
- Scan: slug `angular`
- Prompt pack:
  1. architectural summary + strengths/risks
  2. boundary analysis for `packages/router/src/router.ts`
  3. blast radius for `packages/core/src/render3`
  4. safest insertion point for route-level debug instrumentation

## 7. kubernetes/kubernetes

- URL: `https://github.com/kubernetes/kubernetes`
- Language: `go`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/kubernetes/kubernetes /tmp/bgi-ab-repos/kubernetes
  ```
- Scan: slug `kubernetes` (can scope to `pkg/` for first pass)
- Prompt pack:
  1. architectural summary with evidence-only claims
  2. boundaries around `pkg/kubelet/kubelet.go`
  3. blast radius for `staging/src/k8s.io/apiserver`
  4. safe place to add auth-related request logging

## 8. prometheus/prometheus

- URL: `https://github.com/prometheus/prometheus`
- Language: `go`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/prometheus/prometheus /tmp/bgi-ab-repos/prometheus
  ```
- Scan: slug `prometheus`
- Prompt pack:
  1. project summary + risk points
  2. boundary analysis for `scrape/manager.go`
  3. blast radius for `cmd/prometheus/main.go`
  4. safe implementation path for additional scrape diagnostics

## 9. rust-lang/rust-analyzer

- URL: `https://github.com/rust-lang/rust-analyzer`
- Language: `rust`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/rust-lang/rust-analyzer /tmp/bgi-ab-repos/rust-analyzer
  ```
- Scan: slug `rust-analyzer`
- Prompt pack:
  1. architectural summary + current weaknesses
  2. boundaries around `crates/ide/src/lib.rs`
  3. blast radius for `crates/hir/src/lib.rs`
  4. safest place to add new IDE diagnostic rule

## 10. tokio-rs/tokio

- URL: `https://github.com/tokio-rs/tokio`
- Language: `rust`
- Clone:
  ```bash
  git clone --depth 1 https://github.com/tokio-rs/tokio /tmp/bgi-ab-repos/tokio
  ```
- Scan: slug `tokio`
- Prompt pack:
  1. architectural summary + strong/weak points
  2. boundaries around `tokio/src/runtime/mod.rs`
  3. blast radius for `tokio/src/task/spawn.rs`
  4. safe refactor plan for runtime task instrumentation

---

## 6) Public evidence publishing checklist

Before publishing the results:

1. Include raw prompt/response artifacts (baseline + MCP).
2. Include timing files and scoring CSVs.
3. Include one-paragraph repo-by-repo verdict.
4. Clearly mark any claim as VERIFIED/HYPOTHESIS/UNKNOWN.
5. Publish both wins and failures (credibility > hype).

---

## 7) Suggested headline for public report

> “We ran Big Indexer MCP A/B on 10 public repos: median response time improved, boundary mistakes dropped, and architecture answers became more evidence-backed.”
