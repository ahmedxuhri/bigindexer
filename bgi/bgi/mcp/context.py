"""Architecture context service for MCP tools.

Copyright (c) 2026 bigindexer.com
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
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


def _normalize_cov_token(token: str) -> str:
    norm = token.strip().upper()
    if norm.startswith("COV."):
        norm = norm[4:]
    return norm


def _parse_line_range(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        start = int(raw[0])
        end = int(raw[1])
    except (TypeError, ValueError):
        return None
    if start <= 0 or end < start:
        return None
    return (start, end)


@dataclass(frozen=True)
class PromptClass:
    scope: str
    confidence: float
    needs_ast: bool
    needs_call_graph: bool
    needs_interfaces: bool
    needs_repo_scope: bool
    focal_file: str
    focal_symbol: str
    package_hint: str
    signals: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "confidence": self.confidence,
            "needs_ast": self.needs_ast,
            "needs_call_graph": self.needs_call_graph,
            "needs_interfaces": self.needs_interfaces,
            "needs_repo_scope": self.needs_repo_scope,
            "focal_file": self.focal_file,
            "focal_symbol": self.focal_symbol,
            "package_hint": self.package_hint,
            "signals": self.signals,
        }


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
        self._response_cache: dict[tuple[Any, ...], Any] = {}
        self.reload()

    _FILE_HINT_RE = re.compile(
        r"(?<![\w/.-])([\w./-]+\.(?:go|py|ts|tsx|js|jsx|java|rs|rb|php|c|cc|cpp|h|hpp|cs|kt|scala|lua))(?![\w/.-])",
        re.IGNORECASE,
    )
    _SYMBOL_HINT_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,}|[a-z][A-Za-z0-9_]{2,})\b")
    _PACKAGE_RE = re.compile(r"\b([a-z0-9_.-]+(?:/[a-z0-9_.-]+)+)\b", re.IGNORECASE)

    _AST_TERMS = ("struct", "embed", "embedded", "generics", "type param", "ast", "parser", "build tag", "//go:build")
    _CALLGRAPH_TERMS = ("goroutine", "channel", "chan", "deadlock", "race", "waitgroup", "select", "call graph", "fanout")
    _INTERFACE_TERMS = ("interface", "implements", "satisfy", "satisfies", "mock", "contract")
    _REPO_TERMS = (
        "entire repo",
        "repo-wide",
        "across repository",
        "whole codebase",
        "global architecture",
        "entire codebase",
    )
    _MODULE_TERMS = ("across packages", "cross-package", "module", "boundary", "architecture", "blast radius")
    _IMPLEMENTATION_RUBRIC = [
        "exact function body",
        "no TODOs",
        "exact imports",
        "explicit error handling",
        "test case included",
    ]
    _VAGUE_TASK_TERMS = ("fix", "bug", "issue", "problem", "improve", "optimize", "refactor", "clean up")
    _TASK_TOKEN_TERMS: dict[str, tuple[str, ...]] = {
        "INTAKE": ("input", "request", "payload", "parameter", "param", "args", "ingest", "receive"),
        "OUTPUT": ("output", "response", "return", "render", "reply"),
        "TRANSFORM": ("transform", "map", "convert", "normalize", "format"),
        "MUTATE": ("mutate", "update", "modify", "change state"),
        "SANITIZE": ("sanitize", "escape", "clean", "scrub"),
        "CONDITIONAL": ("if", "condition", "branch", "switch"),
        "LOOP": ("loop", "iterate", "for each", "batch"),
        "GUARD": ("guard", "check", "prevent", "reject"),
        "ROUTE": ("route", "endpoint", "handler", "controller", "api"),
        "SCOPE": ("scope", "local", "global", "nested"),
        "FETCH": ("fetch", "read", "load", "query", "get"),
        "PERSIST": ("persist", "save", "store", "write", "commit", "insert"),
        "EMIT": ("emit", "publish", "notify", "send event", "dispatch"),
        "SUBSCRIBE": ("subscribe", "listener", "consumer", "watch"),
        "DELEGATE": ("delegate", "forward", "proxy", "handoff"),
        "CONTRACT": ("interface", "protocol", "contract", "schema"),
        "COMPOSE": ("compose", "assemble", "aggregate", "combine"),
        "INIT": ("init", "initialize", "setup", "boot"),
        "TEARDOWN": ("teardown", "cleanup", "shutdown", "close"),
        "RAISE": ("raise", "throw", "fail", "error"),
        "RECOVER": ("recover", "retry", "fallback", "handle error"),
        "DEFER": ("defer", "finally", "after", "ensure"),
        "AUTHENTICATE": ("authenticate", "login", "sign in", "identity"),
        "AUTHORIZE": ("authorize", "permission", "access control", "policy"),
        "VALIDATE": ("validate", "verify", "check input", "assert"),
        "LOG": ("log", "audit", "trace"),
        "MEASURE": ("measure", "metric", "latency", "timing", "telemetry"),
        "ASYNC": ("async", "await", "goroutine", "concurrent", "background"),
        "TEST": ("test", "assertion", "unit test", "integration test"),
    }

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
        self._response_cache.clear()
        self.repo_root = self.graph_path.parent.resolve()

        self.units: list[dict[str, Any]] = self.graph.get("units", [])
        self.edges: list[dict[str, Any]] = self.graph.get("edges", [])
        self.clusters: list[dict[str, Any]] = self.graph.get("clusters", [])
        self.fuse_bridges: list[dict[str, Any]] = self.fuse_graph.get("bridges", [])

        self.unit_by_id: dict[str, dict[str, Any]] = {u["id"]: u for u in self.units if "id" in u}
        self.cluster_by_id: dict[str, dict[str, Any]] = {c["id"]: c for c in self.clusters if "id" in c}

        self.units_by_file: dict[str, list[str]] = defaultdict(list)
        self.cluster_ids_by_file: dict[str, set[str]] = defaultdict(set)
        self.units_by_cluster: dict[str, list[str]] = defaultdict(list)
        self.unit_tokens: dict[str, set[str]] = {}
        self.unit_line_ranges: dict[str, tuple[int, int] | None] = {}
        self.unit_confidence: dict[str, float] = {}
        for u in self.units:
            uid = u.get("id")
            if not uid:
                continue
            file_path = _normalize_path(uid.split("::", 1)[0])
            self.units_by_file[file_path].append(uid)
            cid = u.get("cluster")
            if cid:
                self.cluster_ids_by_file[file_path].add(cid)
                self.units_by_cluster[cid].append(uid)
            self.unit_tokens[uid] = self._extract_cov_tokens(u)
            self.unit_line_ranges[uid] = _parse_line_range(u.get("line_range"))
            self.unit_confidence[uid] = float(u.get("confidence", 0.0) or 0.0)

        self.out_neighbors: dict[str, list[str]] = defaultdict(list)
        self.in_neighbors: dict[str, list[str]] = defaultdict(list)
        for e in self.edges:
            src = e.get("source")
            tgt = e.get("target")
            if not src or not tgt:
                continue
            self.out_neighbors[src].append(tgt)
            self.in_neighbors[tgt].append(src)

        self._bridge_rows: list[dict[str, Any]] = []
        self._bridges_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for b in self.fuse_bridges:
            rep_from = b.get("from")
            rep_to = b.get("to")
            if not rep_from or not rep_to:
                continue
            c_from = cluster_id_from_rep(rep_from)
            c_to = cluster_id_from_rep(rep_to)
            row = {
                "from_cluster": c_from,
                "to_cluster": c_to,
                "trigger_source": b.get("trigger_source"),
                "trigger_target": b.get("trigger_target"),
                "confidence": b.get("confidence", 0.0),
                "refused_at_size": b.get("refused_at_size"),
            }
            self._bridge_rows.append(row)
            self._bridges_by_cluster[c_from].append(row)
            if c_to != c_from:
                self._bridges_by_cluster[c_to].append(row)

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

        self._seam_rows_all: list[dict[str, Any]] = []
        for row in seam_stats.values():
            self._seam_rows_all.append(
                {
                    "source_cluster": row["source_cluster"],
                    "target_cluster": row["target_cluster"],
                    "edge_count": row["edge_count"],
                    "max_confidence": round(row["max_confidence"], 4),
                    "dominant_type": row["type_counter"].most_common(1)[0][0],
                    "dominant_pair": row["pair_counter"].most_common(1)[0][0],
                }
            )
        self._seam_rows_all.sort(key=lambda x: (x["edge_count"], x["max_confidence"]), reverse=True)
        self._seams_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for seam in self._seam_rows_all:
            src_c = seam["source_cluster"]
            tgt_c = seam["target_cluster"]
            self._seams_by_cluster[src_c].append(seam)
            if tgt_c != src_c:
                self._seams_by_cluster[tgt_c].append(seam)

        self._get_planner()

        return {
            "graph_path": str(self.graph_path),
            "fuse_graph_path": str(self.fuse_graph_path),
            "units": len(self.units),
            "edges": len(self.edges),
            "clusters": len(self.clusters),
            "fuse_bridges": len(self.fuse_bridges),
        }

    def _cached(self, key: tuple[Any, ...], builder) -> Any:
        if key in self._response_cache:
            return self._response_cache[key]
        value = builder()
        self._response_cache[key] = value
        return value

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

    def classify_prompt(self, prompt: str) -> dict[str, Any]:
        """Classify a prompt into scope and structural needs for staged MCP retrieval."""
        key = ("classify_prompt", prompt)

        def _build() -> dict[str, Any]:
            p = prompt.strip()
            low = p.lower()
            file_hint = ""
            package_hint = ""
            symbol_hint = ""

            file_match = self._FILE_HINT_RE.search(p)
            if file_match:
                file_hint = _normalize_path(file_match.group(1))

            for m in self._PACKAGE_RE.finditer(p):
                candidate = m.group(1)
                if "." in candidate and "/" not in candidate:
                    continue
                if candidate.endswith(".go"):
                    continue
                package_hint = _normalize_path(candidate)
                break

            symbol_matches = self._SYMBOL_HINT_RE.findall(p)
            if symbol_matches:
                for token in symbol_matches:
                    tlow = token.lower()
                    if tlow in {"what", "where", "which", "when", "why", "does", "from", "with", "that", "this"}:
                        continue
                    symbol_hint = token
                    break

            needs_ast = any(t in low for t in self._AST_TERMS)
            needs_call_graph = any(t in low for t in self._CALLGRAPH_TERMS)
            needs_interfaces = any(t in low for t in self._INTERFACE_TERMS)
            needs_repo_scope = any(t in low for t in self._REPO_TERMS)
            has_module_signal = any(t in low for t in self._MODULE_TERMS)

            if file_hint:
                scope = "file"
            elif package_hint:
                scope = "package"
            elif needs_repo_scope:
                scope = "repository"
            elif has_module_signal:
                scope = "module"
            else:
                scope = "package"

            confidence = 0.25
            if file_hint:
                confidence += 0.2
            if package_hint:
                confidence += 0.15
            if needs_ast:
                confidence += 0.12
            if needs_call_graph:
                confidence += 0.16
            if needs_interfaces:
                confidence += 0.12
            if has_module_signal:
                confidence += 0.08
            if needs_repo_scope:
                confidence += 0.05
            confidence = max(0.05, min(0.95, round(confidence, 2)))

            signals = []
            if needs_ast:
                signals.append("ast")
            if needs_call_graph:
                signals.append("call_graph")
            if needs_interfaces:
                signals.append("interfaces")
            if has_module_signal:
                signals.append("module")
            if needs_repo_scope:
                signals.append("repo_scope")
            if file_hint:
                signals.append("file_anchor")
            if package_hint:
                signals.append("package_anchor")

            prompt_class = PromptClass(
                scope=scope,
                confidence=confidence,
                needs_ast=needs_ast,
                needs_call_graph=needs_call_graph,
                needs_interfaces=needs_interfaces,
                needs_repo_scope=needs_repo_scope,
                focal_file=file_hint,
                focal_symbol=symbol_hint,
                package_hint=package_hint,
                signals=signals,
            )
            return prompt_class.to_dict()

        return self._cached(key, _build)

    def _infer_package_scope(self, prompt_class: dict[str, Any]) -> str:
        focal_file = prompt_class.get("focal_file", "")
        if focal_file:
            p = Path(focal_file)
            parent = _normalize_path(str(p.parent))
            return "" if parent == "." else parent
        return prompt_class.get("package_hint", "")

    @staticmethod
    def _extract_cov_tokens(unit: dict[str, Any]) -> set[str]:
        tokens: set[str] = set()
        for key in ("tokens", "class_context"):
            for raw in unit.get(key, []) or []:
                if isinstance(raw, str):
                    norm = _normalize_cov_token(raw)
                    if norm:
                        tokens.add(norm)
        return tokens

    @staticmethod
    def _symbol_from_unit_id(unit_id: str) -> str:
        parts = unit_id.split("::")
        return parts[-1] if parts else unit_id

    def _read_unit_source(self, unit_id: str, max_lines: int = 160) -> str:
        rel_file = _normalize_path(unit_id.split("::", 1)[0])
        source_path = (self.repo_root / rel_file).resolve()
        if self.repo_root not in source_path.parents and source_path != self.repo_root:
            return ""
        if not source_path.exists() or not source_path.is_file():
            return ""
        try:
            lines = source_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        line_range = self.unit_line_ranges.get(unit_id)
        if not line_range:
            return ""
        start, end = line_range
        end = min(end, start + max_lines - 1)
        if start <= 0 or start > len(lines):
            return ""
        snippet = lines[start - 1:end]
        return "\n".join(snippet).strip()

    @staticmethod
    def _gate_twin_confidence(task_confidence: float, best_score: float, candidate_count: int) -> dict[str, Any]:
        if candidate_count <= 0 or task_confidence < 0.25 or best_score < 0.25:
            return {
                "status": "no_confident_twin",
                "allow_output": False,
                "recommended_action": "provide a more specific task description or give one example function",
            }
        if best_score >= 0.7 and task_confidence >= 0.55:
            status = "high"
        elif best_score >= 0.5 and task_confidence >= 0.45:
            status = "medium"
        elif best_score >= 0.35:
            status = "low"
        else:
            status = "no_confident_twin"
        return {
            "status": status,
            "allow_output": status != "no_confident_twin",
            "recommended_action": "proceed with top twin" if status in {"high", "medium"} else "review all twin candidates manually",
        }

    @staticmethod
    def _match_term(text_lower: str, term: str) -> bool:
        if " " in term:
            return term in text_lower
        return re.search(rf"(?<![\\w]){re.escape(term)}(?![\\w])", text_lower) is not None

    def task_fingerprint(self, task: str, max_tokens: int = 8) -> dict[str, Any]:
        """Map a natural-language task into a COV token fingerprint."""
        max_tokens = max(1, min(max_tokens, 16))
        key = ("task_fingerprint", task, max_tokens)

        def _build() -> dict[str, Any]:
            text = task.strip()
            low = text.lower()
            scored: list[dict[str, Any]] = []
            evidence_weight = 0

            for token, terms in self._TASK_TOKEN_TERMS.items():
                matched_terms = [term for term in terms if self._match_term(low, term)]
                if not matched_terms:
                    continue
                evidence_weight += len(matched_terms)
                score = min(0.98, 0.35 + (0.12 * len(matched_terms)))
                scored.append(
                    {
                        "token": token,
                        "score": round(score, 3),
                        "matched_terms": matched_terms,
                    }
                )

            scored.sort(key=lambda row: (row["score"], len(row["matched_terms"]), row["token"]), reverse=True)
            selected = scored[:max_tokens]
            task_cov = [row["token"] for row in selected]

            vague_hits = [term for term in self._VAGUE_TASK_TERMS if self._match_term(low, term)]
            confidence = 0.1
            if selected:
                confidence = 0.28 + (0.08 * len(selected)) + (0.05 * (evidence_weight / max(1, len(selected))))
            if vague_hits and len(selected) <= 2:
                confidence -= 0.12
            confidence = round(max(0.05, min(0.95, confidence)), 2)

            if not selected or confidence < 0.35:
                status = "insufficient_signal"
            elif confidence < 0.55:
                status = "ambiguous"
            else:
                status = "ok"

            return {
                "task": task,
                "tokens": task_cov,
                "scored_tokens": selected,
                "confidence": confidence,
                "status": status,
                "vague_terms_detected": vague_hits,
                "interpretation": f"interpreted as COV tokens: {task_cov}" if task_cov else "could not infer clear COV tokens",
            }

        return self._cached(key, _build)

    def behavioral_twins(
        self,
        task: str,
        limit: int = 3,
        min_score: float = 0.25,
        include_source: bool = True,
    ) -> dict[str, Any]:
        """
        Find top behavioral twins for a task using Jaccard overlap on COV tokens.

        Returns top-N candidates and confidence-gate status.
        """
        max_limit = max(1, min(limit, 10))
        score_floor = max(0.0, min(min_score, 1.0))
        key = ("behavioral_twins", task, max_limit, round(score_floor, 3), bool(include_source))

        def _build() -> dict[str, Any]:
            fingerprint = self.task_fingerprint(task, max_tokens=10)
            task_cov = fingerprint.get("tokens", [])
            task_token_set = set(task_cov)
            if not task_token_set:
                gate = self._gate_twin_confidence(float(fingerprint.get("confidence", 0.0)), 0.0, 0)
                return {
                    "task": task,
                    "task_cov": [],
                    "task_fingerprint": fingerprint,
                    "candidate_pool_size": 0,
                    "twin_candidates": [],
                    "confidence_gate": {
                        **gate,
                        "task_confidence": float(fingerprint.get("confidence", 0.0)),
                        "best_score": 0.0,
                    },
                }

            scored_rows: list[tuple[str, float, list[str], int]] = []
            for uid, unit_token_set in self.unit_tokens.items():
                if not unit_token_set:
                    continue
                overlap = task_token_set & unit_token_set
                if not overlap:
                    continue
                union = task_token_set | unit_token_set
                if not union:
                    continue
                score = len(overlap) / len(union)
                if score < score_floor:
                    continue
                scored_rows.append((uid, score, sorted(overlap), len(unit_token_set)))

            scored_rows.sort(
                key=lambda row: (
                    row[1],
                    len(row[2]),
                    self.unit_confidence.get(row[0], 0.0),
                    row[0],
                ),
                reverse=True,
            )
            top = scored_rows[:max_limit]
            best_score = top[0][1] if top else 0.0
            gate = self._gate_twin_confidence(float(fingerprint.get("confidence", 0.0)), best_score, len(top))

            candidates: list[dict[str, Any]] = []
            for uid, score, overlap_tokens, unit_token_count in top:
                line_range = self.unit_line_ranges.get(uid)
                file_path = _normalize_path(uid.split("::", 1)[0])
                source_text = self._read_unit_source(uid) if include_source else ""
                candidates.append(
                    {
                        "unit": uid,
                        "symbol": self._symbol_from_unit_id(uid),
                        "file": file_path,
                        "cluster": self.unit_by_id.get(uid, {}).get("cluster"),
                        "line_range": list(line_range) if line_range else [],
                        "score": round(score, 3),
                        "overlap_tokens": overlap_tokens,
                        "unit_token_count": unit_token_count,
                        "unit_confidence": round(self.unit_confidence.get(uid, 0.0), 3),
                        "source": source_text,
                        "source_available": bool(source_text),
                    }
                )

            return {
                "task": task,
                "task_cov": task_cov,
                "task_fingerprint": fingerprint,
                "candidate_pool_size": len(scored_rows),
                "twin_candidates": candidates,
                "confidence_gate": {
                    **gate,
                    "task_confidence": float(fingerprint.get("confidence", 0.0)),
                    "best_score": round(best_score, 3),
                },
            }

        return self._cached(key, _build)

    def _suggest_seam(self, task_cov: set[str], twin_candidates: list[dict[str, Any]]) -> dict[str, Any]:
        if not twin_candidates:
            return {}
        top = twin_candidates[0]
        top_cluster = top.get("cluster")
        if not top_cluster or top_cluster not in self.cluster_by_id:
            return {
                "anchor_unit": top.get("unit"),
                "anchor_file": top.get("file"),
                "anchor_line_range": top.get("line_range", []),
                "suggestion": f"{top.get('file', '')} — insert near {top.get('symbol', '')}",
            }

        members = self.units_by_cluster.get(top_cluster, [])
        ranked_members = []
        for uid in members:
            overlap = len(task_cov & self.unit_tokens.get(uid, set()))
            ranked_members.append((overlap, self.unit_confidence.get(uid, 0.0), uid))
        ranked_members.sort(reverse=True)
        anchor_unit = ranked_members[0][2] if ranked_members else top.get("unit")
        anchor_file = _normalize_path(str(anchor_unit).split("::", 1)[0]) if anchor_unit else top.get("file")
        anchor_line = self.unit_line_ranges.get(anchor_unit) if anchor_unit else None

        seams = self.high_coupling_seams(top_cluster, limit=3).get("seams", [])
        related = seams[0] if seams else {}
        related_cluster = (
            related.get("target_cluster")
            if related.get("source_cluster") == top_cluster
            else related.get("source_cluster")
        )

        return {
            "cluster": top_cluster,
            "anchor_unit": anchor_unit,
            "anchor_file": anchor_file,
            "anchor_line_range": list(anchor_line) if anchor_line else [],
            "related_cluster": related_cluster,
            "related_seam": related,
            "suggestion": f"{anchor_file} — insert near {self._symbol_from_unit_id(str(anchor_unit))}",
        }

    def twin_context(
        self,
        task: str,
        limit: int = 3,
        include_source: bool = True,
        min_score: float = 0.25,
    ) -> dict[str, Any]:
        """
        Return implementation-ready context package:
        task fingerprint + top behavioral twins + seam + actionability rubric.
        """
        max_limit = max(1, min(limit, 10))
        score_floor = max(0.0, min(min_score, 1.0))
        key = ("twin_context", task, max_limit, bool(include_source), round(score_floor, 3))

        def _build() -> dict[str, Any]:
            twins = self.behavioral_twins(
                task=task,
                limit=max_limit,
                min_score=score_floor,
                include_source=include_source,
            )
            task_cov = set(twins.get("task_cov", []))
            candidates = twins.get("twin_candidates", [])
            gate = twins.get("confidence_gate", {})
            seam = self._suggest_seam(task_cov, candidates)

            status = "ready_for_delta_generation" if gate.get("allow_output") else "needs_more_context"
            result = {
                "task": task,
                "status": status,
                "task_cov": list(task_cov),
                "task_fingerprint": twins.get("task_fingerprint", {}),
                "twin_candidates": candidates,
                "seam": seam,
                "rubric": list(self._IMPLEMENTATION_RUBRIC),
                "confidence_gate": gate,
            }
            if status == "needs_more_context":
                result["escalation"] = {
                    "status": "no_confident_twin",
                    "task_cov": list(task_cov),
                    "best_partial_match": candidates[0]["unit"] if candidates else "",
                    "request": gate.get("recommended_action", "provide a more specific task"),
                }
            return result

        return self._cached(key, _build)

    @staticmethod
    def _confidence_gain(
        *,
        focal_found: bool,
        unresolved_refs: int,
        coverage_ratio: float,
        ambiguity: float,
    ) -> float:
        gain = (
            (0.4 * float(unresolved_refs))
            + (0.4 * (1.0 - max(0.0, min(1.0, coverage_ratio))))
            + (0.2 * max(0.0, min(1.0, ambiguity)))
        )
        if not focal_found:
            gain += 0.25
        return round(min(1.0, gain), 3)

    def guided_arch_context(self, prompt: str, max_items: int = 8) -> dict[str, Any]:
        """
        Build staged architecture context with scope-first escalation gates.

        This keeps payloads small by default and escalates only when confidence gain is likely.
        """
        max_items = max(2, min(max_items, 20))
        key = ("guided_arch_context", prompt, max_items)

        def _build() -> dict[str, Any]:
            prompt_class = self.classify_prompt(prompt)
            package_scope = self._infer_package_scope(prompt_class)
            focal_symbol = prompt_class.get("focal_symbol", "")
            focal_file = prompt_class.get("focal_file", "")
            scope = prompt_class.get("scope", "package")

            thresholds = {
                "package": 0.4,
                "module": 0.65,
                "repository": 0.85,
            }

            steps: list[dict[str, Any]] = []
            focal_data: dict[str, Any] = {}
            focal_found = False

            if focal_file:
                file_info = self.cluster_of_file(focal_file)
                focal_data["cluster_of_file"] = file_info
                steps.append({"tier": 1, "action": "cluster_of_file", "scope": "file"})
                focal_found = bool(file_info.get("found"))

                if focal_found:
                    bridges = self.boundary_edges(focal_file, limit=min(6, max_items))
                    focal_data["boundary_edges"] = bridges
                    steps.append({"tier": 1, "action": "boundary_edges", "scope": "file"})
            else:
                symbol_query = focal_symbol or prompt.split(" ", 1)[0]
                symbol_info = self.search_symbols(symbol_query, limit=min(6, max_items))
                focal_data["search_symbols"] = symbol_info
                steps.append({"tier": 1, "action": "search_symbols", "scope": "symbol"})
                focal_found = bool(symbol_info.get("count"))

            unresolved_refs = 0 if focal_found else 1
            seed_coverage = 0.7 if focal_found else 0.2
            ambiguity = 0.6 if prompt_class.get("needs_call_graph") else 0.35
            gain = self._confidence_gain(
                focal_found=focal_found,
                unresolved_refs=unresolved_refs,
                coverage_ratio=seed_coverage,
                ambiguity=ambiguity,
            )

            package_data: dict[str, Any] = {}
            if gain >= thresholds["package"] or scope in {"package", "module", "repository"}:
                package_data["architecture_summary"] = self.architecture_summary(
                    path_scope=package_scope,
                    top_clusters=min(4, max_items),
                    seam_limit=min(6, max_items),
                )
                steps.append(
                    {
                        "tier": 2,
                        "action": "architecture_summary",
                        "scope": package_scope or "repository_root",
                    }
                )
                gain = self._confidence_gain(
                    focal_found=focal_found,
                    unresolved_refs=max(0, unresolved_refs - 1),
                    coverage_ratio=0.85 if focal_found else 0.6,
                    ambiguity=0.45 if prompt_class.get("needs_call_graph") else 0.25,
                )

            module_data: dict[str, Any] = {}
            if (
                gain >= thresholds["module"]
                or scope in {"module", "repository"}
                or prompt_class.get("needs_call_graph")
                or prompt_class.get("needs_interfaces")
            ):
                seed = focal_symbol or focal_file or package_scope or prompt
                module_data["impact_neighbors"] = self.impact_neighbors(seed, depth=2, limit=max_items)
                module_data["high_coupling_seams"] = self.high_coupling_seams(package_scope, limit=min(8, max_items))
                steps.append({"tier": 3, "action": "impact_neighbors", "scope": "module"})
                steps.append({"tier": 3, "action": "high_coupling_seams", "scope": package_scope or "module"})
                gain = self._confidence_gain(
                    focal_found=True,
                    unresolved_refs=0,
                    coverage_ratio=0.92,
                    ambiguity=0.15,
                )

            repo_data: dict[str, Any] = {}
            classifier_confidence = float(prompt_class.get("confidence", 0.0))
            if prompt_class.get("needs_repo_scope") and (
                classifier_confidence >= thresholds["repository"] or (scope == "repository" and classifier_confidence >= 0.65)
            ):
                repo_data["architecture_summary"] = self.architecture_summary(
                    path_scope="",
                    top_clusters=min(4, max_items),
                    seam_limit=min(6, max_items),
                )
                steps.append({"tier": 4, "action": "architecture_summary", "scope": "repository"})

            return {
                "prompt": prompt,
                "classification": prompt_class,
                "thresholds": thresholds,
                "estimated_gain": gain,
                "steps": steps,
                "focal_context": focal_data,
                "package_context": package_data,
                "module_context": module_data,
                "repository_context": repo_data,
            }

        return self._cached(key, _build)

    def cluster_of_file(self, file_path: str) -> dict[str, Any]:
        """Return cluster info for a file path."""
        key = ("cluster_of_file", file_path)

        def _build() -> dict[str, Any]:
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

        return self._cached(key, _build)

    def boundary_edges(self, file_or_cluster: str, limit: int = 20) -> dict[str, Any]:
        """Return fuse boundary bridge edges touching a file or cluster."""
        max_limit = max(1, limit)
        key = ("boundary_edges", file_or_cluster, max_limit)

        def _build() -> dict[str, Any]:
            target_clusters = self._resolve_cluster_ids(file_or_cluster)
            if not target_clusters:
                return {"found": False, "query": file_or_cluster, "bridges": []}

            dedup: dict[tuple[Any, ...], dict[str, Any]] = {}
            for cid in target_clusters:
                for bridge in self._bridges_by_cluster.get(cid, []):
                    bridge_key = (
                        bridge.get("from_cluster"),
                        bridge.get("to_cluster"),
                        bridge.get("trigger_source"),
                        bridge.get("trigger_target"),
                    )
                    dedup[bridge_key] = bridge

            bridges = list(dedup.values())
            bridges.sort(key=lambda x: (x.get("confidence", 0.0), x.get("refused_at_size", 0)), reverse=True)
            return {
                "found": bool(bridges),
                "query": file_or_cluster,
                "cluster_ids": sorted(target_clusters),
                "bridge_count": len(bridges),
                "bridges": bridges[:max_limit],
            }

        return self._cached(key, _build)

    def high_coupling_seams(self, file_or_cluster: str = "", limit: int = 20) -> dict[str, Any]:
        """
        Return strongest cross-cluster edge bundles.

        Uses graph edges crossing cluster boundaries as seam indicators.
        """
        max_limit = max(1, limit)
        key = ("high_coupling_seams", file_or_cluster, max_limit)

        def _build() -> dict[str, Any]:
            target_clusters = self._resolve_cluster_ids(file_or_cluster) if file_or_cluster else set()
            if not target_clusters:
                seams = self._seam_rows_all
            else:
                dedup: dict[tuple[str, str], dict[str, Any]] = {}
                for cid in target_clusters:
                    for seam in self._seams_by_cluster.get(cid, []):
                        seam_key = (seam["source_cluster"], seam["target_cluster"])
                        dedup[seam_key] = seam
                seams = list(dedup.values())
                seams.sort(key=lambda x: (x["edge_count"], x["max_confidence"]), reverse=True)
            return {
                "query": file_or_cluster,
                "cluster_ids": sorted(target_clusters) if target_clusters else [],
                "seam_count": len(seams),
                "seams": seams[:max_limit],
            }

        return self._cached(key, _build)

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
        max_depth = max(1, depth)
        max_limit = max(1, limit)
        key = ("impact_neighbors", symbol_or_file, max_depth, max_limit)

        def _build() -> dict[str, Any]:
            seeds = self._resolve_seed_units(symbol_or_file)
            if not seeds:
                return {"found": False, "query": symbol_or_file, "impacted_units": []}

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
                "impacted_units": impacted[:max_limit],
            }

        return self._cached(key, _build)

    def _get_planner(self):
        if self.index_db_path is None or not self.index_db_path.exists():
            return None
        if self._planner is None:
            from bgi.indexer.planner import QueryPlanner

            self._planner = QueryPlanner(str(self.index_db_path))
        return self._planner

    def search_symbols(self, query: str, limit: int = 10, context_unit_id: str | None = None) -> dict[str, Any]:
        """Search symbols using index DB if available, otherwise graph fallback."""
        max_limit = max(1, limit)
        key = ("search_symbols", query, max_limit, context_unit_id or "")

        def _build() -> dict[str, Any]:
            planner = self._get_planner()
            if planner is not None:
                results = []
                seen = set()
                for r in planner.lookup_symbol(query, context_unit_id=context_unit_id, max_results=max_limit):
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
                if len(results) < max_limit:
                    for r in planner.search_prefix(query, context_unit_id=context_unit_id, max_results=max_limit):
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
                        if len(results) >= max_limit:
                            break
                return {"query": query, "source": "index_db", "count": len(results), "results": results}

            qlow = query.lower()
            matches = []
            for uid in self.unit_by_id:
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
            return {"query": query, "source": "graph_fallback", "count": len(matches[:max_limit]), "results": matches[:max_limit]}

        return self._cached(key, _build)

    def architecture_summary(self, path_scope: str = "", top_clusters: int = 5, seam_limit: int = 10) -> dict[str, Any]:
        """Return compact architecture summary for context injection."""
        max_top_clusters = max(1, top_clusters)
        max_seam_limit = max(1, seam_limit)
        key = ("architecture_summary", path_scope, max_top_clusters, max_seam_limit)

        def _build() -> dict[str, Any]:
            target_clusters = self._resolve_cluster_ids(path_scope) if path_scope else set(self.cluster_by_id.keys())
            selected = [self.cluster_by_id[cid] for cid in target_clusters if cid in self.cluster_by_id]
            selected.sort(key=lambda c: (c.get("size", 0), c.get("probability", 0.0)), reverse=True)

            units_in_scope = 0
            for c in selected:
                units_in_scope += len(c.get("members", []))

            seams = self.high_coupling_seams(path_scope if path_scope else "", limit=max_seam_limit)

            return {
                "scope": path_scope or "repository",
                "cluster_count": len(selected),
                "unit_count": units_in_scope,
                "top_clusters": [self._cluster_view(c["id"]) for c in selected[:max_top_clusters]],
                "top_seams": seams.get("seams", []),
            }

        return self._cached(key, _build)

    def close(self) -> None:
        if self._planner is not None:
            self._planner.close()
            self._planner = None
