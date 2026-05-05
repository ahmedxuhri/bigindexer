"""
BGI Pipeline — orchestrates Gate 1 → Gate 2 → Gate 3 → SEP → Output.
This is the top-level wiring. Each gate is independently importable/testable.
"""
from __future__ import annotations
import json
from pathlib import Path


def run_scan(root: str, language: str = "python", output: str = "bgi-graph.json", db: str = "bgi-sep.db") -> None:
    from bgi.gate1.scanner import scan_directory
    from bgi.gate2.keylock import match_fingerprints
    from bgi.gate3.drs import run_drs
    from bgi.sep.pool import SuspendedEdgePool
    from bgi.output.graph import serialize_graph
    import time

    root_path = Path(root).resolve()
    scan_run = f"scan-{int(time.time())}"
    print(f"[BGI] Scanning {root_path} ...")

    fingerprints = scan_directory(root_path, language=language, scan_run=scan_run)
    print(f"[BGI] Gate 1 complete — {len(fingerprints)} units fingerprinted")

    edges, suspended = match_fingerprints(fingerprints)
    print(f"[BGI] Gate 2 complete — {len(edges)} edges detected ({len(suspended)} suspended)")

    drs = run_drs(fingerprints, edges)
    hard = sum(1 for c in drs.clusters if c.is_hard)
    print(f"[BGI] Gate 3 complete — {len(drs.clusters)} clusters ({hard} hard, {len(drs.seam_units)} seams)")

    # SEP — ingest suspended edges, attempt resurrection from current scan
    pool = SuspendedEdgePool(db)
    new_count = pool.ingest(suspended, scan_run=scan_run)
    resurrected = pool.resurrect(fingerprints)
    boundaries = pool.scan_boundaries()
    sep_stats = pool.stats()

    # AI Position 2 — Resurrection Forecaster (heuristics always; AI when key provided)
    from bgi.ai.forecaster import ResurrectionForecaster, forecasts_to_dict
    forecaster = ResurrectionForecaster(enabled=False)
    odd_groups = pool.odd_groups()
    forecasts = forecaster.forecast(odd_groups) if odd_groups else []

    pool.close()

    if new_count:
        print(f"[BGI] SEP — {new_count} new suspended, {len(resurrected)} resurrected, {len(boundaries)} promoted to INTENTIONAL_BOUNDARY")
    if resurrected:
        edges = edges + resurrected

    graph = serialize_graph(fingerprints, edges, drs, sep_stats=sep_stats, forecasts=forecasts_to_dict(forecasts))
    Path(output).write_text(json.dumps(graph, indent=2))
    print(f"[BGI] Graph written to {output}")
    if forecasts:
        print(f"[BGI] Resurrection forecasts: {len(forecasts)} odd group(s) analyzed")

    # AI Position 3 — Architecture Narrator
    from bgi.ai.narrator import ArchitectureNarrator
    narrator = ArchitectureNarrator(enabled=False)
    narration = narrator.narrate(graph, root=str(root_path))

    agents_md_path = Path(output).with_name("agents.md")
    agents_md_path.write_text(narration.agents_md)
    print(f"[BGI] Architecture narration written to {agents_md_path}")
