"""
Gate 2 — Key-Lock matching.

Takes all COVFingerprints from Gate 1 and finds edges between units
where one unit's tokens complement another's (key ↔ lock).

SPECTRAL-MASKS (Step 3):
- If census provided: Run 3 independent spatially-scoped passes (Mask 1/2/3)
- If no census: Fall back to flat global matching (backward compatible)

Complexity: O(N × T × M) where T = avg tokens per unit, M = avg matches per token.
At scale, T and M are small constants — effectively linear in N.
Spectral passes reduce M by scope partitioning (3x–50x reduction in common cases).
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
import time
from typing import TYPE_CHECKING, Any

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
_MASK3_TOKEN_INDEX_CAP = 300
_PROCESS_POOL_MIN_FINGERPRINTS = 20000
_OUTWARD_TOKENS = {COV.DELEGATE, COV.FETCH, COV.EMIT, COV.PERSIST, COV.ROUTE}
_LAST_MATCH_PROFILE: dict[str, Any] = {}


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


# ── Spectral Mask Helpers ─────────────────────────────────────────────────────

@dataclass
class MaskIndex:
    """Token index scoped to a frequency band and spatial region."""
    band: str  # "Mask 1", "Mask 2", or "Mask 3"
    region: str | None  # None = global, "file" or "directory" for scoped
    token_index: dict[tuple[COV, str], list[COVFingerprint]]
    class_token_index: dict[tuple[COV, str, str | None], list[COVFingerprint]]


@dataclass
class MaskWorkItem:
    """Pre-grouped source fingerprint + tokens for one spectral mask."""
    fp: COVFingerprint
    tokens: tuple[COV, ...]
    file_path: str
    dir_path: str
    class_name: str | None


@dataclass
class MaskPassResult:
    """One mask pass execution result."""
    band: str
    edges: list[BGIEdge]
    suspended: list[SuspendedEdge]
    elapsed_ms: float
    partner_checks: int


def _set_last_match_profile(profile: dict[str, Any]) -> None:
    global _LAST_MATCH_PROFILE
    _LAST_MATCH_PROFILE = profile


def get_last_match_profile() -> dict[str, Any]:
    """Return profiling stats from the most recent match_fingerprints call."""
    return dict(_LAST_MATCH_PROFILE)


def _get_directory_path(unit_id: str) -> str:
    """Extract directory path (3 levels from root) from unit_id."""
    file_path = unit_id.split("::")[0]
    parts = file_path.split("/")
    # Take up to 3 parts from the beginning (prevents leaf-only issues)
    return "/".join(parts[:min(3, len(parts))])


def _get_file_path(unit_id: str) -> str:
    """Extract file path from unit_id."""
    return unit_id.split("::")[0]


def _is_class_scoped_pair(token_a: COV, token_b: COV) -> bool:
    canonical = (token_a, token_b) if (token_a, token_b) in _CLASS_SCOPED_PAIRS else (token_b, token_a)
    return canonical in _CLASS_SCOPED_PAIRS


def _prepare_mask_worksets(
    fingerprints: list[COVFingerprint],
    census: 'CensusResult',
) -> dict[str, list[MaskWorkItem]]:
    """
    Build per-mask worksets in a single pass over fingerprints/tokens.
    This avoids repeated full scans during mask index and pass setup.
    """
    worksets: dict[str, list[MaskWorkItem]] = {
        "Mask 1": [],
        "Mask 2": [],
        "Mask 3": [],
    }

    for fp in fingerprints:
        file_path = _get_file_path(fp.unit_id)
        dir_path = _get_directory_path(fp.unit_id)
        parts = fp.unit_id.split("::")
        class_name = parts[1] if len(parts) == 3 else None
        band_tokens: dict[str, list[COV]] = {"Mask 1": [], "Mask 2": [], "Mask 3": []}

        for token in fp.all_tokens():
            if not is_edge_forming(token):
                continue
            band = census.token_bands.get(token)
            if band in band_tokens:
                band_tokens[band].append(token)

        for band, tokens in band_tokens.items():
            if tokens:
                worksets[band].append(MaskWorkItem(
                    fp=fp,
                    tokens=tuple(tokens),
                    file_path=file_path,
                    dir_path=dir_path,
                    class_name=class_name,
                ))

    return worksets


def _build_mask_index(
    work_items: list[MaskWorkItem],
    band: str,
    scope: str | None = None,  # None=global, "file", or "directory"
) -> MaskIndex:
    """
    Build token index for a single mask (frequency band + spatial scope).
    
    Args:
        work_items: Pre-grouped work items for this band
        band: "Mask 1", "Mask 2", or "Mask 3"
        scope: None (global), "file", or "directory" scoping
    """
    token_index: dict[tuple[COV, str], list[COVFingerprint]] = {}
    class_token_index: dict[tuple[COV, str, str | None], list[COVFingerprint]] = {}
    cap = _MASK3_TOKEN_INDEX_CAP if band == "Mask 3" and scope == "file" else _TOKEN_INDEX_CAP

    for item in work_items:
        if scope == "file":
            region_key = item.file_path
        elif scope == "directory":
            region_key = item.dir_path
        else:
            region_key = "global"

        for token in item.tokens:
            key = (token, region_key)
            bucket = token_index.setdefault(key, [])
            if len(bucket) < cap:
                bucket.append(item.fp)
                class_key = (token, region_key, item.class_name)
                class_bucket = class_token_index.setdefault(class_key, [])
                if len(class_bucket) < cap:
                    class_bucket.append(item.fp)

    return MaskIndex(
        band=band,
        region=scope,
        token_index=token_index,
        class_token_index=class_token_index,
    )


def _run_mask_pass(
    work_items: list[MaskWorkItem],
    mask_index: MaskIndex,
) -> MaskPassResult:
    """
    Run matching pass for a single spectral mask.
    
    Returns:
        MaskPassResult with edges, suspended refs, and timing stats.
    """
    start = time.perf_counter()
    edge_rows: list[tuple[str, str, COV, COV, float, EdgeType, str]] = []
    suspended: list[SuspendedEdge] = []
    seen: set[tuple[str, str, COV, COV]] = set()
    partner_checks = 0
    scope_map: dict[str, tuple[str, str | None]] = {
        item.fp.unit_id: (item.file_path, item.class_name) for item in work_items
    }

    if not mask_index.token_index:
        return MaskPassResult(
            band=mask_index.band,
            edges=[],
            suspended=[],
            elapsed_ms=round((time.perf_counter() - start) * 1000.0, 3),
            partner_checks=0,
        )

    for item in work_items:
        fp_a = item.fp
        if mask_index.region == "file":
            region_a = item.file_path
        elif mask_index.region == "directory":
            region_a = item.dir_path
        else:
            region_a = "global"

        for token_a in item.tokens:
            complement_tokens = LOCK_MAP.get(token_a, set())
            if not complement_tokens:
                continue

            matched_any = False
            fanout = 0

            for lock_token in complement_tokens:
                if (
                    mask_index.region == "file"
                    and _is_class_scoped_pair(token_a, lock_token)
                    and item.class_name is not None
                ):
                    class_partners = mask_index.class_token_index.get(
                        (lock_token, region_a, item.class_name), []
                    )
                    module_partners = mask_index.class_token_index.get((lock_token, region_a, None), [])
                    if module_partners:
                        partners = class_partners + module_partners
                    else:
                        partners = class_partners
                else:
                    partners = mask_index.token_index.get((lock_token, region_a), [])

                for fp_b in partners:
                    if fanout >= _GLOBAL_FANOUT_CAP:
                        matched_any = True
                        break
                    if fp_b.unit_id == fp_a.unit_id:
                        continue
                    partner_checks += 1
                    
                    # Scope gate (same as original)
                    if _is_class_scoped_pair(token_a, lock_token):
                        file_a, class_a = scope_map.get(fp_a.unit_id, (item.file_path, item.class_name))
                        file_b, class_b = scope_map.get(fp_b.unit_id, (_get_file_path(fp_b.unit_id), None))
                        if file_a != file_b:
                            continue
                        if class_a is not None and class_b is not None and class_a != class_b:
                            continue
                    
                    key_tok, lk_tok = _directed(token_a, lock_token)
                    uid_pair = tuple(sorted([fp_a.unit_id, fp_b.unit_id]))
                    dedup_key = (uid_pair[0], uid_pair[1], key_tok, lk_tok)
                    matched_any = True
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    fanout += 1
                    
                    confidence = _edge_confidence(fp_a, fp_b)
                    edge_type = _classify_edge(confidence)
                    
                    if (token_a, lock_token) in _KEY_SIDE:
                        source_id, target_id = fp_a.unit_id, fp_b.unit_id
                    else:
                        source_id, target_id = fp_b.unit_id, fp_a.unit_id
                    
                    edge_rows.append((
                        source_id,
                        target_id,
                        key_tok,
                        lk_tok,
                        confidence,
                        edge_type,
                        f"gate2:spectral-{mask_index.band}:{fp_a.source}/{fp_b.source}",
                    ))
            
            if not matched_any and token_a in _OUTWARD_TOKENS:
                suspended.append(SuspendedEdge(
                    source_id=fp_a.unit_id,
                    token=token_a,
                    raw_callee=fp_a.unit_id,
                ))

    edges = [
        BGIEdge(
            source_id=source_id,
            target_id=target_id,
            key_token=key_tok,
            lock_token=lock_tok,
            confidence=confidence,
            edge_type=edge_type,
            provenance=provenance,
        )
        for source_id, target_id, key_tok, lock_tok, confidence, edge_type, provenance in edge_rows
    ]

    return MaskPassResult(
        band=mask_index.band,
        edges=edges,
        suspended=suspended,
        elapsed_ms=round((time.perf_counter() - start) * 1000.0, 3),
        partner_checks=partner_checks,
    )


def _union_edges(edge_lists: list[list[BGIEdge]]) -> list[BGIEdge]:
    """
    Union edges from multiple mask passes with deduplication.
    Uses (source_id, target_id, key_token, lock_token) as dedup key.
    """
    seen: set[tuple[str, str, COV, COV]] = set()
    result: list[BGIEdge] = []
    
    for edge_list in edge_lists:
        for edge in edge_list:
            dedup_key = (edge.source_id, edge.target_id, edge.key_token, edge.lock_token)
            if dedup_key not in seen:
                seen.add(dedup_key)
                result.append(edge)
    
    return result


# ── Main matching function ────────────────────────────────────────────────────

def match_fingerprints(
    fingerprints: list[COVFingerprint],
    census: 'CensusResult | None' = None,
) -> tuple[list[BGIEdge], list[SuspendedEdge]]:
    """
    Match all fingerprints against each other using the LOCK_MAP.
    
    If census is provided: Use SPECTRAL-MASKS (3 independent spatially-scoped passes).
    Otherwise: Use flat global matching (backward compatible).
    
    Args:
        fingerprints: Gate 1 output (COVFingerprints)
        census: Optional CensusResult from TOKEN-CENSUS (for SPECTRAL-MASKS)

    Returns:
        edges     — resolved BGIEdge list (GHOST / PREDICTED / HARD)
        suspended — unresolved references for the SEP
    """
    
    run_start = time.perf_counter()

    # ── SPECTRAL-MASKS (if census available) ──────────────────────────────────
    if census is not None:
        # Pre-group once to avoid repeated full-pass token scans.
        prepare_start = time.perf_counter()
        worksets = _prepare_mask_worksets(fingerprints, census)
        prepare_ms = round((time.perf_counter() - prepare_start) * 1000.0, 3)

        build_times: dict[str, float] = {}
        build_start = time.perf_counter()
        mask1 = _build_mask_index(worksets["Mask 1"], "Mask 1", scope=None)  # global
        build_times["Mask 1"] = round((time.perf_counter() - build_start) * 1000.0, 3)

        build_start = time.perf_counter()
        mask2 = _build_mask_index(worksets["Mask 2"], "Mask 2", scope="directory")  # dir
        build_times["Mask 2"] = round((time.perf_counter() - build_start) * 1000.0, 3)

        build_start = time.perf_counter()
        mask3 = _build_mask_index(worksets["Mask 3"], "Mask 3", scope="file")  # file
        build_times["Mask 3"] = round((time.perf_counter() - build_start) * 1000.0, 3)

        use_process_pool = len(fingerprints) >= _PROCESS_POOL_MIN_FINGERPRINTS
        executor_cls = ProcessPoolExecutor if use_process_pool else ThreadPoolExecutor

        # Run 3 passes in parallel
        with executor_cls(max_workers=3) as executor:
            futures = {
                "Mask 1": executor.submit(_run_mask_pass, worksets["Mask 1"], mask1),
                "Mask 2": executor.submit(_run_mask_pass, worksets["Mask 2"], mask2),
                "Mask 3": executor.submit(_run_mask_pass, worksets["Mask 3"], mask3),
            }
            pass_results = {band: future.result() for band, future in futures.items()}

        # Union edges with deduplication
        all_edges = _union_edges([
            pass_results["Mask 1"].edges,
            pass_results["Mask 2"].edges,
            pass_results["Mask 3"].edges,
        ])

        # Merge suspended (keep all, SEP dedupes)
        all_suspended = (
            pass_results["Mask 1"].suspended
            + pass_results["Mask 2"].suspended
            + pass_results["Mask 3"].suspended
        )

        _set_last_match_profile({
            "mode": "spectral",
            "executor": "process" if use_process_pool else "thread",
            "fingerprints": len(fingerprints),
            "prepare_worksets_ms": prepare_ms,
            "build_index_ms": build_times,
            "mask_match_ms": {band: result.elapsed_ms for band, result in pass_results.items()},
            "mask_work_items": {band: len(worksets[band]) for band in ("Mask 1", "Mask 2", "Mask 3")},
            "mask_edges": {band: len(result.edges) for band, result in pass_results.items()},
            "mask_partner_checks": {band: result.partner_checks for band, result in pass_results.items()},
            "total_edges": len(all_edges),
            "total_suspended": len(all_suspended),
            "total_ms": round((time.perf_counter() - run_start) * 1000.0, 3),
        })

        return all_edges, all_suspended
    
    # ── Flat global matching (fallback, no census) ────────────────────────────

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
                if token_a in _OUTWARD_TOKENS:
                    suspended.append(SuspendedEdge(
                        source_id=fp_a.unit_id,
                        token=token_a,
                        raw_callee=fp_a.unit_id,
                    ))

    _set_last_match_profile({
        "mode": "flat",
        "executor": "single",
        "fingerprints": len(fingerprints),
        "total_edges": len(edges),
        "total_suspended": len(suspended),
        "total_ms": round((time.perf_counter() - run_start) * 1000.0, 3),
    })

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
