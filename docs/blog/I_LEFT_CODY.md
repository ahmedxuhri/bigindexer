# I left Cody. Here's how I made my BYO-API-key AI setup not suck on big repos.

> A walkthrough for the people scrolling through r/ClaudeAI, r/LocalLLaMA, and the Continue Discord asking "what's a good Cody alternative now that AMP charges per line?"

---

If you're reading this, you probably already know the story. Sourcegraph quietly retired Cody and replaced it with AMP, which charges per line of code generated. Cursor caps your usage at $20. Copilot's pricing is opaque. The whole "flat-rate AI coding assistant" market just admitted that the economics don't work at current LLM token prices.

Meanwhile, the BYO-API-key crowd — Continue, Aider, Claude Code with `claude` CLI, Cline — is sitting on a $5–20/month Anthropic or OpenAI bill and getting nearly the same value, *if* they can get the AI to actually understand their codebase. That last part is where it falls apart on big repos. The AI reads files randomly. It misses the architecture. It suggests changes that cross boundaries it shouldn't.

This is a write-up of what's actually been working for me to close that gap, with concrete numbers from a 100-run study and three commits' worth of reproducible code. I'm the maintainer of [Big Indexer](https://github.com/ahmedxuhri/bigindexer), so I'm not exactly unbiased — but the validation data is public, the loss cases are documented, and you can run the whole thing locally on your own repo in 5 minutes.

## The actual problem with BYO-API-key setups on big repos

Continue, Aider, and friends do retrieval. They embed your codebase, pull a few chunks per query, send those to the AI. That works fine for "what does this function do" but it falls over on architectural questions:

- *"Where should I add this feature without leaking responsibilities across modules?"*
- *"What's the blast radius if I change this route handler?"*
- *"Are there other places in the repo that solve a similar problem I should mirror?"*

Embedding-based retrieval doesn't have a model of architecture. It has a model of textual similarity. Those aren't the same thing. The result: AI gives you syntactically reasonable code that crosses the wrong boundaries, gets the wrong abstractions, and reads ten files when it should have read two.

Sourcegraph knew this — that's why Cody had a "structural" code graph backing it. But it was a managed service, your queries went to their cloud, and the per-line economics became untenable.

## What I tried instead

A small open-source tool called [Big Indexer](https://github.com/ahmedxuhri/bigindexer) that does one thing: scan your repo, build a behavioral graph, expose it over MCP (Model Context Protocol). MCP is the standard your AI assistant probably already speaks — Continue, Cursor, Claude Desktop, Cline all support it.

The pitch: BGI is *not* an AI coding assistant. It runs alongside whichever one you've picked. It's the architecture-aware context layer that gives the AI a real model of your codebase's structure, so it stops file-fishing and starts giving you architecturally sane suggestions.

Cost: free, local, Apache 2.0. No service in the loop. No per-token fee.

## Setup, in 5 minutes

```bash
pip install bigindexer
cd /path/to/your/big/repo
bgi scan . --lang auto --out bgi-graph.json --fuse-graph fuse-graph.json
```

Then add it to whichever MCP client you're using. For Continue, that's an entry in `~/.continue/config.json`:

```jsonc
{
  "experimental": {
    "modelContextProtocolServers": [{
      "name": "bgi",
      "transport": {
        "type": "stdio",
        "command": "bgi",
        "args": ["mcp",
          "--graph", "/abs/path/bgi-graph.json",
          "--fuse-graph", "/abs/path/fuse-graph.json"
        ]
      }
    }]
  }
}
```

Restart Continue, and it has 12 new MCP tools available. The three I actually use:

- `task_fingerprint(task)` — convert a natural-language task into the repo's behavioral vocabulary
- `behavioral_twins(task)` — find the top 3 in-repo code units already doing similar work
- `twin_context(task)` — combined: fingerprint + twins + the seam where they connect + a 5-point safety rubric

The full setup walkthrough with more detail (Claude Desktop, Cursor, Cline configs too) is in [`docs/MCP_WITH_CONTINUE.md`](https://github.com/ahmedxuhri/bigindexer/blob/master/docs/MCP_WITH_CONTINUE.md).

## What actually changes

The validation page has 100 scored runs across 5 production OSS repos (django, fastapi, prometheus, pydantic-core, next.js) with three different models (deepseek-v4-flash, GPT-4o, Gemini auto). Raw outputs are committed; you can re-score yourself.

Headline numbers:

| Metric | No BGI | With BGI MCP context |
|---|---:|---:|
| Median agent latency | 133.8s | **66.2s** |
| Boundary accuracy | 0.95 | **1.00** |
| Actionability (1–5) | 4.00 | **4.75** |
| Hallucination rate | 0 | 0 |

The latency drop is the cost story. Median agent run halved. That's because the AI read fewer files — BGI told it which ones mattered. Translates to roughly 20–30% lower input-token cost on big-repo agentic tasks (depends entirely on your starting setup; don't believe specific cost claims without measuring on your own repo).

The boundary and actionability numbers are the answer-quality story. Both moved up. That's the part that matters more — a wrong answer at half the price is still wrong.

## The pydantic-core moment

The clearest result in the dataset is on pydantic-core. Without BGI, the model on prompt p01 scored 0% on evidence coverage and 0 on boundary accuracy — it described a pure-Python architecture. The repo is Python + Rust with a `pyo3` bridge, and the model never found it. With BGI MCP context, same prompt: 80% evidence coverage, 1.0 boundary accuracy. BGI surfaced the bridge directly; the model identified it correctly on the first attempt.

That's not a benchmark trick. That's an architecture-aware context layer doing what an embedding retriever cannot.

## The honest losses

I'm going to publish the loss cases too because that's the only way these "we ran a benchmark" posts are believable.

**Go scanner has a known gap.** On Go repos, BGI's behavioral edges currently stay mostly within file boundaries due to how the spectral mask system interacts with Go's token distribution. Boundary accuracy is still 1.0, actionability is still 4.25–5.0, and the user-visible MCP product still works. But on a recent external benchmark vs Louvain on raw imports, BGI lost on Go and won on Python. Documented in detail at [bigindexer.com/validation](https://bigindexer.com/validation).

**Evidence coverage is style-sensitive.** Different models produce different `VERIFIED/HYPOTHESIS/UNKNOWN` tagging styles. deepseek tags strictly; Gemini tags less; GPT-4o gives correct answers with fewer explicit tags. The rubric reflects tagging style as much as answer quality. We publish a tag-relaxed second score to make the gap visible, and we never normalize numbers behind the scenes.

**Self-scored.** I wrote the rubric. I scored the runs. The full rubric is in `validation/SCORING_RUBRIC.md`, every raw output is committed to `validation/runs/`, and I genuinely want people to re-score independently and open issues if they disagree. That's the level of "self-scored" this is — not a closed-door evaluation.

## Why this is open source and free

Because the business isn't the code. The code is replicable by a motivated engineer in a few months — that's not a moat worth defending. The validation evidence, the network of users, the managed-cloud version eventually, those are the things that compound. The code stays free, AGPL-or-Apache, runs on your machine, and your queries don't leave it.

That's also the answer to the obvious "why isn't this $9.99/month like Cody was" question. There is nothing to charge for. You install it, you scan your repo, you point Continue at it, and it works.

## Try it on your repo

```bash
pip install bigindexer
cd /your/repo
bgi scan . --lang auto --out bgi-graph.json --fuse-graph fuse-graph.json

# then point your AI client at:
#   bgi mcp --graph bgi-graph.json --fuse-graph fuse-graph.json
```

If you've got a big monorepo, use `--incremental` after the first scan and it stays fast.

If your AI assistant gives architecturally bad suggestions on a specific repo, please [open an issue](https://github.com/ahmedxuhri/bigindexer/issues) with the prompt and the response. That's the kind of feedback that makes the next version better.

## What I'd love to know from people trying this

1. Did you switch from Cody/Cursor/etc., or have you been BYO-API-key the whole time?
2. What's your repo size, and which AI client are you using?
3. Which MCP tool actually paid back? `cluster_of_file`? `twin_context`? `boundary_edges`?
4. Where did it fail? Specifically — *which* prompt produced *which* unhelpful answer?

Drop a comment, open an issue, or DM. The 14-day GitHub traffic on the repo just hit 145 unique cloners off a Reddit + Product Hunt burst, so I know the audience exists. Now I'd like to know who you are and what would actually help.

---

Links:

- Repo: [github.com/ahmedxuhri/bigindexer](https://github.com/ahmedxuhri/bigindexer)
- Validation evidence: [bigindexer.com/validation](https://bigindexer.com/validation)
- Continue setup: [docs/MCP_WITH_CONTINUE.md](https://github.com/ahmedxuhri/bigindexer/blob/master/docs/MCP_WITH_CONTINUE.md)
- License: Apache 2.0

— Ahmed
