# ⚙️ Innovation Cycle Workflow

This document defines the exact process rules for running an innovation cycle.

---

## Cycle Structure

Each cycle targets **one specific challenge**. A challenge should be:
- Concrete (not vague)
- Measurable in some way
- Relevant to the AI-Native Architecture Platform

Example challenge:
> "Design a hybrid indexing system for million-LOC monorepos that is both fast to query
> and directly feeds accurate AI-native architecture generation."

---

## Step Order

```
[1] ARCHIVIST  →  human gate  →  all-react
[2] VISIONARY  →  human gate  →  all-react
[3] PRAGMATIST →  human gate  →  all-react
[4] SKEPTIC    →  human gate  →  all-react
[5] MEASURER   →  human gate  →  all-react
[6] JUDGE      →  human gate  →  DONE (or loop back)
```

---

## The Human Gate (mandatory between every step)

The Human Gate is a **two-phase process**:

### Phase 1 — Brainstorm (in `brainstorming.md`)

After each role posts to `shared.md`, Copilot:
1. Resets `brainstorming.md` with the current gate context (which step, what was found)
2. Asks the human the role's focused question
3. The human and Copilot chat freely — multiple back-and-forth turns
   - Half-formed ideas, gut feelings, analogies, questions — all welcome
   - Copilot plays a neutral thinking partner here (not any specific agent role)
4. This continues until the human says **"submit"**

### Phase 2 — Submission (back to `shared.md`)

On "submit":
1. Copilot distills the brainstorm into a clean **[HUMAN INSIGHT]** summary
2. Posts it to `shared.md` under the header:
   ```
   **👤 HUMAN** | `YYYY-MM-DD HH:MM` | Gate after Step [N]
   [distilled insight]
   ```
3. All 6 agent roles briefly react to it in `shared.md`
4. `brainstorming.md` is reset (header updated, old chat cleared) for the next gate
5. The next agent role begins its full step

### The Role's Gate Question Format

Each role ends its `shared.md` post with:

```
🔔 HUMAN INPUT REQUESTED — [ROLE NAME]

I just completed: [brief summary]
Current best approach: [1-2 sentences]
Known weaknesses: [bullet list]
My question for you: [ONE focused question]

→ Head to brainstorming.md — say "submit" when your idea is ready.
```

---

## shared.md Post Format

Every agent post in `shared.md` must follow this format:

```markdown
---
**[SYMBOL] [ROLE NAME]** | `YYYY-MM-DD HH:MM` | Step [N]

[content]

---
```

Example:
```markdown
---
**🌌 VISIONARY** | `2026-05-05 01:15` | Step 2

Idea: treat each file as a neuron, dependencies as synaptic weights...

---
```

---

## Loop / Termination Rules

- The Judge may declare **"CONVERGED"** — cycle is complete, winner is clear.
- The Judge may declare **"ITERATE"** — send top 2 ideas back to Visionary for mutation.
- Maximum 6 full cycles per challenge before forced human decision.
- After completion, move `shared.md` to `sessions/YYYY-MM-DD-[challenge-slug].md`
  and reset `shared.md` for next cycle.

---

## Quality Principles

- **No empty agreement** — every role must have a distinct perspective.
- **Skeptic is never silenced** — even good ideas get attacked.
- **Measurer must cite evidence** — no "this would be faster" without numbers or references.
- **Judge must score** — no vague synthesis; explicit winner with reasoning.
- **Human insights are sacred** — all agents must acknowledge and engage with human input.

---

## Starting a Cycle

Tell Copilot:
```
start cycle: [your challenge description]
```

Copilot will:
1. Write the challenge at the top of `shared.md`
2. Begin as ARCHIVIST
3. Follow this workflow until Judge converges

---

## File Roles

| File | Purpose |
|------|---------|
| `shared.md` | Permanent record — all agent posts + submitted human insights |
| `brainstorming.md` | Recyclable scratchpad — human ↔ Copilot chat at each gate, cleared after submit |
| `sessions/` | Completed cycle archives |
