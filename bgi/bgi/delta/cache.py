"""
BGI Delta / Incremental Scanning — ScanCache.

Tracks per-file content hashes so subsequent scans only re-parse files
that have actually changed. Two change-detection strategies:

  1. mtime  — fast; check OS modification time before hashing.
  2. git    — if the root is a git repo, use `git diff --name-only` to
              enumerate changed/new/deleted paths since the last commit.
              Falls back to mtime when git is unavailable.

Cache file layout (JSON):
  {
    "bgi_cache_version": 1,
    "entries": {
      "<rel_path>": {
        "mtime":  1714000000.0,
        "hash":   "<sha256[:16]>",
        "units":  [ { ...COVFingerprint fields... }, ... ]
      }
    }
  }

Fingerprint serialization:
  tokens / class_context stored as bare COV value strings ("FETCH", not "COV.FETCH").
  Reconstructed via COV(value).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint

_CACHE_VERSION = 1


# ── Fingerprint serialization ────────────────────────────────────────────────

def _fp_to_dict(fp: COVFingerprint) -> dict:
    return {
        "unit_id":    fp.unit_id,
        "tokens":     [t.value for t in fp.tokens],
        "class_context": [t.value for t in fp.class_context],
        "confidence": fp.confidence,
        "source":     fp.source,
        "language":   fp.language,
        "line_range": list(fp.line_range),
    }


def _dict_to_fp(d: dict) -> COVFingerprint:
    return COVFingerprint(
        unit_id=d["unit_id"],
        tokens=[COV(v) for v in d.get("tokens", [])],
        class_context=[COV(v) for v in d.get("class_context", [])],
        confidence=d.get("confidence", 1.0),
        source=d.get("source", "deterministic"),
        language=d.get("language", "python"),
        line_range=tuple(d.get("line_range", [0, 0])),
    )


# ── Git helpers ───────────────────────────────────────────────────────────────

def _git_changed_files(root: Path) -> set[str] | None:
    """
    Return a set of repo-relative file paths that git considers modified,
    added, or deleted (working tree + index) relative to HEAD.
    Returns None if git is not available or root is not a git repository.
    """
    try:
        # Files changed in working tree + index vs HEAD
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        changed = set(result.stdout.splitlines())

        # Also untracked/new files (not in HEAD yet)
        result2 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result2.returncode == 0:
            changed |= set(result2.stdout.splitlines())

        return changed
    except Exception:
        return None


def _file_hash(path: Path) -> str:
    """SHA-256 (first 16 hex chars) of file content."""
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return h[:16]


# ── ScanCache ─────────────────────────────────────────────────────────────────

class ScanCache:
    """
    Persistent cache of per-file scan results.

    Usage::

        cache = ScanCache.load(cache_path)
        dirty, cached_fps = cache.partition(source_files, root, use_git=True)

        # scan only dirty files
        new_fps = scan_those_dirty_files(dirty)
        cache.update_many(dirty, root, new_fps_by_file)

        cache.save(cache_path)
        all_fps = cached_fps + new_fps
    """

    def __init__(self, entries: dict[str, dict] | None = None) -> None:
        # entries: rel_path → {mtime, hash, units}
        self._entries: dict[str, dict] = entries or {}

    # ── Persistence ───────────────────────────────────────────────────────

    @classmethod
    def load(cls, cache_path: str | Path) -> "ScanCache":
        """Load from JSON file; returns empty cache on missing/corrupt file."""
        p = Path(cache_path)
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("bgi_cache_version") != _CACHE_VERSION:
                return cls()
            return cls(data.get("entries", {}))
        except Exception:
            return cls()

    def save(self, cache_path: str | Path) -> None:
        """Persist to JSON file."""
        p = Path(cache_path)
        p.write_text(
            json.dumps(
                {"bgi_cache_version": _CACHE_VERSION, "entries": self._entries},
                indent=2,
            ),
            encoding="utf-8",
        )

    # ── Core API ──────────────────────────────────────────────────────────

    def partition(
        self,
        source_files: list[Path],
        root: Path,
        use_git: bool = True,
    ) -> tuple[list[Path], list[COVFingerprint]]:
        """
        Split *source_files* into (dirty_files, cached_fingerprints).

        dirty_files        — need re-scanning (new / changed / unknown)
        cached_fingerprints — fingerprints from files that haven't changed
        """
        git_changed: set[str] | None = None
        if use_git:
            git_changed = _git_changed_files(root)

        dirty: list[Path] = []
        cached_fps: list[COVFingerprint] = []

        for f in source_files:
            rel = str(f.relative_to(root))
            entry = self._entries.get(rel)

            if entry is None:
                dirty.append(f)
                continue

            # Git-based fast-path
            if git_changed is not None:
                if rel not in git_changed:
                    # git says unchanged → trust cache
                    cached_fps.extend(_dict_to_fp(u) for u in entry.get("units", []))
                    continue
                else:
                    # git explicitly says changed → dirty
                    dirty.append(f)
                    continue

            # mtime fast path
            try:
                current_mtime = f.stat().st_mtime
            except OSError:
                dirty.append(f)
                continue

            if current_mtime == entry.get("mtime"):
                cached_fps.extend(_dict_to_fp(u) for u in entry.get("units", []))
                continue

            # mtime differs — verify by hash
            try:
                current_hash = _file_hash(f)
            except OSError:
                dirty.append(f)
                continue

            if current_hash == entry.get("hash"):
                # Content unchanged; update mtime so next check is faster
                entry["mtime"] = current_mtime
                cached_fps.extend(_dict_to_fp(u) for u in entry.get("units", []))
            else:
                dirty.append(f)

        return dirty, cached_fps

    def update(
        self,
        file_path: Path,
        root: Path,
        fingerprints: list[COVFingerprint],
        file_language: str | None = None,
    ) -> None:
        """Store scan result for *file_path*."""
        rel = str(file_path.relative_to(root))
        try:
            mtime = file_path.stat().st_mtime
            content_hash = _file_hash(file_path)
        except OSError:
            mtime = 0.0
            content_hash = ""
        language = file_language
        if not language and fingerprints:
            language = fingerprints[0].language
        self._entries[rel] = {
            "mtime": mtime,
            "hash":  content_hash,
            "language": language or "unknown",
            "units": [_fp_to_dict(fp) for fp in fingerprints],
        }

    def update_many(
        self,
        file_paths: list[Path],
        root: Path,
        fps_by_rel: dict[str, list[COVFingerprint]],
        file_languages: dict[str, str] | None = None,
    ) -> None:
        """Batch version of update(); keyed by rel_path strings."""
        for f in file_paths:
            rel = str(f.relative_to(root))
            self.update(
                f,
                root,
                fps_by_rel.get(rel, []),
                file_language=(file_languages or {}).get(rel),
            )

    def purge_deleted(self, source_files: list[Path], root: Path) -> list[str]:
        """Remove entries for files that no longer exist. Returns purged rel paths."""
        current = {str(f.relative_to(root)) for f in source_files}
        deleted = [k for k in self._entries if k not in current]
        for k in deleted:
            del self._entries[k]
        return deleted

    # ── Stats / introspection ──────────────────────────────────────────────

    def stats(self) -> dict:
        total_files = len(self._entries)
        total_units = sum(len(e.get("units", [])) for e in self._entries.values())
        return {"cached_files": total_files, "cached_units": total_units}

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        s = self.stats()
        return f"ScanCache(files={s['cached_files']}, units={s['cached_units']})"
