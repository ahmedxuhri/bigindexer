# 🧠 Innovation Engine

> A multi-role AI innovation system where one AI plays all agent roles sequentially,
> with structured human intervention at each step — producing genuinely novel solutions
> through debate, critique, measurement, and evolution.

---

## What This Is

This is the **seed project** for building a Sourcegraph competitor with a unique angle:
an **AI-Native Living Architecture Platform** — a system that automatically builds and
continuously maintains a rich, structured, agent-optimized understanding layer on top of any codebase.

Before building that platform, we use this Innovation Engine to **solve hard design challenges**
through a structured multi-role thinking process.

---

## How It Works

One AI (you, Copilot) plays **6 distinct roles**, one at a time, each with a different
personality, focus, and output. Between each role, the human (you) is consulted.
All thinking happens transparently in `shared.md` — a living chat room.

### The 6 Roles

| Role | Symbol | Personality |
|------|--------|-------------|
| Archivist | 📚 | Researcher — what's already been tried |
| Visionary | 🌌 | Explorer — wild, cross-domain ideas |
| Pragmatist | ⚙️ | Engineer — concrete specs and trade-offs |
| Skeptic | 🔴 | Red Team — attacks every assumption |
| Measurer | 📊 | Evaluator — benchmarks, metrics, evidence |
| Judge | ⚖️ | Synthesizer — scores, selects, synthesizes |

---

## How to Start a New Innovation Cycle

1. **Define the challenge** — write it at the top of `shared.md`
2. **Tell me to begin** — say "start cycle: [your challenge]"
3. I will play each role in order, posting to `shared.md`
4. **At the end of each role's step**, open `brainstorming.md` — we'll chat freely there
5. When your idea is fully formed, say **"submit"** — I'll distill it and post to `shared.md`
6. All agents react to your insight, then the next role begins
7. Repeat until the Judge produces a final synthesis

---

## File Structure

```
mad/
├── README.md          ← you are here
├── WORKFLOW.md        ← detailed process rules
├── shared.md          ← permanent agent chat room (all roles post here)
├── brainstorming.md   ← recyclable human ↔ Copilot scratchpad at each gate
├── agents/
│   ├── ARCHIVIST.md   ← role instructions
│   ├── VISIONARY.md
│   ├── PRAGMATIST.md
│   ├── SKEPTIC.md
│   ├── MEASURER.md
│   └── JUDGE.md
└── sessions/          ← archived completed cycles
```

---

## The Product Vision

> "While others help you **search** code, we help AI agents (and humans) truly
> **understand** complex projects in minutes instead of days — by building and
> maintaining a living, AI-native architecture intelligence layer."

**Primary outputs of the platform we're building:**
- `ARCHITECTURE.md` — rich, human-readable
- `context.json`, `containers.json`, `components.json`, `code-map.json`
- `knowledge-graph.jsonl` — for GraphRAG
- `AGENTS.md` — agent-specific consumption instructions
