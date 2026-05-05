"""
COV — Canonical Operation Vocabulary
28 core tokens split into edge-forming (Gate 2) and characterization (Gate 3/DRS).
"""
from __future__ import annotations
from enum import Enum


class COV(str, Enum):
    # ── Data Flow ─────────────────────────────────────────────────────────────
    INTAKE    = "INTAKE"
    OUTPUT    = "OUTPUT"
    TRANSFORM = "TRANSFORM"
    MUTATE    = "MUTATE"
    SANITIZE  = "SANITIZE"    # composite: GUARD + TRANSFORM internally

    # ── Control Flow ──────────────────────────────────────────────────────────
    CONDITIONAL = "CONDITIONAL"
    LOOP        = "LOOP"
    GUARD       = "GUARD"
    ROUTE       = "ROUTE"
    SCOPE       = "SCOPE"

    # ── State ─────────────────────────────────────────────────────────────────
    FETCH   = "FETCH"
    PERSIST = "PERSIST"

    # ── Communication ─────────────────────────────────────────────────────────
    EMIT      = "EMIT"
    SUBSCRIBE = "SUBSCRIBE"
    DELEGATE  = "DELEGATE"

    # ── Structure ─────────────────────────────────────────────────────────────
    CONTRACT = "CONTRACT"
    COMPOSE  = "COMPOSE"
    INIT     = "INIT"
    TEARDOWN = "TEARDOWN"

    # ── Error ─────────────────────────────────────────────────────────────────
    RAISE   = "RAISE"
    RECOVER = "RECOVER"
    DEFER   = "DEFER"

    # ── Cross-cutting ─────────────────────────────────────────────────────────
    AUTHENTICATE = "AUTHENTICATE"
    AUTHORIZE    = "AUTHORIZE"
    VALIDATE     = "VALIDATE"
    LOG          = "LOG"
    MEASURE      = "MEASURE"
    ASYNC        = "ASYNC"

    # ── Testing ───────────────────────────────────────────────────────────────
    TEST = "TEST"


# ── Key-Lock Pairs ────────────────────────────────────────────────────────────
# Edge-forming tokens only. Each tuple is (key, lock).
# Multi-pairs share one side — BGI emits an edge on ANY match.
KEY_LOCK_PAIRS: list[tuple[COV, COV]] = [
    (COV.INTAKE,       COV.OUTPUT),
    (COV.FETCH,        COV.PERSIST),
    (COV.EMIT,         COV.SUBSCRIBE),
    (COV.RAISE,        COV.RECOVER),
    (COV.INIT,         COV.TEARDOWN),
    (COV.INIT,         COV.DEFER),       # what's initialized must be deferred
    (COV.TEST,         COV.CONTRACT),
    (COV.VALIDATE,     COV.INTAKE),
    (COV.SANITIZE,     COV.INTAKE),
    (COV.GUARD,        COV.CONTRACT),    # multi-pair
    (COV.GUARD,        COV.INTAKE),      # multi-pair
    (COV.AUTHENTICATE, COV.ROUTE),
    (COV.AUTHORIZE,    COV.ROUTE),
    (COV.DELEGATE,     COV.CONTRACT),
]

# Characterization tokens — Gate 3 / DRS / quality scoring only (no key-lock)
CHARACTERIZATION_TOKENS: frozenset[COV] = frozenset({
    COV.TRANSFORM,
    COV.MUTATE,
    COV.SCOPE,
    COV.CONDITIONAL,
    COV.LOOP,
    COV.ASYNC,
    COV.COMPOSE,
    COV.LOG,
    COV.MEASURE,
})

# Build fast lookup: token → set of tokens it locks with
def _build_lock_map() -> dict[COV, set[COV]]:
    lock_map: dict[COV, set[COV]] = {}
    for key, lock in KEY_LOCK_PAIRS:
        lock_map.setdefault(key, set()).add(lock)
        lock_map.setdefault(lock, set()).add(key)
    return lock_map

LOCK_MAP: dict[COV, set[COV]] = _build_lock_map()


def locks_with(token: COV) -> set[COV]:
    """Return all tokens that form an edge with the given token."""
    return LOCK_MAP.get(token, set())


def is_edge_forming(token: COV) -> bool:
    return token not in CHARACTERIZATION_TOKENS
