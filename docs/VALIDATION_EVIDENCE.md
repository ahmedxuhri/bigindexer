# Big Indexer — Validation Evidence

> **Public evidence record** — 80 scored runs across 5 repos (Python + Go + TypeScript).
> Every raw output is committed. Every claim is traceable to a run artifact.

## Does Big Indexer actually help AI coding assistants?

We ran Opencode on 5 production open-source repos in three modes and measured four things:
**evidence coverage** (recall of architectural facts), **boundary accuracy** (correct seam identification),
**actionability** (1–5, does the AI give implementable guidance), and **hallucinations** (incorrect claims).

---

## Three-stage core + GPT-4o replication

Each stage adds a layer. The numbers show what each layer contributed.

| Metric | No BGI (baseline) | BGI MCP | BGI MCP + TWIN | TWIN delta |
|---|---|---|---|---|
| Actionability (1–5) | 4.00 | 4.00 | **4.75** | **+0.75** |
| Evidence coverage | 78.7% | 84.9% | 79.9% / **96%†** | — |
| Boundary accuracy | 0.95 | **1.00** | **1.00** | held |
| Hallucination flags | 0 | 0 | 0 | 0 |
| Median latency | 133.8s | 66.2s | 68.5s | — |

† 79.9% is all-prompt mean for the 20-run TWIN refresh. **96%** is the p04 (safe implementation path) slice across 5 repos — the most actionability-relevant prompt.

**What each stage fixed:**
- **BGI MCP** fixed boundary accuracy (0.95 → 1.00) and halved latency (133.8s → 66.2s)
- **BGI TWIN** fixed actionability (4.00 → 4.75) by surfacing behavioral twins + seam + rubric

### Independent model replication (GPT-4o on Azure OpenAI)

We re-ran the full TWIN prompt pack on a different model (`azure/gpt-4o`) across all 5 repos (20 runs).

| Metric | BGI-TWIN (deepseek-v4-flash) | BGI-TWIN replication (GPT-4o) |
|---|---|---|
| Actionability (1–5) | 4.75 | **4.85** |
| Evidence coverage | 79.9% (96% p04 slice) | **47.9%** (49.3% p04 slice) |
| Evidence (tag-relaxed, second score)\* | **94.8%** (100% p04) | **59.5%** (62.7% p04) |
| Boundary accuracy | 1.00 | **1.00** |
| Hallucination flags | 0 | **0** |
| Median latency | 68.5s | **41.6s** |

Interpretation: actionability, boundary accuracy, and zero-hallucination behavior replicated on GPT-4o, with faster latency.

\* Tag-relaxed evidence score formula:  
`min(100, evidence_coverage_pct + min(25, (unlabeled_repo_anchor_lines / checklist_items) * 100 * 0.15))`  
Repo-anchor lines are non-log lines mentioning concrete repo files/modules (e.g. `*.py`, `*.go`, `*.ts`) without explicit `VERIFIED/HYPOTHESIS/UNKNOWN` tags.

#### Evidence-gap interpretation (explicit)

The evidence-coverage gap is real and should be read directly:
- deepseek TWIN refresh (20 runs): **278** explicit `VERIFIED/HYPOTHESIS/UNKNOWN` labels (**13.9/run**)
- GPT-4o TWIN replication (20 runs): **139** labels (**6.95/run**)

On the p04 implementation slice, label density was **10.8/run** (deepseek) vs **5.2/run** (GPT-4o), while actionability remained high (4.8 vs 5.0), boundary remained 1.0 in both, and hallucinations remained 0 in both.

This means the current evidence metric is sensitive to explicit tagging/citation style. GPT-4o often gives usable direction with fewer explicit evidence labels, so this rubric can score it lower on evidence coverage even when other quality signals remain strong. We keep this unnormalized and publish raw outputs for independent re-scoring.

Example from the same prompt (fastapi p03, blast radius of `solve_dependencies`):

```text
deepseek (validation/runs/fastapi/opencode_mcp_p03_twin_refresh_r2.txt)
| Definition spans lines 598–735 ... | VERIFIED |
| get_request_handler ...             | VERIFIED |
| get_websocket_app ...               | VERIFIED |
VERIFIED: Only 3 call sites exist in the codebase.

GPT-4o (validation/runs/fastapi/opencode_mcp_p03_twin_refresh_gpt4o_r1.txt)
1. VERIFIED: Changes to solve_dependencies will directly impact tests.
2. HYPOTHESIS: Other clusters may have dependent implications.
```

---

## What is BGI-TWIN?

Three deterministic MCP tools that convert architecture context into implementation-ready guidance.

| Tool | What it does |
|---|---|
| `task_fingerprint(task)` | NL task → COV token set (deterministic, no LLM) |
| `behavioral_twins(task)` | Top-3 code units ranked by Jaccard overlap with task fingerprint |
| `twin_context(task)` | Combined: task COV + top twins + seam suggestion + 5-point rubric + confidence gate |

BGI-TWIN is a context compiler. It does not generate code, does not call an LLM, and does not speculate. Every output is derived directly from the indexed graph and fuse artifacts.

---

## Per-repo breakdown

5 repos, 4 slices, 80 scored runs.

| Repo | Mode | Runs | Median Latency | Evidence Cov. | Boundary | Actionability |
|---|---|---|---|---|---|---|
| django/django | Baseline | 4 | 99.8s | 73.3% | 1.00 | 4.0 |
| django/django | BGI MCP | 4 | 73.1s | **84.0%** | 1.00 | 4.0 |
| django/django | **BGI TWIN** | 4 | 60.9s | 75.3% | 1.00 | **5.0** |
| django/django | **BGI TWIN (GPT-4o)** | 4 | 48.3s | 47.0% | 1.00 | **5.0** |
| tiangolo/fastapi | Baseline | 3 | 131.3s | 93.2% | 1.00 | 4.3 |
| tiangolo/fastapi | BGI MCP | 3 | **54.8s** | 66.7% | 1.00 | 4.3 |
| tiangolo/fastapi | **BGI TWIN** | 4 | 79.5s | 82.0% | 1.00 | **5.0** |
| tiangolo/fastapi | **BGI TWIN (GPT-4o)** | 4 | 31.6s | 45.4% | 1.00 | **5.0** |
| pydantic/pydantic-core | Baseline | 4 | 192.2s | 48.6% | 0.75 | 4.0 |
| pydantic/pydantic-core | BGI MCP | 4 | 63.3s | **86.7%** | **1.00** | 4.0 |
| pydantic/pydantic-core | **BGI TWIN** | 4 | **47.5s** | 71.3% | 1.00 | **4.7** |
| pydantic/pydantic-core | **BGI TWIN (GPT-4o)** | 4 | 40.4s | 43.8% | 1.00 | **4.5** |
| prometheus/prometheus | Baseline | 6 | **89.9s** | 90.0% | 1.00 | 4.0 |
| prometheus/prometheus | BGI MCP | 6 | 119.9s | 90.0% | 1.00 | 4.0 |
| prometheus/prometheus | **BGI TWIN** | 4 | 70.0s | 80.8% | 1.00 | **5.0** |
| prometheus/prometheus | **BGI TWIN (GPT-4o)** | 4 | 53.4s | 59.6% | 1.00 | **4.8** |
| vercel/next.js | Baseline | 3 | 291.8s | 89.2% | 1.00 | 3.7 |
| vercel/next.js | BGI MCP | 3 | **66.4s** | **91.7%** | 1.00 | 3.7 |
| vercel/next.js | **BGI TWIN** | 4 | 88.9s | 63.4% | 1.00 | **4.0** |
| vercel/next.js | **BGI TWIN (GPT-4o)** | 4 | 33.6s | 44.0% | 1.00 | **5.0** |

BGI TWIN rows are post-shipment refresh runs (p01–p04, `CallToolRequest` evidence confirmed in every run).

---

## Notable findings

### pydantic-core — the clearest result in the dataset

Baseline p01: evidence **0%**, boundary **0**. The model described a pure-Python architecture. The repo is Python + Rust with a `pyo3` bridge that the baseline model never found.

BGI MCP p01: evidence **80%**, boundary **1.0**. BGI injected the exact `pyo3` boundary and the model identified it correctly on the first attempt.

BGI-TWIN p04: evidence **100%**, actionability **5/5**. The safe-implementation prompt produced a copy-paste-ready patch path with specific file and function references.

### fastapi — honest reporting of a mixed result

Evidence coverage dropped on two fastapi MCP runs (p03: 33.3%, p04: 66.7% vs baseline 90%, 100%). This is real:

The baseline model, with no architecture context, read every source file individually and built a detailed verified-claim table. The MCP model received blast-radius context (1,614 impacted units) and treated that as the full picture — it made fewer granular verifications.

What this reveals: MCP architecture context trades file-reading breadth for boundary accuracy. On well-structured repos with good baseline exploration, the evidence-coverage gain is smaller. Boundary accuracy was perfect (1.0) in all fastapi modes. BGI-TWIN's refresh recovered evidence to 82% mean with 5/5 actionability because behavioral twins anchor the model to specific files rather than summaries.

Raw outputs: [validation/runs/fastapi/](../validation/runs/fastapi/)

### Prometheus (Go) — cross-language neutral result

Evidence is flat at 90.0% in baseline and MCP modes. MCP is slower (119.9s vs 89.9s) on this Go codebase. BGI-TWIN improved actionability to 5/5 and reduced latency to 70s.

Key insight: MCP accuracy gains are largest when baseline models are architecturally blind. BGI-TWIN's actionability gains hold regardless.

### next.js (TypeScript) — large monorepo signal

Baseline latency 291.8s — BGI reduces it to 66–89s in all modes. Boundary accuracy perfect across all three modes. Actionability improved from 3.7 to 4.0 with BGI-TWIN.

### Hallucination rate: 0 across 80 scored runs

No factually incorrect module or file claim in any baseline, MCP, or TWIN run.

---

## Limitations

We publish limitations before readers find them. A reader who discovers a flaw themselves trusts evidence less than one who was told.

**Self-reported scoring.** Checklists were written by us, scored by us. The checklists were defined before scoring by reading actual source code. The full rubric is at [validation/SCORING_RUBRIC.md](../validation/SCORING_RUBRIC.md). Every raw output is public at [validation/runs/](../validation/runs/). Re-score independently and open an issue if you disagree.

**5 repos is not a large sample.** Python + Go + TypeScript is broader than Python-only, but still limited. The pydantic-core finding stands on its own. The first independent-model replication (GPT-4o) is now complete, but we still need additional repos and external replications.

**BGI-TWIN refresh is MCP-only.** No updated baseline was run alongside the refresh. We have no reason to believe the baseline changed, but this is a real experimental design limitation.

**Evidence coverage is style-sensitive across models.** The rubric rewards explicit claim-level `VERIFIED/HYPOTHESIS/UNKNOWN` labeling with citations. Models that provide fewer explicit labels can under-score on evidence coverage despite strong actionability and boundary outcomes.

**One invalid MCP run.** One next.js p04 original A/B run had no `CallToolRequest` evidence and is marked explicitly unscored in `runs.csv`. All 20 TWIN refresh runs have invocation evidence.

**We still need external replication.** We now have one independent-model replication (GPT-4o), but we still need external teams to run and publish the protocol on their own repos.

---

## Methodology

| Item | Detail |
|---|---|
| Repos | tiangolo/fastapi, django/django, pydantic/pydantic-core, prometheus/prometheus, vercel/next.js |
| CLI | opencode 1.14.41 |
| Model | deepseek-v4-flash + azure/gpt-4o |
| MCP server | `bgi mcp --graph ... --fuse-graph ...` |
| TWIN invocation | `twin_context` explicitly required in prompt; `CallToolRequest` confirmed in every TWIN run |
| Evidence coverage | Recall of architectural facts vs ground-truth checklist (sensitive to explicit label/citation style) |
| Evidence (tag-relaxed, second score) | Primary evidence score + capped credit for unlabeled repo-anchor lines (no reruns required) |
| Boundary accuracy | 0/1 — correct seam identification |
| Actionability | 1–5 rubric: 5 = immediately actionable (copy-paste), 1 = vague |
| Hallucination flags | Count of factually incorrect module/file claims |
| Total scored runs | 80 (20 baseline + 20 MCP + 20 TWIN deepseek + 20 TWIN GPT-4o replication) |
| Full rubric | [validation/SCORING_RUBRIC.md](../validation/SCORING_RUBRIC.md) |
| All run artifacts | [validation/runs/](../validation/runs/) |
| Run log | [validation/runs.csv](../validation/runs.csv) |

---

## Reproduce

```bash
# Install
pip install bigindexer

# Clone any repo and build the index
git clone --depth 1 https://github.com/tiangolo/fastapi
bgi scan fastapi/ --out output/

# Start MCP server (includes BGI-TWIN tools)
bgi mcp --graph output/bgi-graph.json --fuse-graph output/fuse-graph.json

# Run with opencode (opencode.json in the repo dir):
# { "mcp": { "bgi": { "command": "bgi", "args": ["mcp", ...] } } }
opencode  # AI receives architecture summary + behavioral twins + seam + rubric
```

Full setup: [docs/MCP_SETUP.md](../docs/MCP_SETUP.md)

---

*Big Indexer — Architecture-aware context for AI coding assistants.*  
*https://bigindexer.com*
