"""
Tests for TOKEN-CENSUS (Step 2).
"""
import pytest
from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate2.census import compute_census, _apply_defaults, get_token_band, CensusResult


class TestSmallRepoGuard:
    """Test that small repos (<500 units) use hardcoded defaults."""
    
    def test_uses_defaults_for_100_units(self):
        """Repos with <500 units should use hardcoded defaults."""
        fps = [
            COVFingerprint(
                unit_id=f"test.py::func_{i}",
                tokens=[COV.INTAKE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            )
            for i in range(100)
        ]
        
        result = compute_census(fps, total_files=10)
        assert result.used_defaults is True
        assert result.total_units == 100
        assert result.total_files == 10
        assert result.token_bands[COV.AUTHENTICATE] == "Mask 1"
        assert result.token_bands[COV.INTAKE] == "Mask 3"
    
    def test_computes_for_500_plus_units(self):
        """Repos with ≥500 units should compute census."""
        fps = [
            COVFingerprint(
                unit_id=f"test_{i//50}.py::func_{i}",
                tokens=[COV.INTAKE] if i % 2 == 0 else [COV.OUTPUT],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            )
            for i in range(500)
        ]
        
        result = compute_census(fps, total_files=50)
        assert result.used_defaults is False
        assert result.total_units == 500


class TestTokenFrequencyClassification:
    """Test token classification by file frequency %."""
    
    def test_rare_token_below_1_percent(self):
        """Token in <1% of files → Mask 1 (rare)."""
        fps = [
            COVFingerprint(
                unit_id=f"file_{i}.py::func_{j}",
                tokens=[COV.INTAKE] if i == 0 else [COV.OUTPUT],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            )
            for i in range(100)
            for j in range(5)  # 500 units, 100 files
        ]
        
        result = compute_census(fps, total_files=100)
        
        # AUTHENTICATE should be rare (0 files = 0%)
        assert result.band_by_file_frequency[COV.AUTHENTICATE] == "Mask 1"
        
        # INTAKE in 1 file = 1%, AUTHENTICATE at boundary
        file_pct = result.token_file_pcts[COV.AUTHENTICATE]
        assert file_pct == 0.0
    
    def test_common_token_above_10_percent(self):
        """Token in >10% of files → Mask 3 (common)."""
        fps = [
            COVFingerprint(
                unit_id=f"file_{i}.py::func_{j}",
                tokens=[COV.OUTPUT],  # OUTPUT in all files
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            )
            for i in range(100)
            for j in range(5)  # 500 units, 100 files
        ]
        
        result = compute_census(fps, total_files=100)
        
        # OUTPUT in all 100 files = 100%
        file_pct = result.token_file_pcts[COV.OUTPUT]
        assert file_pct == 1.0
        assert result.band_by_file_frequency[COV.OUTPUT] == "Mask 3"


class TestPercentileRankClassification:
    """Test token classification by percentile rank among 28 tokens."""
    
    def test_bottom_third_is_mask1(self):
        """Bottom ~9 tokens by unit count → Mask 1."""
        fps = [
            COVFingerprint(
                unit_id=f"file_{i}.py::func_{j}",
                tokens=[COV.INTAKE, COV.OUTPUT],  # Both common
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            )
            for i in range(100)
            for j in range(5)  # 500 units
        ]
        
        result = compute_census(fps, total_files=100)
        
        # Tokens with 0 unit count should be in bottom third
        rare_tokens = [t for t in COV if result.token_unit_counts.get(t, 0) == 0]
        assert len(rare_tokens) > 0
        for token in rare_tokens[:3]:  # First few rare tokens
            if result.token_unit_counts.get(token, 0) == 0:
                assert result.band_by_percentile[token] == "Mask 1"


class TestDualClassificationMerge:
    """Test that final band = stricter of file_frequency and percentile."""
    
    def test_stricter_band_wins(self):
        """When file_frequency says Mask 2, percentile says Mask 1 → final = Mask 1."""
        fps = [
            COVFingerprint(
                unit_id=f"file_{i}.py::func_{j}",
                tokens=[COV.VALIDATE],  # Test a specific token
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            )
            for i in range(100)
            for j in range(5)  # 500 units, 100 files
        ]
        
        result = compute_census(fps, total_files=100)
        
        # Final band should be stricter (lower or equal rank)
        for token in COV:
            file_band_rank = {"Mask 1": 0, "Mask 2": 1, "Mask 3": 2}[result.band_by_file_frequency[token]]
            percentile_band_rank = {"Mask 1": 0, "Mask 2": 1, "Mask 3": 2}[result.band_by_percentile[token]]
            final_band_rank = {"Mask 1": 0, "Mask 2": 1, "Mask 3": 2}[result.token_bands[token]]
            
            assert final_band_rank == min(file_band_rank, percentile_band_rank)


class TestGetTokenBand:
    """Test convenience function get_token_band."""
    
    def test_returns_correct_band(self):
        """get_token_band should return the band from token_bands."""
        fps = [
            COVFingerprint(
                unit_id=f"file_{i}.py::func_{j}",
                tokens=[COV.INTAKE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            )
            for i in range(500)
            for j in range(1)
        ]
        
        result = compute_census(fps, total_files=100)
        assert get_token_band(result, COV.INTAKE) == result.token_bands[COV.INTAKE]
