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

from bgi.core.cov import COV
from bgi.core.edges import BGIEdge
from bgi.core.fingerprint import COVFingerprint


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

class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        self._parent[self.find(x)] = self.find(y)

    def groups(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for k in self._parent:
            result[self.find(k)].append(k)
        return dict(result)


# ── Main DRS function ─────────────────────────────────────────────────────────

def run_drs(
    fingerprints: list[COVFingerprint],
    edges: list[BGIEdge],
) -> DRSResult:
    """
    Run the Dynamic Radar Scope clustering algorithm.
    Returns a DRSResult with clusters, unit→cluster mapping, and seam units.
    """
    if not fingerprints:
        return DRSResult(clusters=[], unit_to_cluster={}, seam_units=set())

    fp_by_id = {fp.unit_id: fp for fp in fingerprints}

    # ── Pass 1: Within-file proximity grouping ────────────────────────────────
    # Group units by file, sort by line number, do a radar-scan

    by_file: dict[str, list[COVFingerprint]] = defaultdict(list)
    for fp in fingerprints:
        by_file[_file_of(fp.unit_id)].append(fp)
    for lst in by_file.values():
        lst.sort(key=lambda fp: fp.line_range[0])

    uf = _UnionFind()
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

    # ── Pass 1.5: Namespace clustering ───────────────────────────────────────
    # Units in the same subdirectory that share a dominant high-prior token
    # are likely part of the same component (e.g. security/, middleware/).
    # Merge their clusters cross-file when they share a token with prior ≥ 0.7.

    _NAMESPACE_THRESHOLD = 0.7   # minimum token prior to trigger namespace merge
    _NAMESPACE_MIN_SHARED = 1    # minimum number of shared high-prior tokens

    def _subdir(unit_id: str) -> str:
        """Return the immediate parent directory of a unit, or '' for root."""
        parts = unit_id.split("::")[0].split("/")
        return parts[-2] if len(parts) >= 2 else ""

    # Group units by subdir
    by_subdir: dict[str, list[str]] = defaultdict(list)
    for fp in fingerprints:
        sd = _subdir(fp.unit_id)
        if sd:  # only non-root subdirs
            by_subdir[sd].append(fp.unit_id)

    # For each subdir with multiple files, check token overlap
    for subdir, unit_ids in by_subdir.items():
        # Collect high-prior tokens per unit
        unit_high_tokens: dict[str, set[COV]] = {}
        for uid in unit_ids:
            fp = fp_by_id.get(uid)
            if fp:
                high = {t for t in fp.all_tokens() if _COV_PRIOR.get(t, 0) >= _NAMESPACE_THRESHOLD}
                if high:
                    unit_high_tokens[uid] = high

        # Find units in different files that share high-prior tokens
        file_groups: dict[str, list[str]] = defaultdict(list)
        for uid in unit_high_tokens:
            file_groups[_file_of(uid)].append(uid)

        if len(file_groups) < 2:
            continue  # all in same file, already handled by Pass 1

        # Pick a representative from each file and check token overlap
        file_reps = [(f, uids[0]) for f, uids in file_groups.items()]
        for i, (fi, ui) in enumerate(file_reps):
            for fj, uj in file_reps[i + 1:]:
                shared = unit_high_tokens.get(ui, set()) & unit_high_tokens.get(uj, set())
                if len(shared) >= _NAMESPACE_MIN_SHARED:
                    uf.union(ui, uj)

    # ── Pass 2: Cross-file merging via HARD edges ─────────────────────────────
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

    def _is_test_unit(uid: str) -> bool:
        """True if the unit lives in a test file or test directory."""
        parts = uid.split("::")
        path = parts[0].replace("\\", "/").lower()
        return (
            "/test" in path
            or path.startswith("test")
            or path.endswith("_test.py")
            or path.endswith("test_.py")
            or "/tests/" in path
            or "/spec/" in path
        )

    for edge in edges:
        if edge.edge_type != "HARD":
            continue
        if edge.source_id not in fp_by_id or edge.target_id not in fp_by_id:
            continue
        src_file = _file_of(edge.source_id)
        tgt_file = _file_of(edge.target_id)
        if src_file == tgt_file:
            uf.union(edge.source_id, edge.target_id)
            continue
        # Cross-file: only merge if both units are in same domain
        # (both test OR both production) AND pair is a merge-worthy pattern
        pair = (edge.key_token, edge.lock_token)
        pair_rev = (edge.lock_token, edge.key_token)
        src_is_test = _is_test_unit(edge.source_id)
        tgt_is_test = _is_test_unit(edge.target_id)
        if src_is_test != tgt_is_test:
            continue  # never merge test ↔ production across files
        if pair in _CROSS_FILE_MERGE_PAIRS or pair_rev in _CROSS_FILE_MERGE_PAIRS:
            uf.union(edge.source_id, edge.target_id)

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

    # ── Pass 4: Seam finalization ─────────────────────────────────────────────
    # A seam unit is one where its cluster and an adjacent cluster's probability
    # are within SEAM_THRESHOLD of each other AND the unit bridges them via edges.
    confirmed_seams: set[str] = set()

    for uid in potential_seams:
        cid = unit_to_cluster.get(uid)
        cluster = next((c for c in clusters if c.cluster_id == cid), None)
        if cluster:
            cluster.seam_unit_ids.add(uid)
            confirmed_seams.add(uid)

    return DRSResult(
        clusters=clusters,
        unit_to_cluster=unit_to_cluster,
        seam_units=confirmed_seams,
    )


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
