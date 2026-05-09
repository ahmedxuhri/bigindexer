"""Architecture context service for MCP tools."""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


def cluster_id_from_rep(rep: str) -> str:
    """
    Map a union-find representative unit id to BGI cluster id format.

    Must mirror Gate 3 logic in drs.py.
    """
    return "cluster_" + rep.replace("/", "_").replace("::", "_").replace(".", "_")[:32]


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


class ArchitectureContextService:
    """Query helper over BGI graph artifacts for MCP tools."""

    def __init__(
        self,
        graph_path: str = "bgi-graph.json",
        fuse_graph_path: str | None = None,
        index_db_path: str | None = None,
    ) -> None:
        self.graph_path = Path(graph_path)
        self.fuse_graph_path = Path(fuse_graph_path) if fuse_graph_path else self.graph_path.with_name("fuse-graph.json")
        self.index_db_path = Path(index_db_path) if index_db_path else None
        self._planner = None
        self.reload()

    def _load_graph(self) -> dict[str, Any]:
        if not self.graph_path.exists():
            raise FileNotFoundError(f"Graph file not found: {self.graph_path}")
        return json.loads(self.graph_path.read_text(encoding="utf-8"))

    def _load_fuse_graph(self) -> dict[str, Any]:
        if not self.fuse_graph_path.exists():
            return {"meta": {}, "boundary_clusters": [], "bridges": []}
        return json.loads(self.fuse_graph_path.read_text(encoding="utf-8"))

    def reload(self) -> dict[str, Any]:
        """Reload graph/fuse artifacts from disk."""
        self.graph = self._load_graph()
        self.fuse_graph = self._load_fuse_graph()

        self.units: list[dict[str, Any]] = self.graph.get("units", [])
        self.edges: list[dict[str, Any]] = self.graph.get("edges", [])
        self.clusters: list[dict[str, Any]] = self.graph.get("clusters", [])
        self.fuse_bridges: list[dict[str, Any]] = self.fuse_graph.get("bridges", [])

        self.unit_by_id: dict[str, dict[str, Any]] = {u["id"]: u for u in self.units if "id" in u}
        self.cluster_by_id: dict[str, dict[str, Any]] = {c["id"]: c for c in self.clusters if "id" in c}

        self.units_by_file: dict[str, list[str]] = defaultdict(list)
        self.cluster_ids_by_file: dict[str, set[str]] = defaultdict(set)
        for u in self.units:
            uid = u.get("id")
            if not uid:
                continue
            file_path = _normalize_path(uid.split("::", 1)[0])
            self.units_by_file[file_path].append(uid)
            cid = u.get("cluster")
            if cid:
                self.cluster_ids_by_file[file_path].add(cid)

        self.out_neighbors: dict[str, list[str]] = defaultdict(list)
        self.in_neighbors: dict[str, list[str]] = defaultdict(list)
        for e in self.edges:
            src = e.get("source")
            tgt = e.get("target")
            if not src or not tgt:
                continue
            self.out_neighbors[src].append(tgt)
            self.in_neighbors[tgt].append(src)

        return {
            "graph_path": str(self.graph_path),
            "fuse_graph_path": str(self.fuse_graph_path),
            "units": len(self.units),
            "edges": len(self.edges),
            "clusters": len(self.clusters),
            "fuse_bridges": len(self.fuse_bridges),
        }

    def _matching_files(self, file_path: str) -> list[str]:
        query = _normalize_path(file_path)
        if query in self.units_by_file:
            return [query]
        matches = [fp for fp in self.units_by_file if fp.endswith(query)]
        return sorted(matches)

    def _resolve_cluster_ids(self, file_or_cluster: str) -> set[str]:
        if file_or_cluster in self.cluster_by_id:
            return {file_or_cluster}
        cluster_ids: set[str] = set()
        for fp in self._matching_files(file_or_cluster):
            cluster_ids.update(self.cluster_ids_by_file.get(fp, set()))
        return cluster_ids

    def _cluster_view(self, cluster_id: str) -> dict[str, Any]:
        c = self.cluster_by_id[cluster_id]
        return {
            "id": c.get("id"),
            "size": c.get("size"),
            "probability": c.get("probability"),
            "is_hard": c.get("is_hard"),
            "is_cross_file": c.get("is_cross_file"),
            "dominant_tokens": c.get("dominant_tokens", []),
            "files": c.get("files", []),
            "member_count": len(c.get("members", [])),
        }

    def cluster_of_file(self, file_path: str) -> dict[str, Any]:
        """Return cluster info for a file path."""
        files = self._matching_files(file_path)
        if not files:
            return {"found": False, "file_path": file_path, "clusters": []}
        cluster_ids: set[str] = set()
        for fp in files:
            cluster_ids.update(self.cluster_ids_by_file.get(fp, set()))
        clusters = [self._cluster_view(cid) for cid in cluster_ids if cid in self.cluster_by_id]
        clusters.sort(key=lambda c: (c.get("size", 0), c.get("probability", 0.0)), reverse=True)
        return {
            "found": bool(clusters),
            "file_path": file_path,
            "matched_files": files,
            "cluster_count": len(clusters),
            "clusters": clusters,
        }

    def boundary_edges(self, file_or_cluster: str, limit: int = 20) -> dict[str, Any]:
        """Return fuse boundary bridge edges touching a file or cluster."""
        target_clusters = self._resolve_cluster_ids(file_or_cluster)
        if not target_clusters:
            return {"found": False, "query": file_or_cluster, "bridges": []}

        bridges: list[dict[str, Any]] = []
        for b in self.fuse_bridges:
            rep_from = b.get("from")
            rep_to = b.get("to")
            if not rep_from or not rep_to:
                continue
            c_from = cluster_id_from_rep(rep_from)
            c_to = cluster_id_from_rep(rep_to)
            if c_from in target_clusters or c_to in target_clusters:
                bridges.append(
                    {
                        "from_cluster": c_from,
                        "to_cluster": c_to,
                        "trigger_source": b.get("trigger_source"),
                        "trigger_target": b.get("trigger_target"),
                        "confidence": b.get("confidence", 0.0),
                        "refused_at_size": b.get("refused_at_size"),
                    }
                )

        bridges.sort(key=lambda x: (x.get("confidence", 0.0), x.get("refused_at_size", 0)), reverse=True)
        return {
            "found": bool(bridges),
            "query": file_or_cluster,
            "cluster_ids": sorted(target_clusters),
            "bridge_count": len(bridges),
            "bridges": bridges[: max(1, limit)],
        }

    def high_coupling_seams(self, file_or_cluster: str = "", limit: int = 20) -> dict[str, Any]:
        """
        Return strongest cross-cluster edge bundles.

        Uses graph edges crossing cluster boundaries as seam indicators.
        """
        target_clusters = self._resolve_cluster_ids(file_or_cluster) if file_or_cluster else set()
        seam_stats: dict[tuple[str, str], dict[str, Any]] = {}

        for e in self.edges:
            src = e.get("source")
            tgt = e.get("target")
            if not src or not tgt:
                continue
            src_u = self.unit_by_id.get(src)
            tgt_u = self.unit_by_id.get(tgt)
            if not src_u or not tgt_u:
                continue
            src_c = src_u.get("cluster")
            tgt_c = tgt_u.get("cluster")
            if not src_c or not tgt_c or src_c == tgt_c:
                continue
            if target_clusters and src_c not in target_clusters and tgt_c not in target_clusters:
                continue

            key = (src_c, tgt_c)
            if key not in seam_stats:
                seam_stats[key] = {
                    "source_cluster": src_c,
                    "target_cluster": tgt_c,
                    "edge_count": 0,
                    "max_confidence": 0.0,
                    "type_counter": Counter(),
                    "pair_counter": Counter(),
                }
            row = seam_stats[key]
            row["edge_count"] += 1
            row["max_confidence"] = max(row["max_confidence"], float(e.get("confidence", 0.0)))
            row["type_counter"][e.get("type", "UNKNOWN")] += 1
            pair = f"{e.get('key', '?')}->{e.get('lock', '?')}"
            row["pair_counter"][pair] += 1

        seams: list[dict[str, Any]] = []
        for row in seam_stats.values():
            seams.append(
                {
                    "source_cluster": row["source_cluster"],
                    "target_cluster": row["target_cluster"],
                    "edge_count": row["edge_count"],
                    "max_confidence": round(row["max_confidence"], 4),
                    "dominant_type": row["type_counter"].most_common(1)[0][0],
                    "dominant_pair": row["pair_counter"].most_common(1)[0][0],
                }
            )
        seams.sort(key=lambda x: (x["edge_count"], x["max_confidence"]), reverse=True)
        return {
            "query": file_or_cluster,
            "cluster_ids": sorted(target_clusters) if target_clusters else [],
            "seam_count": len(seams),
            "seams": seams[: max(1, limit)],
        }

    def _resolve_seed_units(self, symbol_or_file: str) -> list[str]:
        query = symbol_or_file.strip()
        if query in self.unit_by_id:
            return [query]

        file_matches = self._matching_files(query)
        if file_matches:
            seeds: list[str] = []
            for fp in file_matches:
                seeds.extend(self.units_by_file.get(fp, []))
            return seeds

        qlow = query.lower()
        seeds = [uid for uid in self.unit_by_id if uid.lower().endswith(f"::{qlow}")]
        if seeds:
            return seeds
        return [uid for uid in self.unit_by_id if qlow in uid.lower()]

    def impact_neighbors(self, symbol_or_file: str, depth: int = 2, limit: int = 50) -> dict[str, Any]:
        """Return likely architectural blast radius from a file or symbol."""
        seeds = self._resolve_seed_units(symbol_or_file)
        if not seeds:
            return {"found": False, "query": symbol_or_file, "impacted_units": []}

        max_depth = max(1, depth)
        seen: dict[str, int] = {}
        q = deque((s, 0) for s in seeds)
        for s in seeds:
            seen[s] = 0

        while q:
            uid, dist = q.popleft()
            if dist >= max_depth:
                continue
            neighbors = self.out_neighbors.get(uid, []) + self.in_neighbors.get(uid, [])
            for nb in neighbors:
                if nb not in seen or seen[nb] > dist + 1:
                    seen[nb] = dist + 1
                    q.append((nb, dist + 1))

        impacted = []
        for uid, dist in seen.items():
            u = self.unit_by_id.get(uid, {})
            impacted.append(
                {
                    "unit_id": uid,
                    "distance": dist,
                    "cluster": u.get("cluster"),
                    "language": u.get("language"),
                }
            )
        impacted.sort(key=lambda x: (x["distance"], x["unit_id"]))

        cluster_counter = Counter([u.get("cluster") for u in impacted if u.get("cluster")])
        return {
            "found": True,
            "query": symbol_or_file,
            "seed_count": len(seeds),
            "impacted_count": len(impacted),
            "top_clusters": [{"cluster": cid, "units": cnt} for cid, cnt in cluster_counter.most_common(10)],
            "impacted_units": impacted[: max(1, limit)],
        }

    def _get_planner(self):
        if self.index_db_path is None or not self.index_db_path.exists():
            return None
        if self._planner is None:
            from bgi.indexer.planner import QueryPlanner

            self._planner = QueryPlanner(str(self.index_db_path))
        return self._planner

    def search_symbols(self, query: str, limit: int = 10, context_unit_id: str | None = None) -> dict[str, Any]:
        """Search symbols using index DB if available, otherwise graph fallback."""
        planner = self._get_planner()
        if planner is not None:
            results = []
            seen = set()
            for r in planner.lookup_symbol(query, context_unit_id=context_unit_id, max_results=limit):
                if r.unit_id in seen:
                    continue
                seen.add(r.unit_id)
                results.append(
                    {
                        "unit_id": r.unit_id,
                        "name": r.name,
                        "file_path": r.file_path,
                        "score": round(r.score, 4),
                        "reasoning": r.reasoning,
                        "is_exported": bool(r.is_exported),
                    }
                )
            if len(results) < limit:
                for r in planner.search_prefix(query, context_unit_id=context_unit_id, max_results=limit):
                    if r.unit_id in seen:
                        continue
                    seen.add(r.unit_id)
                    results.append(
                        {
                            "unit_id": r.unit_id,
                            "name": r.name,
                            "file_path": r.file_path,
                            "score": round(r.score, 4),
                            "reasoning": r.reasoning,
                            "is_exported": bool(r.is_exported),
                        }
                    )
                    if len(results) >= limit:
                        break
            return {"query": query, "source": "index_db", "count": len(results), "results": results}

        qlow = query.lower()
        matches = []
        for uid, unit in self.unit_by_id.items():
            symbol_name = uid.split("::")[-1]
            if qlow in symbol_name.lower() or qlow in uid.lower():
                matches.append(
                    {
                        "unit_id": uid,
                        "name": symbol_name,
                        "file_path": uid.split("::", 1)[0],
                        "score": 0.5,
                        "reasoning": "fallback graph symbol scan",
                        "is_exported": False,
                    }
                )
        matches.sort(key=lambda x: x["name"])
        return {"query": query, "source": "graph_fallback", "count": len(matches[:limit]), "results": matches[:limit]}

    def architecture_summary(self, path_scope: str = "", top_clusters: int = 5, seam_limit: int = 10) -> dict[str, Any]:
        """Return compact architecture summary for context injection."""
        target_clusters = self._resolve_cluster_ids(path_scope) if path_scope else set(self.cluster_by_id.keys())
        selected = [self.cluster_by_id[cid] for cid in target_clusters if cid in self.cluster_by_id]
        selected.sort(key=lambda c: (c.get("size", 0), c.get("probability", 0.0)), reverse=True)

        units_in_scope = 0
        for c in selected:
            units_in_scope += len(c.get("members", []))

        seams = self.high_coupling_seams(path_scope if path_scope else "", limit=seam_limit)

        return {
            "scope": path_scope or "repository",
            "cluster_count": len(selected),
            "unit_count": units_in_scope,
            "top_clusters": [self._cluster_view(c["id"]) for c in selected[: max(1, top_clusters)]],
            "top_seams": seams.get("seams", []),
        }

    def close(self) -> None:
        if self._planner is not None:
            self._planner.close()
            self._planner = None
