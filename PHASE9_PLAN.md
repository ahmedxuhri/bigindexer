# Phase 9 — Public Launch Plan

> Execution route from private repo → public MCP product → revenue.
> Read `owners_concerns.md` first for the strategic rationale.

---

## Overview

Phase 9 has 5 stages in order. Do not skip ahead — each stage builds on the previous.

```
Stage 1: Prepare the public repo (license, cleanup, README polish)
Stage 2: MCP registry submission
Stage 3: Public launch (GitHub release + HN + social)
Stage 4: Private cloud repo setup (managed service foundation)
Stage 5: Continuous follow-up (metrics, community, iteration)
```

---

## Stage 1 — Prepare the Public Repo

**Goal:** Make `ahmedxuhri/bigindexer` public-ready. One shot at a first impression.

### 1.1 Choose and add a license

Add `LICENSE` file to repo root.

Recommended: **AGPL v3** (protects against cloud competitors)  
Alternative: **Apache 2.0** (maximum adoption)

Decision depends on your priority:
- "I want maximum developers using this" → Apache 2.0
- "I don't want another company hosting my code as a service without contributing back" → AGPL v3

Action: create `LICENSE` file (full text from choosealicense.com), add SPDX identifier to `pyproject.toml`.

### 1.2 Final README pass

The README is your product page. It must answer in the first 5 seconds:
- What is this?
- Who is it for?
- How do I start in 60 seconds?

Check:
- [ ] First paragraph: plain English problem statement
- [ ] One-command install: `pip install bigindexer`
- [ ] One-command scan + MCP start (copy-paste ready)
- [ ] Link to `bigindexer.com/validation` (your evidence)
- [ ] Badges: PyPI version, license, tests passing

### 1.3 Clean up secrets and internal notes

Before making public:
- [ ] Search for any hardcoded paths, API keys, emails, internal hostnames
- [ ] Review `.gitignore` — make sure no sensitive output files are tracked
- [ ] Remove or sanitize any internal planning files that shouldn't be public
  - `owners_concerns.md` — OK to keep (explains strategy, no secrets)
  - `masterplan.md` — OK to keep (good for transparency)
  - `session.md`, `opencode.json` — review, likely remove or gitignore

### 1.4 Confirm pip package works cleanly

```bash
pip install bigindexer   # from PyPI (publish if not already)
bgi scan --help
bgi mcp --help
```

If not yet on PyPI, publish:
```bash
python -m build
twine upload dist/*
```

### 1.5 Make repo public

GitHub → Settings → Danger Zone → Change repository visibility → Public

---

## Stage 2 — MCP Registry Submission

**Goal:** Get `bgi mcp` listed in official MCP discovery surfaces.

### 2.1 Submit to modelcontextprotocol/servers

Repository: `https://github.com/modelcontextprotocol/servers`

Steps:
1. Fork the repo
2. Add entry to `README.md` in the Community Servers section:
   ```markdown
   - **[Big Indexer](https://github.com/ahmedxuhri/bigindexer)** — Architecture-aware context for AI coding assistants. Injects cluster boundaries, seam edges, and blast-radius analysis via `bgi mcp`. ([docs](https://bigindexer.com))
   ```
3. Open a PR to their repo with your entry
4. Link your validation evidence (`bigindexer.com/validation`) in the PR description

### 2.2 Submit to awesome-mcp-servers lists

Several community-maintained lists aggregate MCP servers:
- `github.com/punkpeye/awesome-mcp-servers`
- `github.com/appcypher/awesome-mcp-servers`
- `mcp.so` (community directory)

Submit to each with a one-liner description and link.

### 2.3 Add MCP badge and install block to README

```markdown
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-blue)](https://modelcontextprotocol.io)
```

Add a `## Use with MCP` section near the top of README with the opencode.json / Claude Desktop config block.

---

## Stage 3 — Public Launch

**Goal:** Create the initial wave of awareness. Do all three on the same day.

### 3.1 GitHub Release

Create release `v2.0.0` (or appropriate version) with release notes:

```markdown
## Big Indexer v2.0 — Architecture-Aware MCP Context

Big Indexer now ships an MCP server that injects architecture boundaries,
cluster maps, and blast-radius analysis directly into your AI coding assistant.

### What's new
- `bgi mcp` — MCP server for Opencode, Claude Desktop, Cursor, Copilot
- 6 MCP tools: cluster_of_file, boundary_edges, high_coupling_seams, impact_neighbors, search_symbols, architecture_summary
- A/B validation: +10.6% evidence coverage, 55% faster responses, 0 hallucinations

### Install
pip install bigindexer

### Evidence
https://bigindexer.com/validation
```

### 3.2 Hacker News — Show HN post

Title: `Show HN: Big Indexer – MCP server that injects architecture boundaries into AI coding assistants`

Body (keep under 200 words):
- What it does in one sentence
- The problem it solves (AI assistants don't know your architecture)
- The validation evidence (link to bigindexer.com/validation)
- How to install (one command)
- What's next (managed cloud)

Best time to post: Tuesday–Thursday, 9am–11am US Eastern.

### 3.3 Twitter/X and LinkedIn post

Short demo clip: screen-record a 30-second terminal session:
1. `bgi scan fastapi/` — watch it produce graph
2. `bgi mcp --graph ...` — MCP server starts
3. Run opencode, ask "what boundaries does this change cross?" — watch MCP inject context

Caption: "AI coding assistants don't know your architecture. Big Indexer fixes that. [link]"

---

## Stage 4 — Private Cloud Repo Setup

**Goal:** Foundation for the managed service that generates revenue.

### 4.1 Create `bigindexer-cloud` private repo

```bash
gh repo create ahmedxuhri/bigindexer-cloud --private
```

Initial structure:
```
bigindexer-cloud/
  api/          # FastAPI or Express REST API
  auth/         # JWT + API key management
  billing/      # Stripe integration
  worker/       # Indexing job queue (RQ or Celery)
  storage/      # Azure Blob client for graphs
  dashboard/    # React/Next.js team dashboard (later)
  infra/        # Terraform / Bicep for Azure
```

### 4.2 Define the managed service MVP

The minimum viable managed service:

1. **User signs up** at bigindexer.com → gets API key
2. **User provides** GitHub repo URL + branch
3. **Worker clones, scans**, stores `bgi-graph.json` + `fuse-graph.json` in Azure Blob
4. **User configures MCP** with hosted endpoint instead of local `bgi mcp`
5. **Billing**: $X/month per repo or per-seat

This is 4–6 weeks of development.

### 4.3 Pricing hypothesis (test with first 10 customers)

| Tier | Price | What you get |
|---|---|---|
| Community | Free | Self-hosted, open source |
| Solo | $9/month | 3 repos, hosted graphs, managed MCP endpoint |
| Team | $49/month | 20 repos, team access, PR boundary guard |
| Enterprise | Custom | Unlimited, on-prem, SLA, audit trail |

Do not build the paid tier before you have 5 people saying "I would pay for this."  
First: get design partners from your waitlist.

---

## Stage 5 — Continuous Follow-Up

**Goal:** Don't launch and disappear. Compound the momentum.

### 5.1 Weekly metrics to track

**Adoption:**
- GitHub stars (weekly delta)
- PyPI installs (`pypistats.org/packages/bigindexer`)
- bigindexer.com waitlist signups
- MCP registry listing views (if available)

**Community:**
- GitHub issues opened (feature requests = demand signal)
- GitHub Discussions (if enabled)
- Mentions on X/LinkedIn/HN

**Revenue pipeline:**
- Waitlist → design-partner conversations
- Design partners → pilot sign-ups
- Pilots → paid conversions

### 5.2 Monthly iteration loop

Each month:
1. Review top GitHub issues — build the most-requested thing
2. Update `bigindexer.com/validation` with any new evidence runs
3. Write one short blog post or X thread with a real use case
4. DM 2–3 waitlist signups personally to ask what they're building

### 5.3 Community health signals

When you hit 100 GitHub stars:
- Add GitHub Discussions
- Add `CONTRIBUTING.md`
- Label issues with `good first issue`

When you hit 500 stars:
- Consider a Discord or Slack community
- Look for first contributors to mentor

### 5.4 Protect the open source community

Never:
- Remove features from the open source version to push paid
- Break self-hosted setups with breaking changes without major version bump
- Ignore community PRs for more than 2 weeks

Always:
- Keep the core pipeline open source forever
- Changelog every release
- Respond to issues within 3 days

---

## Summary Timeline

```
Week 1    Stage 1 — Prepare + go public
Week 1    Stage 2 — MCP registry submission (same week as public)
Week 1    Stage 3 — Launch day (GitHub release + HN + social)
Week 2+   Stage 5 begins immediately — monitor, respond, iterate
Month 2+  Stage 4 — Start cloud infra (only after seeing adoption signal)
Month 3+  First design-partner pilots
Month 4+  First paid customer
```

---

## Decision Checklist Before Going Public

- [ ] LICENSE file exists in repo root
- [ ] No secrets, keys, or private paths in tracked files
- [ ] `pip install bigindexer && bgi mcp --help` works cleanly
- [ ] README has one-command quickstart
- [ ] `bigindexer.com` is live and links to GitHub
- [ ] `bigindexer.com/validation` is live (done ✅)
- [ ] MCP registry PR drafted and ready to submit same day

---

*Big Indexer — Architecture-aware context for AI coding assistants.*  
*https://bigindexer.com*
