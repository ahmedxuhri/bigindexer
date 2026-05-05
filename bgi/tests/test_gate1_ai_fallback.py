"""
Tests for Gate 1 — AI Position 1: Token Fallback (ai_fallback.py).

Coverage:
  - classify() — call-level fallback
  - classify_unit() — unit-level fallback
  - flush() — JSONL logging
  - unresolved_snapshot()
  - Integration: unit-level fallback fires when function has no behavioural tokens
  - Integration: fallback does NOT fire when disabled (enabled=False)
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import pytest

from bgi.core.cov import COV
from bgi.gate1.ai_fallback import AIFallback


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client_response(text: str):
    """Build a mock OpenAI-compatible client whose chat.completions.create() returns text."""
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _make_call_node(text: str = "someLib.doSomething(x)"):
    """Minimal mock tree-sitter Node for a call expression."""
    from bgi.gate1.rules import node_text as _nt  # noqa: F401
    node = MagicMock()
    node.type = "call_expression"
    # patch node_text to return our string
    with patch("bgi.gate1.ai_fallback.node_text", return_value=text):
        yield node


# ── classify() — call-level ───────────────────────────────────────────────────

class TestClassifyCall:
    def test_disabled_returns_none(self):
        ai = AIFallback(enabled=False)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="foo()"):
            result = ai.classify(node)
        assert result is None

    def test_disabled_still_logs(self):
        ai = AIFallback(enabled=False)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="cache.set(k,v)"):
            ai.classify(node)
        assert len(ai.unresolved_snapshot()) == 1
        assert ai.unresolved_snapshot()[0]["type"] == "call"

    def test_enabled_returns_classified_token(self):
        client = _make_client_response("FETCH 0.82")
        ai = AIFallback(enabled=True, client=client)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="http.get(url)"):
            result = ai.classify(node, context_snippet="http.get(url)")
        assert result is not None
        token, conf = result
        assert token == COV.FETCH
        assert abs(conf - 0.82) < 0.001

    def test_enabled_unknown_returns_none(self):
        client = _make_client_response("UNKNOWN 0.0")
        ai = AIFallback(enabled=True, client=client)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="foo()"):
            result = ai.classify(node)
        assert result is None

    def test_low_confidence_returns_none(self):
        """Confidence <= 0.5 should be rejected."""
        client = _make_client_response("FETCH 0.4")
        ai = AIFallback(enabled=True, client=client)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="x()"):
            result = ai.classify(node)
        assert result is None

    def test_invalid_token_returns_none(self):
        client = _make_client_response("NOTAVALIDTOKEN 0.9")
        ai = AIFallback(enabled=True, client=client)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="x()"):
            result = ai.classify(node)
        assert result is None

    def test_malformed_response_returns_none(self):
        client = _make_client_response("something unexpected here with extra words")
        ai = AIFallback(enabled=True, client=client)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="x()"):
            result = ai.classify(node)
        assert result is None

    def test_exception_returns_none(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("network error")
        ai = AIFallback(enabled=True, client=client)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="x()"):
            result = ai.classify(node)
        assert result is None


# ── classify_unit() — unit-level ──────────────────────────────────────────────

class TestClassifyUnit:
    def test_disabled_returns_empty_list(self):
        ai = AIFallback(enabled=False)
        result = ai.classify_unit("mod.py::foo", "def foo(): pass")
        assert result == []

    def test_disabled_still_logs(self):
        ai = AIFallback(enabled=False)
        ai.classify_unit("mod.py::bar", "def bar(): pass", language="python")
        snapshot = ai.unresolved_snapshot()
        assert len(snapshot) == 1
        entry = snapshot[0]
        assert entry["type"] == "unit"
        assert entry["unit_id"] == "mod.py::bar"
        assert entry["language"] == "python"

    def test_enabled_returns_token_list(self):
        client = _make_client_response('[["FETCH", 0.85], ["TRANSFORM", 0.7]]')
        ai = AIFallback(enabled=True, client=client)
        result = ai.classify_unit("api.py::load_data", "def load_data(): ...", language="python")
        assert len(result) == 2
        tokens = [t for t, _ in result]
        assert COV.FETCH in tokens
        assert COV.TRANSFORM in tokens

    def test_enabled_empty_llm_response(self):
        client = _make_client_response("[]")
        ai = AIFallback(enabled=True, client=client)
        result = ai.classify_unit("a.py::x", "def x(): pass")
        assert result == []

    def test_enabled_filters_low_confidence(self):
        client = _make_client_response('[["FETCH", 0.3], ["LOG", 0.9]]')
        ai = AIFallback(enabled=True, client=client)
        result = ai.classify_unit("a.py::x", "def x(): ...", language="python")
        tokens = [t for t, _ in result]
        assert COV.FETCH not in tokens
        assert COV.LOG in tokens

    def test_enabled_invalid_token_skipped(self):
        client = _make_client_response('[["NOTREAL", 0.9], ["PERSIST", 0.8]]')
        ai = AIFallback(enabled=True, client=client)
        result = ai.classify_unit("a.py::x", "def x(): ...", language="python")
        tokens = [t for t, _ in result]
        assert len(tokens) == 1
        assert COV.PERSIST in tokens

    def test_exception_returns_empty(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("boom")
        ai = AIFallback(enabled=True, client=client)
        result = ai.classify_unit("a.py::x", "def x(): pass")
        assert result == []

    def test_language_passed_in_log(self):
        ai = AIFallback(enabled=False)
        ai.classify_unit("a.ts::Svc::method", "method() {}", language="typescript")
        entry = ai.unresolved_snapshot()[0]
        assert entry["language"] == "typescript"


# ── flush() / logging ─────────────────────────────────────────────────────────

class TestFlush:
    def test_flush_writes_jsonl(self, tmp_path):
        log = tmp_path / "unreslvd.jsonl"
        ai = AIFallback(enabled=False, log_path=log)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="x()"):
            ai.classify(node)
        ai.classify_unit("a.py::f", "def f(): pass")
        written = ai.flush(scan_run="test-run")
        assert written == 2
        lines = log.read_text().strip().splitlines()
        assert len(lines) == 2
        records = [json.loads(l) for l in lines]
        types = {r["type"] for r in records}
        assert types == {"call", "unit"}
        assert all(r["scan_run"] == "test-run" for r in records)

    def test_flush_clears_buffer(self, tmp_path):
        log = tmp_path / "unreslvd.jsonl"
        ai = AIFallback(enabled=False, log_path=log)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="x()"):
            ai.classify(node)
        ai.flush()
        assert ai.unresolved_snapshot() == []

    def test_flush_empty_returns_zero(self, tmp_path):
        log = tmp_path / "unreslvd.jsonl"
        ai = AIFallback(enabled=False, log_path=log)
        written = ai.flush()
        assert written == 0
        assert not log.exists()

    def test_flush_appends(self, tmp_path):
        log = tmp_path / "unreslvd.jsonl"
        ai = AIFallback(enabled=False, log_path=log)
        node = MagicMock()
        with patch("bgi.gate1.ai_fallback.node_text", return_value="a()"):
            ai.classify(node)
        ai.flush(scan_run="run1")
        with patch("bgi.gate1.ai_fallback.node_text", return_value="b()"):
            ai.classify(node)
        ai.flush(scan_run="run2")
        lines = log.read_text().strip().splitlines()
        assert len(lines) == 2


# ── Integration: unit-level fallback fires in Python scanner ──────────────────

class TestUnitFallbackIntegration:
    """Scan a Python file where the function has no detectable behavioural tokens.
    The unit-level AI fallback should fire and assign tokens."""

    # A function whose name, body and params produce no Tier 1-4/2/3 hits
    _MYSTERY_SOURCE = textwrap.dedent("""\
        def xyzzy_handler(cfg):
            cfg._internal_dispatch()
    """)

    def test_fallback_fires_when_no_tokens(self, tmp_path):
        src = tmp_path / "mystery.py"
        src.write_text(self._MYSTERY_SOURCE)

        client = _make_client_response('[["DELEGATE", 0.75]]')
        ai = AIFallback(enabled=True, client=client)

        from bgi.gate1.scanner import scan_file
        results = scan_file(src, root=tmp_path, ai=ai)

        # At least one unit should have been classified by AI
        ai_units = [fp for fp in results if fp.source in ("ai_classified", "composite")]
        assert len(ai_units) >= 1
        unit = ai_units[0]
        assert COV.DELEGATE in unit.tokens

    def test_fallback_disabled_leaves_tokens_empty(self, tmp_path):
        src = tmp_path / "mystery.py"
        src.write_text(self._MYSTERY_SOURCE)

        ai = AIFallback(enabled=False)
        from bgi.gate1.scanner import scan_file
        results = scan_file(src, root=tmp_path, ai=ai)

        for fp in results:
            assert fp.source != "ai_classified"
        # Still logged
        assert len(ai.unresolved_snapshot()) >= 1
