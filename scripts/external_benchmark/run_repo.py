"""End-to-end head-to-head benchmark runner.

For one repo, score three methods against the package-layout ground truth:
  - bgi_native:        BGI's clusters field (file-level majority vote)
  - louvain_imports:   Louvain on the language's import graph
  - louvain_bgi_edges: Louvain on BGI's HARD edges projected to file level

This isolates BGI's edge contribution from the unit-vs-file granularity
issue: louvain_bgi_edges and louvain_imports use the same algorithm,
differing only in their edge source.

Metrics: pairwise precision/recall/F1 + MoJoFM. All restricted to the
file set common to all four (truth + the three methods).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bgi_clusters import file_clusters_from_graph
from bgi_edge_graph import file_graph_from_bgi_edges, louvain_clusters_from_graph
from ground_truth import collect_files, package_layout_clusters
from louvain_baseline import build_import_graph, louvain_clusters
from metrics import mojofm, pairwise_prf


METHODS = ("bgi_native", "louvain_imports", "louvain_bgi_hard", "louvain_bgi_all")


def _score(pred: dict, truth: dict) -> dict:
    prf = pairwise_prf(pred, truth)
    mj = mojofm(pred, truth)
    return {
        "n_clusters": mj["n_pred_clusters"],
        "precision": prf["precision"],
        "recall": prf["recall"],
        "f1": prf["f1"],
        "mojofm": mj["mojofm"],
        "tp": prf["tp"], "fp": prf["fp"], "fn": prf["fn"],
    }


def run(
    repo_slug: str,
    repo_root: str,
    package_root: str,
    bgi_graph_path: str,
    extensions: list[str],
    out_dir: str,
    truth_depth: int = 1,
    truth_split_dirs: tuple[str, ...] = (),
    language: str = "python",
) -> dict:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print(f"[{repo_slug}] collecting files under {package_root}...")
    files = collect_files(repo_root, package_root, extensions,
                          exclude_dirs=("__pycache__", "vendor"))
    print(f"  found {len(files)} source files")

    print(f"[{repo_slug}] building ground truth (depth={truth_depth}, "
          f"split={truth_split_dirs})...")
    truth = package_layout_clusters(files, package_root, depth=truth_depth,
                                     split_dirs=truth_split_dirs)
    print(f"  truth: {len(truth)} files, {len(set(truth.values()))} clusters")

    print(f"[{repo_slug}] method 1/3: bgi_native (clusters field)...")
    bgi_full = file_clusters_from_graph(bgi_graph_path)
    bgi_native = {f: c for f, c in bgi_full.items() if f in truth}
    print(f"  files covered: {len(bgi_native)}, clusters: {len(set(bgi_native.values()))}")

    print(f"[{repo_slug}] method 2/3: louvain_imports ({language})...")
    t0 = time.time()
    if language == "python":
        import_g = build_import_graph(repo_root, files)
    elif language == "go":
        from louvain_baseline_go import build_go_import_graph
        import_g = build_go_import_graph(repo_root, files)
    else:
        raise ValueError(f"unsupported language: {language}")
    louvain_imports = louvain_clusters(import_g)
    t_imports = time.time() - t0
    print(f"  graph: {import_g.number_of_nodes()} nodes, "
          f"{import_g.number_of_edges()} edges ({t_imports:.1f}s)")
    print(f"  Louvain communities: {len(set(louvain_imports.values()))}")

    print(f"[{repo_slug}] method 3/4: louvain_bgi_hard (HARD-only)...")
    t0 = time.time()
    bgi_hard_g = file_graph_from_bgi_edges(bgi_graph_path, files=files, hard_only=True)
    louvain_bgi_hard = louvain_clusters_from_graph(bgi_hard_g)
    t_bgi_hard = time.time() - t0
    print(f"  graph: {bgi_hard_g.number_of_nodes()} nodes, "
          f"{bgi_hard_g.number_of_edges()} edges ({t_bgi_hard:.1f}s)")
    print(f"  Louvain communities: {len(set(louvain_bgi_hard.values()))}")

    print(f"[{repo_slug}] method 4/4: louvain_bgi_all (HARD + PREDICTED)...")
    t0 = time.time()
    bgi_all_g = file_graph_from_bgi_edges(bgi_graph_path, files=files, hard_only=False)
    louvain_bgi_all = louvain_clusters_from_graph(bgi_all_g)
    t_bgi_all = time.time() - t0
    print(f"  graph: {bgi_all_g.number_of_nodes()} nodes, "
          f"{bgi_all_g.number_of_edges()} edges ({t_bgi_all:.1f}s)")
    print(f"  Louvain communities: {len(set(louvain_bgi_all.values()))}")

    common = sorted(set(truth) & set(bgi_native) & set(louvain_imports)
                    & set(louvain_bgi_hard) & set(louvain_bgi_all))
    print(f"[{repo_slug}] common file set: {len(common)} "
          f"(of {len(truth)} ground-truth files)")
    if len(common) < 50:
        print("  WARNING: small common file set, metrics may not be meaningful")

    truth_c = {f: truth[f] for f in common}
    preds = {
        "bgi_native":       {f: bgi_native[f] for f in common},
        "louvain_imports":  {f: louvain_imports[f] for f in common},
        "louvain_bgi_hard": {f: louvain_bgi_hard[f] for f in common},
        "louvain_bgi_all":  {f: louvain_bgi_all[f] for f in common},
    }

    print(f"[{repo_slug}] scoring...")
    summary = {
        "repo": repo_slug,
        "n_common_files": len(common),
        "n_total_files": len(files),
        "n_ground_truth_files": len(truth),
        "n_truth_clusters": len(set(truth_c.values())),
        "import_graph": {
            "nodes": import_g.number_of_nodes(),
            "edges": import_g.number_of_edges(),
            "build_time_sec": round(t_imports, 2),
        },
        "bgi_hard_graph": {
            "nodes": bgi_hard_g.number_of_nodes(),
            "edges": bgi_hard_g.number_of_edges(),
            "build_time_sec": round(t_bgi_hard, 2),
        },
        "bgi_all_graph": {
            "nodes": bgi_all_g.number_of_nodes(),
            "edges": bgi_all_g.number_of_edges(),
            "build_time_sec": round(t_bgi_all, 2),
        },
        "methods": {m: _score(preds[m], truth_c) for m in METHODS},
    }

    with (out_path / "summary.json").open("w") as f:
        json.dump(summary, f, indent=2)

    with (out_path / "metrics.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["repo", "method", "n_clusters", "precision", "recall", "f1", "mojofm"])
        for m in METHODS:
            d = summary["methods"][m]
            w.writerow([repo_slug, m, d["n_clusters"], d["precision"],
                        d["recall"], d["f1"], d["mojofm"]])

    with (out_path / "clusterings.json").open("w") as f:
        json.dump({"common_files": common, "truth": truth_c, **preds}, f)

    print()
    print(f"=== {repo_slug}  (n={len(common)} files, "
          f"{summary['n_truth_clusters']} truth clusters) ===")
    print(f"{'method':<22}{'clusters':>10}{'precision':>12}{'recall':>10}"
          f"{'f1':>8}{'mojofm':>10}")
    for m in METHODS:
        d = summary["methods"][m]
        print(f"{m:<22}{d['n_clusters']:>10}{d['precision']:>12.3f}"
              f"{d['recall']:>10.3f}{d['f1']:>8.3f}{d['mojofm']:>10.3f}")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-slug", required=True)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--package-root", required=True)
    ap.add_argument("--bgi-graph", required=True)
    ap.add_argument("--ext", default="py")
    ap.add_argument("--language", default="python", choices=["python", "go"])
    ap.add_argument("--truth-depth", type=int, default=1)
    ap.add_argument("--truth-split", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    run(
        repo_slug=args.repo_slug,
        repo_root=args.repo_root,
        package_root=args.package_root,
        bgi_graph_path=args.bgi_graph,
        extensions=args.ext.split(","),
        out_dir=args.out,
        truth_depth=args.truth_depth,
        truth_split_dirs=tuple(d for d in args.truth_split.split(",") if d),
        language=args.language,
    )


if __name__ == "__main__":
    main()
