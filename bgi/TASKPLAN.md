# BGI — Task Plan

## Step 1 — JavaScript language support
Add JavaScript as a scannable language. JS uses the same tree-sitter grammar as TypeScript (minus type annotations), so `ts_scanner.py` and `typescript_rules.py` can be reused almost entirely with a JS-specific parser. Covers `.js` and `.jsx` files.

## Step 2 — AI Position 1 activation (Token Fallback)
When no tier fires any COV token for a unit, call an LLM to inspect the function body and assign tokens. This makes the fingerprinter robust on unusual patterns (DSL wrappers, generated code, heavy metaprogramming). Needs prompt design, response parsing, and confidence calibration.

## Step 3 — AI Position 3 polish (Architecture Narrator)
The narrator already produces `agents.md` with template-based cluster roles ("Lifecycle Manager", "Data Access"). Activating the LLM gives each cluster a real, context-aware description — naming the actual domain (e.g. "JWT authentication pipeline" instead of "Interface / Contract Definition"). Needs prompt design and output validation.

## Step 4 — Graph visualization
Export the BGI graph to a self-contained HTML file (D3.js or Cytoscape.js). Nodes = units coloured by dominant COV token, edges weighted by confidence, clusters as visual groups. Makes the output tangible and shareable without any tooling.

## Step 5 — Multi-repo / incremental scanning
Right now each scan is a full rescan from scratch. Add delta scanning: fingerprint only files changed since the last scan (via git diff or mtime), merge with the existing graph, and resurrect SEP edges from previous runs. Enables BGI on large monorepos without full re-parse on every run.

## Step 6 — Vocabulary Curator end-to-end
Wire up the `bgi curate` command fully: read `bgi-unresolved.jsonl` (AI Position 1 log), group unmatched patterns, score extension candidates (MEMOIZE, PATTERN_MATCH, AMBIENT, BATCH), and output a ranked `cov-extension-candidates.json`. Enables the vocabulary to grow formally rather than ad-hoc.
