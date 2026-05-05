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

After each role completes their step, **before passing to the next role**, that active
role must ask the human exactly this structured question:

```
---
🔔 HUMAN INPUT REQUESTED — [ROLE NAME]

I just completed: [brief summary of what I did]

The current best approach is: [1-2 sentences]

Its known weaknesses are:
- [weakness 1]
- [weakness 2]

To move forward better, I need your perspective on:
[ONE focused question]

Your input will be shared with all agents before the next step.
---
```

The human responds freely. Then **all 6 roles** briefly react to the human's input
in `shared.md` before the next role begins its full step.

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
