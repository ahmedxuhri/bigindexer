#!/usr/bin/env python3
"""
Micro-benchmark for Gate 2 Mask 3 matching.

Focuses on:
- Mask 3 workset preparation size
- Mask 3 index build time
- Mask 3 pass runtime, edge count, partner checks
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from bgi.gate1.ai_fallback import AIFallback
from bgi.gate1.scanner import scan_repository
from bgi.gate2.census import compute_census
from bgi.gate2.keylock import _build_mask_index, _prepare_mask_worksets, _run_mask_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Gate2 Mask 3 pass")
    parser.add_argument("--repo", required=True, help="Repository root to scan")
    parser.add_argument(
        "--output",
        default="output/validation/mask3-microbench.json",
        help="Output JSON file for benchmark report",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    ai = AIFallback(enabled=False)

    t0 = time.perf_counter()
    fingerprints = scan_repository(repo, ai=ai)
    gate1_sec = time.perf_counter() - t0

    total_files = len({fp.unit_id.split("::")[0] for fp in fingerprints})
    census = compute_census(fingerprints, total_files)

    prep_start = time.perf_counter()
    worksets = _prepare_mask_worksets(fingerprints, census)
    prep_ms = (time.perf_counter() - prep_start) * 1000.0

    build_start = time.perf_counter()
    mask3 = _build_mask_index(worksets["Mask 3"], "Mask 3", scope="file")
    build_ms = (time.perf_counter() - build_start) * 1000.0

    pass_result = _run_mask_pass(worksets["Mask 3"], mask3)

    report = {
        "repo": str(repo),
        "units": len(fingerprints),
        "files": total_files,
        "gate1_time_sec": round(gate1_sec, 3),
        "prepare_worksets_ms": round(prep_ms, 3),
        "build_mask3_index_ms": round(build_ms, 3),
        "mask3_work_items": len(worksets["Mask 3"]),
        "mask3_token_regions": len(mask3.token_index),
        "mask3_elapsed_ms": pass_result.elapsed_ms,
        "mask3_edges": len(pass_result.edges),
        "mask3_suspended": len(pass_result.suspended),
        "mask3_partner_checks": pass_result.partner_checks,
    }

    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
