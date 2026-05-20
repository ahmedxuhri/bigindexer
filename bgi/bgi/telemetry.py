"""BGI telemetry — opt-in anonymous pings.

This module is the only place in BGI that makes outbound network calls
about user behavior. Disabled by default. Enable with:

    BGI_TELEMETRY=1

Or disable explicitly with `--no-telemetry` on the CLI (handled by the caller).

What we collect (full schema in docs/TELEMETRY.md):
  - BGI version, OS, OS version
  - Event kind: 'mcp_start' or 'tool_call'
  - Tool name (for tool_call only)
  - Repo identity: sha256 of `git remote get-url origin` truncated to 12 chars
    — this lets us deduplicate "same repo seen twice" without ever knowing
    which repo. No paths, no code, no user identity.
  - Repo size bucket: S/M/L/XL based on file count
  - Language tier count: how many distinct language tiers appear in the repo

What we never collect:
  - File paths, source code, identifiers, query strings
  - Repo names, organization names, URLs
  - Any user-identifying information
  - Server-side IP addresses (nginx-level: not logged)

Network behavior:
  - 2-second hard timeout
  - Failures are silent — telemetry must never break the user's workflow
  - One thread per ping, fire-and-forget, never blocks the caller
"""
from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import threading
import urllib.request
from json import dumps
from pathlib import Path
from typing import Any

__all__ = [
    "is_enabled",
    "compute_repo_id",
    "repo_size_bucket",
    "report_event",
    "DEFAULT_ENDPOINT",
]


DEFAULT_ENDPOINT = "https://bigindexer.com/api/telemetry"
_TIMEOUT_SECONDS = 2.0


def is_enabled() -> bool:
    """True only when BGI_TELEMETRY is set to a truthy value."""
    val = os.environ.get("BGI_TELEMETRY", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _normalize_os() -> str:
    sys_name = platform.system().lower()
    if sys_name == "linux":
        return "linux"
    if sys_name == "darwin":
        return "darwin"
    if sys_name == "windows":
        return "windows"
    return "other"


def _safe_os_version() -> str:
    """Return a short OS version string. No machine-identifying detail."""
    try:
        return platform.release()[:64]
    except Exception:
        return ""


def _git_remote_url(repo_root: Path) -> str | None:
    """Return the origin remote URL, or None if unavailable.

    Uses subprocess so it works even when GitPython isn't installed.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=2.0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def compute_repo_id(repo_root: Path | str) -> str:
    """Stable 12-char hex identity for a repo.

    Derived from `git remote get-url origin` so the same repo cloned to
    different paths yields the same id. If no remote is configured, falls
    back to the absolute path's hash so repeated runs from the same checkout
    still deduplicate. Never reveals the underlying URL or path.
    """
    root = Path(repo_root).resolve()
    seed = _git_remote_url(root)
    if not seed:
        seed = f"path:{root}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return digest[:12]


def repo_size_bucket(file_count: int) -> str:
    """Coarse bucket for repo size. Defensible boundaries, no identifying detail."""
    if file_count < 200:
        return "S"
    if file_count < 2000:
        return "M"
    if file_count < 20000:
        return "L"
    return "XL"


def _post(endpoint: str, payload: dict[str, Any]) -> None:
    body = dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "bgi-telemetry"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS):
            pass
    except Exception:
        # Telemetry must never break the user's workflow.
        pass


def report_event(
    event_kind: str,
    *,
    version: str,
    repo_id: str,
    repo_size_bucket: str | None = None,
    lang_tier_count: int | None = None,
    tool_name: str | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    block: bool = False,
) -> None:
    """Send an opt-in telemetry event. Returns immediately unless block=True.

    No-op if BGI_TELEMETRY is not set. Network failures are silent.
    """
    if not is_enabled():
        return
    payload: dict[str, Any] = {
        "event_kind": event_kind,
        "version": version,
        "repo_id": repo_id,
        "os": _normalize_os(),
        "os_version": _safe_os_version(),
    }
    if repo_size_bucket is not None:
        payload["repo_size_bucket"] = repo_size_bucket
    if lang_tier_count is not None:
        payload["lang_tier_count"] = lang_tier_count
    if tool_name is not None:
        payload["tool_name"] = tool_name

    if block:
        _post(endpoint, payload)
        return
    threading.Thread(
        target=_post, args=(endpoint, payload),
        daemon=True, name="bgi-telemetry",
    ).start()
