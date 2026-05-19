"""Go import-graph Louvain baseline.

Go imports are package-level (not file-level). We:
  1. Parse `import (...)` blocks and single `import "..."` lines with regex.
  2. Build a package -> set of files map (all .go files in same dir = same package).
  3. For each file, expand its imports to all files in the imported package's
     directory (within this repo). External imports (golang.org/x, github.com/...)
     are dropped — only intra-repo edges count for clustering.
  4. Build an undirected weighted graph and run Louvain.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict

import networkx as nx
from networkx.algorithms.community import louvain_communities


_IMPORT_BLOCK_RE = re.compile(r'import\s*\(([^)]*)\)', re.DOTALL)
_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+(?:[\w.]+\s+)?"([^"]+)"', re.MULTILINE)
_IMPORT_LINE_RE = re.compile(r'^\s*(?:[\w.]+\s+)?"([^"]+)"', re.MULTILINE)


def _module_path_from_go_mod(repo_root: str) -> str | None:
    go_mod = os.path.join(repo_root, "go.mod")
    if not os.path.isfile(go_mod):
        return None
    try:
        with open(go_mod, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("module "):
                    return line.split(None, 1)[1].strip()
    except OSError:
        return None
    return None


def _parse_imports(text: str) -> list[str]:
    out: list[str] = []
    for m in _IMPORT_BLOCK_RE.finditer(text):
        block = m.group(1)
        for line_m in _IMPORT_LINE_RE.finditer(block):
            out.append(line_m.group(1))
    for m in _IMPORT_SINGLE_RE.finditer(text):
        out.append(m.group(1))
    return out


def build_go_import_graph(repo_root: str, files: list[str]) -> nx.Graph:
    module_path = _module_path_from_go_mod(repo_root)
    files_set = set(files)

    # Group files by directory (= Go package boundary).
    dir_to_files: dict[str, list[str]] = defaultdict(list)
    for f in files:
        if not f.endswith(".go"):
            continue
        dir_to_files[os.path.dirname(f)].append(f)

    edges: dict[tuple[str, str], int] = defaultdict(int)

    for f in files:
        if not f.endswith(".go"):
            continue
        try:
            with open(os.path.join(repo_root, f), "r", encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue

        imports = _parse_imports(text)
        for imp in imports:
            target_dir: str | None = None
            if module_path and imp.startswith(module_path + "/"):
                target_dir = imp[len(module_path) + 1:]
            elif imp.startswith("./") or imp.startswith("../"):
                target_dir = os.path.normpath(os.path.join(os.path.dirname(f), imp))
            else:
                continue

            target_files = dir_to_files.get(target_dir, [])
            if not target_files:
                continue
            for tf in target_files:
                if tf == f or tf not in files_set:
                    continue
                edges[(f, tf)] += 1

    g = nx.Graph()
    g.add_nodes_from(files)
    for (u, v), w in edges.items():
        if g.has_edge(u, v):
            g[u][v]["weight"] += w
        else:
            g.add_edge(u, v, weight=w)
    return g


def louvain_clusters_go(graph: nx.Graph, seed: int = 42) -> dict[str, str]:
    communities = louvain_communities(graph, weight="weight", seed=seed)
    out: dict[str, str] = {}
    for i, comm in enumerate(communities):
        for node in comm:
            out[node] = f"louvain_{i:03d}"
    return out
