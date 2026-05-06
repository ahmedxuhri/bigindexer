"""
Phase 2 — Incremental auto mode for multi-package monorepos.

Extends ScanCache to support scanning monorepos with multiple packages/languages.
Each package (detected by setup.py, package.json, go.mod, etc.) gets its own cache.

This enables incremental scanning of entire monorepos while respecting
package boundaries and optimizing per-language.
"""
from __future__ import annotations
from pathlib import Path
from typing import Iterator
import json

from bgi.core.fingerprint import COVFingerprint
from bgi.delta.cache import ScanCache


class PackageInfo:
    """Metadata for a detected package."""
    
    def __init__(self, path: Path, language: str, manager: str) -> None:
        """
        Args:
            path: Package root directory
            language: Detected primary language (python, typescript, java, go, rust, ruby)
            manager: Package manager (pip, npm, cargo, go, bundler, maven, etc.)
        """
        self.path = path.resolve()
        self.language = language
        self.manager = manager
    
    def __repr__(self) -> str:
        return f"PackageInfo({self.language} @ {self.path.name})"


def detect_packages(root: Path) -> list[PackageInfo]:
    """
    Detect packages in a monorepo by looking for package manager config files.
    
    Returns packages in depth-first order (deepest packages first).
    
    Args:
        root: Repository root
    
    Returns:
        List of PackageInfo objects sorted by depth (deepest first)
    """
    root = root.resolve()
    packages: list[PackageInfo] = []
    
    # Map of config files to (language, manager)
    config_map = {
        "setup.py": ("python", "pip"),
        "pyproject.toml": ("python", "pip"),
        "requirements.txt": ("python", "pip"),
        "package.json": ("typescript", "npm"),
        "yarn.lock": ("typescript", "yarn"),
        "pnpm-lock.yaml": ("typescript", "pnpm"),
        "go.mod": ("go", "go"),
        "go.sum": ("go", "go"),
        "Cargo.toml": ("rust", "cargo"),
        "Gemfile": ("ruby", "bundler"),
        "pom.xml": ("java", "maven"),
        "build.gradle": ("java", "gradle"),
        ".gitignore": None,  # Skip .gitignore-only dirs
    }
    
    seen_packages = set()
    
    # DFS: look for package markers at each level
    def scan_dir(path: Path, depth: int = 0) -> None:
        if not path.is_dir() or path.name.startswith("."):
            return
        
        # Avoid infinite recursion in symlinks
        try:
            real_path = path.resolve()
            if real_path.samefile(root.parent):
                return
        except (OSError, RuntimeError):
            return
        
        # Check for package markers
        has_marker = False
        detected_lang = None
        detected_manager = None
        
        for config_file, marker_info in config_map.items():
            config_path = path / config_file
            if config_path.exists():
                has_marker = True
                if marker_info:  # Skip .gitignore
                    detected_lang, detected_manager = marker_info
                    break
        
        if has_marker and detected_lang and real_path not in seen_packages:
            packages.append(PackageInfo(path, detected_lang, detected_manager))
            seen_packages.add(real_path)
            return  # Don't recurse into packages (avoid double-detection)
        
        # Recurse into subdirectories
        for subdir in sorted(path.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("."):
                scan_dir(subdir, depth + 1)
    
    scan_dir(root)
    
    # Sort by depth (deepest first)
    packages.sort(key=lambda p: -len(p.path.relative_to(root).parts))
    
    return packages


class MultiPackageCache:
    """
    Manages caching for multi-package monorepos.
    
    Extends ScanCache to support per-package caching with a unified cache file.
    """
    
    def __init__(self, entries: dict[str, dict] | None = None) -> None:
        """
        Args:
            entries: Cache data with structure:
                {
                  "version": 1,
                  "packages": {
                    "<pkg_rel_path>": {
                      "language": "python",
                      "manager": "pip",
                      "cache": <ScanCache._entries format>
                    }
                  }
                }
        """
        self.data = entries or {"version": 1, "packages": {}}
    
    @classmethod
    def load(cls, cache_path: str | Path) -> "MultiPackageCache":
        """Load multi-package cache from JSON file."""
        p = Path(cache_path)
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("version") != 1:
                return cls()
            return cls(data)
        except Exception:
            return cls()
    
    def save(self, cache_path: str | Path) -> None:
        """Persist multi-package cache to JSON file."""
        p = Path(cache_path)
        p.write_text(
            json.dumps(self.data, indent=2),
            encoding="utf-8",
        )
    
    def get_package_cache(self, pkg_path: Path, root: Path) -> ScanCache:
        """Get ScanCache for a specific package."""
        rel = str(pkg_path.relative_to(root))
        if rel not in self.data["packages"]:
            self.data["packages"][rel] = {
                "language": "unknown",
                "manager": "unknown",
                "cache": {}
            }
        
        pkg_data = self.data["packages"][rel]
        return ScanCache(pkg_data.get("cache", {}))
    
    def set_package_cache(
        self, 
        pkg_path: Path, 
        root: Path, 
        language: str,
        manager: str,
        cache: ScanCache,
    ) -> None:
        """Update cache for a specific package."""
        rel = str(pkg_path.relative_to(root))
        self.data["packages"][rel] = {
            "language": language,
            "manager": manager,
            "cache": cache._entries
        }
    
    def merge_packages(self, packages: list[PackageInfo], root: Path) -> None:
        """Initialize/update package metadata in cache."""
        for pkg in packages:
            rel = str(pkg.path.relative_to(root))
            if rel not in self.data["packages"]:
                self.data["packages"][rel] = {
                    "language": pkg.language,
                    "manager": pkg.manager,
                    "cache": {}
                }
            else:
                # Update language/manager if needed
                self.data["packages"][rel]["language"] = pkg.language
                self.data["packages"][rel]["manager"] = pkg.manager


def scan_monorepo_incremental(
    root: Path,
    cache_path: Path | str = ".bgi-mono-cache.json",
    scan_fn_by_lang: dict[str, callable] | None = None,
) -> tuple[list[COVFingerprint], dict[str, int]]:
    """
    Scan a multi-package monorepo with per-package incremental caching.
    
    Args:
        root: Repository root
        cache_path: Path to multi-package cache file
        scan_fn_by_lang: Dict mapping language → scan function(pkg_path, cache)
    
    Returns:
        (all_fingerprints, scan_stats) where stats = {lang: file_count, ...}
    """
    root = Path(root).resolve()
    
    # Detect packages
    packages = detect_packages(root)
    if not packages:
        # Fall back to single-package root-level scan
        packages = [PackageInfo(root, "unknown", "unknown")]
    
    # Load multi-package cache
    cache = MultiPackageCache.load(cache_path)
    cache.merge_packages(packages, root)
    
    all_fingerprints: list[COVFingerprint] = []
    scan_stats: dict[str, int] = {}
    
    # Default scan functions (can be overridden)
    if scan_fn_by_lang is None:
        from bgi.gate1.scanner import scan_directory
        scan_fn_by_lang = {}
    
    # Scan each package
    for pkg in packages:
        print(f"[BGI-Mono] Scanning {pkg.language} package at {pkg.path.relative_to(root)}")
        
        # Get per-package cache
        pkg_cache = cache.get_package_cache(pkg.path, root)
        
        # Collect source files
        if pkg.language == "python":
            source_files = sorted(pkg.path.rglob("*.py"))
        elif pkg.language == "typescript":
            source_files = sorted(set(
                f for ext in ["*.ts", "*.tsx"]
                for f in pkg.path.rglob(ext)
                if ".d.ts" not in f.name
            ))
        elif pkg.language == "java":
            source_files = sorted(pkg.path.rglob("*.java"))
        elif pkg.language == "go":
            source_files = sorted(pkg.path.rglob("*.go"))
        elif pkg.language == "rust":
            source_files = sorted(pkg.path.rglob("*.rs"))
        else:
            continue
        
        # Partition into dirty/cached
        dirty, cached_fps = pkg_cache.partition(source_files, pkg.path, use_git=True)
        all_fingerprints.extend(cached_fps)
        
        # Scan dirty files if any
        if dirty:
            from bgi.gate1.scanner import scan_file
            from bgi.gate1.ai_fallback import AIFallback
            ai = AIFallback(enabled=False)
            for file_path in dirty:
                try:
                    fps = scan_file(file_path, pkg.path, ai=ai)
                    all_fingerprints.extend(fps)
                    pkg_cache.update(file_path, pkg.path, fps)
                except Exception as e:
                    print(f"[BGI-Mono] Warning: skipped {file_path}: {e}")
        
        # Update package cache in multi-package cache
        cache.set_package_cache(pkg.path, root, pkg.language, pkg.manager, pkg_cache)
        
        scan_stats[pkg.language] = len(source_files)
        print(f"[BGI-Mono] {pkg.language}: {len(source_files)} files "
              f"({len(dirty)} dirty, {len(cached_fps)} cached)")
    
    # Save updated cache
    cache.save(cache_path)
    
    return all_fingerprints, scan_stats
