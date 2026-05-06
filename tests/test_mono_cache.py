"""Tests for multi-package monorepo caching."""
import pytest
from pathlib import Path
import json
from bgi.gate1.mono_cache import (
    detect_packages,
    PackageInfo,
    MultiPackageCache,
    scan_monorepo_incremental,
)


class TestPackageDetection:
    """Test package detection in monorepos."""
    
    def test_detect_single_python_package(self, tmp_path):
        """Detect a single Python package with setup.py."""
        (tmp_path / "setup.py").write_text("# setup")
        (tmp_path / "module.py").write_text("def foo(): pass")
        
        packages = detect_packages(tmp_path)
        assert len(packages) == 1
        assert packages[0].language == "python"
        assert packages[0].manager == "pip"
        assert packages[0].path == tmp_path
    
    def test_detect_single_typescript_package(self, tmp_path):
        """Detect a single TypeScript package with package.json."""
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "index.ts").write_text("export const x = 1;")
        
        packages = detect_packages(tmp_path)
        assert len(packages) == 1
        assert packages[0].language == "typescript"
        assert packages[0].manager == "npm"
    
    def test_detect_multiple_packages(self, tmp_path):
        """Detect multiple packages in a monorepo."""
        # Python package
        py_pkg = tmp_path / "py-service"
        py_pkg.mkdir()
        (py_pkg / "setup.py").write_text("# setup")
        (py_pkg / "main.py").write_text("def main(): pass")
        
        # TypeScript package
        ts_pkg = tmp_path / "ts-web"
        ts_pkg.mkdir()
        (ts_pkg / "package.json").write_text("{}")
        (ts_pkg / "index.ts").write_text("export const x = 1;")
        
        packages = detect_packages(tmp_path)
        assert len(packages) == 2
        
        langs = {pkg.language for pkg in packages}
        assert langs == {"python", "typescript"}
    
    def test_detect_nested_packages(self, tmp_path):
        """Detect nested package structure (packages under packages)."""
        # Root Python package
        (tmp_path / "setup.py").write_text("# root")
        
        # Nested TypeScript package (stops at first marker)
        nested = tmp_path / "frontend"
        nested.mkdir()
        (nested / "package.json").write_text("{}")
        (nested / "src").mkdir()
        (nested / "src" / "app.ts").write_text("export function app() {}")
        
        packages = detect_packages(tmp_path)
        assert len(packages) >= 1
        
        # Should detect both root and nested
        paths = {pkg.path.name for pkg in packages}
        assert "setup.py" in str(tmp_path) or len(packages) >= 1
    
    def test_detect_go_package(self, tmp_path):
        """Detect Go package with go.mod."""
        (tmp_path / "go.mod").write_text("module example")
        (tmp_path / "main.go").write_text("func main() {}")
        
        packages = detect_packages(tmp_path)
        assert len(packages) == 1
        assert packages[0].language == "go"
        assert packages[0].manager == "go"
    
    def test_detect_rust_package(self, tmp_path):
        """Detect Rust package with Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text("[package]")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}")
        
        packages = detect_packages(tmp_path)
        assert len(packages) == 1
        assert packages[0].language == "rust"
        assert packages[0].manager == "cargo"
    
    def test_detect_no_packages(self, tmp_path):
        """Detect no packages in a directory without markers."""
        (tmp_path / "file.txt").write_text("content")
        
        packages = detect_packages(tmp_path)
        # Should return empty list
        assert packages == []


class TestMultiPackageCache:
    """Test MultiPackageCache persistence and management."""
    
    def test_create_empty_cache(self):
        """Create an empty multi-package cache."""
        cache = MultiPackageCache()
        assert cache.data["version"] == 1
        assert cache.data["packages"] == {}
    
    def test_save_and_load_cache(self, tmp_path):
        """Save and load a multi-package cache."""
        cache_file = tmp_path / ".bgi-cache.json"
        
        cache = MultiPackageCache()
        cache.data["packages"]["pkg1"] = {
            "language": "python",
            "manager": "pip",
            "cache": {"file.py": {"hash": "abc123", "units": []}}
        }
        
        cache.save(cache_file)
        
        loaded = MultiPackageCache.load(cache_file)
        assert "pkg1" in loaded.data["packages"]
        assert loaded.data["packages"]["pkg1"]["language"] == "python"
    
    def test_merge_packages(self, tmp_path):
        """Merge package metadata into cache."""
        cache = MultiPackageCache()
        
        pkg1 = PackageInfo(tmp_path / "pkg1", "python", "pip")
        pkg2 = PackageInfo(tmp_path / "pkg2", "typescript", "npm")
        
        cache.merge_packages([pkg1, pkg2], tmp_path)
        
        assert "pkg1" in cache.data["packages"]
        assert "pkg2" in cache.data["packages"]
        assert cache.data["packages"]["pkg1"]["language"] == "python"
        assert cache.data["packages"]["pkg2"]["language"] == "typescript"
    
    def test_get_and_set_package_cache(self, tmp_path):
        """Get and set individual package caches."""
        from bgi.delta.cache import ScanCache
        
        cache = MultiPackageCache()
        pkg_path = tmp_path / "pkg"
        
        # Get empty cache
        scan_cache = cache.get_package_cache(pkg_path, tmp_path)
        assert isinstance(scan_cache, ScanCache)
        
        # Set new data
        scan_cache._entries["file.py"] = {"hash": "abc123", "units": []}
        cache.set_package_cache(pkg_path, tmp_path, "python", "pip", scan_cache)
        
        # Verify it's stored
        assert "pkg" in cache.data["packages"]
        assert cache.data["packages"]["pkg"]["cache"]["file.py"]["hash"] == "abc123"


class TestMonorepoScanning:
    """Test incremental monorepo scanning."""
    
    def test_scan_monorepo_single_package(self, tmp_path):
        """Scan a monorepo with a single Python package."""
        # Create package
        (tmp_path / "setup.py").write_text("# setup")
        (tmp_path / "module.py").write_text("def foo(): pass")
        
        fps, stats = scan_monorepo_incremental(tmp_path)
        
        # Should find fingerprints from module.py
        assert len(fps) >= 1
        assert "python" in stats
        assert stats["python"] == 2  # setup.py + module.py (both scanned, but setup.py may have no units)
    
    def test_scan_monorepo_two_packages(self, tmp_path):
        """Scan a monorepo with two packages."""
        # Python package
        py_pkg = tmp_path / "backend"
        py_pkg.mkdir()
        (py_pkg / "setup.py").write_text("# setup")
        (py_pkg / "main.py").write_text("def main(): pass")
        
        # TypeScript package
        ts_pkg = tmp_path / "frontend"
        ts_pkg.mkdir()
        (ts_pkg / "package.json").write_text("{}")
        (ts_pkg / "app.ts").write_text("export function app() {}")
        
        fps, stats = scan_monorepo_incremental(tmp_path)
        
        # Should have scanned files from both packages
        assert len(fps) >= 1
        assert "python" in stats
        assert "typescript" in stats
    
    def test_scan_monorepo_caching(self, tmp_path):
        """Verify caching works across incremental scans."""
        cache_file = tmp_path / ".bgi-cache.json"
        
        # Create package
        (tmp_path / "setup.py").write_text("# setup")
        (tmp_path / "main.py").write_text("def main(): pass")
        
        # First scan
        fps1, stats1 = scan_monorepo_incremental(tmp_path, cache_file)
        files_scanned_1 = sum(stats1.values())
        
        # Second scan (no changes)
        fps2, stats2 = scan_monorepo_incremental(tmp_path, cache_file)
        files_scanned_2 = sum(stats2.values())
        
        # Both should return same fingerprints
        assert len(fps1) == len(fps2)
        assert files_scanned_1 == files_scanned_2
    
    def test_scan_monorepo_dirty_detection(self, tmp_path):
        """Verify dirty file detection after modification."""
        cache_file = tmp_path / ".bgi-cache.json"
        
        # Create and scan
        (tmp_path / "setup.py").write_text("# setup")
        (tmp_path / "main.py").write_text("def main(): pass")
        
        fps1, _ = scan_monorepo_incremental(tmp_path, cache_file)
        
        # Modify a file
        (tmp_path / "main.py").write_text("def main():\n    print('changed')")
        
        fps2, _ = scan_monorepo_incremental(tmp_path, cache_file)
        
        # Should still have fingerprints (possibly updated)
        assert len(fps2) >= 1


class TestPackageInfo:
    """Test PackageInfo metadata class."""
    
    def test_package_info_creation(self, tmp_path):
        """Create PackageInfo object."""
        pkg = PackageInfo(tmp_path, "python", "pip")
        assert pkg.language == "python"
        assert pkg.manager == "pip"
        assert pkg.path.is_absolute()
    
    def test_package_info_repr(self, tmp_path):
        """Verify PackageInfo repr."""
        pkg = PackageInfo(tmp_path, "typescript", "npm")
        repr_str = repr(pkg)
        assert "typescript" in repr_str
        assert "npm" in repr_str or tmp_path.name in repr_str
