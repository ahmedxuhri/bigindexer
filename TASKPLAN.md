# BGI Task Plan

## North star

BGI is a **quality-first architecture cartography pipeline**:

- produce meaningful behavioral edges
- keep clusters bounded and interpretable
- emit architectural boundaries (`fuse-graph.json`) as first-class output

Speed work is important, but it must not degrade edge/cluster quality.

---

## Status summary

### Core architecture status: ON TRACK

The adopted Spectral-Fuse design from `bgi2.md` is implemented and active:

1. TOKEN-CENSUS (adaptive token frequency bands)
2. SPECTRAL-MASKS in Gate 2 (scoped matching)
3. FUSE-MAP in Gate 3 (hard cluster cap + fuse boundaries)
4. MASK-4-GATE-3 (import-proximity clustering signal)
5. WATER-CLOCK + `.scm` extraction path

Quality guardrails remain stable in large validation runs:

- max cluster around `1.113%` (well under 3% cap)
- fuse events can remain `0` in healthy runs

---

## Documentation mini-plan (2026-05-09) - COMPLETE

This mini-plan was added to improve external clarity and credibility for first-time readers.

1. **Outcome-first README rewrite** - complete  
   Added direct problem statement, user outcomes, and plain-English glossary.
2. **Concrete end-to-end example** - complete  
   Added runnable fixture example with observed output shape and counts.
3. **Evidence beyond speed** - complete  
   Added quality guard evidence from tests plus explicit statement of missing external precision/recall benchmark.
4. **Language support tiers clarity** - complete  
   Added explicit tiered support model (query-backed vs dedicated scanner vs generic fallback).
5. **BGI vs alternatives comparison** - complete  
   Added capability table vs LSP/SCIP-style and generic call-graph approaches.
6. **Limits and non-goals section** - complete  
   Added static-analysis scope limits and benchmarking caveats.

Deliverable: `README.md` now serves as onboarding doc for new readers instead of internal-only phase notes.

---

## Commercialization track (new)

Business and launch execution now has a dedicated plan in `masterplan.md`.
That plan covers:

1. MCP server build and public launch.
2. Big Indexer branding and domain rollout (`bigindexer.com`).
3. Azure credits usage for hosted pilots.
4. Monetization path from open source adoption to paid team features.

Engineering execution in this file remains focused on core quality/performance.

---

## Active phase: Phase 8 MCP implementation kickoff (2026-05-09) - IN PROGRESS

Completed in this kickoff:

1. Added MCP architecture context service (`bgi/bgi/mcp/context.py`) with tools for:
   - cluster lookup by file
   - boundary edge lookup
   - high-coupling seam extraction
   - impact-neighbor blast radius
   - architecture summary
   - symbol search (index DB when available, graph fallback otherwise)
2. Added MCP server runtime (`bgi/bgi/mcp/server.py`) and CLI command:
   - `bgi mcp --graph ... --fuse-graph ... --index-db ...`
3. Added setup documentation:
   - `docs/MCP_SETUP.md`
4. Added tests:
   - `tests/test_mcp_context.py`

Next for MCP track:

1. Validate MCP with real client sessions (OpenCode/Gemini/Copilot).
2. Add demo script + example transcript for public launch.
3. Add thin website/waitlist flow on `bigindexer.com`.
4. Use `validation/` workspace for managed A/B runs and public evidence collection.

Phase 8 Step 1 kickoff evidence (real client):

- OpenCode debug session against `fastapi` verified MCP server wiring and tool call:
  - MCP client created with 7 tools
  - `CallToolRequest` observed for `bigindexer_architecture_summary`
  - Artifacts:
    - `validation/runs/fastapi/opencode_mcp_phase8_debug.txt`
    - `validation/runs/fastapi/opencode_mcp_phase8_debug.time`
    - `validation/runs.csv` row: `fastapi-p01-mcp-phase8-kickoff-r1`

---

## Completed milestones

### Phase 1 (quality fixes) - COMPLETE

- FUSE-MAP cluster cap and fuse-edge boundary model
- TOKEN-CENSUS frequency-band classification
- SPECTRAL-MASKS scoped matching
- MASK-4-GATE-3 import-proximity pass

Outcome: mega-cluster behavior resolved; quality constraints now structural.

### Phase 5 (v2.1 Water-Clock) - COMPLETE

- single-pass `.scm` extraction
- multiprocessing in Gate 1
- incremental auto mode for monorepos
- language registration and extension support

### Phase 6 Option A (interactive index) - COMPLETE

- SQLite index schema and builder
- query planner
- FastAPI query API
- VS Code extension prototype

Outcome: interactive lookup/prefix/caller flows available as separate read-path capability.

### Phase 7 Option B (Gate 2 optimization) - COMPLETE

- Controlled baseline (go-only comparable): 3-run Gate 2 median `66.477s`
- Final stability pass (go-only comparable): 5-run Gate 2 median `37.244s`
  (min `34.980s`, max `53.948s`, stdev `7.844s`)
- Improvement: `43.97%` vs Phase 7 controlled baseline median
- Quality guards held across all stability runs:
  - max cluster `1.113%`
  - fuse events `0`
  - edge count stable
- Runtime decision locked:
  - spectral executor default = `thread`
  - env override = `BGI_GATE2_EXECUTOR=thread|process|auto`

---

## Phase 7 closeout record

### Phase 7 Option B (performance optimization) - COMPLETE

### Objective

Reduce **Gate 2** time on large comparable runs while keeping quality stable.

### Non-negotiables

1. max cluster stays under configured cap (default 3%)
2. fuse boundaries remain semantically consistent
3. no quality regression accepted for speed

### Scope clarification

Option B currently targets **Gate 2 latency**, not full-pipeline `<60s` on kubernetes.

### Current validated facts

- Comparable mode for historical continuity:
  - `go`-only scan mode
  - ~`162,917` units / `14,370` files
- Historical Gate 2 baseline in this mode: `138.869s`
- Recent comparable sample (`kubernetes-optionb-controlled-median-v21.json`):
  - Gate 1: `141.964s`
  - Gate 2: `67.261s` (about 51.57% lower than baseline)
  - Gate 3: `9.359s`
  - Total: `218.584s`
  - Quality: max cluster `1.113%`, fuse events `0`
- Phase 7 controlled baseline (`kubernetes-phase7-gate2-baseline-summary.json`):
  - 3-run Gate 2 median: `66.477s` (min `64.736s`, max `72.275s`)
- Phase 7 tuning sweeps:
  - Mask 3 probe-cap and fanout-cap sweeps regressed Gate 2 on this host; reverted.
  - Executor sweep showed process-pool overhead dominates at this scale.
- New Gate 2 runtime decision:
  - Default spectral executor is now `thread` (override with `BGI_GATE2_EXECUTOR=process|auto`).
  - 3-run Gate 2 median after change: `36.259s` (about **45.46%** better vs 66.477s baseline median).
  - Quality held: max cluster `1.113%`, fuse events `0`, edge count stable.
- 5-run stability confirmation (`kubernetes-phase7-gate2-stability-5run-summary.json`):
  - Gate 2 median `37.244s` (about **43.97%** better vs 66.477s baseline median).
  - Gate 2 range: `34.980s` to `53.948s` (shared-host variance observed in one run).
  - Quality held on all runs: max cluster `1.113%`, fuse events `0`, edge count stable.
- Dominant Gate 2 hotspot remains Mask 3 partner matching.

### What has been learned

- Adaptive Mask 3 caps provided major gains, but tuning is sensitive to host variance.
- Gate 3 union-find micro-optimizations were tested and rolled back when they regressed runtime.
- For very large scans, ProcessPool pickling/IPC overhead can outweigh parallel-pass gains.
- Gate 3 is currently stable; Gate 2 still centers on Mask 3 partner matching efficiency.

---

## Next execution sequence (Option B)

1. Keep thread executor default for large comparable runs; use env override only for targeted A/B.
2. Continue Mask 3 efficiency work only when it beats the `~37s` Gate 2 median on 3-run medians.
3. Keep only changes that preserve quality guardrails (cluster cap + fuse stability).
4. Roll back immediately on regression.

---

## Decision log

- Quality-first priority remains unchanged from convergence in `bgi2.md`.
- Option A (interactive search) is complete and retained as an additive capability.
- Option B is complete for this iteration; latest 5-run comparable median is `37.244s` with quality intact and thread-default executor locked.

---

## Practical validation commands

```bash
# full tests
python3 -m pytest tests/ -x -q

# focused gate3 tests
python3 -m pytest tests/test_gate3.py -q
```

---

## Reference artifacts

- Latest comparable sample:
  - `output/validation/kubernetes-optionb-controlled-median-v21.json`
- Phase 7 Gate 2 baselines:
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-baseline-summary.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-baseline-r1.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-baseline-r2.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-baseline-r3.json`
- Phase 7 tuning sweeps:
  - `validation/runs/kubernetes/kubernetes-phase7-mask3-probe-sweep.json`
  - `validation/runs/kubernetes/kubernetes-phase7-mask3-fanout-sweep.json`
  - `validation/runs/kubernetes/kubernetes-phase7-executor-sweep.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-thread-default-summary.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-thread-default-r1.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-thread-default-r2.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-thread-default-r3.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-stability-r1.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-stability-r2.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-stability-r3.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-stability-r4.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-stability-r5.json`
  - `validation/runs/kubernetes/kubernetes-phase7-gate2-stability-5run-summary.json`
- Prior Option B runs:
  - `output/validation/kubernetes-optionb-gate2-profile-go-comparable-v8.json`
  - `output/validation/kubernetes-optionb-gate2-profile-go-comparable-v10.json`
  - `output/validation/kubernetes-optionb-controlled-v20.json`
- Phase 8 MCP kickoff artifacts:
  - `validation/runs/fastapi/opencode_mcp_phase8_debug.txt`
  - `validation/runs/fastapi/opencode_mcp_phase8_debug.time`
  - `validation/runs.csv` (row: `fastapi-p01-mcp-phase8-kickoff-r1`)

---

## Notes for contributors

- Use `README.md` for onboarding and conceptual overview.
- Use this file for active execution state and decision boundaries.
- Keep benchmark claims explicitly tied to run mode (auto vs go-only comparable) to avoid false comparisons.
- Treat `problem.md` as historical context; do not report it as current state without cross-checking this file and latest artifacts.
