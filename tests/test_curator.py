"""Tests for bgi.ai.curator — Vocabulary Curator (AI Position 4)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bgi.ai.curator import (
    EXTENSION_ZONE,
    ExtensionCandidate,
    VocabularyCurator,
    _heuristic_candidates,
    _load_sep_tokens,
    _load_token_distribution,
    _load_unresolved,
    candidates_to_dict,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


def _make_openai_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_client(content: str):
    client = MagicMock()
    client.chat.completions.create.return_value = _make_openai_response(content)
    return client


# ── _load_unresolved ──────────────────────────────────────────────────────────

class TestLoadUnresolved:
    def test_returns_empty_for_missing_file(self, tmp_path):
        result = _load_unresolved(tmp_path / "missing.jsonl")
        assert result == []

    def test_loads_snippets(self, tmp_path):
        p = tmp_path / "u.jsonl"
        _write_jsonl(p, [{"snippet": "lru_cache(fn)"}, {"snippet": "retry(3, f)"}])
        result = _load_unresolved(p)
        assert "lru_cache(fn)" in result
        assert "retry(3, f)" in result

    def test_skips_empty_snippets(self, tmp_path):
        p = tmp_path / "u.jsonl"
        _write_jsonl(p, [{"snippet": ""}, {"snippet": "batch_insert(rows)"}])
        result = _load_unresolved(p)
        assert "" not in result
        assert len(result) == 1

    def test_skips_malformed_lines(self, tmp_path):
        p = tmp_path / "u.jsonl"
        p.write_text('{"snippet": "ok"}\nnot-json\n{"snippet": "also-ok"}\n')
        result = _load_unresolved(p)
        assert len(result) == 2

    def test_skips_blank_lines(self, tmp_path):
        p = tmp_path / "u.jsonl"
        p.write_text('{"snippet": "x"}\n\n{"snippet": "y"}\n')
        result = _load_unresolved(p)
        assert len(result) == 2

    def test_returns_list_of_strings(self, tmp_path):
        p = tmp_path / "u.jsonl"
        _write_jsonl(p, [{"snippet": "foo()"}])
        result = _load_unresolved(p)
        assert all(isinstance(s, str) for s in result)


# ── _load_sep_tokens ──────────────────────────────────────────────────────────

class TestLoadSepTokens:
    def test_returns_empty_for_missing_db(self, tmp_path):
        result = _load_sep_tokens(tmp_path / "missing.db")
        assert result == Counter()

    def test_loads_from_sqlite(self, tmp_path):
        import sqlite3
        db = tmp_path / "sep.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE suspended_edges (token TEXT, resolved INTEGER)")
        conn.executemany("INSERT INTO suspended_edges VALUES (?, 0)",
                         [("COV.FETCH",), ("COV.FETCH",), ("COV.RECOVER",)])
        conn.commit()
        conn.close()
        result = _load_sep_tokens(db)
        assert result["FETCH"] == 2
        assert result["RECOVER"] == 1

    def test_excludes_resolved_edges(self, tmp_path):
        import sqlite3
        db = tmp_path / "sep.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE suspended_edges (token TEXT, resolved INTEGER)")
        conn.executemany("INSERT INTO suspended_edges VALUES (?, ?)",
                         [("COV.FETCH", 0), ("COV.FETCH", 1)])  # one resolved
        conn.commit()
        conn.close()
        result = _load_sep_tokens(db)
        assert result["FETCH"] == 1

    def test_strips_cov_prefix(self, tmp_path):
        import sqlite3
        db = tmp_path / "sep.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE suspended_edges (token TEXT, resolved INTEGER)")
        conn.execute("INSERT INTO suspended_edges VALUES ('COV.DELEGATE', 0)")
        conn.commit()
        conn.close()
        result = _load_sep_tokens(db)
        assert "DELEGATE" in result

    def test_handles_corrupt_db(self, tmp_path):
        db = tmp_path / "bad.db"
        db.write_bytes(b"not a sqlite file")
        result = _load_sep_tokens(db)
        assert result == Counter()


# ── _load_token_distribution ──────────────────────────────────────────────────

class TestLoadTokenDistribution:
    def test_returns_empty_for_missing_graph(self, tmp_path):
        result = _load_token_distribution(tmp_path / "missing.json")
        assert result == Counter()

    def test_counts_tokens(self, tmp_path):
        graph = {
            "units": [
                {"tokens": ["COV.FETCH", "COV.PERSIST"], "class_context": []},
                {"tokens": ["COV.FETCH"], "class_context": ["COV.AUTHENTICATE"]},
            ]
        }
        p = tmp_path / "g.json"
        p.write_text(json.dumps(graph))
        result = _load_token_distribution(p)
        assert result["FETCH"] == 2
        assert result["PERSIST"] == 1
        assert result["AUTHENTICATE"] == 1

    def test_handles_corrupt_graph(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        result = _load_token_distribution(p)
        assert result == Counter()


# ── _heuristic_candidates ─────────────────────────────────────────────────────

class TestHeuristicCandidates:
    def test_empty_snippets_returns_empty(self):
        result = _heuristic_candidates([], Counter())
        assert result == []

    def test_single_match_below_threshold(self):
        # Only 1 snippet — evidence < 2, should not appear
        result = _heuristic_candidates(["lru_cache(fn)"], Counter())
        assert result == []

    def test_two_matches_produces_candidate(self):
        # Need ≥3 evidence to clear 0.60 threshold: 0.5 + 3*0.04 = 0.62
        snippets = ["lru_cache(get_user)", "memoize(fetch_data)", "lru_cache(get_item)"]
        result = _heuristic_candidates(snippets, Counter())
        names = [c.token_name for c in result]
        assert "MEMOIZE" in names

    def test_candidate_has_required_fields(self):
        snippets = ["lru_cache(a)", "lru_cache(b)", "memoize(c)"]
        result = _heuristic_candidates(snippets, Counter())
        c = next(r for r in result if r.token_name == "MEMOIZE")
        assert c.evidence_count >= 2
        assert c.confidence >= 0.60
        assert len(c.example_snippets) <= 5
        assert c.source == "heuristic"

    def test_retry_pattern_detected(self):
        snippets = ["retry(3, call_api)", "backoff(fn, delay=1)", "retry(2, fetch)"]
        result = _heuristic_candidates(snippets, Counter())
        names = [c.token_name for c in result]
        assert "RETRY" in names

    def test_batch_pattern_detected(self):
        snippets = ["batch_insert(rows)", "bulk_update(items)", "batch_delete(ids)"]
        result = _heuristic_candidates(snippets, Counter())
        names = [c.token_name for c in result]
        assert "BATCH" in names

    def test_paginate_pattern_detected(self):
        snippets = ["paginate(query, cursor)", "offset_query(10, 20)", "paginate(qs, 50)"]
        result = _heuristic_candidates(snippets, Counter())
        names = [c.token_name for c in result]
        assert "PAGINATE" in names

    def test_sep_signal_boosts_confidence(self):
        snippets = ["lru_cache(a)", "lru_cache(b)", "memoize(c)"]
        sep = Counter({"FETCH": 5})  # MEMOIZE → FETCH in sep_related map
        result_no_sep = _heuristic_candidates(snippets, Counter())
        result_with_sep = _heuristic_candidates(snippets, sep)
        c_no_sep = next(r for r in result_no_sep if r.token_name == "MEMOIZE")
        c_with_sep = next(r for r in result_with_sep if r.token_name == "MEMOIZE")
        assert c_with_sep.confidence >= c_no_sep.confidence
        assert "sep_odd_group" in c_with_sep.signal_sources

    def test_is_extension_zone_flag(self):
        snippets = ["lru_cache(a)", "memoize(b)", "lru_cache(c)"]
        result = _heuristic_candidates(snippets, Counter())
        c = next(r for r in result if r.token_name == "MEMOIZE")
        assert c.is_extension_zone is True

    def test_confidence_capped_at_0_92(self):
        snippets = [f"lru_cache(fn{i})" for i in range(50)]
        result = _heuristic_candidates(snippets, Counter({"FETCH": 10}))
        c = next(r for r in result if r.token_name == "MEMOIZE")
        assert c.confidence <= 0.92

    def test_sorted_multi_signal_first(self):
        snippets = (
            ["lru_cache(a)", "lru_cache(b)"] +
            ["retry(a)", "retry(b)", "retry(c)"]
        )
        sep = Counter({"FETCH": 3})
        result = _heuristic_candidates(snippets, sep)
        # MEMOIZE has SEP signal, RETRY doesn't → MEMOIZE should come first
        if len(result) >= 2:
            memoize_idx = next(i for i, c in enumerate(result) if c.token_name == "MEMOIZE")
            retry_idx = next(i for i, c in enumerate(result) if c.token_name == "RETRY")
            assert memoize_idx < retry_idx

    def test_example_snippets_deduped(self):
        snippets = ["lru_cache(fn)"] * 5
        result = _heuristic_candidates(snippets, Counter())
        if result:
            c = result[0]
            assert len(c.example_snippets) == len(set(c.example_snippets))


# ── VocabularyCurator ─────────────────────────────────────────────────────────

class TestVocabularyCurator:
    def _make_unresolved(self, tmp_path: Path, snippets: list[str]) -> Path:
        p = tmp_path / "unresolved.jsonl"
        p.write_text("\n".join(json.dumps({"snippet": s}) for s in snippets))
        return p

    def test_heuristic_path_no_key(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["lru_cache(a)", "lru_cache(b)", "memoize(c)"])
        curator = VocabularyCurator(enabled=False)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        assert any(c.token_name == "MEMOIZE" for c in candidates)

    def test_empty_log_returns_empty(self, tmp_path):
        curator = VocabularyCurator(enabled=False)
        candidates = curator.curate(
            tmp_path / "missing.jsonl", tmp_path / "missing.db", tmp_path / "missing.json"
        )
        assert candidates == []

    def test_ai_disabled_skips_ai_call(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["retry(f)", "retry(g)"])
        client = MagicMock()
        curator = VocabularyCurator(enabled=False, client=client)
        curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        client.chat.completions.create.assert_not_called()

    def test_ai_enabled_calls_api(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["retry(f)", "retry(g)"])
        ai_resp = json.dumps([{
            "token_name": "RETRY", "evidence_count": 2,
            "confidence": 0.75, "example_snippets": ["retry(f)"],
            "reasoning": "retry pattern", "is_new": False,
        }])
        client = _make_client(ai_resp)
        curator = VocabularyCurator(enabled=True, client=client)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        client.chat.completions.create.assert_called_once()
        assert any(c.token_name == "RETRY" for c in candidates)

    def test_ai_merges_into_heuristic_candidate(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["lru_cache(a)", "lru_cache(b)"])
        ai_resp = json.dumps([{
            "token_name": "MEMOIZE", "evidence_count": 5,
            "confidence": 0.90, "example_snippets": ["lru_cache(a)"],
            "reasoning": "memoize", "is_new": False,
        }])
        client = _make_client(ai_resp)
        curator = VocabularyCurator(enabled=True, client=client)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        memoize = next(c for c in candidates if c.token_name == "MEMOIZE")
        assert "ai_analysis" in memoize.signal_sources
        assert memoize.source == "ai"

    def test_ai_adds_new_candidate(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["retry(a)", "retry(b)"])
        ai_resp = json.dumps([{
            "token_name": "NEW_TOKEN", "evidence_count": 3,
            "confidence": 0.72, "example_snippets": ["new_fn()"],
            "reasoning": "novel pattern", "is_new": True,
        }])
        client = _make_client(ai_resp)
        curator = VocabularyCurator(enabled=True, client=client)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        names = [c.token_name for c in candidates]
        assert "NEW_TOKEN" in names

    def test_ai_below_confidence_threshold_skipped(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["retry(a)", "retry(b)"])
        ai_resp = json.dumps([{
            "token_name": "WEAK_TOKEN", "evidence_count": 1,
            "confidence": 0.40,  # below 0.60 threshold
            "example_snippets": [], "reasoning": "", "is_new": True,
        }])
        client = _make_client(ai_resp)
        curator = VocabularyCurator(enabled=True, client=client)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        names = [c.token_name for c in candidates]
        assert "WEAK_TOKEN" not in names

    def test_ai_exception_falls_back_to_heuristics(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["lru_cache(a)", "lru_cache(b)", "memoize(c)"])
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("API down")
        curator = VocabularyCurator(enabled=True, client=client)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        # Falls back to heuristic candidates
        assert any(c.token_name == "MEMOIZE" for c in candidates)
        memoize = next(c for c in candidates if c.token_name == "MEMOIZE")
        assert "AI unavailable" in memoize.reasoning

    def test_ai_malformed_json_falls_back(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["lru_cache(a)", "lru_cache(b)", "memoize(c)"])
        client = _make_client("not json at all")
        curator = VocabularyCurator(enabled=True, client=client)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        # heuristic path still works
        assert any(c.token_name == "MEMOIZE" for c in candidates)

    def test_model_param_forwarded(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["retry(a)", "retry(b)"])
        ai_resp = json.dumps([])
        client = _make_client(ai_resp)
        curator = VocabularyCurator(enabled=True, client=client, model="my-model")
        curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        call_kwargs = client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("model") == "my-model" or \
               call_kwargs[1].get("model") == "my-model" or \
               "my-model" in str(call_kwargs)

    def test_ai_code_fence_stripped(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["retry(a)", "retry(b)"])
        ai_resp = "```json\n[]\n```"
        client = _make_client(ai_resp)
        curator = VocabularyCurator(enabled=True, client=client)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        assert isinstance(candidates, list)

    def test_ai_no_array_in_response_falls_back(self, tmp_path):
        log = self._make_unresolved(tmp_path, ["lru_cache(a)", "lru_cache(b)", "memoize(c)"])
        client = _make_client("I found some patterns but no JSON.")
        curator = VocabularyCurator(enabled=True, client=client)
        candidates = curator.curate(log, tmp_path / "missing.db", tmp_path / "missing.json")
        # Heuristic results still present
        assert any(c.token_name == "MEMOIZE" for c in candidates)


# ── candidates_to_dict ─────────────────────────────────────────────────────────

class TestCandidatesToDict:
    def _make_candidate(self, name: str, confidence: float, sources: list[str],
                        in_ext: bool = True) -> ExtensionCandidate:
        return ExtensionCandidate(
            token_name=name, evidence_count=3, signal_sources=sources,
            confidence=confidence, example_snippets=["fn()"],
            reasoning="test", is_extension_zone=in_ext, source="heuristic",
        )

    def test_returns_dict_with_required_keys(self):
        result = candidates_to_dict([])
        assert "bgi_version" in result
        assert "extension_zone" in result
        assert "candidates" in result

    def test_extension_zone_listed(self):
        result = candidates_to_dict([])
        assert "MEMOIZE" in result["extension_zone"]
        assert "RETRY" in result["extension_zone"]

    def test_candidate_fields(self):
        c = self._make_candidate("MEMOIZE", 0.82, ["unresolved_calls"])
        result = candidates_to_dict([c])
        item = result["candidates"][0]
        for field in ("token_name", "evidence_count", "signal_sources", "confidence",
                      "example_snippets", "reasoning", "is_extension_zone", "source", "action"):
            assert field in item

    def test_action_promote_high_confidence_extension(self):
        c = self._make_candidate("MEMOIZE", 0.85, ["unresolved_calls", "sep_odd_group"], True)
        result = candidates_to_dict([c])
        assert result["candidates"][0]["action"] == "PROMOTE"

    def test_action_review_medium_confidence(self):
        c = self._make_candidate("MEMOIZE", 0.70, ["unresolved_calls"], True)
        result = candidates_to_dict([c])
        assert result["candidates"][0]["action"] == "REVIEW"

    def test_action_watch_low_confidence(self):
        c = self._make_candidate("MEMOIZE", 0.45, ["unresolved_calls"], True)
        result = candidates_to_dict([c])
        assert result["candidates"][0]["action"] == "WATCH"

    def test_action_review_not_in_extension_zone(self):
        c = self._make_candidate("NOVEL_TOKEN", 0.85, ["unresolved_calls"], False)
        result = candidates_to_dict([c])
        assert result["candidates"][0]["action"] == "REVIEW"

    def test_empty_candidates(self):
        result = candidates_to_dict([])
        assert result["candidates"] == []

    def test_json_serializable(self):
        c = self._make_candidate("RETRY", 0.75, ["unresolved_calls"])
        result = candidates_to_dict([c])
        # Should not raise
        encoded = json.dumps(result)
        assert "RETRY" in encoded


# ── Smoke test: real unresolved log ───────────────────────────────────────────

class TestSmokeRealLog:
    def test_heuristic_on_real_log(self):
        """Run heuristic pass against the actual bgi-unresolved.jsonl if present."""
        log = Path("/root/mad/bgi/bgi-unresolved.jsonl")
        if not log.exists():
            pytest.skip("bgi-unresolved.jsonl not present")
        snippets = _load_unresolved(log)
        assert len(snippets) > 0
        candidates = _heuristic_candidates(snippets, Counter())
        # Should produce at least some result (or none — just shouldn't crash)
        assert isinstance(candidates, list)
