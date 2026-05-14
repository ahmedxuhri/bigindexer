# BGI - Big Indexer

[![ahmedxuhri/bigindexer MCP server](https://glama.ai/mcp/servers/ahmedxuhri/bigindexer/badges/score.svg)](https://glama.ai/mcp/servers/ahmedxuhri/bigindexer)
[![PyPI version](https://img.shields.io/pypi/v/bigindexer.svg)](https://pypi.org/project/bigindexer/)
[![License](https://img.shields.io/github/license/ahmedxuhri/bigindexer.svg)](https://github.com/ahmedxuhri/bigindexer/blob/master/LICENSE)
[![Tests](https://img.shields.io/badge/Tests-Passing-brightgreen)](https://bigindexer.com/validation)
[![MCP Registry](https://img.shields.io/badge/MCP-Registry-blue)](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.ahmedxuhri/bigindexer)

<!-- mcp-name: io.github.ahmedxuhri/bigindexer -->

BGI is a static architecture analysis tool for large codebases.
It groups code units by **behavioral role** and emits explicit architectural boundaries.
Project domain: `bigindexer.com`

## Use via MCP Registry

Big Indexer is published in the MCP Registry as `io.github.ahmedxuhri/bigindexer`.

```bash
pip install bigindexer==0.1.3
bgi mcp --graph bgi-graph.json --fuse-graph fuse-graph.json
```

Validation: https://bigindexer.com/validation

## PR Architecture Risk Bot

The Marketplace Action now lives in a dedicated repo:

https://github.com/ahmedxuhri/bigindexer-pr-risk-bot

## What problem this solves

Most architecture graphs fail at scale in two ways:

- too many noisy edges
- giant clusters that collapse unrelated components together

BGI is built to keep both under control, so the output remains usable on large repos.

## What you can do with it

1. **"Where should this boundary be before we refactor?"**  
   BGI groups units by behavioral role (COV tokens + DRS clustering) so likely component boundaries are visible.
2. **"Which subsystem coupling is risky?"**  
   BGI surfaces high-coupling seams and fuse-boundary signals between clusters so integration risk is easier to spot.
3. **"How do we plug architecture data into automation?"**  
   BGI emits machine-readable artifacts (`bgi-graph.json`, `fuse-graph.json`) plus optional human context (`bigindexer.md`).
4. **"How do we make AI changes less random?"**  
   MCP tools (`task_fingerprint`, `behavioral_twins`, `twin_context`) ground prompts in in-repo behavior patterns.

---

## 30-second demo

Run BGI on the included fixture repo:

```bash
git clone https://github.com/ahmedxuhri/bigindexer
cd bigindexer
pip install -e .
bgi scan tests/fixtures --lang python --out /tmp/bgi-example.json
head -50 /tmp/bgi-example.json
```

Observed result on this repository:

- units: `12`
- edges: `14`
- clusters: `2`
- max cluster in sample: `6` units

One produced edge looks like:

```json
{
  "source": "auth_module.py::AuthService::__init__",
  "target": "auth_module.py::AuthService::__del__",
  "key": "COV.INIT",
  "lock": "COV.TEARDOWN",
  "type": "HARD"
}
```

Why this matters: instead of raw syntax references only, you get behavioral relationships plus cluster structure that can drive architecture decisions.

---

## Plain-English glossary

| BGI term | Plain meaning |
|---|---|
| **COV token** | A behavior label for a unit (for example: `FETCH`, `PERSIST`, `AUTHENTICATE`) |
| **Key-Lock edge** | A behavioral connection between two units with complementary roles |
| **DRS cluster** | A group of units likely belonging to one architectural component |
| **Fuse edge / fuse event** | A refused merge because cluster growth hit the cap; treated as boundary signal |
| **Spectral masks** | Scope rules that limit where matching is allowed (global, directory, file) |

---

## Architecture in one view

```text
Source files
   ->
Gate 1: fingerprint unit behavior (COV tokens)
   ->
Gate 2: create behavioral edges with scoped matching
   ->
Gate 3: cluster with hard size cap + boundary emission
   ->
Artifacts: bgi-graph.json, fuse-graph.json, bigindexer.md, optional routes/graphml/html
```

Core approach:

1. **TOKEN-CENSUS** - classify token frequency per repo.
2. **SPECTRAL-MASKS** - restrict match scope by token frequency.
3. **FUSE-MAP** - cap cluster growth and record refused merges.
4. **MASK-4-GATE-3** - use import proximity as clustering signal.
5. **WATER-CLOCK + `.scm`** - single-pass query extraction path in Gate 1.

---

## Why BGI is different from common alternatives

| Capability | LSP / SCIP index | Call-graph + generic community detection | BGI |
|---|---|---|---|
| Fast symbol lookup | Strong | Medium | Available (Phase 6 index) |
| Behavioral token model | No | Usually no | **Yes** |
| Hard-bounded clustering | No | Usually no | **Yes** |
| First-class boundary artifact | No | Usually no | **Yes (`fuse-graph.json`)** |
| Scope-constrained edge generation | Limited | Rare | **Yes (spectral masks)** |

---

## Evidence (current, verifiable)

### Large-repo scale evidence

Comparable kubernetes sample (`go` comparable mode, 162,917 units):

- Gate 1: `141.964s`
- Gate 2: `67.261s` (historical comparable baseline: `138.869s`)
- Gate 3: `9.359s`
- Total: `218.584s`
- Max cluster: `1.113%`
- Fuse events: `0`

Artifact: `output/validation/kubernetes-optionb-controlled-median-v21.json`

### Quality guard evidence (beyond raw speed)

- Gate 2 scope safety tests block invalid cross-scope merges (see `tests/test_gate2.py`).
- Gate 3 tests verify no legacy namespace over-merge without import evidence (see `tests/test_gate3.py`).
- Current full suite status: `python3 -m pytest tests/ -x -q` (project baseline target remains passing).

### Evidence summary

- Current published validation set: **100 scored runs** across 5 repos and 3 models.
- Full 20-run post-shipment benchmark refresh for BGI-TWIN context (`task → COV → top-3 twins + seam + rubric`) is complete: actionability **4.75/5** (p04 slice: **4.8/5**), boundary **1.0**, hallucinations **0**.
- Independent-model replication is now complete on **azure/gpt-4o** (20 runs) and **gemini/auto** (20 runs): GPT-4o actionability **4.85/5**, Gemini actionability **4.25/5**, both with zero hallucinations; Gemini boundary **0.95** reflects one genuine `django/p02` miss.
- Still missing: labeled precision/recall benchmark on an external corpus and head-to-head quantitative benchmark vs external tools on the same labeled dataset.

---

## Language support tiers (explicit)

BGI does not treat all languages equally; support is tiered:

1. **Query-backed (`.scm`)**: `python`, `typescript`
2. **Tree-sitter scanner + rule path**: `javascript`, `java`, `go`, `rust`, `ruby`, `csharp`, `php`, `kotlin`, `c`, `scala`, `lua`, `elixir`
3. **Generic regex fallback by extension**: `swift`, `r`, `dart`, `bash`, `nim`, `zig`, `haskell`, `ocaml`, `fsharp`, `clojure`, `erlang`, `matlab`, `vb`, `crystal`, `cobol`, `groovy`

Use this as a reliability signal: query-backed and dedicated scanner tiers are stronger than generic fallback.

---

## Limitations and non-goals

1. BGI is **static analysis**; it does not ingest runtime traces.
2. Cross-file semantic resolution is heuristic and language-dependent.
3. Cluster-size health is measured; full external precision/recall is not yet published.
4. Shared-host benchmarking introduces variance; decisions should use controlled medians.

---

## Install

```bash
pip install -e .
```

## Quickstart commands

```bash
# scan
bgi scan /path/to/repo --lang auto --out bgi-graph.json

# optional outputs
bgi scan /path/to/repo --lang auto \
  --fuse-graph fuse-graph.json \
  --routes routes.json \
  --graphml graph.graphml \
  --html

# incremental
bgi scan /path/to/repo --lang auto --incremental --cache .bgi-cache.json

# diff
bgi diff /path/before /path/after --lang auto --out diff.json

# run MCP server over generated artifacts
bgi mcp --graph bgi-graph.json --fuse-graph fuse-graph.json
```

Example MCP usage pattern (from your client prompt):

```text
Use MCP tool twin_context for:
"Add endpoint that validates input and persists data."
Return top twin candidate, seam suggestion, and rubric checklist.
```

---

## Documentation map

- `MEMORANDUM.md` - design contracts and invariants
- `docs/LANGUAGE_SUPPORT.md` - language implementation details
- `docs/CONTRIBUTING_LANGUAGES.md` - language contribution guide
- `docs/INDEX_SCHEMA.md` - interactive index schema
- `docs/QUERY_PLANNER.md` - query planner scoring
- `docs/MCP_SETUP.md` - MCP server setup and usage
- `docs/GITHUB_ACTION_PR_RISK_BOT.md` - PR Architecture Risk Bot usage
- `https://bigindexer.com/validation` - public validation evidence
- `docs/MCP_QUICKSTART_DEMO.md` - 5-minute demo walkthrough
- `docs/MCP_EXAMPLE_TRANSCRIPTS.md` - real-world MCP tool invocation examples
- `docs/MCP_REAL_TRANSCRIPT.md` - unedited transcript from FastAPI analysis
- `scripts/mcp-demo.sh` - automated demo script for multiple CLIs and repositories

## License and Copyright

- License: Apache License 2.0 (`LICENSE`)
- Contributor terms: Developer Certificate of Origin (`DCO`) enforced on pull requests
