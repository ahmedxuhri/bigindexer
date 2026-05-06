"""
COVFingerprint — the output of Gate 1 for a single code unit (function/method).
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from typing import Literal

from bgi.core.cov import COV


SourceType = Literal["deterministic", "ai_classified", "composite"]
EdgeType   = Literal["GHOST", "PREDICTED", "HARD"]


@dataclass
class COVFingerprint:
    unit_id: str
    """Stable identifier: 'path/to/file.py::ClassName::method_name'"""

    tokens: list[COV]
    """Ordered COV tokens detected in the function body (method-level only)."""

    class_context: list[COV]
    """Class-level COV tokens (from Tier 5 base-class matching).
    Kept separate — NOT injected into tokens. Consulted during Gate 2 matching."""

    confidence: float
    """0.0–1.0. 1.0 = fully deterministic. <1.0 = AI-assisted or composite."""

    source: SourceType
    """How this fingerprint was produced."""

    language: str
    """e.g. 'python', 'typescript'"""

    line_range: tuple[int, int]
    """(start_line, end_line) in source file — 1-indexed."""

    fingerprint_hash: str = field(init=False)
    """hash(unit_id + token sequence) — fast lookup key."""

    def __post_init__(self) -> None:
        token_str = ":".join(self.tokens)
        self.fingerprint_hash = hashlib.sha256(
            f"{self.unit_id}|{token_str}".encode()
        ).hexdigest()[:16]

    def has_token(self, token: COV) -> bool:
        return token in self.tokens

    def has_class_token(self, token: COV) -> bool:
        return token in self.class_context

    def all_tokens(self) -> list[COV]:
        """Method tokens + class context combined (for DRS/quality use only)."""
        seen: set[COV] = set()
        result: list[COV] = []
        for t in self.tokens + self.class_context:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result

    def __repr__(self) -> str:
        return (
            f"COVFingerprint({self.unit_id!r}, "
            f"tokens={[str(t) for t in self.tokens]}, "
            f"confidence={self.confidence:.2f}, "
            f"hash={self.fingerprint_hash!r})"
        )
