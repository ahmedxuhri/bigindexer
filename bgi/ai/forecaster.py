"""
AI Position 2 — Resurrection Forecaster.

Reads OddGroups from the SEP and predicts:
  1. Which external module / namespace is most likely to provide the missing lock.
  2. Whether the suspended edge is likely an INTENTIONAL_BOUNDARY (cross-stack gap by design).
  3. A suggested COV token for the phantom unit that should satisfy the lock.

Output is a list of ResurrectionForecast objects.
These are written back to the SEP as annotations and can be surfaced in the output graph.

Design:
  - Disabled by default (no API key required to run BGI).
  - When enabled, batches all OddGroups into a single LLM call to minimise cost.
  - Confidence from AI is folded into provenance metadata, not used to raise edge confidence
    (AI Position 2 is advisory, not authoritative — Gate 2 remains the source of truth).
  - Falls back to heuristic-only mode when disabled.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bgi.core.cov import COV, LOCK_MAP
from bgi.sep.pool import OddGroup


# ── Output types ──────────────────────────────────────────────────────────────

@dataclass
class ResurrectionForecast:
    """
    Prediction for one OddGroup's unresolved suspended edges.
    """
    token: COV                       # the unresolved key token
    member_ids: list[str]            # source units that are suspended
    predicted_module: str            # e.g. "payment_service", "external.api"
    predicted_lock_token: COV        # token the missing unit likely has
    confidence: float                # 0.0–1.0
    is_boundary: bool                # True → likely INTENTIONAL_BOUNDARY
    reasoning: str                   # short explanation
    source: str                      # "heuristic" | "ai"


# ── Heuristics (always run, no API required) ──────────────────────────────────

# For each outward key token, what lock token are we most likely missing?
# This mirrors KEY_LOCK_PAIRS but gives a directional "best guess".
_LIKELY_LOCK: dict[COV, COV] = {
    COV.FETCH:         COV.PERSIST,
    COV.EMIT:          COV.SUBSCRIBE,
    COV.PERSIST:       COV.FETCH,
    COV.DELEGATE:      COV.CONTRACT,
    COV.ROUTE:         COV.AUTHENTICATE,
}

# Patterns in unit_id / raw_callee that hint at cross-stack boundaries
_BOUNDARY_PATTERNS = [
    r"external\.",
    r"third.party",
    r"vendor\.",
    r"sdk\.",
    r"\bapi\b",
    r"\bclient\b",
    r"\.io\b",
]
_BOUNDARY_RE = re.compile("|".join(_BOUNDARY_PATTERNS), re.IGNORECASE)

# Module name extraction heuristic: take the first segment of the callee
# e.g. "payment_service.py::PaymentGateway::charge" → "payment_service"
def _extract_module(source_id: str) -> str:
    return source_id.split("::")[0].replace(".py", "").replace("/", ".").strip()


def _heuristic_forecast(group: OddGroup) -> ResurrectionForecast:
    lock_tok = _LIKELY_LOCK.get(group.token, COV.CONTRACT)

    # Boundary check: scan pattern AND any member source_id
    boundary_signals = [group.pattern] + group.member_ids
    is_boundary = (
        any(_BOUNDARY_RE.search(s) for s in boundary_signals)
        or group.is_boundary
    )

    # Infer probable module from majority source_id pattern
    modules = [_extract_module(uid) for uid in group.member_ids]
    # Most common module name (crude majority vote)
    module_votes: dict[str, int] = {}
    for m in modules:
        module_votes[m] = module_votes.get(m, 0) + 1
    predicted_module = max(module_votes, key=module_votes.__getitem__, default="unknown")

    confidence = 0.4 if is_boundary else 0.55

    reasoning = (
        f"{group.count} unit(s) emit {group.token} with no current lock. "
        f"Expected lock: {lock_tok}. "
        + ("Looks like a cross-stack boundary — consider adding INTENTIONAL_BOUNDARY annotation."
           if is_boundary else
           f"Predicted missing module: '{predicted_module}'.")
    )

    return ResurrectionForecast(
        token=group.token,
        member_ids=group.member_ids,
        predicted_module=predicted_module,
        predicted_lock_token=lock_tok,
        confidence=confidence,
        is_boundary=is_boundary,
        reasoning=reasoning,
        source="heuristic",
    )


# ── Forecaster ────────────────────────────────────────────────────────────────

class ResurrectionForecaster:
    """
    AI Position 2.

    Usage:
        forecaster = ResurrectionForecaster(enabled=True, client=anthropic_client)
        forecasts = forecaster.forecast(pool.odd_groups())
    """

    def __init__(self, enabled: bool = False, client=None):
        self.enabled = enabled
        self.client = client

    def forecast(self, groups: list[OddGroup]) -> list[ResurrectionForecast]:
        """
        Produce forecasts for all OddGroups.
        Heuristics always run first. AI refines when enabled.
        """
        if not groups:
            return []

        # Step 1: heuristic baseline for every group
        forecasts = [_heuristic_forecast(g) for g in groups]

        # Step 2: AI refinement (single batched call)
        if self.enabled and self.client is not None:
            try:
                forecasts = self._ai_refine(groups, forecasts)
            except Exception as exc:
                # AI failure is non-fatal; heuristics remain
                for f in forecasts:
                    f.reasoning += f" [AI unavailable: {exc}]"

        return forecasts

    def _ai_refine(
        self,
        groups: list[OddGroup],
        heuristics: list[ResurrectionForecast],
    ) -> list[ResurrectionForecast]:
        """
        Send all OddGroups to the LLM in one batched prompt.
        Parse structured response and merge with heuristic baseline.
        """
        from bgi.core.cov import COV  # local import keeps module importable without anthropic

        items_text = "\n".join(
            f"{i+1}. token={g.token} count={g.count} "
            f"sources={g.member_ids[:3]} "
            f"oldest_age_hours={g.oldest_age_s/3600:.1f} "
            f"already_boundary={g.is_boundary}"
            for i, g in enumerate(groups)
        )

        prompt = (
            "You are an architecture analyst for a code intelligence system called BGI.\n"
            "Each item below is an 'OddGroup' — a cluster of code units that emit an outward "
            "semantic token (e.g. FETCH, EMIT, DELEGATE) but have no matching lock in the "
            "current codebase scan. Your job is to predict:\n"
            "  - predicted_module: the most likely module/service that provides the missing lock\n"
            "  - predicted_lock: the COV token the missing unit likely has\n"
            "  - is_boundary: true if this is likely an INTENTIONAL cross-stack boundary\n"
            "  - confidence: 0.0–1.0\n"
            "  - reasoning: 1-sentence explanation\n\n"
            f"OddGroups:\n{items_text}\n\n"
            "Reply with exactly one JSON array, one object per item, in order. "
            "Use this schema per object:\n"
            '{"predicted_module": str, "predicted_lock": str, "is_boundary": bool, '
            '"confidence": float, "reasoning": str}\n'
            "Only output the JSON array, nothing else."
        )

        response = self.client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()

        import json
        parsed = json.loads(raw)

        refined = []
        for i, (group, base, item) in enumerate(zip(groups, heuristics, parsed)):
            try:
                lock_str = item.get("predicted_lock", str(base.predicted_lock_token)).split(".")[-1]
                lock_tok = COV[lock_str]
            except (KeyError, AttributeError):
                lock_tok = base.predicted_lock_token

            refined.append(ResurrectionForecast(
                token=group.token,
                member_ids=group.member_ids,
                predicted_module=item.get("predicted_module", base.predicted_module),
                predicted_lock_token=lock_tok,
                confidence=float(item.get("confidence", base.confidence)),
                is_boundary=bool(item.get("is_boundary", base.is_boundary)),
                reasoning=item.get("reasoning", base.reasoning),
                source="ai",
            ))

        return refined


# ── Serialization ─────────────────────────────────────────────────────────────

def forecasts_to_dict(forecasts: list[ResurrectionForecast]) -> list[dict]:
    return [
        {
            "token": str(f.token),
            "member_ids": f.member_ids,
            "predicted_module": f.predicted_module,
            "predicted_lock_token": str(f.predicted_lock_token),
            "confidence": f.confidence,
            "is_boundary": f.is_boundary,
            "reasoning": f.reasoning,
            "source": f.source,
        }
        for f in forecasts
    ]
