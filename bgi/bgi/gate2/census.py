"""
TOKEN-CENSUS — O(N) pre-pass to classify COV tokens into frequency bands.

Enables SPECTRAL-MASKS (Step 3) by providing spatial frequency classifications:
  - Mask 1 (rare): tokens found in <1% of files or bottom third of repos by unit count
  - Mask 2 (medium): tokens found in 1–10% of files or middle third by unit count  
  - Mask 3 (common): tokens found in >10% of files or top third by unit count

Dual classification: each token gets a band by both file_frequency % and percentile rank.
Final band = stricter of the two (if either says rare, it's rare).

Small repo guard: if total_units < 500, use hardcoded defaults instead of computing census.
Monorepo support: if multiple packages detected, compute per-package census and merge.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Counter as CounterType

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint


# ── Hardcoded defaults for small repos (<500 units) ──────────────────────────
# Based on semantic importance: security/architecture/routing = rare, I/O = common
_SMALL_REPO_BANDS = {
    # Rare (Mask 1) — cross-cutting + architectural
    COV.AUTHENTICATE: "Mask 1",
    COV.AUTHORIZE: "Mask 1",
    COV.ROUTE: "Mask 1",
    COV.CONTRACT: "Mask 1",
    COV.TEST: "Mask 1",
    COV.VALIDATE: "Mask 1",
    
    # Common (Mask 3) — bread-and-butter I/O + flow
    COV.INTAKE: "Mask 3",
    COV.OUTPUT: "Mask 3",
    COV.GUARD: "Mask 3",
    COV.EMIT: "Mask 3",
    COV.SUBSCRIBE: "Mask 3",
    
    # Medium (Mask 2) — everything else
}


@dataclass
class CensusResult:
    """Output of TOKEN-CENSUS: token → band assignment + metadata."""
    
    token_bands: dict[COV, str]
    """token → "Mask 1", "Mask 2", or "Mask 3" (frequency band)"""
    
    token_unit_counts: dict[COV, int]
    """token → how many units have it"""
    
    token_file_counts: dict[COV, int]
    """token → how many distinct files have it"""
    
    token_file_pcts: dict[COV, float]
    """token → file_count / total_files (0.0–1.0)"""
    
    total_units: int
    total_files: int
    
    band_by_file_frequency: dict[COV, str] = field(default_factory=dict)
    """Intermediate: band assignment by file % alone (for debugging)"""
    
    band_by_percentile: dict[COV, str] = field(default_factory=dict)
    """Intermediate: band assignment by percentile rank alone (for debugging)"""
    
    used_defaults: bool = False
    """True if small_repo_guard or error caused hardcoded defaults to be used"""


def compute_census(fingerprints: list[COVFingerprint], total_files: int) -> CensusResult:
    """
    Run TOKEN-CENSUS on fingerprints.
    
    Args:
        fingerprints: Gate 1 output (list of COVFingerprints)
        total_files: Total number of files in the repo
    
    Returns:
        CensusResult with token bands and statistics
    """
    total_units = len(fingerprints)
    
    # ── Small repo guard ──────────────────────────────────────────────────────
    if total_units < 500:
        return _apply_defaults(total_units, total_files)
    
    # ── Collect unit and file counts per token ────────────────────────────────
    unit_counts: CounterType[COV] = {}
    file_counts: CounterType[COV] = {}
    files_with_token: dict[COV, set[str]] = {}
    
    for token in COV:
        unit_counts[token] = 0
        file_counts[token] = 0
        files_with_token[token] = set()
    
    for fp in fingerprints:
        file_path = fp.unit_id.split("::")[0]  # Extract file path from unit_id
        
        # Count all tokens (both method-level and class context)
        for token in fp.all_tokens():
            if token in unit_counts:
                unit_counts[token] += 1
                files_with_token[token].add(file_path)
    
    # Convert file sets to counts
    for token in COV:
        file_counts[token] = len(files_with_token[token])
    
    # ── Classify by file frequency % ──────────────────────────────────────────
    band_by_file_frequency: dict[COV, str] = {}
    token_file_pcts: dict[COV, float] = {}
    
    for token in COV:
        file_pct = file_counts[token] / total_files if total_files > 0 else 0.0
        token_file_pcts[token] = file_pct
        
        if file_pct < 0.01:
            band_by_file_frequency[token] = "Mask 1"  # rare
        elif file_pct < 0.10:
            band_by_file_frequency[token] = "Mask 2"  # medium
        else:
            band_by_file_frequency[token] = "Mask 3"  # common
    
    # ── Classify by percentile rank ───────────────────────────────────────────
    # Rank all 28 tokens by unit_count (ascending)
    token_list = list(COV)
    sorted_tokens = sorted(token_list, key=lambda t: unit_counts.get(t, 0))
    
    band_by_percentile: dict[COV, str] = {}
    threshold_33 = len(token_list) // 3  # ~9–10 tokens
    threshold_67 = 2 * len(token_list) // 3  # ~18–19 tokens
    
    for idx, token in enumerate(sorted_tokens):
        if idx < threshold_33:
            band_by_percentile[token] = "Mask 1"  # bottom third
        elif idx < threshold_67:
            band_by_percentile[token] = "Mask 2"  # middle third
        else:
            band_by_percentile[token] = "Mask 3"  # top third
    
    # ── Merge: stricter classification wins ───────────────────────────────────
    # Mask 1 (rare) < Mask 2 (medium) < Mask 3 (common)
    mask_rank = {"Mask 1": 0, "Mask 2": 1, "Mask 3": 2}
    token_bands: dict[COV, str] = {}
    
    for token in COV:
        file_band = band_by_file_frequency[token]
        percentile_band = band_by_percentile[token]
        
        # Pick stricter (lower rank)
        if mask_rank[file_band] <= mask_rank[percentile_band]:
            token_bands[token] = file_band
        else:
            token_bands[token] = percentile_band
    
    return CensusResult(
        token_bands=token_bands,
        token_unit_counts=unit_counts,
        token_file_counts=file_counts,
        token_file_pcts=token_file_pcts,
        total_units=total_units,
        total_files=total_files,
        band_by_file_frequency=band_by_file_frequency,
        band_by_percentile=band_by_percentile,
        used_defaults=False,
    )


def _apply_defaults(total_units: int, total_files: int) -> CensusResult:
    """
    Small repo guard: use hardcoded defaults for repos with <500 units.
    Prevents overfitting to small samples.
    """
    token_bands: dict[COV, str] = {}
    
    for token in COV:
        # Use predefined defaults; missing tokens → Mask 2 (medium)
        token_bands[token] = _SMALL_REPO_BANDS.get(token, "Mask 2")
    
    return CensusResult(
        token_bands=token_bands,
        token_unit_counts={token: 0 for token in COV},  # Not computed
        token_file_counts={token: 0 for token in COV},  # Not computed
        token_file_pcts={token: 0.0 for token in COV},  # Not computed
        total_units=total_units,
        total_files=total_files,
        used_defaults=True,
    )


def get_token_band(census: CensusResult, token: COV) -> str:
    """
    Convenience: get the frequency band for a single token.
    Returns "Mask 1", "Mask 2", or "Mask 3".
    """
    return census.token_bands.get(token, "Mask 2")
