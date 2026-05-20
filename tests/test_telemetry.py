"""Tests for bgi/telemetry.py.

Coverage:
  - is_enabled: respects BGI_TELEMETRY env in all standard truthy/falsy forms
  - compute_repo_id: deterministic for same input, no PII leak
  - repo_size_bucket: thresholds
  - report_event: no-op when disabled, fire-and-forget when enabled,
    silent on network failure
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bgi.telemetry import (
    compute_repo_id,
    is_enabled,
    report_event,
    repo_size_bucket,
)


# ── is_enabled ────────────────────────────────────────────────────────────────

class TestIsEnabled:
    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "True", "YES"])
    def test_truthy_values_enable(self, val, monkeypatch):
        monkeypatch.setenv("BGI_TELEMETRY", val)
        assert is_enabled() is True

    @pytest.mark.parametrize("val", ["", "0", "false", "no", "off", "anything-else"])
    def test_falsy_values_disable(self, val, monkeypatch):
        monkeypatch.setenv("BGI_TELEMETRY", val)
        assert is_enabled() is False

    def test_unset_disables(self, monkeypatch):
        monkeypatch.delenv("BGI_TELEMETRY", raising=False)
        assert is_enabled() is False


# ── repo_size_bucket ──────────────────────────────────────────────────────────

class TestRepoSizeBucket:
    @pytest.mark.parametrize("count,bucket", [
        (0, "S"), (1, "S"), (199, "S"),
        (200, "M"), (500, "M"), (1999, "M"),
        (2000, "L"), (10000, "L"), (19999, "L"),
        (20000, "XL"), (100000, "XL"), (1000000, "XL"),
    ])
    def test_thresholds(self, count, bucket):
        assert repo_size_bucket(count) == bucket


# ── compute_repo_id ───────────────────────────────────────────────────────────

class TestComputeRepoId:
    def test_returns_12_hex_chars(self, tmp_path):
        rid = compute_repo_id(tmp_path)
        assert len(rid) == 12
        assert all(c in "0123456789abcdef" for c in rid)

    def test_deterministic_for_same_path(self, tmp_path):
        assert compute_repo_id(tmp_path) == compute_repo_id(tmp_path)

    def test_different_paths_different_ids(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        assert compute_repo_id(a) != compute_repo_id(b)

    def test_id_does_not_leak_path(self, tmp_path):
        # The id must not contain the path or any obvious substring of it
        secret = tmp_path / "secret-project-name"
        secret.mkdir()
        rid = compute_repo_id(secret)
        assert "secret" not in rid
        assert "project" not in rid

    def test_handles_missing_git(self, monkeypatch, tmp_path):
        # Force git remote lookup to fail by clobbering PATH
        monkeypatch.setenv("PATH", "/nonexistent")
        rid = compute_repo_id(tmp_path)
        assert len(rid) == 12


# ── report_event ──────────────────────────────────────────────────────────────

class TestReportEvent:
    def test_noop_when_disabled(self, monkeypatch):
        monkeypatch.delenv("BGI_TELEMETRY", raising=False)
        called = []
        with patch("bgi.telemetry._post", side_effect=lambda *a, **kw: called.append(a)):
            report_event("mcp_start", version="0.1.4", repo_id="abc123def456")
        assert called == []

    def test_posts_when_enabled(self, monkeypatch):
        monkeypatch.setenv("BGI_TELEMETRY", "1")
        called = []
        with patch("bgi.telemetry._post", side_effect=lambda *a, **kw: called.append(a)):
            report_event("mcp_start", version="0.1.4", repo_id="abc123def456",
                         block=True)
        assert len(called) == 1
        endpoint, payload = called[0]
        assert "/api/telemetry" in endpoint
        assert payload["event_kind"] == "mcp_start"
        assert payload["version"] == "0.1.4"
        assert payload["repo_id"] == "abc123def456"
        assert payload["os"] in {"linux", "darwin", "windows", "other"}

    def test_includes_optional_fields(self, monkeypatch):
        monkeypatch.setenv("BGI_TELEMETRY", "1")
        called = []
        with patch("bgi.telemetry._post", side_effect=lambda *a, **kw: called.append(a)):
            report_event("tool_call", version="0.1.4", repo_id="abc123def456",
                         repo_size_bucket="L", lang_tier_count=3,
                         tool_name="cluster_of_file", block=True)
        assert len(called) == 1
        payload = called[0][1]
        assert payload["repo_size_bucket"] == "L"
        assert payload["lang_tier_count"] == 3
        assert payload["tool_name"] == "cluster_of_file"

    def test_silent_on_network_failure(self, monkeypatch):
        """Telemetry must never raise — exceptions in _post are swallowed."""
        monkeypatch.setenv("BGI_TELEMETRY", "1")
        with patch("urllib.request.urlopen", side_effect=RuntimeError("network down")):
            # Should not raise:
            report_event("mcp_start", version="0.1.4", repo_id="abc123def456",
                         block=True)

    def test_async_does_not_block(self, monkeypatch):
        """Default block=False returns immediately even if endpoint is slow."""
        monkeypatch.setenv("BGI_TELEMETRY", "1")
        slow_calls = []
        def slow_post(*args, **kwargs):
            import time
            time.sleep(5)
            slow_calls.append(args)
        with patch("bgi.telemetry._post", side_effect=slow_post):
            import time
            t0 = time.time()
            report_event("mcp_start", version="0.1.4", repo_id="abc123def456")
            # Should return well under the slow_post sleep duration
            assert time.time() - t0 < 1.0
