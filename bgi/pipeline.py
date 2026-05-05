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
) -> None:
    from bgi.gate1.scanner import scan_directory, scan_file
    from bgi.gate2.keylock import match_fingerprints
    from bgi.gate3.drs import run_drs
    from bgi.sep.pool import SuspendedEdgePool
    from bgi.output.graph import serialize_graph
    from bgi.gate1.ai_fallback import AIFallback
    import time

    root_path = Path(root).resolve()
    scan_run = f"scan-{int(time.time())}"
    ai = AIFallback(enabled=False)

    if incremental:
        from bgi.delta.cache import ScanCache
        from bgi.gate1.scanner import scan_file as _scan_py
        try:
            from bgi.gate1.ts_scanner import scan_file_ts as _scan_ts
        except ImportError:
            _scan_ts = None
        try:
            from bgi.gate1.js_scanner import scan_file_js as _scan_js
        except ImportError:
            _scan_js = None
        try:
            from bgi.gate1.java_scanner import scan_file_java as _scan_java
        except ImportError:
            _scan_java = None
        try:
            from bgi.gate1.go_scanner import scan_file_go as _scan_go
        except ImportError:
            _scan_go = None
        try:
            from bgi.gate1.rust_scanner import scan_file_rust as _scan_rust
        except ImportError:
            _scan_rust = None
        try:
            from bgi.gate1.ruby_scanner import scan_file_ruby as _scan_ruby
        except ImportError:
            _scan_ruby = None
        try:
            from bgi.gate1.csharp_scanner import scan_file_csharp as _scan_csharp
        except ImportError:
            _scan_csharp = None
        try:
            from bgi.gate1.php_scanner import scan_file_php as _scan_php
        except ImportError:
            _scan_php = None
        try:
            from bgi.gate1.kotlin_scanner import scan_file_kotlin as _scan_kotlin
        except ImportError:
            _scan_kotlin = None
        try:
            from bgi.gate1.c_scanner import scan_file_c as _scan_c
        except ImportError:
            _scan_c = None
        try:
            from bgi.gate1.scala_scanner import scan_file_scala as _scan_scala
        except ImportError:
            _scan_scala = None
        try:
            from bgi.gate1.lua_scanner import scan_file_lua as _scan_lua
        except ImportError:
            _scan_lua = None
        try:
            from bgi.gate1.elixir_scanner import scan_file_elixir as _scan_elixir
        except ImportError:
            _scan_elixir = None

        lang = language.lower()
        if lang == "python":
            source_files = sorted(root_path.rglob("*.py"))
            _scan_fn = _scan_py
        elif lang in ("typescript", "tsx", "ts"):
            exts = {"*.ts", "*.tsx"}
            source_files = sorted(
                f for ext in exts for f in root_path.rglob(ext)
                if ".d.ts" not in f.name
            )
            _scan_fn = _scan_ts
        elif lang in ("javascript", "jsx", "js"):
            exts = {"*.js", "*.jsx"}
            source_files = sorted(f for ext in exts for f in root_path.rglob(ext))
            _scan_fn = _scan_js
        elif lang == "java":
            source_files = sorted(root_path.rglob("*.java"))
            _scan_fn = _scan_java
        elif lang == "go":
            source_files = sorted(root_path.rglob("*.go"))
            _scan_fn = _scan_go
        elif lang == "rust":
            source_files = sorted(root_path.rglob("*.rs"))
            _scan_fn = _scan_rust
        elif lang == "ruby":
            source_files = sorted(root_path.rglob("*.rb"))
            _scan_fn = _scan_ruby
        elif lang == "csharp":
            source_files = sorted(root_path.rglob("*.cs"))
            _scan_fn = _scan_csharp
        elif lang == "php":
            source_files = sorted(root_path.rglob("*.php"))
            _scan_fn = _scan_php
        elif lang == "kotlin":
            source_files = sorted(root_path.rglob("*.kt"))
            _scan_fn = _scan_kotlin
        elif lang == "c":
            source_files = sorted(root_path.rglob("*.c"))
            _scan_fn = _scan_c
        elif lang == "scala":
            source_files = sorted(root_path.rglob("*.scala"))
            _scan_fn = _scan_scala
        elif lang == "lua":
            source_files = sorted(root_path.rglob("*.lua"))
            _scan_fn = _scan_lua
        elif lang == "elixir":
            source_files = sorted(root_path.rglob("*.ex"))
            _scan_fn = _scan_elixir
        else:
            raise NotImplementedError(f"Language '{language}' not yet supported.")

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
    else:
        print(f"[BGI] Scanning {root_path} ...")
        fingerprints = scan_directory(root_path, language=language, ai=ai, scan_run=scan_run)
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

    # Step 4 — HTML visualization
    if html:
        from bgi.output.html_viz import generate_html
        html_path = str(Path(output).with_suffix(".html"))
        title = f"BGI — {Path(root).name}"
        generate_html(graph, html_path, inline_d3=True, title=title)
        print(f"[BGI] HTML visualization written to {html_path}")
