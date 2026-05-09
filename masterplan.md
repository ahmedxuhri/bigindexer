# Big Indexer Master Plan

## 1) Goal

Turn Big Indexer (BGI) into a real product line with revenue by shipping an MCP server that injects architecture context into AI coding assistants.

Core thesis:

- teams already pay for AI coding
- AI assistants fail when they do not understand architecture boundaries
- Big Indexer can provide that missing context via `bgi-graph.json`, `fuse-graph.json`, and index APIs

---

## 2) Strategic direction

Primary path (recommended):

1. Ship MCP server for architectural context.
2. Prove daily utility with real engineering workflows.
3. Convert usage into paid hosted/team features.
4. Use Microsoft/Azure sponsorship as acceleration after traction exists.

Do not start with sponsorship-first positioning. Start with adoption proof.

---

## 3) Current assets already in hand

1. Core pipeline (Gate 1/2/3) with quality constraints implemented.
2. Boundary signal output (`fuse-graph` behavior).
3. Large-repo validation history (kubernetes profile runs).
4. Query/index stack from Phase 6 (schema, builder, planner, API, VS Code prototype).
5. Domain: `bigindexer.com`.
6. Azure credits: $200 (good for pilot hosting and telemetry).

---

## 4) What must be improved now

## A. Product clarity

- Convert architecture language into practical developer outcomes.
- Keep technical naming, but always pair with plain-English meaning.

## B. Proof quality

- Keep performance evidence.
- Add utility evidence: concrete "AI asked X, MCP returned Y, engineer changed Z safely."
- Add external quality benchmark set over time (precision/recall style evaluation).

## C. Distribution readiness

- Provide a dead-simple MCP setup.
- Publish demo repo + short walkthrough.

## D. Commercial packaging

- Clear split: open source core vs paid managed/team features.
- Define early pricing hypotheses and pilot offer.

---

## 5) Product blueprint: MCP server

## MCP server v1 scope (must-have tools)

1. `cluster_of_file(file_path)`
   - returns cluster ID, dominant tokens, cluster size, confidence.
2. `boundary_edges(file_path_or_cluster)`
   - returns fuse boundaries touching the file/cluster.
3. `high_coupling_seams(file_path_or_cluster, limit)`
   - returns strongest cross-boundary seams.
4. `impact_neighbors(symbol_or_file, depth)`
   - returns likely architectural blast radius.
5. `search_symbols(query, limit)`
   - wraps existing index search APIs for MCP clients.
6. `architecture_summary(path_scope)`
   - compact summary for AI context window injection.

## MCP server v1 non-goals

- no runtime tracing
- no fully semantic call-target resolution claims
- no auto-refactor actions in v1

---

## 6) Build plan (step-by-step)

## Phase 0 - Branding and documentation baseline

1. Use "Big Indexer" naming across external surfaces.
2. Keep acronym BGI for continuity.
3. Keep README outcome-first and explicit about limits.

## Phase 1 - MCP local product

1. Add `bgi/mcp/server.py`.
2. Add MCP tool handlers mapped to existing graph/index data.
3. Add config for:
   - graph path
   - fuse graph path
   - optional index DB path
4. Add `docs/MCP_SETUP.md` with:
   - Cursor setup
   - Claude Desktop setup
   - Copilot-compatible adapter notes
5. Add a small demo script using one real repo.

Definition of done:

- local MCP server runs
- at least three MCP tools are stable and useful in real prompts
- setup is reproducible by another user in less than 10 minutes

## Phase 2 - Real workflow validation

1. Select 2-3 realistic repos (including one large repo).
2. Run repeated AI tasks:
   - "where should this file live?"
   - "what boundaries will this change cross?"
   - "what should I review before editing this?"
3. Capture before/after usefulness notes.
4. Publish a short validation report with real prompt/response snippets.

Definition of done:

- at least 10 high-signal MCP-assisted examples documented
- clear list of most-requested MCP queries for v2 roadmap

## Phase 3 - Public launch

1. Open-source MCP server repo section in main project.
2. Publish to MCP server registry.
3. Publish launch posts:
   - GitHub release notes
   - HN post
   - X/LinkedIn post with short demo clip
4. Add issue template: "MCP query request."

Definition of done:

- public installation docs complete
- first external users can run it without direct support

## Phase 4 - Azure pilot backend (using $200 credits)

Goal: offer managed indexing for early team pilots.

Minimal Azure architecture:

1. **Container Apps**: host API + MCP service.
2. **Azure Database for PostgreSQL** or **Azure SQL/SQLite blob strategy** for index metadata.
3. **Blob Storage** for graph artifacts and snapshots.
4. **Application Insights** for telemetry and error monitoring.
5. **GitHub Actions** for CI/CD deployment.

Credit usage guidance:

- keep always-on resources minimal
- prefer auto-scale to zero where possible
- run short pilot windows, not permanent high-throughput infra

Definition of done:

- one hosted pilot environment running from Azure
- usage telemetry visible
- cost tracking dashboard created

## Phase 5 - Monetization conversion

Open source stays free for local/self-host.

Paid value should be team/managed features:

1. hosted index refresh and storage
2. team-wide architecture policy checks (PR boundary guards)
3. architecture drift alerts over time
4. dashboard + audit trail
5. priority support and onboarding

Initial monetization motion:

1. free community tier (local MCP)
2. design-partner pilot tier (manual onboarding)
3. first paid team tier after repeatable value is confirmed

---

## 7) KPI framework

Track these weekly:

Product adoption:

1. MCP installs.
2. active repos using MCP tools.
3. weekly MCP tool query count.

Product utility:

1. percentage of sessions where MCP answer is used in final code decision.
2. top 10 MCP questions asked by engineers.
3. repeated-user retention.

Business:

1. number of pilot teams.
2. conversion from pilot to paid.
3. monthly recurring revenue trend.

Quality and trust:

1. regression count in architecture outputs.
2. benchmark stability window for key repos.
3. documented false-positive/false-negative cases and fixes.

---

## 8) Risk register and mitigation

Risk 1: MCP hype without durable value.  
Mitigation: validate with real engineering tasks and publish concrete examples.

Risk 2: over-claiming language support quality.  
Mitigation: keep explicit support tiers and test coverage per tier.

Risk 3: unclear differentiation vs existing tools.  
Mitigation: keep "why BGI" table and case studies centered on boundary-aware context.

Risk 4: infra credits consumed too quickly.  
Mitigation: strict low-cost architecture, short pilot cycles, daily cost checks.

---

## 9) Microsoft / sponsorship approach

Recommended order:

1. get traction first (usage + pilots)
2. then pitch Microsoft for Startups/sponsorship with evidence:
   - active usage metrics
   - pilot logos or testimonials
   - clear Azure expansion plan

Pitch angle:

- Big Indexer improves AI coding safety in large repos by injecting architecture boundaries into MCP workflows.
- Azure credits accelerate managed deployment for enterprise pilots.

---

## 10) Immediate next actions (now)

1. Implement MCP server v1 with 3-6 core tools.
2. Create `docs/MCP_SETUP.md` and one quick demo video/GIF.
3. Run internal validation on one large repo and one medium repo.
4. Publish launch package (registry + HN + social).
5. Start collecting pilot leads via `bigindexer.com` landing page.

---

## 11) Definition of success for this master plan

Success means:

1. engineers use Big Indexer MCP in real coding loops
2. usage converts to pilot teams
3. pilot teams convert to paid managed usage
4. product reputation is based on real architectural safety gains, not only benchmark speed
