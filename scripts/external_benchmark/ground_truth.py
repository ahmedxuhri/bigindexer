"""Ground-truth clustering from a repo's top-level package layout.

The maintainers' own directory layout is used as architectural ground
truth: each top-level subdirectory under the package root = one cluster.
Files at the package root form a single 'root' cluster.

This is the standard fallback in architecture-recovery work when no
labeled corpus is available, and it predates the BGI evaluation entirely.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def collect_files(repo_root: str, package_root: str, extensions: Iterable[str],
                  exclude_dirs: Iterable[str] = ()) -> list[str]:
    pkg = Path(repo_root) if package_root in ("", ".") else Path(repo_root) / package_root
    excluded = {e.strip("/") for e in exclude_dirs}
    out: list[str] = []
    exts = tuple(e if e.startswith(".") else f".{e}" for e in extensions)
    for root, dirs, files in os.walk(pkg):
        dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
        for f in files:
            if f.endswith(exts):
                rel = os.path.relpath(os.path.join(root, f), repo_root)
                out.append(rel)
    return sorted(out)


def package_layout_clusters(
    files: list[str],
    package_root: str,
    depth: int = 1,
    split_dirs: tuple[str, ...] = (),
) -> dict[str, str]:
    """Map each file to a cluster derived from its directory path.

    depth=1 (default): top-level subpackage under package_root.
    depth=2: top-level + second-level (e.g. django/contrib/auth → its own
             cluster). Files shallower than depth keep their actual depth.
    split_dirs: top-level dirs that should always be split one level deeper
                even when depth=1 (e.g. django/contrib is a meta-package
                of independent apps; treating it as one cluster is wrong).

    Files directly under package_root land in cluster '<package_root>:_root'.
    """
    clusters: dict[str, str] = {}
    is_repo_root = package_root in ("", ".")
    pkg_prefix = "" if is_repo_root else package_root.rstrip("/") + "/"
    label = "repo" if is_repo_root else package_root
    split_set = set(split_dirs)
    for f in files:
        if pkg_prefix and not f.startswith(pkg_prefix):
            continue
        rest = f[len(pkg_prefix):] if pkg_prefix else f
        parts = rest.split("/")
        if len(parts) == 1:
            clusters[f] = f"{label}:_root"
            continue
        effective_depth = depth
        if depth == 1 and parts[0] in split_set and len(parts) > 2:
            effective_depth = 2
        take = min(effective_depth, len(parts) - 1)
        cluster = f"{label}:" + "/".join(parts[:take])
        clusters[f] = cluster
    return clusters


if __name__ == "__main__":
    import sys
    repo, pkg = sys.argv[1], sys.argv[2]
    exts = sys.argv[3].split(",") if len(sys.argv) > 3 else ["py"]
    files = collect_files(repo, pkg, exts)
    gt = package_layout_clusters(files, pkg)
    from collections import Counter
    sizes = Counter(gt.values())
    print(f"files: {len(files)}, clusters: {len(sizes)}")
    for c, n in sizes.most_common():
        print(f"  {c}: {n}")
