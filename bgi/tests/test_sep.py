"""
Tests for the Suspended Edge Pool (SEP).

Uses in-memory SQLite to avoid file I/O.
"""
import time
import pytest
from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate2.keylock import SuspendedEdge
from bgi.sep.pool import SuspendedEdgePool


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_se(source_id: str, token: COV, raw_callee: str = "test.callee") -> SuspendedEdge:
    return SuspendedEdge(source_id=source_id, token=token, raw_callee=raw_callee)


def make_fp(
    unit_id: str,
    tokens: list[COV],
    class_context: list[COV] | None = None,
) -> COVFingerprint:
    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=class_context or [],
        confidence=1.0,
        source="deterministic",
        language="python",
        line_range=(1, 10),
    )


@pytest.fixture
def pool():
    """Fresh in-memory pool for each test."""
    p = SuspendedEdgePool(":memory:")
    yield p
    p.close()


# ── Ingestion ─────────────────────────────────────────────────────────────────

class TestIngest:
    def test_ingest_single_edge(self, pool):
        se = make_se("a.py::fetcher", COV.FETCH)
        count = pool.ingest([se], scan_run="scan-001")
        assert count == 1

    def test_ingest_multiple_edges(self, pool):
        edges = [
            make_se("a.py::f", COV.FETCH),
            make_se("a.py::g", COV.EMIT),
            make_se("b.py::h", COV.DELEGATE),
        ]
        count = pool.ingest(edges, scan_run="scan-001")
        assert count == 3

    def test_ingest_skips_duplicate(self, pool):
        se = make_se("a.py::f", COV.FETCH)
        pool.ingest([se], scan_run="scan-001")
        count = pool.ingest([se], scan_run="scan-002")
        assert count == 0

    def test_stats_after_ingest(self, pool):
        pool.ingest([make_se("a.py::f", COV.FETCH)], scan_run="scan-001")
        s = pool.stats()
        assert s["total"] == 1
        assert s["pending"] == 1
        assert s["resolved"] == 0
        assert s["intentional_boundary"] == 0


# ── Resurrection ─────────────────────────────────────────────────────────────

class TestResurrection:
    def test_resurrect_with_matching_fingerprint(self, pool):
        se = make_se("a.py::fetcher", COV.FETCH)
        pool.ingest([se], scan_run="scan-001")

        # Provide a fingerprint that has PERSIST (lock for FETCH)
        fp_with_persist = make_fp("b.py::saver", [COV.PERSIST])
        resurrected = pool.resurrect([fp_with_persist])

        assert len(resurrected) == 1
        e = resurrected[0]
        assert e.key_token == COV.FETCH
        assert e.lock_token == COV.PERSIST

    def test_resurrect_marks_edge_resolved(self, pool):
        se = make_se("a.py::fetcher", COV.FETCH)
        pool.ingest([se], scan_run="scan-001")
        pool.resurrect([make_fp("b.py::saver", [COV.PERSIST])])

        s = pool.stats()
        assert s["resolved"] == 1
        assert s["pending"] == 0

    def test_resurrect_with_no_matching_token(self, pool):
        se = make_se("a.py::fetcher", COV.FETCH)
        pool.ingest([se], scan_run="scan-001")

        # EMIT has no lock that matches FETCH
        fp_with_emit = make_fp("b.py::emitter", [COV.EMIT])
        resurrected = pool.resurrect([fp_with_emit])

        assert len(resurrected) == 0
        assert pool.stats()["pending"] == 1

    def test_resurrect_empty_pool(self, pool):
        fp = make_fp("b.py::saver", [COV.PERSIST])
        resurrected = pool.resurrect([fp])
        assert resurrected == []

    def test_resurrect_emit_with_subscribe(self, pool):
        se = make_se("a.py::publisher", COV.EMIT)
        pool.ingest([se], scan_run="scan-001")
        fp = make_fp("b.py::subscriber", [COV.SUBSCRIBE])
        resurrected = pool.resurrect([fp])
        assert len(resurrected) == 1
        assert resurrected[0].key_token == COV.EMIT
        assert resurrected[0].lock_token == COV.SUBSCRIBE


# ── Odd Groups ────────────────────────────────────────────────────────────────

class TestOddGroups:
    def test_odd_group_created_for_pending_edge(self, pool):
        pool.ingest([make_se("a.py::f", COV.FETCH)], scan_run="scan-001")
        groups = pool.odd_groups()
        assert len(groups) == 1
        assert groups[0].token == COV.FETCH
        assert "a.py::f" in groups[0].member_ids

    def test_odd_groups_empty_when_all_resolved(self, pool):
        se = make_se("a.py::fetcher", COV.FETCH)
        pool.ingest([se], scan_run="scan-001")
        pool.resurrect([make_fp("b.py::saver", [COV.PERSIST])])
        groups = pool.odd_groups()
        assert len(groups) == 0

    def test_odd_groups_sorted_by_count(self, pool):
        pool.ingest([
            make_se("a.py::f", COV.FETCH),
            make_se("a.py::g", COV.FETCH),
            make_se("b.py::h", COV.EMIT),
        ], scan_run="scan-001")
        groups = pool.odd_groups()
        assert groups[0].token == COV.FETCH
        assert groups[0].count == 2

    def test_odd_group_count_matches_members(self, pool):
        pool.ingest([
            make_se("a.py::f", COV.FETCH),
            make_se("b.py::g", COV.FETCH),
            make_se("c.py::h", COV.FETCH),
        ], scan_run="scan-001")
        groups = pool.odd_groups()
        assert groups[0].count == 3
        assert len(groups[0].member_ids) == 3


# ── Boundary detection ────────────────────────────────────────────────────────

class TestBoundaryDetection:
    def test_stale_edge_promoted_to_boundary(self, pool):
        se = make_se("a.py::orphan", COV.FETCH)
        pool.ingest([se], scan_run="scan-001")

        # Scan with max_age_s=0 to treat everything as stale
        promoted = pool.scan_boundaries(max_age_s=0)

        assert "a.py::orphan" in promoted
        assert pool.stats()["intentional_boundary"] == 1

    def test_fresh_edge_not_promoted(self, pool):
        se = make_se("a.py::fresh", COV.FETCH)
        pool.ingest([se], scan_run="scan-001")

        # Use very large max_age — nothing should be stale
        promoted = pool.scan_boundaries(max_age_s=999_999)
        assert len(promoted) == 0
        assert pool.stats()["intentional_boundary"] == 0

    def test_resolved_edge_not_promoted(self, pool):
        se = make_se("a.py::fetcher", COV.FETCH)
        pool.ingest([se], scan_run="scan-001")
        pool.resurrect([make_fp("b.py::saver", [COV.PERSIST])])

        promoted = pool.scan_boundaries(max_age_s=0)
        assert len(promoted) == 0
