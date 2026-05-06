"""
Gate 2 — Key-Lock matching.

Takes all COVFingerprints from Gate 1 and finds edges between units
where one unit's tokens complement another's (key ↔ lock).

Algorithm:
1. Build a token index: COV → [fingerprints that have this token]
2. For each fingerprint, for each of its edge-forming tokens,
   look up complements in the token index → create BGIEdge
3. Unresolved tokens (no lock found in the scan) → suspended edge list

Complexity: O(N × T × M) where T = avg tokens per unit, M = avg matches per token.
At scale, T and M are small constants — effectively linear in N.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bgi.core.cov import COV, LOCK_MAP, is_edge_forming, KEY_LOCK_PAIRS
from bgi.core.edges import BGIEdge, EdgeType
from bgi.core.fingerprint import COVFingerprint

if TYPE_CHECKING:
    from bgi.gate2.census import CensusResult


# ── Edge confidence thresholds ────────────────────────────────────────────────

def _edge_confidence(fp_a: COVFingerprint, fp_b: COVFingerprint) -> float:
    """
    Compute edge confidence from the two endpoint fingerprints.
    Base = min of their confidences.
    Boosts for locality (same file or same class).
    """
    base = min(fp_a.confidence, fp_b.confidence)

    # Same file boost
    file_a = fp_a.unit_id.split("::")[0]
    file_b = fp_b.unit_id.split("::")[0]
    if file_a == file_b:
        base = min(1.0, base + 0.05)

    # Same class boost
    parts_a = fp_a.unit_id.split("::")
    parts_b = fp_b.unit_id.split("::")
    if len(parts_a) == 3 and len(parts_b) == 3 and parts_a[1] == parts_b[1] and file_a == file_b:
        base = min(1.0, base + 0.05)

    return round(base, 4)


def _classify_edge(confidence: float) -> EdgeType:
    if confidence >= 0.85:
        return "HARD"
    if confidence >= 0.50:
        return "PREDICTED"
    return "GHOST"


# ── Key direction lookup ──────────────────────────────────────────────────────
# For each pair (key, lock), the KEY is the "source" token.
# Built from KEY_LOCK_PAIRS so direction is consistent.

_KEY_SIDE: set[tuple[COV, COV]] = {(k, l) for k, l in KEY_LOCK_PAIRS}


def _directed(token_a: COV, token_b: COV) -> tuple[COV, COV]:
    """Return (key_token, lock_token) in canonical direction."""
    if (token_a, token_b) in _KEY_SIDE:
        return token_a, token_b
    return token_b, token_a


# ── Scope constraints ─────────────────────────────────────────────────────────
# High-frequency token pairs that are only meaningful within a local scope.
# Pairing them globally (across all N units) produces O(N²) noise edges.
#
# INTAKE↔OUTPUT: nearly every function has params + return, so global pairing
# matches ~383×383 = 146k pairs. Restrict to same-class (methods that feed
# each other) or same-file for module-level functions.

_CLASS_SCOPED_PAIRS: set[tuple[COV, COV]] = {
    (COV.INTAKE, COV.OUTPUT),
    (COV.OUTPUT, COV.INTAKE),
    # GUARD (assert) appears in almost every function for type checking — scope it
    # to same-class so it doesn't pair all asserting functions globally
    (COV.GUARD, COV.INTAKE),
    (COV.INTAKE, COV.GUARD),
    (COV.GUARD, COV.CONTRACT),
    (COV.CONTRACT, COV.GUARD),
}

# ── Fan-out cap ───────────────────────────────────────────────────────────────
# When a token appears in more than this many units, matching it globally is
# O(N²). Instead of pairing every unit against every other, cap at the N most
# locally-similar units (prefer same-file, then same-directory).
#
# Benchmark (FastAPI, 4 509 units, Gate 2):
#   Before cap: 217k edges, 20.7s
#   After  cap: ~15k edges,  <1s
_GLOBAL_FANOUT_CAP = 100   # max partners emitted per (unit, token) combo
_TOKEN_INDEX_CAP   = 500   # if a token has >N entries, only keep first N per file group


def _same_scope(fp_a: COVFingerprint, fp_b: COVFingerprint) -> bool:
    """
    True if both fingerprints belong to the same class (for class methods)
    or the same file (for module-level functions).
    Used to gate high-frequency token pairs that produce noise when global.
    """
    parts_a = fp_a.unit_id.split("::")
    parts_b = fp_b.unit_id.split("::")
    if parts_a[0] != parts_b[0]:          # different files → always out
        return False
    if len(parts_a) == 3 and len(parts_b) == 3:
        return parts_a[1] == parts_b[1]   # both class methods → same class required
    return True                            # at least one is module-level → same file ok


# ── Suspended edge (unresolved reference) ────────────────────────────────────

@dataclass
class SuspendedEdge:
    """
    A token in a fingerprint that has no matching lock in the current scan.
    Handed off to the SEP (Suspended Edge Pool) for later resurrection.
    """
    source_id: str
    token: COV
    raw_callee: str  # best-effort callee name for pattern matching


# ── Main matching function ────────────────────────────────────────────────────

def match_fingerprints(
    fingerprints: list[COVFingerprint],
    census: 'CensusResult | None' = None,
) -> tuple[list[BGIEdge], list[SuspendedEdge]]:
    """
    Match all fingerprints against each other using the LOCK_MAP.
    
    Args:
        fingerprints: Gate 1 output (COVFingerprints)
        census: Optional CensusResult from TOKEN-CENSUS (used by Step 3: SPECTRAL-MASKS)

    Returns:
        edges     — resolved BGIEdge list (GHOST / PREDICTED / HARD)
        suspended — unresolved references for the SEP
    """

    # Build token index: token → list of fingerprints containing it
    # Use all_tokens() so class_context participates in matching
    token_index: dict[COV, list[COVFingerprint]] = {}
    for fp in fingerprints:
        for token in fp.all_tokens():
            if is_edge_forming(token):
                token_index.setdefault(token, []).append(fp)

    # Trim oversized token buckets to _TOKEN_INDEX_CAP entries.
    # Keep same-file entries first (most architecturally relevant), then others.
    for token, bucket in token_index.items():
        if len(bucket) > _TOKEN_INDEX_CAP:
            # Sort: same-file groups first (by file prefix), then truncate
            from collections import defaultdict as _dd
            by_file: dict[str, list[COVFingerprint]] = _dd(list)
            for fp in bucket:
                by_file[fp.unit_id.split("::")[0]].append(fp)
            trimmed: list[COVFingerprint] = []
            for fps_in_file in by_file.values():
                trimmed.extend(fps_in_file)
                if len(trimmed) >= _TOKEN_INDEX_CAP:
                    break
            token_index[token] = trimmed[:_TOKEN_INDEX_CAP]

    edges: list[BGIEdge] = []
    suspended: list[SuspendedEdge] = []

    # Track seen pairs to avoid duplicates
    # Key: frozenset of the two unit_ids + the token pair (direction-aware)
    seen: set[tuple[str, str, str, str]] = set()

    for fp_a in fingerprints:
        for token_a in fp_a.all_tokens():
            if not is_edge_forming(token_a):
                continue

            complement_tokens = LOCK_MAP.get(token_a, set())
            if not complement_tokens:
                continue

            matched_any = False
            fanout = 0  # per-(fp_a, token_a) edge count cap

            for lock_token in complement_tokens:
                partners = token_index.get(lock_token, [])
                for fp_b in partners:
                    if fanout >= _GLOBAL_FANOUT_CAP:
                        matched_any = True  # we have partners, just capped
                        break
                    if fp_b.unit_id == fp_a.unit_id:
                        continue

                    # Scope gate: high-frequency pairs only match within same class/file
                    canonical = (token_a, lock_token) if (token_a, lock_token) in _CLASS_SCOPED_PAIRS \
                                else (lock_token, token_a)
                    if canonical in _CLASS_SCOPED_PAIRS and not _same_scope(fp_a, fp_b):
                        continue

                    key_tok, lk_tok = _directed(token_a, lock_token)

                    # Canonical dedup key — order by unit_id to prevent A→B and B→A duplicates
                    uid_pair = tuple(sorted([fp_a.unit_id, fp_b.unit_id]))
                    dedup_key = (uid_pair[0], uid_pair[1], str(key_tok), str(lk_tok))
                    matched_any = True   # found a valid partner — mark before dedup check
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    fanout += 1

                    confidence = _edge_confidence(fp_a, fp_b)
                    edge_type  = _classify_edge(confidence)

                    # Determine canonical source/target from key direction
                    if (token_a, lock_token) in _KEY_SIDE:
                        source_id, target_id = fp_a.unit_id, fp_b.unit_id
                    else:
                        source_id, target_id = fp_b.unit_id, fp_a.unit_id

                    edges.append(BGIEdge(
                        source_id=source_id,
                        target_id=target_id,
                        key_token=key_tok,
                        lock_token=lk_tok,
                        confidence=confidence,
                        edge_type=edge_type,
                        provenance=f"gate2:tier1-5:{fp_a.source}/{fp_b.source}",
                    ))

            # If this edge-forming token found NO partners at all → suspend it
            if not matched_any:
                # Only suspend tokens that imply an outward reference
                _OUTWARD = {COV.DELEGATE, COV.FETCH, COV.EMIT, COV.PERSIST, COV.ROUTE}
                if token_a in _OUTWARD:
                    suspended.append(SuspendedEdge(
                        source_id=fp_a.unit_id,
                        token=token_a,
                        raw_callee=fp_a.unit_id,
                    ))

    return edges, suspended


def edges_summary(edges: list[BGIEdge]) -> dict:
    """Quick summary for logging/output."""
    by_type: dict[str, int] = {"HARD": 0, "PREDICTED": 0, "GHOST": 0}
    for e in edges:
        by_type[e.edge_type] += 1
    return {
        "total": len(edges),
        "by_type": by_type,
        "pairs": sorted({(e.key_token, e.lock_token) for e in edges},
                        key=lambda x: str(x)),
    }
