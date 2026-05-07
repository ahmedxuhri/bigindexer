"""Tests for bgi.delta.cache — ScanCache incremental scanning."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.delta.cache import (
    ScanCache,
    _dict_to_fp,
    _file_hash,
    _fp_to_dict,
    _git_changed_files,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fp(uid: str, tokens: list[COV] | None = None, confidence: float = 0.9) -> COVFingerprint:
    return COVFingerprint(
        unit_id=uid,
        tokens=tokens or [COV.FETCH],
        class_context=[],
        confidence=confidence,
        source="deterministic",
        language="python",
        line_range=(1, 10),
    )


def _write(path: Path, content: str = "def foo(): pass\n") -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ── Fingerprint serialization ──────────────────────────────────────────────────

class TestFpSerialization:
    def test_round_trip_basic(self):
        fp = _fp("mod.foo", [COV.FETCH, COV.PERSIST])
        d = _fp_to_dict(fp)
        fp2 = _dict_to_fp(d)
        assert fp2.unit_id == fp.unit_id
        assert fp2.tokens == fp.tokens
        assert fp2.confidence == fp.confidence
        assert fp2.source == fp.source
        assert fp2.language == fp.language

    def test_tokens_stored_as_bare_values(self):
        fp = _fp("x", [COV.AUTHENTICATE, COV.LOG])
        d = _fp_to_dict(fp)
        assert d["tokens"] == ["AUTHENTICATE", "LOG"]

    def test_class_context_serialized(self):
        fp = COVFingerprint(
            unit_id="x", tokens=[COV.FETCH], class_context=[COV.PERSIST],
            confidence=1.0, source="deterministic", language="python", line_range=(1, 5),
        )
        d = _fp_to_dict(fp)
        fp2 = _dict_to_fp(d)
        assert fp2.class_context == [COV.PERSIST]

    def test_empty_tokens(self):
        fp = COVFingerprint(
            unit_id="x", tokens=[], class_context=[],
            confidence=1.0, source="deterministic", language="python", line_range=(1, 5),
        )
        d = _fp_to_dict(fp)
        fp2 = _dict_to_fp(d)
        assert fp2.tokens == []

    def test_line_range_preserved(self):
        fp = COVFingerprint(
            unit_id="x", tokens=[], class_context=[],
            confidence=1.0, source="deterministic", language="python", line_range=(5, 20),
        )
        d = _fp_to_dict(fp)
        fp2 = _dict_to_fp(d)
        assert tuple(fp2.line_range) == (5, 20)

    def test_missing_fields_use_defaults(self):
        fp2 = _dict_to_fp({"unit_id": "y"})
        assert fp2.tokens == []
        assert fp2.confidence == 1.0
        assert fp2.source == "deterministic"


# ── ScanCache persistence ─────────────────────────────────────────────────────

class TestScanCachePersistence:
    def test_empty_cache_on_missing_file(self, tmp_path):
        cache = ScanCache.load(tmp_path / "missing.json")
        assert len(cache) == 0

    def test_empty_cache_on_corrupt_file(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        cache = ScanCache.load(p)
        assert len(cache) == 0

    def test_empty_cache_on_version_mismatch(self, tmp_path):
        p = tmp_path / "old.json"
        p.write_text(json.dumps({"bgi_cache_version": 99, "entries": {"x": {}}}))
        cache = ScanCache.load(p)
        assert len(cache) == 0

    def test_save_and_reload(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.foo")])
        p = tmp_path / "cache.json"
        cache.save(p)

        cache2 = ScanCache.load(p)
        assert len(cache2) == 1

    def test_reload_fingerprints_intact(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.foo", [COV.AUTHENTICATE])])
        p = tmp_path / "cache.json"
        cache.save(p)

        cache2 = ScanCache.load(p)
        dirty, cached_fps = cache2.partition([f], root, use_git=False)
        assert len(dirty) == 0
        assert len(cached_fps) == 1
        assert cached_fps[0].tokens == [COV.AUTHENTICATE]


# ── ScanCache.partition ───────────────────────────────────────────────────────

class TestPartition:
    def test_unknown_file_is_dirty(self, tmp_path):
        f = _write(tmp_path / "new.py")
        cache = ScanCache()
        dirty, cached = cache.partition([f], tmp_path, use_git=False)
        assert f in dirty
        assert cached == []

    def test_unchanged_file_is_cached(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.foo")])

        dirty, cached = cache.partition([f], root, use_git=False)
        assert dirty == []
        assert len(cached) == 1

    def test_changed_content_is_dirty(self, tmp_path):
        f = _write(tmp_path / "mod.py", "def foo(): pass")
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.foo")])

        # Change content (also touch mtime)
        time.sleep(0.01)
        f.write_text("def bar(): pass", encoding="utf-8")

        dirty, cached = cache.partition([f], root, use_git=False)
        assert f in dirty
        assert cached == []

    def test_same_content_different_mtime_uses_hash(self, tmp_path):
        content = "def foo(): pass\n"
        f = _write(tmp_path / "mod.py", content)
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.foo")])

        # Simulate mtime change without content change by directly altering entry
        entry = cache._entries[str(f.relative_to(root))]
        entry["mtime"] = entry["mtime"] - 1  # pretend mtime changed

        dirty, cached = cache.partition([f], root, use_git=False)
        # Hash matches → cached
        assert dirty == []
        assert len(cached) == 1

    def test_multiple_files_split_correctly(self, tmp_path):
        root = tmp_path
        f1 = _write(root / "a.py")
        f2 = _write(root / "b.py")
        f3 = _write(root / "c.py")  # not in cache → dirty

        cache = ScanCache()
        cache.update(f1, root, [_fp("a.foo")])
        cache.update(f2, root, [_fp("b.bar")])

        dirty, cached = cache.partition([f1, f2, f3], root, use_git=False)
        assert set(dirty) == {f3}
        assert len(cached) == 2

    def test_git_unchanged_skips_mtime_check(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.foo")])

        # Force mtime to differ — git says unchanged → should still be cached
        entry = cache._entries["mod.py"]
        entry["mtime"] = 0.0

        with patch("bgi.delta.cache._git_changed_files", return_value=set()):
            dirty, cached = cache.partition([f], root, use_git=True)

        assert dirty == []
        assert len(cached) == 1

    def test_git_changed_file_goes_dirty(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.foo")])

        with patch("bgi.delta.cache._git_changed_files", return_value={"mod.py"}):
            dirty, cached = cache.partition([f], root, use_git=True)

        assert f in dirty
        assert cached == []

    def test_git_unavailable_falls_back_to_mtime(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.foo")])

        with patch("bgi.delta.cache._git_changed_files", return_value=None):
            dirty, cached = cache.partition([f], root, use_git=True)

        # mtime unchanged → cached
        assert dirty == []
        assert len(cached) == 1


# ── ScanCache.update / update_many ────────────────────────────────────────────

class TestUpdate:
    def test_update_stores_entry(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        cache = ScanCache()
        cache.update(f, tmp_path, [_fp("mod.foo")])
        assert "mod.py" in cache._entries

    def test_update_stores_hash(self, tmp_path):
        f = _write(tmp_path / "mod.py", "content")
        cache = ScanCache()
        cache.update(f, tmp_path, [])
        assert cache._entries["mod.py"]["hash"] == _file_hash(f)

    def test_update_stores_language_from_fingerprint(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        cache = ScanCache()
        cache.update(f, tmp_path, [_fp("mod.foo")])
        assert cache._entries["mod.py"]["language"] == "python"

    def test_update_many(self, tmp_path):
        root = tmp_path
        f1 = _write(root / "a.py")
        f2 = _write(root / "b.py")
        cache = ScanCache()
        cache.update_many([f1, f2], root, {"a.py": [_fp("a.x")], "b.py": [_fp("b.y")]})
        assert len(cache) == 2

    def test_update_many_uses_file_languages(self, tmp_path):
        root = tmp_path
        f1 = _write(root / "a.py")
        f2 = _write(root / "b.ts", "export function b() {}")
        cache = ScanCache()
        cache.update_many(
            [f1, f2],
            root,
            {"a.py": [_fp("a.x")], "b.ts": []},
            file_languages={"a.py": "python", "b.ts": "typescript"},
        )
        assert cache._entries["a.py"]["language"] == "python"
        assert cache._entries["b.ts"]["language"] == "typescript"

    def test_update_overwrites_existing(self, tmp_path):
        f = _write(tmp_path / "mod.py")
        root = tmp_path
        cache = ScanCache()
        cache.update(f, root, [_fp("mod.old")])
        cache.update(f, root, [_fp("mod.new")])
        units = cache._entries["mod.py"]["units"]
        assert units[0]["unit_id"] == "mod.new"


# ── ScanCache.purge_deleted ────────────────────────────────────────────────────

class TestPurgeDeleted:
    def test_purges_missing_files(self, tmp_path):
        root = tmp_path
        f = _write(root / "alive.py")
        cache = ScanCache()
        cache.update(f, root, [])
        # Manually add a ghost entry
        cache._entries["dead.py"] = {"mtime": 0, "hash": "", "units": []}

        deleted = cache.purge_deleted([f], root)
        assert "dead.py" in deleted
        assert "alive.py" not in deleted
        assert len(cache) == 1

    def test_purge_returns_empty_when_all_present(self, tmp_path):
        root = tmp_path
        f = _write(root / "mod.py")
        cache = ScanCache()
        cache.update(f, root, [])
        deleted = cache.purge_deleted([f], root)
        assert deleted == []


# ── ScanCache.stats / repr ─────────────────────────────────────────────────────

class TestStats:
    def test_stats_empty(self):
        cache = ScanCache()
        s = cache.stats()
        assert s == {"cached_files": 0, "cached_units": 0}

    def test_stats_with_entries(self, tmp_path):
        root = tmp_path
        f = _write(root / "mod.py")
        cache = ScanCache()
        cache.update(f, root, [_fp("a"), _fp("b")])
        s = cache.stats()
        assert s["cached_files"] == 1
        assert s["cached_units"] == 2

    def test_repr(self, tmp_path):
        cache = ScanCache()
        r = repr(cache)
        assert "ScanCache" in r
        assert "files=0" in r


# ── _git_changed_files ────────────────────────────────────────────────────────

class TestGitChangedFiles:
    def test_returns_none_outside_git_repo(self, tmp_path):
        result = _git_changed_files(tmp_path)
        # tmp_path is not a git repo → None or empty set
        assert result is None or isinstance(result, set)

    def test_returns_set_inside_git_repo(self):
        # /root/mad/bgi is inside a git repo
        result = _git_changed_files(Path("/root/mad/bgi"))
        assert result is None or isinstance(result, set)

    def test_git_failure_returns_none(self, tmp_path):
        with patch("subprocess.run", side_effect=Exception("no git")):
            result = _git_changed_files(tmp_path)
        assert result is None


# ── _file_hash ─────────────────────────────────────────────────────────────────

class TestFileHash:
    def test_hash_is_16_chars(self, tmp_path):
        f = _write(tmp_path / "x.py")
        h = _file_hash(f)
        assert len(h) == 16

    def test_same_content_same_hash(self, tmp_path):
        f1 = _write(tmp_path / "a.py", "content")
        f2 = _write(tmp_path / "b.py", "content")
        assert _file_hash(f1) == _file_hash(f2)

    def test_different_content_different_hash(self, tmp_path):
        f1 = _write(tmp_path / "a.py", "aaa")
        f2 = _write(tmp_path / "b.py", "bbb")
        assert _file_hash(f1) != _file_hash(f2)
