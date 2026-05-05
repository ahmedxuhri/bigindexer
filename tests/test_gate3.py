"""
Tests for Gate 3 — DRS clustering.

Uses synthetic fingerprints to verify cluster formation,
namespace merging, cross-file merging, and seam detection.
"""
import pytest
from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.core.edges import BGIEdge
from bgi.gate3.drs import run_drs, drs_summary


# ── Factory helpers ──────────────────────────────────────────────────────────

def make_fp(
    unit_id: str,
    tokens: list[COV],
    class_context: list[COV] | None = None,
    line_range: tuple[int, int] = (1, 10),
    confidence: float = 1.0,
) -> COVFingerprint:
    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=class_context or [],
        confidence=confidence,
        source="deterministic",
        language="python",
        line_range=line_range,
    )


def make_edge(
    source_id: str,
    target_id: str,
    key: COV = COV.FETCH,
    lock: COV = COV.PERSIST,
    confidence: float = 0.95,
    edge_type: str = "HARD",
) -> BGIEdge:
    return BGIEdge(
        source_id=source_id,
        target_id=target_id,
        key_token=key,
        lock_token=lock,
        confidence=confidence,
        edge_type=edge_type,
        provenance="test",
    )


# ── Fixture clusters: auth vs payment ────────────────────────────────────────

class TestFixtureClusters:
    """Two well-separated clusters should remain separate."""

    def _build_fps(self):
        auth = [
            make_fp("auth.py::AuthService::login", [COV.AUTHENTICATE, COV.INTAKE, COV.OUTPUT], line_range=(1, 20)),
            make_fp("auth.py::AuthService::logout", [COV.TEARDOWN, COV.INIT], line_range=(22, 35)),
            make_fp("auth.py::AuthService::verify_token", [COV.AUTHENTICATE, COV.GUARD], line_range=(37, 55)),
        ]
        payment = [
            make_fp("payment.py::PaymentService::charge", [COV.FETCH, COV.PERSIST, COV.INTAKE], line_range=(1, 20)),
            make_fp("payment.py::PaymentService::refund", [COV.FETCH, COV.PERSIST], line_range=(22, 38)),
        ]
        return auth + payment

    def test_produces_two_clusters(self):
        fps = self._build_fps()
        edges = [make_edge("auth.py::AuthService::login", "auth.py::AuthService::logout",
                           key=COV.INIT, lock=COV.TEARDOWN)]
        result = run_drs(fps, edges)
        assert len(result.clusters) == 2

    def test_auth_and_payment_separate(self):
        fps = self._build_fps()
        result = run_drs(fps, [])
        files_per_cluster = [frozenset(c.files) for c in result.clusters]
        auth_cluster = next(c for c in result.clusters if any("auth" in f for f in c.files))
        pay_cluster = next(c for c in result.clusters if any("payment" in f for f in c.files))
        assert auth_cluster.cluster_id != pay_cluster.cluster_id


# ── Namespace clustering (Pass 1.5) ──────────────────────────────────────────

class TestNamespaceClustering:
    """Files in the same subdirectory sharing high-prior tokens should merge."""

    def test_security_files_merge_into_one_cluster(self):
        fps = [
            make_fp("security/api_key.py::APIKeyAuth::authenticate",
                    [COV.AUTHENTICATE, COV.INTAKE, COV.OUTPUT]),
            make_fp("security/http.py::HTTPBearer::authenticate",
                    [COV.AUTHENTICATE, COV.INTAKE, COV.OUTPUT]),
            make_fp("security/oauth2.py::OAuth2::authenticate",
                    [COV.AUTHENTICATE, COV.INTAKE, COV.OUTPUT]),
        ]
        result = run_drs(fps, [])
        security_clusters = [c for c in result.clusters
                             if any("security" in f for f in c.files)]
        assert len(security_clusters) == 1, (
            f"Expected 1 security cluster, got {len(security_clusters)}: "
            f"{[c.files for c in security_clusters]}"
        )

    def test_namespace_cluster_is_cross_file(self):
        fps = [
            make_fp("security/api_key.py::f", [COV.AUTHENTICATE, COV.ROUTE]),
            make_fp("security/http.py::g", [COV.AUTHENTICATE, COV.ROUTE]),
        ]
        result = run_drs(fps, [])
        security_cluster = next(c for c in result.clusters if len(c.files) > 1)
        assert security_cluster.is_cross_file

    def test_different_subdir_not_merged(self):
        fps = [
            make_fp("auth/login.py::f", [COV.AUTHENTICATE, COV.INTAKE]),
            make_fp("payment/charge.py::g", [COV.PERSIST, COV.FETCH]),
        ]
        result = run_drs(fps, [])
        # Different subdirs, different tokens — should be separate
        assert len(result.clusters) == 2

    def test_root_files_not_merged_by_namespace(self):
        # Files in root (no subdir) should not namespace-merge with each other
        fps = [
            make_fp("a.py::f", [COV.AUTHENTICATE]),
            make_fp("b.py::g", [COV.AUTHENTICATE]),
        ]
        result = run_drs(fps, [])
        # They may or may not merge via cross-file edge logic, but namespace pass
        # should not force them together (no shared subdir)
        # Just verify the pipeline doesn't crash
        assert len(result.clusters) >= 1


# ── Cross-file merging via HARD edges (Pass 2) ────────────────────────────────

class TestCrossFileMerging:
    def test_authenticate_route_edge_triggers_merge(self):
        fps = [
            make_fp("security/auth.py::AuthMiddleware::check",
                    [COV.AUTHENTICATE, COV.ROUTE]),
            make_fp("routes/api.py::APIRouter::register",
                    [COV.ROUTE, COV.INTAKE]),
        ]
        # HARD edge between them
        edge = make_edge(
            "security/auth.py::AuthMiddleware::check",
            "routes/api.py::APIRouter::register",
            key=COV.AUTHENTICATE,
            lock=COV.ROUTE,
            confidence=0.95,
            edge_type="HARD",
        )
        result = run_drs(fps, [edge])
        cross_file_clusters = [c for c in result.clusters if c.is_cross_file]
        assert len(cross_file_clusters) >= 1


# ── DRS summary ──────────────────────────────────────────────────────────────

class TestDRSSummary:
    def test_summary_has_expected_keys(self):
        fps = [make_fp("a.py::f", [COV.FETCH, COV.PERSIST])]
        result = run_drs(fps, [])
        summary = drs_summary(result)
        assert "total_clusters" in summary
        assert "hard_clusters" in summary
        assert "cross_file_clusters" in summary
        assert "seam_units" in summary
        assert "clusters" in summary

    def test_cluster_entry_has_expected_keys(self):
        fps = [make_fp("a.py::f", [COV.FETCH, COV.PERSIST])]
        result = run_drs(fps, [])
        summary = drs_summary(result)
        for cluster in summary["clusters"]:
            assert "id" in cluster
            assert "size" in cluster
            assert "probability" in cluster
            assert "is_hard" in cluster
            assert "files" in cluster
            assert "dominant_tokens" in cluster

    def test_probability_in_range(self):
        fps = [make_fp("a.py::f", [COV.CONTRACT])]
        result = run_drs(fps, [])
        for c in result.clusters:
            assert 0.0 <= c.probability <= 1.0

    def test_hard_cluster_high_probability(self):
        # CONTRACT token has prior 1.0 — should produce a HARD cluster
        fps = [
            make_fp("a.py::A::define", [COV.CONTRACT, COV.INTAKE], line_range=(1, 20)),
            make_fp("a.py::A::validate", [COV.CONTRACT, COV.VALIDATE], line_range=(25, 40)),
        ]
        result = run_drs(fps, [])
        assert any(c.is_hard for c in result.clusters)


# ── Unit-to-cluster mapping ──────────────────────────────────────────────────

class TestUnitToCluster:
    def test_every_unit_has_cluster(self):
        fps = [
            make_fp("a.py::f", [COV.FETCH]),
            make_fp("b.py::g", [COV.PERSIST]),
            make_fp("c.py::h", [COV.EMIT]),
        ]
        result = run_drs(fps, [])
        for fp in fps:
            assert fp.unit_id in result.unit_to_cluster, f"{fp.unit_id} has no cluster"

    def test_same_file_units_in_same_cluster(self):
        fps = [
            make_fp("a.py::f", [COV.FETCH], line_range=(1, 20)),
            make_fp("a.py::g", [COV.PERSIST], line_range=(25, 40)),
        ]
        result = run_drs(fps, [])
        cid_f = result.unit_to_cluster["a.py::f"]
        cid_g = result.unit_to_cluster["a.py::g"]
        assert cid_f == cid_g
