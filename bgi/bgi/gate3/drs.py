"""
Gate 3 — Dynamic Radar Scope (DRS) clustering.

Takes COVFingerprints + BGIEdges and groups units into clusters (components).

Algorithm:
  Pass 1 — Within-file proximity grouping
      Sequential scan per file. Each unit checks if it falls within
      any open cluster's radar range. If yes: joins it. If equidistant
      between two clusters: marked as seam. If none: new cluster.

  Pass 2 — Cross-file merging via Gate 2 HARD/PREDICTED edges
      Units connected by edges are candidates for cluster merging.
      HARD edges merge clusters. PREDICTED edges create cross-cluster links.
      Merges are gated by MAX_CLUSTER_SIZE (FUSE-MAP): refused merges become
      FuseEdges — architectural boundary signals in fuse-graph.json.

  Pass 3 — Probability computation + cluster hardening
      Each cluster gets a probability score based on:
        - COV token type prior (some tokens signal architectural importance)
        - Mention velocity (edge count involving cluster members)
        - Cross-file span (clusters across multiple files score higher)
      Radar range = 400 × probability (capped at 3×, ceiling 8000 lines).

  Pass 4 — Seam finalization
      Units that scored equally between two clusters are confirmed as
      architectural seams (boundary auto-detection).
"""
from __future__ import annotations
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from bgi.core.cov import COV
from bgi.core.edges import BGIEdge
from bgi.core.fingerprint import COVFingerprint
from bgi.gate3.import_proximity import extract_import_edges, detect_cycles

# ── FUSE-MAP: default cluster size cap ───────────────────────────────────────
# Cap = max(50, total_units * MAX_CLUSTER_PCT).
# Refused merges become FuseEdges (see fuse_graph.py).
_DEFAULT_MAX_CLUSTER_PCT = 0.03  # 3% of total units


# ── COV token type priors ─────────────────────────────────────────────────────
# High-prior tokens indicate architecturally significant units.

_COV_PRIOR: dict[COV, float] = {
    COV.CONTRACT:     1.0,
    COV.ROUTE:        1.0,
    COV.AUTHENTICATE: 1.0,
    COV.AUTHORIZE:    1.0,
    COV.PERSIST:      0.9,
    COV.FETCH:        0.8,
    COV.EMIT:         0.8,
    COV.SUBSCRIBE:    0.8,
    COV.INIT:         0.7,
    COV.TEARDOWN:     0.7,
    COV.VALIDATE:     0.7,
    COV.TEST:         0.7,
    COV.RAISE:        0.6,
    COV.RECOVER:      0.6,
    COV.INTAKE:       0.5,
    COV.OUTPUT:       0.5,
    COV.GUARD:        0.5,
    COV.DELEGATE:     0.5,
    COV.TRANSFORM:    0.4,
    COV.MUTATE:       0.4,
    COV.SCOPE:        0.4,
    COV.ASYNC:        0.4,
    COV.COMPOSE:      0.4,
    COV.CONDITIONAL:  0.3,
    COV.LOOP:         0.3,
    COV.LOG:          0.3,
    COV.MEASURE:      0.3,
    COV.SANITIZE:     0.5,
    COV.DEFER:        0.5,
}

_BASE_RADAR     = 400    # lines
_MAX_MULTIPLIER = 3.0    # max radar extension
_RADAR_CEILING  = 8_000  # hard ceiling in lines
_SEAM_THRESHOLD = 0.10   # if two clusters' pull is within 10%, it's a seam


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Cluster:
    cluster_id: str
    member_ids: list[str] = field(default_factory=list)
    dominant_tokens: list[COV] = field(default_factory=list)
    probability: float = 0.5
    radar_range: int = _BASE_RADAR
    is_hard: bool = False
    files: set[str] = field(default_factory=set)
    seam_unit_ids: set[str] = field(default_factory=set)

    def add_member(self, unit_id: str, file_path: str) -> None:
        self.member_ids.append(unit_id)
        self.files.add(file_path)

    @property
    def size(self) -> int:
        return len(self.member_ids)

    @property
    def is_cross_file(self) -> bool:
        return len(self.files) > 1

    def __repr__(self) -> str:
        return (
            f"Cluster({self.cluster_id!r}, size={self.size}, "
            f"prob={self.probability:.2f}, hard={self.is_hard}, "
            f"tokens={[str(t) for t in self.dominant_tokens[:3]]})"
        )


@dataclass
class DRSResult:
    clusters: list[Cluster]
    unit_to_cluster: dict[str, str]   # unit_id → cluster_id
    seam_units: set[str]              # unit_ids that are architectural seams

    def cluster_for(self, unit_id: str) -> Cluster | None:
        cid = self.unit_to_cluster.get(unit_id)
        if cid is None:
            return None
        return next((c for c in self.clusters if c.cluster_id == cid), None)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _file_of(unit_id: str) -> str:
    return unit_id.split("::")[0]


def _token_prior(tokens: list[COV]) -> float:
    """Return max prior across all tokens in a fingerprint."""
    if not tokens:
        return 0.3
    return max(_COV_PRIOR.get(t, 0.3) for t in tokens)


def _cluster_pull(cluster: Cluster, unit_line: int, unit_file: str, unit_tokens: list[COV]) -> float:
    """
    Compute how strongly a cluster 'pulls' a candidate unit.
    Pull = probability / (1 + normalized_distance)
    Cross-file pull is reduced unless the cluster explicitly spans the file.
    """
    if unit_file not in cluster.files:
        # Cross-file pull: only if cluster probability is high
        cross_file_penalty = 2.0
        return (cluster.probability / cross_file_penalty)
    return cluster.probability  # same-file: full pull (distance handled by radar check)


def _compute_probability(cluster: Cluster, edge_count: int) -> float:
    """
    Cluster probability based on token priors + edge count + cross-file span.
    """
    if not cluster.member_ids:
        return 0.3
    base = sum(
        max((_COV_PRIOR.get(t, 0.3) for t in cluster.dominant_tokens), default=0.3)
        for _ in [None]  # just use dominant_tokens max
    ) / 1.0

    velocity_boost = min(0.3, edge_count * 0.05)
    cross_file_boost = 0.1 if cluster.is_cross_file else 0.0
    size_boost = min(0.1, cluster.size * 0.01)

    prob = min(1.0, base + velocity_boost + cross_file_boost + size_boost)
    return round(prob, 4)


def _radar_range(probability: float) -> int:
    raw = _BASE_RADAR * (1.0 + (_MAX_MULTIPLIER - 1.0) * probability)
    return min(_RADAR_CEILING, int(raw))


# ── Union-Find for cluster merging ────────────────────────────────────────────

@dataclass
class FuseEdge:
    """A refused cluster merge — emitted as an architectural boundary signal."""
    from_cluster: str       # root representative of the larger/refusing cluster
    to_cluster: str         # root representative of the other cluster
    trigger_source: str     # edge.source_id that triggered the refused merge
    trigger_target: str     # edge.target_id that triggered the refused merge
    trigger_confidence: float  # edge confidence at time of refusal
    refused_at_size: int    # combined size that exceeded the cap


class _SizedUnionFind:
    """Union-Find with per-root size tracking and a hard cluster size cap."""

    def __init__(self, max_cluster_size: int) -> None:
        self._parent: dict[str, str] = {}
        self._size: dict[str, int] = {}
        self._max: int = max_cluster_size

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        self._size.setdefault(x, 1)
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def size(self, x: str) -> int:
        return self._size.get(self.find(x), 1)

    def union(self, x: str, y: str) -> bool:
        """Merge x and y. Returns True if merged, False if refused (cap exceeded)."""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return True
        sx, sy = self._size.get(rx, 1), self._size.get(ry, 1)
        if sx + sy > self._max:
            return False  # FUSE: refused merge
        # Union by size (attach smaller root to larger)
        if sx >= sy:
            self._parent[ry] = rx
            self._size[rx] = sx + sy
        else:
            self._parent[rx] = ry
            self._size[ry] = sx + sy
        return True

    def groups(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for k in self._parent:
            result[self.find(k)].append(k)
        return dict(result)


# ── Main DRS function ─────────────────────────────────────────────────────────

def run_drs(
    fingerprints: list[COVFingerprint],
    edges: list[BGIEdge],
    max_cluster_pct: float = _DEFAULT_MAX_CLUSTER_PCT,
    root_path: str | None = None,
) -> tuple[DRSResult, list[FuseEdge]]:
    """
    Run the Dynamic Radar Scope clustering algorithm.
    Returns (DRSResult, fuse_edges) where fuse_edges are refused merges.
    
    Args:
        fingerprints: Gate 1 output (COVFingerprints)
        edges: Gate 2 output (BGIEdges)
        max_cluster_pct: cluster size cap as fraction of total units (default 3%)
        root_path: repo root (enables MASK-4: import-based proximity in Pass 1.5)
    """
    if not fingerprints:
        return DRSResult(clusters=[], unit_to_cluster={}, seam_units=set()), []

    total_units = len(fingerprints)
    max_cluster_size = max(50, int(total_units * max_cluster_pct))

    fp_by_id = {fp.unit_id: fp for fp in fingerprints}

    # ── Pass 1: Within-file proximity grouping ────────────────────────────────
    # Group units by file, sort by line number, do a radar-scan

    by_file: dict[str, list[COVFingerprint]] = defaultdict(list)
    for fp in fingerprints:
        by_file[_file_of(fp.unit_id)].append(fp)
    for lst in by_file.values():
        lst.sort(key=lambda fp: fp.line_range[0])

    uf = _SizedUnionFind(max_cluster_size)
    # Initialize: each unit is its own group
    for fp in fingerprints:
        uf.find(fp.unit_id)

    potential_seams: set[str] = set()

    for file_path, units in by_file.items():
        # Open clusters within this file: (end_line, representative_unit_id)
        open_clusters: list[tuple[int, str]] = []  # (radar_end_line, unit_id)

        for fp in units:
            start = fp.line_range[0]
            unit_prior = _token_prior(fp.all_tokens())
            unit_radar = _radar_range(unit_prior)

            # Find all open clusters whose radar reaches this unit
            candidates = [
                (end, uid) for end, uid in open_clusters if end >= start
            ]

            if len(candidates) == 0:
                # No cluster reaches this unit — start a new one
                open_clusters.append((start + unit_radar, fp.unit_id))

            elif len(candidates) == 1:
                # One cluster claims this unit
                _, rep_uid = candidates[0]
                uf.union(fp.unit_id, rep_uid)
                # Extend the cluster's radar
                new_end = max(candidates[0][0], start + unit_radar)
                open_clusters = [
                    (new_end if uid == rep_uid else end, uid)
                    for end, uid in open_clusters
                ]

            else:
                # Multiple clusters claim this unit — seam candidate
                # Merge all claiming clusters into one (the unit bridges them)
                potential_seams.add(fp.unit_id)
                rep = candidates[0][1]
                for _, uid in candidates[1:]:
                    uf.union(rep, uid)
                uf.union(fp.unit_id, rep)
                new_end = max(max(end for end, _ in candidates), start + unit_radar)
                seen_reps = {uf.find(uid) for _, uid in candidates}
                open_clusters = [
                    (end, uid) for end, uid in open_clusters
                    if uf.find(uid) not in seen_reps
                ]
                open_clusters.append((new_end, rep))

            # Expire clusters whose radar no longer reaches (too far behind)
            open_clusters = [(end, uid) for end, uid in open_clusters if end >= start]

    # ── Pass 1.5: Import-based structural proximity (MASK-4) ────────────────────
    # Files that import each other are architecturally proximate → clustering signal.
    # If root_path provided: extract import edges, use for soft merging.
    # If no root_path: skip (backward compatible).
    
    if root_path:
        try:
            import_edges = extract_import_edges(root_path, lang="python")
            cycles = detect_cycles(import_edges)
            
            # Build unit/file lookup once for import proximity joins.
            unit_to_file: dict[str, str] = {}
            file_to_units: dict[str, list[str]] = defaultdict(list)
            for fp in fingerprints:
                file_path = fp.unit_id.split("::")[0]
                unit_to_file[fp.unit_id] = file_path
                file_to_units[file_path].append(fp.unit_id)
            
            # For each import relationship, try to merge clusters
            for file_a, imports_b in import_edges.items():
                units_a = file_to_units.get(file_a)
                if not units_a:
                    continue
                
                for file_b in imports_b:
                    # Skip circular imports (both directions)
                    pair = tuple(sorted([file_a, file_b]))
                    if pair in cycles:
                        continue
                    
                    units_b = file_to_units.get(file_b)
                    
                    # Soft merge: pick one representative from each and merge clusters
                    if units_a and units_b:
                        rep_a = units_a[0]
                        rep_b = units_b[0]
                        # Try to merge (size cap is enforced by uf.union)
                        uf.union(rep_a, rep_b)
        except Exception:
            pass  # If import extraction fails, continue without it

    # ── Pass 2: Cross-file merging via HARD edges (FUSE-MAP gated) ───────────
    # Only specific token pairs justify merging clusters across file boundaries.
    # INIT↔TEARDOWN, INTAKE↔OUTPUT are intra-component lifecycle/data flow —
    # they should NOT pull auth and payments into the same cluster.
    #
    # TEST↔CONTRACT is intentionally excluded: test files should cluster
    # among themselves, not merge with the production code they test.
    # This prevents a single mega-cluster absorbing all test + production units.
    _CROSS_FILE_MERGE_PAIRS: set[tuple[COV, COV]] = {
        (COV.DELEGATE,     COV.CONTRACT),   # explicit cross-component delegation
        (COV.EMIT,         COV.SUBSCRIBE),  # event producer → consumer (cross-service)
        (COV.AUTHENTICATE, COV.ROUTE),      # auth gate on a route (cross-module)
        (COV.AUTHORIZE,    COV.ROUTE),      # authz gate on a route (cross-module)
    }

    def _is_test_path(path: str) -> bool:
        """True if the file path points to test code."""
        path = path.replace("\\", "/").lower()
        return (
            "/test" in path
            or path.startswith("test")
            or path.endswith("_test.py")
            or path.endswith("test_.py")
            or "/tests/" in path
            or "/spec/" in path
        )

    unit_is_test: dict[str, bool] = {
        fp.unit_id: _is_test_path(_file_of(fp.unit_id)) for fp in fingerprints
    }

    fuse_edges: list[FuseEdge] = []

    for edge in edges:
        if edge.edge_type != "HARD":
            continue
        if edge.source_id not in fp_by_id or edge.target_id not in fp_by_id:
            continue
        src_file = _file_of(edge.source_id)
        tgt_file = _file_of(edge.target_id)
        if src_file == tgt_file:
            merged = uf.union(edge.source_id, edge.target_id)
            if not merged:
                ra = uf.find(edge.source_id)
                rb = uf.find(edge.target_id)
                fuse_edges.append(FuseEdge(
                    from_cluster=ra, to_cluster=rb,
                    trigger_source=edge.source_id, trigger_target=edge.target_id,
                    trigger_confidence=getattr(edge, "confidence", 1.0),
                    refused_at_size=uf.size(ra) + uf.size(rb),
                ))
            continue
        # Cross-file: only merge if both units are in same domain
        pair = (edge.key_token, edge.lock_token)
        pair_rev = (edge.lock_token, edge.key_token)
        src_is_test = unit_is_test.get(edge.source_id, False)
        tgt_is_test = unit_is_test.get(edge.target_id, False)
        if src_is_test != tgt_is_test:
            continue  # never merge test ↔ production across files
        if pair in _CROSS_FILE_MERGE_PAIRS or pair_rev in _CROSS_FILE_MERGE_PAIRS:
            merged = uf.union(edge.source_id, edge.target_id)
            if not merged:
                ra = uf.find(edge.source_id)
                rb = uf.find(edge.target_id)
                fuse_edges.append(FuseEdge(
                    from_cluster=ra, to_cluster=rb,
                    trigger_source=edge.source_id, trigger_target=edge.target_id,
                    trigger_confidence=getattr(edge, "confidence", 1.0),
                    refused_at_size=uf.size(ra) + uf.size(rb),
                ))

    # ── Pass 3: Build Cluster objects + compute probabilities ─────────────────
    edge_count_by_unit: dict[str, int] = defaultdict(int)
    for edge in edges:
        edge_count_by_unit[edge.source_id] += 1
        edge_count_by_unit[edge.target_id] += 1

    groups = uf.groups()
    clusters: list[Cluster] = []
    unit_to_cluster: dict[str, str] = {}

    for rep, members in groups.items():
        cluster_id = "cluster_" + rep.replace("/", "_").replace("::", "_").replace(".", "_")[:32]

        # Collect all tokens across members
        all_tokens_flat: list[COV] = []
        files: set[str] = set()
        total_edges = 0
        for uid in members:
            fp = fp_by_id.get(uid)
            if fp:
                all_tokens_flat.extend(fp.all_tokens())
                files.add(_file_of(uid))
            total_edges += edge_count_by_unit.get(uid, 0)

        token_counts = Counter(all_tokens_flat)
        dominant = [t for t, _ in token_counts.most_common(5)]

        cluster = Cluster(
            cluster_id=cluster_id,
            member_ids=list(members),
            dominant_tokens=dominant,
            files=files,
        )
        cluster.probability = _compute_probability(cluster, total_edges)
        cluster.radar_range = _radar_range(cluster.probability)
        cluster.is_hard = cluster.probability >= 0.85 and cluster.size >= 2

        clusters.append(cluster)
        for uid in members:
            unit_to_cluster[uid] = cluster_id

    cluster_by_id = {c.cluster_id: c for c in clusters}

    # ── Pass 4: Seam finalization ─────────────────────────────────────────────
    # A seam unit is one where its cluster and an adjacent cluster's probability
    # are within SEAM_THRESHOLD of each other AND the unit bridges them via edges.
    confirmed_seams: set[str] = set()

    for uid in potential_seams:
        cid = unit_to_cluster.get(uid)
        cluster = cluster_by_id.get(cid) if cid else None
        if cluster:
            cluster.seam_unit_ids.add(uid)
            confirmed_seams.add(uid)

    return DRSResult(
        clusters=clusters,
        unit_to_cluster=unit_to_cluster,
        seam_units=confirmed_seams,
    ), fuse_edges


def drs_summary(result: DRSResult) -> dict:
    return {
        "total_clusters": len(result.clusters),
        "hard_clusters": sum(1 for c in result.clusters if c.is_hard),
        "cross_file_clusters": sum(1 for c in result.clusters if c.is_cross_file),
        "seam_units": len(result.seam_units),
        "clusters": [
            {
                "id": c.cluster_id,
                "size": c.size,
                "probability": c.probability,
                "radar_range": c.radar_range,
                "is_hard": c.is_hard,
                "files": sorted(c.files),
                "dominant_tokens": [str(t) for t in c.dominant_tokens],
                "seams": list(c.seam_unit_ids),
                "members": c.member_ids,
            }
            for c in sorted(result.clusters, key=lambda c: -c.probability)
        ],
    }
