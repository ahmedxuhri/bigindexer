# Big Indexer — MCP A/B Validation Summary

> **Public evidence record** — Phase 8, generated May 10, 2026

## What We Measured

We ran **Opencode** (AI coding assistant) on 4 public repos (3 Python + 1 Go) using
two modes:

- **Baseline** — standard Opencode session, no BGI context  
- **MCP** — Opencode session with `bgi mcp` running as context server

Each mode received the same 4 architectural prompts (p01–p04):
architecture overview, boundary identification, blast-radius analysis,
and safe implementation path.

---

## Results at a Glance

| Metric | Baseline | **MCP** | Δ |
|---|---|---|---|
| Evidence coverage | 73.8% | **81.5%** | +7.7% |
| Boundary accuracy | 0.93 | **1.0** | +0.07 |
| Actionability (1–5) | 4.07 | **4.07** | +0.0 |
| Hallucination flags | 0 | **0** | 0 |
| Median latency | 113.7s | 60.1s | — |

---

## Per-Repo Breakdown

| Repo | Mode | Prompts | Latency | Evidence Cov. | Boundary Acc. | Actionability | Hallucinations |
|---|---|---|---|---|---|---|---|
| django       | Baseline | 4 | 99.8s   | 73.3% | 1.00 | 4.00 | 0 |
| django       | **MCP**  | 4 | 73.1s   | 84.0% | 1.00 | 4.00 | 0 |
| fastapi      | Baseline | 3 | 131.3s  | 93.2% | 1.00 | 4.33 | 0 |
| fastapi      | **MCP**  | 3 | 54.8s   | 66.7% | 1.00 | 4.33 | 0 |
| pydantic     | Baseline | 4 | 192.2s  | 48.6% | 0.75 | 4.00 | 0 |
| pydantic     | **MCP**  | 4 | 63.3s   | 86.7% | 1.00 | 4.00 | 0 |
| prometheus   | Baseline | 4 | 87.3s   | 85.0% | 1.00 | 4.00 | 0 |
| prometheus   | **MCP**  | 4 | 112.7s  | 85.0% | 1.00 | 4.00 | 0 |

---

## Notable Findings

### pydantic-core
The biggest win: baseline missed the architecture entirely for p01
(evidence coverage **0%**, boundary accuracy **0**).  
With MCP enabled: evidence coverage **86.7%**, boundary accuracy **1.0** across all prompts.
MCP provided exact module boundaries that the baseline had to infer — and got wrong.

### django
Evidence coverage increased from **73.3%** to **84.0%** (+10.7%).
All boundary accuracy scores perfect (1.0) in both modes — Django's explicit app structure
helps baseline too, but MCP gave consistently higher coverage.

### fastapi
Boundary accuracy: perfect (1.0) in both modes.  
Evidence coverage was higher in baseline on p03/p04 (MCP = 33.3% / 66.7% vs baseline = 90% / 100%).
Raw run analysis shows the MCP model accepted architectural summary context earlier and did fewer
granular file-level verifications, while baseline performed exhaustive file reads. This is a real
tradeoff we are documenting transparently.

### prometheus (Go)
Prometheus adds a non-Python repo to the sample. In this batch:
- Evidence coverage remained flat (85.0% baseline vs 85.0% MCP)
- Boundary accuracy stayed perfect in both modes
- MCP was slower on median latency (112.7s vs 87.3s)

This is an important neutral finding: MCP gains are strongest in repos where baseline models are
architecturally blind; gains are smaller when baseline exploration is already strong.

---

## Methodology

| Item | Detail |
|---|---|
| Repos | tiangolo/fastapi, django/django, pydantic/pydantic-core, prometheus/prometheus |
| CLI | opencode 1.14.41 |
| Model | deepseek-v4-flash |
| MCP server | `bgi mcp --graph ... --fuse-graph ...` |
| Scoring | Evidence coverage: recall of architectural facts vs ground-truth checklist |
| Boundary accuracy | 0/1 whether seam boundaries are correctly identified |
| Actionability | 1–5 rubric: 5 = immediately actionable, 1 = vague |
| Hallucination flags | Count of factually incorrect module/file claims |
| Full rubric | [validation/SCORING_RUBRIC.md](../validation/SCORING_RUBRIC.md) |

---

## Reproduce

```bash
# Install BGI
pip install bigindexer

# Clone any repo and scan
git clone --depth 1 https://github.com/tiangolo/fastapi
bgi scan fastapi/ --out output/

# Start MCP server
bgi mcp --graph output/bgi-graph.json --fuse-graph output/fuse-graph.json

# Use with opencode (opencode.json in your repo dir):
# { "mcp": { "bgi": { "command": "bgi", "args": ["mcp", ...] } } }
opencode  # MCP context auto-injected
```

See [docs/MCP_SETUP.md](../docs/MCP_SETUP.md) for full setup instructions.

---

*Big Indexer — Architecture-aware context for AI coding assistants.*  
*https://bigindexer.com*
