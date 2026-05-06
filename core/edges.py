"""
Edge types for the BGI graph.

GHOST     — inferred, low confidence (<0.5). Exists but not trusted.
PREDICTED — immune memory predicted this edge (0.5–0.99). Act on it.
HARD      — confirmed, high confidence (≥0.99). Treat as ground truth.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from bgi.core.cov import COV

EdgeType = Literal["GHOST", "PREDICTED", "HARD"]


@dataclass
class BGIEdge:
    source_id: str          # unit_id of the key unit
    target_id: str          # unit_id of the lock unit
    key_token: COV          # the token on the source side
    lock_token: COV         # the complementary token on the target side
    confidence: float       # 0.0–1.0
    edge_type: EdgeType     # GHOST | PREDICTED | HARD
    provenance: str         # how this edge was found

    @property
    def is_actionable(self) -> bool:
        """PREDICTED and HARD edges are actionable. GHOST edges wait."""
        return self.edge_type in ("PREDICTED", "HARD")

    def __repr__(self) -> str:
        return (
            f"BGIEdge({self.source_id!r} --[{self.key_token}↔{self.lock_token}]--> "
            f"{self.target_id!r}, {self.edge_type}, conf={self.confidence:.2f})"
        )
