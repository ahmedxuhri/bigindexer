"""
BGI Pipeline — orchestrates Gate 1 → Gate 2 → Gate 3 → SEP → Output.
This is the top-level wiring. Each gate is independently importable/testable.
"""
from __future__ import annotations
import json
from pathlib import Path


def run_scan(
    root: str,
    language: str = "python",
    output: str = "bgi-graph.json",
    db: str = "bgi-sep.db",
    ai_key: str | None = None,
    ai_model: str = "deepseek-v4-flash",
    html: bool = False,
    incremental: bool = False,
    cache_file: str = ".bgi-cache.json",
    routes_output: str | None = None,
    graphml_output: str | None = None,
    max_cluster_pct: float = 0.03,
    fuse_graph_output: str | None = None,
    exclude_dirs: set[str] | None = None,
    parallel: bool = False,
    max_workers: int | None = None,
) -> None:
    from bgi.gate1.scanner import scan_directory, scan_file, scan_repository, _scan_file_auto, _EXT_TO_LANG
    from bgi.gate2.keylock import match_fingerprints
    from bgi.gate2.census import compute_census
    from bgi.gate3.drs import run_drs
    from bgi.sep.pool import SuspendedEdgePool
    from bgi.output.graph import serialize_graph
    from bgi.gate1.ai_fallback import AIFallback
    import time

    root_path = Path(root).resolve()
    scan_run = f"scan-{int(time.time())}"
    ai = AIFallback(enabled=False)
    auto_mode = language.lower() == "auto"

    if incremental and not auto_mode:
        from bgi.delta.cache import ScanCache

        # Resolve per-language scanner function
        lang = language.lower()
        _scan_fn = _get_scanner_fn(lang)
        exts = _get_lang_exts(lang, _EXT_TO_LANG)
        source_files = _collect_source_files(root_path, exts, lang)

        cache_path = Path(output).parent / cache_file
        cache = ScanCache.load(cache_path)
        dirty, cached_fps = cache.partition(source_files, root_path, use_git=True)
        deleted = cache.purge_deleted(source_files, root_path)

        print(
            f"[BGI] Incremental scan — "
            f"{len(dirty)} dirty / {len(source_files) - len(dirty)} cached"
            + (f" / {len(deleted)} deleted" if deleted else "")
        )

        new_fps: list = []
        fps_by_rel: dict = {}
        for f in dirty:
            try:
                fps = _scan_fn(f, root_path, ai)
            except Exception as exc:
                print(f"[BGI] Warning: skipped {f}: {exc}")
                fps = []
            new_fps.extend(fps)
            fps_by_rel[str(f.relative_to(root_path))] = fps

        cache.update_many(dirty, root_path, fps_by_rel)
        cache.save(cache_path)
        ai.flush(scan_run=scan_run)

        fingerprints = cached_fps + new_fps
        print(f"[BGI] Gate 1 complete — {len(fingerprints)} units ({len(new_fps)} re-scanned)")

    elif auto_mode:
        print(f"[BGI] Auto-scan {root_path} (multi-language) ...")
        fingerprints = scan_repository(root_path, ai=ai, scan_run=scan_run)
        print(f"[BGI] Gate 1 complete — {len(fingerprints)} units fingerprinted")

    else:
        print(f"[BGI] Scanning {root_path} ...")
        if parallel and language.lower() != "auto":
            from bgi.gate1.parallel_scanner import scan_directory_parallel
            fingerprints = scan_directory_parallel(root_path, language=language, max_workers=max_workers)
        else:
            fingerprints = scan_directory(root_path, language=language, ai=ai, scan_run=scan_run)
        print(f"[BGI] Gate 1 complete — {len(fingerprints)} units fingerprinted")

    # TOKEN-CENSUS — classify COV tokens into frequency bands
    total_files = len({fp.unit_id.split("::")[0] for fp in fingerprints})
    census = compute_census(fingerprints, total_files)
    print(f"[BGI] TOKEN-CENSUS — {total_files} files, bands: "
          f"Mask 1={sum(1 for b in census.token_bands.values() if b == 'Mask 1')}, "
          f"Mask 2={sum(1 for b in census.token_bands.values() if b == 'Mask 2')}, "
          f"Mask 3={sum(1 for b in census.token_bands.values() if b == 'Mask 3')}")

    edges, suspended = match_fingerprints(fingerprints, census=census)
    print(f"[BGI] Gate 2 complete — {len(edges)} edges detected ({len(suspended)} suspended)")

    drs, fuse_edges = run_drs(fingerprints, edges, max_cluster_pct=max_cluster_pct, root_path=str(root_path))
    hard = sum(1 for c in drs.clusters if c.is_hard)
    print(f"[BGI] Gate 3 complete — {len(drs.clusters)} clusters ({hard} hard, {len(drs.seam_units)} seams, {len(fuse_edges)} fuse events)")

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

    # Fuse-graph output (architectural boundary map)
    if fuse_edges:
        fuse_path = fuse_graph_output or str(Path(output).parent / "fuse-graph.json")
        from bgi.output.fuse_graph import write_fuse_graph
        max_cap = max(50, int(len(fingerprints) * max_cluster_pct))
        write_fuse_graph(fuse_edges, fuse_path, max_cluster_size=max_cap, total_units=len(fingerprints))
        print(f"[BGI] Fuse-graph written to {fuse_path} ({len(fuse_edges)} boundary events)")

    # AI Position 3 — Architecture Narrator
    from bgi.ai.narrator import ArchitectureNarrator
    from bgi.gate1.ai_fallback import make_deepseek_client

    ai_client = make_deepseek_client(ai_key) if ai_key else None
    narrator = ArchitectureNarrator(
        enabled=bool(ai_key),
        client=ai_client,
        model=ai_model,
    )
    narration = narrator.narrate(graph, root=str(root_path))
    if narration.ai_enhanced:
        print(f"[BGI] Narrator AI-enhanced ({ai_model})")

    agents_md_path = Path(output).parent / "agents.md"
    agents_md_path.write_text(narration.agents_md)
    print(f"[BGI] Architecture narration written to {agents_md_path}")

    # Route manifest (optional)
    if routes_output:
        from bgi.output.route_manifest import write_route_manifest
        write_route_manifest(fingerprints, routes_output)
        print(f"[BGI] Route manifest written to {routes_output}")

    # GraphML cluster graph (optional)
    if graphml_output:
        from bgi.output.graph import write_graphml
        write_graphml(edges, drs_result, graphml_output, cluster_level=True)
        print(f"[BGI] GraphML cluster graph written to {graphml_output}")

    # Step 4 — HTML visualization
    if html:
        from bgi.output.html_viz import generate_html
        html_path = str(Path(output).with_suffix(".html"))
        title = f"BGI — {Path(root).name}"
        generate_html(graph, html_path, inline_d3=True, title=title)
        print(f"[BGI] HTML visualization written to {html_path}")


# ── Language dispatch helpers (used by pipeline and incremental scan) ─────────

def _get_scanner_fn(lang: str):
    """Return the scan_file_* function for a given language identifier."""
    from bgi.gate1.scanner import scan_file
    if lang == "python":
        return scan_file
    if lang in ("typescript", "tsx", "ts"):
        from bgi.gate1.ts_scanner import scan_file_ts
        return scan_file_ts
    if lang in ("javascript", "jsx", "js"):
        from bgi.gate1.js_scanner import scan_file_js
        return scan_file_js
    if lang == "java":
        from bgi.gate1.java_scanner import scan_file_java
        return scan_file_java
    if lang == "go":
        from bgi.gate1.go_scanner import scan_file_go
        return scan_file_go
    if lang == "rust":
        from bgi.gate1.rust_scanner import scan_file_rust
        return scan_file_rust
    if lang == "ruby":
        from bgi.gate1.ruby_scanner import scan_file_ruby
        return scan_file_ruby
    if lang == "csharp":
        from bgi.gate1.csharp_scanner import scan_file_csharp
        return scan_file_csharp
    if lang == "php":
        from bgi.gate1.php_scanner import scan_file_php
        return scan_file_php
    if lang == "kotlin":
        from bgi.gate1.kotlin_scanner import scan_file_kotlin
        return scan_file_kotlin
    if lang == "c":
        from bgi.gate1.c_scanner import scan_file_c
        return scan_file_c
    if lang == "scala":
        from bgi.gate1.scala_scanner import scan_file_scala
        return scan_file_scala
    if lang == "lua":
        from bgi.gate1.lua_scanner import scan_file_lua
        return scan_file_lua
    if lang == "elixir":
        from bgi.gate1.elixir_scanner import scan_file_elixir
        return scan_file_elixir
    raise NotImplementedError(f"Language '{lang}' not supported for incremental scan. Use --lang=auto.")


def _get_lang_exts(lang: str, ext_map: dict) -> list[str]:
    """Return glob patterns for a language's file extensions."""
    return sorted({
        f"*{ext}" for ext, l in ext_map.items() if l == lang
    }) or [f"*.{lang}"]


def _collect_source_files(root: Path, exts: list[str], lang: str) -> list[Path]:
    """Collect all source files for the given extension patterns."""
    files: list[Path] = []
    for pattern in exts:
        for f in root.rglob(pattern):
            if lang in ("typescript", "ts") and f.name.endswith(".d.ts"):
                continue
            files.append(f)
    return sorted(set(files))
