# Big Indexer — Validation Scoring Rubric

> Full methodology for the A/B runs published at [bigindexer.com/validation](https://bigindexer.com/validation).
> Raw output files are in `validation/runs/<repo>/`. Anyone can re-score independently.

---

## Overview

Each run consists of one AI session (Opencode) answering one architectural prompt about a real public repository.
Runs come in pairs: **baseline** (no BGI context) and **MCP** (BGI context server active), same prompt, same model, same repo.

Runs are scored by reading the raw output file and checking it against a ground-truth checklist.
The checklist is defined per prompt (see below). The checklist was written **before** scoring by reading the actual source code of each repo.

---

## Metrics

### 1. Evidence Coverage (0–100%)

**Definition:** What percentage of the ground-truth checklist items does the response correctly address?

**Formula:** `(verified_items / total_checklist_items) × 100`

**Rules:**
- An item is "verified" if the response makes a correct, specific claim about it (not vague or wrong).
- Partial credit: if the response partially addresses an item (e.g., names the right file but wrong line range), it counts as 0 — no partial scores.
- Items the response marks as "UNKNOWN" or "HYPOTHESIS" without verification count as 0.
- False claims (factually wrong) count as 0 and trigger a hallucination flag.

### 1b. Evidence (Tag-Relaxed, second score) (0–100%)

**Definition:** Secondary evidence score that adds conservative credit for grounded repo anchors even when explicit labels are missing.

**Formula:**
`min(100, evidence_coverage_pct + min(25, (unlabeled_repo_anchor_lines / checklist_items) × 100 × 0.15))`

Where:
- `unlabeled_repo_anchor_lines` = non-log response lines that include concrete repo anchors (`*.py`, `*.go`, `*.ts`, etc.) and do **not** contain `VERIFIED/HYPOTHESIS/UNKNOWN`.
- `checklist_items` = prompt+repo checklist size in this rubric.

**Purpose:** Reduce sensitivity to label style differences across models while keeping the strict primary evidence score as the canonical metric.

### 2. Boundary Accuracy (0 or 1)

**Definition:** Did the response correctly identify the architectural seam(s) relevant to the prompt?

**Scoring:**
- `1` — correct seam identified (right files, right coupling direction, right cluster membership)
- `0` — seam missed, wrong files identified, or no seam analysis attempted

This is a binary per-run score, not averaged across checklist items.

### 3. Actionability (1–5 rubric)

**Definition:** How immediately usable is the response for an engineer making a real code change?

| Score | Meaning |
|---|---|
| 5 | Response gives a specific, copy-paste-ready implementation or exact file + line guidance with reasoning |
| 4 | Response gives clear direction with specific files and patterns, minor gaps |
| 3 | Response is directionally correct but vague — engineer must still investigate before acting |
| 2 | Response gives general principles without repo-specific grounding |
| 1 | Response is generic, unhelpful, or wrong |

### 4. Hallucination Flags (count)

**Definition:** Count of factually incorrect claims about the repo's actual code.

Examples of hallucinations:
- Naming a function or class that doesn't exist in the repo
- Claiming a file is at a path that doesn't exist
- Asserting a call relationship that doesn't exist in the source

Hallucinations are counted per run. Zero is expected; any non-zero value is a serious quality signal.

### 5. Rework Needed (yes/no)

**Definition:** Would an engineer following this response need to do significant additional investigation before the guidance is usable?

- `yes` — guidance is missing, wrong, or too vague to act on
- `no` — guidance is sufficient to proceed

---

## Prompt Definitions and Ground-Truth Checklists

### p01 — Architecture Overview

**Prompt:** "Give me an architecture overview of this codebase. What are the main modules, their responsibilities, and how do they communicate?"

**Checklist (repo-specific; items defined before scoring):**

#### fastapi
1. Identifies `fastapi/routing.py` as the core request dispatch layer
2. Identifies `fastapi/dependencies/` as the dependency injection system
3. Identifies `fastapi/openapi/` as schema generation
4. Identifies `fastapi/applications.py` as the top-level `FastAPI` class
5. Mentions ASGI interface as the communication layer
6. Identifies `fastapi/responses.py` and `fastapi/datastructures.py` as supporting layers
7. Notes test suite structure under `tests/`

#### django
1. Identifies MTV (Model-Template-View) pattern by name or clearly describes it
2. Identifies ORM in `django/db/` as the data layer
3. Identifies URL routing in `django/urls/`
4. Identifies middleware pipeline in `django/middleware/`
5. Identifies admin app in `django/contrib/admin/`
6. Identifies forms in `django/forms/`
7. Notes signal system in `django/dispatch/`

#### pydantic-core
1. Identifies Rust core (`src/`) as the performance-critical layer
2. Identifies Python bindings (`python/pydantic_core/`) as the public API
3. Identifies `pydantic_core_init.pyi` as the type stub interface
4. Notes `SchemaValidator` and `SchemaSerializer` as the primary entry points
5. Identifies `benches/` as the benchmark layer
6. Notes PyO3 as the Rust-Python binding mechanism

#### prometheus/prometheus
1. Identifies `cmd/prometheus/main.go` as the entry point / orchestrator
2. Identifies `tsdb/` as the local time-series storage engine
3. Identifies `scrape/` as the metrics collection layer
4. Identifies `rules/` as the alerting/recording rules engine
5. Identifies `web/` as the HTTP API and UI layer
6. Notes `model/labels/` as the shared label data model used across layers
7. Notes `discovery/` as the service discovery subsystem

#### vercel/next.js
1. Identifies monorepo layout with `packages/` as the primary source root
2. Identifies `packages/next/src/` as the core framework implementation
3. Identifies `packages/next/src/server/` as the server/runtime layer
4. Identifies `packages/next/src/build/` as the build pipeline layer
5. Identifies `packages/next/src/client/` as the browser/runtime layer
6. Identifies Rust/native layer in `crates/` and/or `turbopack/`
7. Explains at least one concrete communication path (e.g. router↔render IPC, build manifests↔runtime, or client↔server request flow)

### p02 — Boundary Analysis

**Prompt:** "Identify the main architectural boundaries in this codebase. Where are the integration seams? What are the strongest coupling points between modules?"

**Checklist:**

#### fastapi
1. Identifies routing↔dependencies seam as primary coupling
2. Identifies applications.py as the integration hub (wires all layers)
3. Identifies ASGI as the external boundary
4. Notes test suite as a consumer of all boundaries
5. Identifies openapi↔routing as a generation dependency

#### django
1. Identifies ORM↔views as primary seam
2. Identifies URL resolver as the routing boundary
3. Identifies middleware as the request/response pipeline seam
4. Identifies admin↔ORM coupling as the tightest internal seam
5. Notes contrib apps as boundary-crossing consumers of core

#### pydantic-core
1. Identifies Python↔Rust boundary via PyO3 as THE primary seam
2. Identifies `SchemaValidator` as the entry point across that boundary
3. Notes `.pyi` stubs as the formal contract for the boundary
4. Identifies `benches/` as consuming the public Python boundary
5. Notes that error types cross the boundary (Rust errors surfaced to Python)

#### prometheus/prometheus
1. Identifies scrape↔tsdb as the primary write path seam
2. Identifies tsdb↔web/api as the primary read path seam
3. Identifies rules engine as a consumer of both scrape and query layers
4. Notes the Appender interface as the storage boundary contract
5. Identifies remote read/write as the external integration seam

#### vercel/next.js
1. Identifies process/runtime boundary between router-server and render server (or equivalent server boundary)
2. Identifies JavaScript↔Rust boundary (SWC/NAPI or turbopack native integration)
3. Identifies build↔runtime seam (manifest/chunk/config artifacts crossing phases)
4. Identifies bundler seam/coupling (Webpack/Turbopack/Rspack integration point)
5. Identifies RSC/app-render↔client boundary (or equivalent server-render/client-render seam)
6. Identifies incremental cache / server lib seam as an integration boundary
7. Identifies internal header / request metadata seam (security/protocol boundary)
8. Names at least one concrete high-coupling hotspot file/module

### p03 — Blast Radius

**Prompt:** "If I change [target function/module], what is the blast radius? What other parts of the codebase would be affected?"

**Targets per repo:**
- fastapi: `solve_dependencies` in `fastapi/dependencies/utils.py`
- django: `get_response` in `django/core/handlers/base.py`
- pydantic-core: `SchemaValidator.__init__` in the Rust core
- prometheus: `fanout.Querier` in `storage/fanout.go`
- next.js: `BaseServer` in `packages/next/src/server/base-server.ts`

**Checklist (fastapi — `solve_dependencies`):**
1. Identifies HTTP request path (routing.py) as a direct call site
2. Identifies WebSocket path (routing.py) as a direct call site
3. Identifies recursive call (utils.py itself) as a call site
4. Notes SolvedDependency return type as a contract (breaking change risk)
5. Notes zero direct unit tests (only integration tests catch regressions)
6. Identifies all routes as affected (100% of HTTP traffic)

**Checklist (django — `get_response`):**
1. Identifies middleware chain as the call site
2. Notes every HTTP request goes through this function
3. Identifies exception handler wrapping
4. Notes test runner as a consumer
5. Identifies `process_request` / `process_response` hooks as dependents

**Checklist (pydantic-core — `SchemaValidator.__init__`):**
1. Identifies all Python validation calls as depending on this
2. Notes PyO3 boundary as the risk point
3. Identifies `benches/` as affected
4. Notes type stubs as a contract surface
5. Identifies downstream pydantic (v2) as a consumer

**Checklist (prometheus — `fanout.Querier`):**
1. Identifies all query paths (HTTP API, rules engine) as dependents
2. Notes the Querier interface contract (breaking change propagates to all storage backends)
3. Identifies remote read as an affected path
4. Notes federation as a consumer of query results
5. Identifies chunk iterators / series set protocol as the downstream contract

**Checklist (next.js — `BaseServer`):**
1. Identifies direct dependents (`next-server.ts`, `next-dev-server.ts`) as primary blast radius
2. Identifies type consumers of `RequestLifecycleOpts` / related server types
3. Identifies coupling to at least one major subsystem (build, app-render, client components, incremental cache)
4. Notes signature/API changes as high-risk across subclasses/consumers
5. Provides at least one concrete validation path (tests/typecheck/build checks)

### p04 — Safe Implementation Path

**Prompt:** "What is the safest way to add [feature] to this codebase, given the existing architecture?"

**Features per repo:**
- fastapi: Add a request timing middleware
- django: Add a per-request audit log
- pydantic-core: Add a custom string validator
- prometheus: Add a new HTTP API endpoint for label cardinality statistics
- next.js: Add a per-request trace-id response header

**Checklist (fastapi — timing middleware):**
1. Recommends `@app.middleware("http")` or ASGI middleware pattern (not modifying routing internals)
2. Correctly identifies `build_middleware_stack` / user_middleware chain
3. Notes the streaming caveat (time-to-first-byte vs full transfer)
4. Provides copy-paste-ready code or specific file reference
5. Does NOT recommend modifying `routing.py` (that crosses the seam)

**Checklist (django — audit log):**
1. Recommends middleware or signal-based approach
2. Identifies the correct middleware insertion point
3. Notes ORM dependency for log storage
4. Does NOT recommend modifying `get_response` directly
5. Provides specific implementation guidance

**Checklist (pydantic-core — custom validator):**
1. Recommends `@validator` / `__get_validators__` protocol (Python side, not Rust)
2. Correctly identifies that custom validators live in Python, not Rust core
3. Notes the schema compilation step
4. Does NOT recommend modifying Rust code
5. Provides concrete implementation pattern

**Checklist (prometheus — label cardinality endpoint):**
1. Recommends adding to `web/api/v1/api.go` (not creating a new server)
2. Correctly identifies `tsdb.Head` / `tsdb.DB` as the data source
3. Notes the existing `/api/v1/labels` endpoint as the pattern to follow
4. Identifies the `series` query path for cardinality data
5. Does NOT recommend modifying the storage layer itself

**Checklist (next.js — trace-id header):**
1. Recommends outer server handler insertion point (`router-server.ts`/equivalent) for widest path coverage
2. Recommends server-generated request ID (not trusting client header input)
3. Mentions `INTERNAL_HEADERS` hardening / anti-forgery boundary for request-id header
4. Mentions request metadata propagation for downstream usage
5. Notes implementation safety guard(s) (e.g. `headersSent`, optional OTel trace alignment, or equivalent)

---

## What the Scores Mean — FastAPI p03/p04 Regression Explained

FastAPI p03 and p04 showed lower MCP scores than baseline. Reading the raw outputs reveals the exact cause:

**What happened:**
- Baseline (no MCP): model had zero architecture context → read every file manually → produced a 10-item verified claim table with explicit `VERIFIED` / source citations
- MCP: model received blast-radius data (1,614 impacted units, top seam confidence 0.75) → accepted that as the architecture picture → made 3–4 verified claims and left 2 as `HYPOTHESIS` / `UNKNOWN` without file verification

**Root cause:** MCP architectural confidence reduced the model's manual verification effort. The model trusted the MCP blast-radius output and produced a higher-level response instead of a granular claim-by-claim verification.

**Is this a bug?** Partially. The MCP responses were architecturally more accurate (correct seam identification, correct blast radius magnitude), but scored lower because the rubric rewards granular verified claims, and the MCP model verified fewer of them explicitly.

**What this means for the product:** MCP helps most on repos where baseline has poor coverage (pydantic: 0% → 80%). On well-structured repos (fastapi), MCP may trade granular file-reading for architectural confidence. Prompt refinement (e.g. "use MCP AND verify each claim by reading the source file") would likely close this gap.

The raw outputs for both runs are in:
- `validation/runs/fastapi/opencode_baseline_p03.txt` — baseline (90%)
- `validation/runs/fastapi/opencode_mcp_p03.txt` — MCP (33.3%)
- `validation/runs/fastapi/opencode_baseline_p04.txt` — baseline (100%)
- `validation/runs/fastapi/opencode_mcp_p04.txt` — MCP (66.7%)

---

## Independence Note

All runs were scored by the project author. The checklist was defined before scoring by reading the actual source code of each repo. The full raw AI output is committed alongside each score so any reader can audit the scoring independently.

We explicitly invite independent scoring: if you re-score any run and disagree, open a GitHub issue with your reasoning.

---

## Run Protocol

1. Clone target repo to `/tmp/bgi-ab-repos/<slug>` (`--depth 1`)
2. `bgi scan <repo_dir> --out output/validation/mcp-ab/<slug>/`
3. Update `opencode.json` to point to `<slug>` graph artifacts (MCP runs only)
4. Baseline run: `mv opencode.json opencode.json.off && opencode [prompt]`
5. MCP run: `mv opencode.json.off opencode.json && opencode [prompt]`
6. Save output to `validation/runs/<slug>/opencode_{baseline|mcp}_p{XX}.txt`
7. Score against checklist → record in `validation/runs.csv`

The `runs.csv` schema:
```
run_id, timestamp_utc, repo_slug, repo_dir, cli, model, mcp_mode, prompt_id,
latency_sec, output_file, time_file, evidence_coverage_pct, boundary_accuracy,
actionability, hallucination_flags, rework_needed, executor, notes, evidence_tag_relaxed_pct
```
