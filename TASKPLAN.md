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

---

## Active phase

### Phase 7 Option B (performance optimization) - IN PROGRESS

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
- Dominant Gate 2 hotspot remains Mask 3 partner matching.

### What has been learned

- Adaptive Mask 3 caps provided major gains, but tuning is sensitive to host variance.
- Gate 3 union-find micro-optimizations were tested and rolled back when they regressed runtime.
- Gate 3 is currently stable; Gate 2 Mask 3 is still the main optimization frontier.

---

## Next execution sequence (Option B)

1. Run controlled median baselines (3-5 comparable runs) before any new tuning pass.
2. Sweep Mask 3 fanout/probe limits one variable at a time.
3. Keep only changes that improve median Gate 2 while preserving quality.
4. Roll back immediately on regression.

---

## Decision log

- Quality-first priority remains unchanged from convergence in `bgi2.md`.
- Option A (interactive search) is complete and retained as an additive capability.
- Option B remains active until Gate 2 target behavior is satisfactory under controlled medians.

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
- Prior Option B runs:
  - `output/validation/kubernetes-optionb-gate2-profile-go-comparable-v8.json`
  - `output/validation/kubernetes-optionb-gate2-profile-go-comparable-v10.json`
  - `output/validation/kubernetes-optionb-controlled-v20.json`

---

## Notes for contributors

- Use `README.md` for onboarding and conceptual overview.
- Use this file for active execution state and decision boundaries.
- Keep benchmark claims explicitly tied to run mode (auto vs go-only comparable) to avoid false comparisons.
