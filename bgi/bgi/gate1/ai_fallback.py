"""
Gate 1 — AI Position 1: Token Fallback classifier.

Uses an OpenAI-compatible client (default: DeepSeek via https://api.deepseek.com).
Any provider that speaks the OpenAI Chat Completions API works here.

Two modes of operation:

1. Call-level fallback (existing):
   Fires for call_expression nodes that no Tier 1–4 rule matched.
   Returns (COV, confidence) or None.

2. Unit-level fallback:
   Fires when a function's entire token list is empty after all tiers.
   This catches DSL wrappers, generated code, and heavy metaprogramming
   that produce no detectable AST patterns.
   Returns list[(COV, confidence)] — may assign multiple tokens.

Both modes log to bgi-unresolved.jsonl for curator consumption.
When enabled=False (default), both modes return None/[] without calling the LLM.

Quick start:
    from bgi.gate1.ai_fallback import AIFallback, make_deepseek_client
    ai = AIFallback(enabled=True, client=make_deepseek_client("sk-..."))
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from tree_sitter import Node

from bgi.core.cov import COV
from bgi.gate1.rules import node_text


# Default model — DeepSeek v4 Flash (fast, cheap, OpenAI-compatible)
_DEFAULT_MODEL = "deepseek-v4-flash"
_DEFAULT_BASE_URL = "https://api.deepseek.com"

# Tokens AI is allowed to assign
_CLASSIFIABLE = {
    COV.TRANSFORM, COV.PERSIST, COV.FETCH, COV.MUTATE,
    COV.VALIDATE, COV.LOG, COV.MEASURE, COV.EMIT, COV.SUBSCRIBE,
    COV.ROUTE, COV.DELEGATE, COV.AUTHENTICATE, COV.AUTHORIZE,
    COV.SCOPE, COV.COMPOSE, COV.SANITIZE,
}

# Where unresolved snippets are accumulated for curator consumption
_DEFAULT_LOG = Path("bgi-unresolved.jsonl")

# Prompt templates
_CALL_PROMPT = """\
You are classifying a single code call into exactly one semantic token.

Allowed tokens: {tokens}

Code snippet:
```
{snippet}
```

Reply with ONLY the token name and a confidence 0.0-1.0, separated by a space.
Example: FETCH 0.82
If you cannot classify with confidence > 0.5, reply: UNKNOWN 0.0"""

_UNIT_PROMPT = """\
You are classifying a code function/method into behavioral semantic tokens.

Allowed tokens: {tokens}

The full function source:
```
{snippet}
```

This function produced NO tokens from static analysis. Assign 1–3 tokens \
that best describe what it does.

Reply with ONLY a JSON array of [token, confidence] pairs.
Example: [["FETCH", 0.8], ["OUTPUT", 0.9]]
If you cannot classify, reply: []"""


def make_deepseek_client(api_key: str | None = None, base_url: str = _DEFAULT_BASE_URL):
    """
    Create an OpenAI-compatible client pointed at DeepSeek.
    api_key defaults to DEEPSEEK_API_KEY env var if not provided.
    """
    from openai import OpenAI
    return OpenAI(
        api_key=api_key or os.environ.get("DEEPSEEK_API_KEY", ""),
        base_url=base_url,
    )


class AIFallback:
    """
    AI Position 1 — Token Fallback.

    Uses an OpenAI-compatible client (DeepSeek by default) to classify
    ambiguous code units and calls.

    Disabled by default (enabled=False). Set enabled=True and provide
    a client (via make_deepseek_client() or any openai.OpenAI instance)
    to activate.

    When disabled, all methods still log unresolved snippets to the
    JSONL log for offline curator analysis and future training data.
    """

    def __init__(
        self,
        enabled: bool = False,
        client=None,
        model: str = _DEFAULT_MODEL,
        log_path: Path | None = None,
    ):
        self.enabled = enabled
        self.client = client
        self.model = model
        self._log_path = log_path or _DEFAULT_LOG
        self._unresolved: list[dict] = []  # in-memory buffer; flushed on flush()

    def _chat(self, prompt: str, max_tokens: int = 80) -> str | None:
        """Send a prompt to the LLM and return the response text, or None on error."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return None

    # ── Call-level fallback ───────────────────────────────────────────────────

    def classify(self, call_node: Node, context_snippet: str = "") -> tuple[COV, float] | None:
        """
        Attempt to classify an unmatched call expression node.
        Returns (COV token, confidence) or None.
        Logs the snippet regardless of enabled state.
        """
        callee_text = node_text(call_node)[:120]
        self._unresolved.append({"type": "call", "snippet": callee_text})

        if not self.enabled or self.client is None:
            return None

        prompt = _CALL_PROMPT.format(
            tokens=sorted(t.value for t in _CLASSIFIABLE),
            snippet=context_snippet or callee_text,
        )

        raw = self._chat(prompt, max_tokens=128)
        if raw is None:
            return None
        parts = raw.split()
        if len(parts) != 2:
            return None
        token_str, conf_str = parts
        if token_str == "UNKNOWN":
            return None
        try:
            token = COV(token_str)
        except ValueError:
            return None
        if token not in _CLASSIFIABLE:
            return None
        try:
            conf = float(conf_str)
        except ValueError:
            return None
        if conf <= 0.5:
            return None
        return (token, conf)

    # ── Unit-level fallback ───────────────────────────────────────────────────

    def classify_unit(
        self,
        unit_id: str,
        source_snippet: str,
        language: str = "python",
    ) -> list[tuple[COV, float]]:
        """
        Classify an entire unit whose token list is empty after all tiers.
        Returns list of (COV, confidence) pairs — may be empty if AI declines.
        Logs the unit regardless of enabled state.
        """
        self._unresolved.append({
            "type": "unit",
            "unit_id": unit_id,
            "snippet": source_snippet[:500],
            "language": language,
        })

        if not self.enabled or self.client is None:
            return []

        prompt = _UNIT_PROMPT.format(
            tokens=sorted(t.value for t in _CLASSIFIABLE),
            snippet=source_snippet[:800],
        )

        raw = self._chat(prompt, max_tokens=200)
        if raw is None or raw == "[]":
            return []

        try:
            pairs = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []

        result = []
        for item in pairs:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            token_str, conf = item
            try:
                token = COV(token_str)
            except ValueError:
                continue
            if token in _CLASSIFIABLE and float(conf) > 0.5:
                result.append((token, float(conf)))
        return result

    # ── Logging ───────────────────────────────────────────────────────────────

    def flush(self, scan_run: str = "") -> int:
        """
        Append in-memory unresolved entries to the log file (JSONL).
        Returns number of entries written. Safe to call after every scan.
        """
        if not self._unresolved:
            return 0
        with self._log_path.open("a") as f:
            for entry in self._unresolved:
                f.write(json.dumps({**entry, "scan_run": scan_run}) + "\n")
        written = len(self._unresolved)
        self._unresolved.clear()
        return written

    def unresolved_snapshot(self) -> list[dict]:
        """Return collected unresolved entries (for inspection/testing)."""
        return list(self._unresolved)
