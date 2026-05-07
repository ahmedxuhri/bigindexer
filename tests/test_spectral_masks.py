"""
Tests for SPECTRAL-MASKS (Step 3).
"""
import pytest
from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint
from bgi.gate2.census import compute_census
from bgi.gate2.keylock import (
    get_last_match_profile,
    match_fingerprints,
    _get_directory_path,
    _get_file_path,
)


class TestDirectoryPathExtraction:
    """Test directory path extraction for Mask 2 scoping."""
    
    def test_extracts_first_3_levels(self):
        """_get_directory_path should return first 3 path levels from repo root."""
        unit_id = "src/main/java/com/example/MyClass::method_name"
        assert _get_directory_path(unit_id) == "src/main/java"
    
    def test_handles_shallow_paths(self):
        """Shallow paths should take up to 3 parts."""
        unit_id = "src/file.py::func"
        assert _get_directory_path(unit_id) == "src/file.py"
    
    def test_handles_single_file(self):
        """Single file path should work."""
        unit_id = "main.py::func"
        assert _get_directory_path(unit_id) == "main.py"


class TestFilePathExtraction:
    """Test file path extraction for Mask 3 scoping."""
    
    def test_extracts_file_path(self):
        """_get_file_path should extract file path before ::."""
        unit_id = "src/main/MyClass.py::method_name"
        assert _get_file_path(unit_id) == "src/main/MyClass.py"


class TestSpectralMasksWithCensus:
    """Test SPECTRAL-MASKS behavior when census is provided."""
    
    def test_uses_spectral_when_census_provided(self):
        """When census is provided, should use spectral masks instead of flat matching."""
        fps = [
            # Mask 1 token (rare)
            COVFingerprint(
                unit_id="file_a.py::authenticate",
                tokens=[COV.AUTHENTICATE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            ),
            # Mask 1 token complement (should match globally)
            COVFingerprint(
                unit_id="file_b.py::route",
                tokens=[COV.ROUTE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            ),
        ]
        
        census = compute_census(fps, total_files=2)
        edges, suspended = match_fingerprints(fps, census=census)
        
        # AUTHENTICATE (Mask 1 rare) and ROUTE (Mask 1 rare) should form Mask 1 global edge
        assert len(edges) > 0  # Should have at least 1 edge
        # Spectral provenance should mention spectral-Mask
        assert any("spectral-Mask" in e.provenance for e in edges)
    
    def test_mask3_file_scope_contains_matches(self):
        """Mask 3 (common) tokens should only match within same file."""
        fps = [
            # Two units in file_a with INTAKE+OUTPUT
            COVFingerprint(
                unit_id="file_a.py::func1",
                tokens=[COV.INTAKE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            ),
            COVFingerprint(
                unit_id="file_a.py::func2",
                tokens=[COV.OUTPUT],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(11, 20),
            ),
            # Unit in file_b with INTAKE (should NOT match file_a's OUTPUT)
            COVFingerprint(
                unit_id="file_b.py::func3",
                tokens=[COV.INTAKE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            ),
        ]
        
        census = compute_census(fps, total_files=2)
        edges, suspended = match_fingerprints(fps, census=census)
        
        # Should have edge within file_a (INTAKE↔OUTPUT)
        file_a_edges = [e for e in edges if "file_a.py" in e.source_id and "file_a.py" in e.target_id]
        assert len(file_a_edges) > 0
        
        # Should NOT have edge between file_a and file_b for INTAKE↔OUTPUT pair
        cross_file_edges = [e for e in edges 
                           if ("file_a.py" in e.source_id and "file_b.py" in e.target_id)
                           or ("file_b.py" in e.source_id and "file_a.py" in e.target_id)]
        # If cross-file exists, it should not be INTAKE/OUTPUT pair
        for edge in cross_file_edges:
            token_pair = (str(edge.key_token), str(edge.lock_token))
            assert token_pair not in [("INTAKE", "OUTPUT"), ("OUTPUT", "INTAKE")]

    def test_records_per_mask_profile_stats(self):
        """Spectral path should expose per-mask profiling details."""
        fps = [
            COVFingerprint(
                unit_id="file_a.py::authenticate",
                tokens=[COV.AUTHENTICATE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            ),
            COVFingerprint(
                unit_id="file_b.py::route",
                tokens=[COV.ROUTE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            ),
        ]
        census = compute_census(fps, total_files=2)
        edges, _ = match_fingerprints(fps, census=census)

        profile = get_last_match_profile()
        assert profile["mode"] == "spectral"
        assert set(profile["mask_match_ms"].keys()) == {"Mask 1", "Mask 2", "Mask 3"}
        assert set(profile["mask_work_items"].keys()) == {"Mask 1", "Mask 2", "Mask 3"}
        assert profile["total_edges"] == len(edges)


class TestSpectralWithoutCensus:
    """Test backward compatibility when census is not provided."""
    
    def test_falls_back_to_flat_when_no_census(self):
        """When census is None, should use flat global matching."""
        fps = [
            COVFingerprint(
                unit_id="file_a.py::func1",
                tokens=[COV.AUTHENTICATE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            ),
            COVFingerprint(
                unit_id="file_b.py::func2",
                tokens=[COV.ROUTE],
                class_context=[],
                confidence=1.0,
                source="deterministic",
                language="python",
                line_range=(1, 10),
            ),
        ]
        
        # No census provided
        edges, suspended = match_fingerprints(fps, census=None)
        
        # Should still get edges from flat matching
        assert len(edges) > 0
        # Provenance should NOT mention spectral
        assert not any("spectral" in e.provenance for e in edges)
        assert get_last_match_profile()["mode"] == "flat"
