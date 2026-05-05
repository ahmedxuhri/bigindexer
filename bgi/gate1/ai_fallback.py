"""
Gate 1 — AI fallback classifier (Position 1 AI).
Fires only for call_expression nodes that no Tier 1-4 rule matched.
Returns (COV, confidence) or None if AI declines to classify.
"""
from __future__ import annotations

import json
from pathlib import Path
from tree_sitter import Node

from bgi.core.cov import COV
from bgi.gate1.rules import node_text


# Tokens AI is allowed to assign for ambiguous call nodes
_CLASSIFIABLE = {
    COV.TRANSFORM, COV.PERSIST, COV.FETCH, COV.MUTATE,
    COV.VALIDATE, COV.LOG, COV.MEASURE, COV.EMIT, COV.SUBSCRIBE,
    COV.ROUTE, COV.DELEGATE,
}

# Where unresolved call snippets are accumulated for curator consumption
_DEFAULT_LOG = Path("bgi-unresolved.jsonl")


class AIFallback:
    """
    Wraps an LLM to classify ambiguous AST nodes.
    Disabled by default — set enabled=True and provide a client.
    In v0, returns None (unknown) for all nodes. Logged for future training.
    """

    def __init__(self, enabled: bool = False, client=None, log_path: Path | None = None):
        self.enabled = enabled
        self.client = client
        self._log_path = log_path or _DEFAULT_LOG
        self._unresolved: list[str] = []  # in-memory buffer; flushed on flush()

    def classify(self, call_node: Node, context_snippet: str = "") -> tuple[COV, float] | None:
        """
        Attempt to classify an unmatched call node.
        Returns (COV token, confidence) or None.
        """
        callee_text = node_text(call_node)[:120]
        self._unresolved.append(callee_text)

        if not self.enabled or self.client is None:
            return None

        prompt = (
            "You are classifying a Python code operation into exactly one of these "
            f"semantic tokens: {[str(t) for t in _CLASSIFIABLE]}.\n\n"
            f"Code snippet:\n```python\n{context_snippet or callee_text}\n```\n\n"
            "Reply with ONLY the token name and a confidence 0.0-1.0, "
            "separated by a space. Example: FETCH 0.82\n"
            "If you cannot classify, reply: UNKNOWN 0.0"
        )

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=16,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip().split()
            if len(raw) != 2:
                return None
            token_str, conf_str = raw
            if token_str == "UNKNOWN":
                return None
            token = COV(token_str)
            if token not in _CLASSIFIABLE:
                return None
            return (token, float(conf_str))
        except Exception:
            return None

    def flush(self, scan_run: str = "") -> int:
        """
        Append in-memory unresolved call snippets to the log file (JSONL).
        Returns number of entries written. Safe to call after every scan.
        """
        if not self._unresolved:
            return 0
        with self._log_path.open("a") as f:
            for snippet in self._unresolved:
                f.write(json.dumps({"snippet": snippet, "scan_run": scan_run}) + "\n")
        written = len(self._unresolved)
        self._unresolved.clear()
        return written

    def unresolved_snapshot(self) -> list[str]:
        """Return collected unresolved callee texts (for batch training later)."""
        return list(self._unresolved)
