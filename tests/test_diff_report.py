"""Tests for `bgi diff --report` markdown drift narration.

Coverage:
  - _drift_verdict: Stable / Drifting / Restructured thresholds
  - _aggregate_token_drift: gained vs lost across all change kinds
  - _file_churn: per-file change counts
  - format_diff_markdown: section presence, caps, escapes, edge cases
"""
from __future__ import annotations

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.delta.diff import (
    ScanDiff,
    _aggregate_token_drift,
    _drift_verdict,
    _file_churn,
    diff_scans,
    format_diff_markdown,
)


def _fp(unit_id: str, tokens: list[COV], language: str = "python") -> COVFingerprint:
    return COVFingerprint(
        unit_id=unit_id,
        tokens=tokens,
        class_context=[],
        confidence=1.0,
        source="deterministic",
        language=language,
        line_range=(1, 5),
    )


# ── _drift_verdict ────────────────────────────────────────────────────────────

class TestDriftVerdict:
    def test_clean_diff_is_stable(self):
        diff = ScanDiff()
        diff.lang_counts = {"python": (10, 10)}
        verdict, _ = _drift_verdict(diff)
        assert verdict == "Stable"

    def test_few_changes_is_stable(self):
        before = [_fp(f"f.py::g{i}", [COV.OUTPUT]) for i in range(5)]
        after = [_fp(f"f.py::g{i}", [COV.OUTPUT]) for i in range(5)]
        after[0] = _fp("f.py::g0", [COV.OUTPUT, COV.FETCH])
        diff = diff_scans(before, after)
        verdict, _ = _drift_verdict(diff)
        assert verdict == "Stable"

    def test_moderate_changes_is_drifting(self):
        before = [_fp(f"f.py::g{i}", [COV.OUTPUT]) for i in range(50)]
        after = [_fp(f"f.py::g{i}", [COV.OUTPUT, COV.FETCH]) for i in range(50)]
        diff = diff_scans(before, after)
        verdict, _ = _drift_verdict(diff)
        assert verdict == "Drifting"

    def test_large_changes_is_restructured(self):
        before = [_fp(f"f.py::g{i}", [COV.OUTPUT]) for i in range(300)]
        after = [_fp(f"f.py::h{i}", [COV.PERSIST]) for i in range(300)]
        diff = diff_scans(before, after)
        verdict, _ = _drift_verdict(diff)
        assert verdict == "Restructured"


# ── _aggregate_token_drift ────────────────────────────────────────────────────

class TestAggregateTokenDrift:
    def test_added_unit_contributes_gained(self):
        before = []
        after = [_fp("f.py::g", [COV.FETCH, COV.PERSIST])]
        diff = diff_scans(before, after)
        drift = _aggregate_token_drift(diff)
        assert drift["FETCH"] == (1, 0)
        assert drift["PERSIST"] == (1, 0)

    def test_removed_unit_contributes_lost(self):
        before = [_fp("f.py::g", [COV.AUTHENTICATE])]
        after = []
        diff = diff_scans(before, after)
        drift = _aggregate_token_drift(diff)
        assert drift["AUTHENTICATE"] == (0, 1)

    def test_changed_unit_contributes_both_sides(self):
        before = [_fp("f.py::g", [COV.OUTPUT])]
        after = [_fp("f.py::g", [COV.OUTPUT, COV.FETCH])]
        diff = diff_scans(before, after)
        drift = _aggregate_token_drift(diff)
        assert drift["FETCH"] == (1, 0)
        # OUTPUT was unchanged, no entry
        assert "OUTPUT" not in drift


# ── _file_churn ───────────────────────────────────────────────────────────────

class TestFileChurn:
    def test_groups_by_file(self):
        before = [_fp("a.py::g1", [COV.OUTPUT]), _fp("b.py::g2", [COV.OUTPUT])]
        after = [_fp("a.py::g1", [COV.OUTPUT, COV.FETCH])]  # b.py::g2 removed, a.py::g1 changed
        diff = diff_scans(before, after)
        churn = _file_churn(diff)
        assert churn["a.py"] == 1
        assert churn["b.py"] == 1


# ── format_diff_markdown ──────────────────────────────────────────────────────

class TestFormatDiffMarkdown:
    def test_clean_diff_states_stability(self):
        before = [_fp("f.py::g", [COV.OUTPUT])]
        after = [_fp("f.py::g", [COV.OUTPUT])]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff, "main", "feature")
        assert "# BGI Architecture Drift" in md
        assert "main" in md and "feature" in md
        assert "Stable" in md

    def test_route_changes_section_appears(self):
        before = [_fp("a.py::handler", [COV.OUTPUT])]
        after = [_fp("a.py::handler", [COV.OUTPUT, COV.ROUTE])]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        # The route diff is built from token presence, but in this case
        # the unit existed before; it's a re-tokenized unit. Check that
        # ROUTE token appears in token drift instead.
        assert "ROUTE" in md or "Token drift" in md

    def test_added_route_appears_in_routes_section(self):
        before = []
        after = [_fp("a.py::new_handler", [COV.ROUTE, COV.OUTPUT])]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        assert "Architectural surface changes" in md
        assert "new_handler" in md

    def test_added_units_cap_at_15_routes(self):
        before = []
        after = [_fp(f"a.py::r{i}", [COV.ROUTE]) for i in range(20)]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        assert "and 5 more" in md

    def test_token_drift_section_only_with_signal(self):
        # one added unit with one token = 1 emission, below threshold
        before = []
        after = [_fp("a.py::g", [COV.LOG])]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        # token drift section requires (gained + lost) >= 2 to show
        assert "Token drift" not in md

    def test_token_drift_appears_with_repeated_signal(self):
        before = []
        after = [_fp(f"a.py::g{i}", [COV.AUTHENTICATE]) for i in range(3)]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        assert "Token drift" in md
        assert "AUTHENTICATE" in md

    def test_language_shift_section_appears(self):
        before = [_fp(f"a.py::g{i}", [COV.OUTPUT], language="python") for i in range(3)]
        after = before + [_fp("a.go::g", [COV.OUTPUT], language="go")]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        assert "Language composition" in md
        assert "go" in md

    def test_language_shift_hidden_when_unchanged(self):
        before = [_fp(f"a.py::g{i}", [COV.OUTPUT]) for i in range(3)]
        after = [_fp(f"a.py::g{i}", [COV.OUTPUT, COV.FETCH]) for i in range(3)]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        assert "Language composition" not in md

    def test_summary_table_present(self):
        before = []
        after = [_fp("a.py::g", [COV.OUTPUT])]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        assert "## Summary" in md
        assert "Added units" in md

    def test_inline_retokenized_list_for_small_diffs(self):
        before = [_fp("a.py::g", [COV.OUTPUT])]
        after = [_fp("a.py::g", [COV.OUTPUT, COV.FETCH])]
        diff = diff_scans(before, after)
        md = format_diff_markdown(diff)
        assert "Re-tokenized units" in md
        assert "+FETCH" in md
