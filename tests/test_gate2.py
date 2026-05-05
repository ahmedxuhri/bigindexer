"""
Tests for Gate 2 — Key-Lock matching.

Builds COVFingerprints directly and verifies edge creation,
scope constraints, and suspended edge production.
"""
import pytest
from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.core.edges import BGIEdge
from bgi.gate2.keylock import match_fingerprints, SuspendedEdge, _same_scope


# ── Factory helpers ──────────────────────────────────────────────────────────

def make_fp(
    unit_id: str,
    tokens: list[COV],
    class_context: list[COV] | None = None,
    confidence: float = 1.0,
) -> COVFingerprint:
    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=class_context or [],
        confidence=confidence,
        source="deterministic",
        language="python",
        line_range=(1, 10),
    )


def edges_between(fps: list[COVFingerprint]) -> list[BGIEdge]:
    edges, _ = match_fingerprints(fps)
    return edges


def suspended_from(fps: list[COVFingerprint]) -> list[SuspendedEdge]:
    _, suspended = match_fingerprints(fps)
    return suspended


# ── Basic edge creation ──────────────────────────────────────────────────────

class TestBasicEdges:
    def test_fetch_persist_edge_created(self):
        fp_a = make_fp("service.py::Repo::save", [COV.PERSIST])
        fp_b = make_fp("service.py::Repo::load", [COV.FETCH])
        edges = edges_between([fp_a, fp_b])
        assert len(edges) == 1
        e = edges[0]
        assert e.key_token == COV.FETCH
        assert e.lock_token == COV.PERSIST

    def test_raise_recover_edge_created(self):
        fp_a = make_fp("a.py::raise_fn", [COV.RAISE])
        fp_b = make_fp("a.py::handle_fn", [COV.RECOVER])
        edges = edges_between([fp_a, fp_b])
        assert any(e.key_token == COV.RAISE and e.lock_token == COV.RECOVER for e in edges)

    def test_emit_subscribe_edge_created(self):
        fp_a = make_fp("a.py::publisher", [COV.EMIT])
        fp_b = make_fp("b.py::subscriber", [COV.SUBSCRIBE])
        edges = edges_between([fp_a, fp_b])
        assert len(edges) == 1

    def test_init_teardown_edge(self):
        fp_a = make_fp("a.py::A::__init__", [COV.INIT])
        fp_b = make_fp("a.py::A::__del__", [COV.TEARDOWN])
        edges = edges_between([fp_a, fp_b])
        assert any(e.key_token == COV.INIT and e.lock_token == COV.TEARDOWN for e in edges)

    def test_no_self_edge(self):
        fp = make_fp("a.py::f", [COV.FETCH, COV.PERSIST])
        edges, _ = match_fingerprints([fp])
        assert all(e.source_id != e.target_id for e in edges)

    def test_no_duplicate_edges(self):
        fp_a = make_fp("a.py::A::f", [COV.FETCH])
        fp_b = make_fp("a.py::A::g", [COV.PERSIST])
        edges = edges_between([fp_a, fp_b])
        dedup_keys = {(e.source_id, e.target_id, e.key_token, e.lock_token) for e in edges}
        assert len(dedup_keys) == len(edges)


# ── Edge confidence and types ────────────────────────────────────────────────

class TestEdgeConfidence:
    def test_same_class_gives_hard_edge(self):
        # Both deterministic (conf=1.0) + same class → 1.0 + boosts → HARD
        fp_a = make_fp("a.py::A::saver", [COV.PERSIST], confidence=1.0)
        fp_b = make_fp("a.py::A::loader", [COV.FETCH], confidence=1.0)
        edges = edges_between([fp_a, fp_b])
        assert all(e.edge_type == "HARD" for e in edges)

    def test_low_confidence_gives_predicted_or_ghost(self):
        fp_a = make_fp("a.py::saver", [COV.PERSIST], confidence=0.6)
        fp_b = make_fp("b.py::loader", [COV.FETCH], confidence=0.6)
        edges = edges_between([fp_a, fp_b])
        assert all(e.edge_type in ("PREDICTED", "GHOST") for e in edges)

    def test_ghost_edge_below_threshold(self):
        fp_a = make_fp("a.py::saver", [COV.PERSIST], confidence=0.4)
        fp_b = make_fp("b.py::loader", [COV.FETCH], confidence=0.4)
        edges = edges_between([fp_a, fp_b])
        assert all(e.edge_type == "GHOST" for e in edges)


# ── Scope constraints: INTAKE↔OUTPUT ─────────────────────────────────────────

class TestScopeConstraints:
    def test_intake_output_same_class_creates_edge(self):
        fp_a = make_fp("a.py::A::producer", [COV.OUTPUT])
        fp_b = make_fp("a.py::A::consumer", [COV.INTAKE])
        edges = edges_between([fp_a, fp_b])
        assert any(COV.INTAKE in (e.key_token, e.lock_token) and
                   COV.OUTPUT in (e.key_token, e.lock_token) for e in edges)

    def test_intake_output_different_class_no_edge(self):
        fp_a = make_fp("a.py::A::producer", [COV.OUTPUT])
        fp_b = make_fp("a.py::B::consumer", [COV.INTAKE])
        io_edges = [e for e in edges_between([fp_a, fp_b])
                    if COV.INTAKE in (e.key_token, e.lock_token)]
        assert len(io_edges) == 0

    def test_intake_output_different_file_no_edge(self):
        fp_a = make_fp("a.py::producer", [COV.OUTPUT])
        fp_b = make_fp("b.py::consumer", [COV.INTAKE])
        io_edges = [e for e in edges_between([fp_a, fp_b])
                    if COV.OUTPUT in (e.key_token, e.lock_token)]
        assert len(io_edges) == 0

    def test_intake_output_same_file_module_level_creates_edge(self):
        fp_a = make_fp("a.py::producer", [COV.OUTPUT])
        fp_b = make_fp("a.py::consumer", [COV.INTAKE])
        io_edges = [e for e in edges_between([fp_a, fp_b])
                    if COV.OUTPUT in (e.key_token, e.lock_token)]
        assert len(io_edges) == 1

    def test_guard_intake_different_class_no_edge(self):
        fp_a = make_fp("a.py::A::asserter", [COV.GUARD])
        fp_b = make_fp("a.py::B::receiver", [COV.INTAKE])
        guard_edges = [e for e in edges_between([fp_a, fp_b])
                       if COV.GUARD in (e.key_token, e.lock_token)]
        assert len(guard_edges) == 0

    def test_guard_intake_same_class_creates_edge(self):
        fp_a = make_fp("a.py::A::asserter", [COV.GUARD])
        fp_b = make_fp("a.py::A::receiver", [COV.INTAKE])
        guard_edges = [e for e in edges_between([fp_a, fp_b])
                       if COV.GUARD in (e.key_token, e.lock_token)]
        assert len(guard_edges) == 1


# ── Suspended edges ──────────────────────────────────────────────────────────

class TestSuspendedEdges:
    def test_unmatched_fetch_creates_suspended(self):
        fp = make_fp("a.py::orphan_fetcher", [COV.FETCH])
        suspended = suspended_from([fp])
        assert any(s.token == COV.FETCH for s in suspended)

    def test_unmatched_emit_creates_suspended(self):
        fp = make_fp("a.py::orphan_emitter", [COV.EMIT])
        suspended = suspended_from([fp])
        assert any(s.token == COV.EMIT for s in suspended)

    def test_matched_fetch_no_suspended(self):
        fp_a = make_fp("a.py::A::saver", [COV.PERSIST])
        fp_b = make_fp("a.py::A::loader", [COV.FETCH])
        suspended = suspended_from([fp_a, fp_b])
        assert len(suspended) == 0

    def test_non_outward_tokens_not_suspended(self):
        # RAISE, RECOVER, INIT, TEARDOWN — not in _OUTWARD set
        fp = make_fp("a.py::f", [COV.RAISE])
        suspended = suspended_from([fp])
        assert len(suspended) == 0


# ── _same_scope helper ───────────────────────────────────────────────────────

class TestSameScope:
    def test_same_class(self):
        fp_a = make_fp("a.py::Foo::f", [])
        fp_b = make_fp("a.py::Foo::g", [])
        assert _same_scope(fp_a, fp_b)

    def test_different_class_same_file(self):
        fp_a = make_fp("a.py::Foo::f", [])
        fp_b = make_fp("a.py::Bar::g", [])
        assert not _same_scope(fp_a, fp_b)

    def test_module_level_same_file(self):
        fp_a = make_fp("a.py::f", [])
        fp_b = make_fp("a.py::g", [])
        assert _same_scope(fp_a, fp_b)

    def test_different_files(self):
        fp_a = make_fp("a.py::f", [])
        fp_b = make_fp("b.py::f", [])
        assert not _same_scope(fp_a, fp_b)
