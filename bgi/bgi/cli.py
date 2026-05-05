"""BGI CLI — entry point."""
from __future__ import annotations
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bgi",
        description="Bio-Gate Indexing — language-agnostic code intelligence",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan a directory and produce a BGI graph")
    scan.add_argument("path", help="Root path to scan")
    scan.add_argument("--lang", default="python",
                      choices=["auto",
                               "python", "typescript", "tsx", "ts", "javascript", "jsx", "js",
                               "java", "go", "rust", "ruby", "csharp", "php", "kotlin", "c",
                               "scala", "lua", "elixir",
                               "swift", "r", "dart", "bash", "nim", "zig", "haskell",
                               "ocaml", "fsharp", "clojure", "erlang", "matlab", "vb",
                               "crystal", "cobol", "groovy", "generic"],
                      help="Language to scan (default: python). Use 'auto' for multi-language repos.")
    scan.add_argument("--out", default="bgi-graph.json", help="Output file")
    scan.add_argument("--db", default="bgi-sep.db", help="SEP SQLite database path")
    scan.add_argument("--ai-key", default=None,
                      help="AI API key (enables AI Position 1 + 3). Also reads DEEPSEEK_API_KEY env var.")
    scan.add_argument("--ai-model", default="deepseek-v4-flash",
                      help="AI model name (default: deepseek-v4-flash)")
    scan.add_argument("--html", action="store_true", default=False,
                      help="Also generate a self-contained HTML visualization")
    scan.add_argument("--incremental", action="store_true", default=False,
                      help="Only re-scan files changed since last run (uses .bgi-cache.json)")
    scan.add_argument("--cache", default=".bgi-cache.json",
                      help="Cache file for incremental mode (default: .bgi-cache.json)")
    scan.add_argument("--routes", default=None, metavar="FILE",
                      help="Also write a route manifest JSON (e.g. routes.json)")

    curate = sub.add_parser("curate", help="Analyze unresolved patterns and propose COV extension tokens")
    curate.add_argument("--unresolved", default="bgi-unresolved.jsonl", help="AIFallback log path")
    curate.add_argument("--db", default="bgi-sep.db", help="SEP database path")
    curate.add_argument("--graph", default="bgi-graph.json", help="Graph JSON path")
    curate.add_argument("--out", default="cov-extension-candidates.json", help="Output file")
    curate.add_argument("--ai-key", default=None,
                        help="AI API key (enables AI Position 4). Also reads DEEPSEEK_API_KEY env var.")
    curate.add_argument("--ai-model", default="deepseek-v4-flash",
                        help="AI model for curation (default: deepseek-v4-flash)")

    diff_cmd = sub.add_parser("diff", help="Diff two scan roots and report architectural changes")
    diff_cmd.add_argument("before", help="Path to 'before' scan root")
    diff_cmd.add_argument("after",  help="Path to 'after' scan root")
    diff_cmd.add_argument("--lang", default="auto",
                          help="Language to scan (default: auto for multi-language)")
    diff_cmd.add_argument("--out", default=None, metavar="FILE",
                          help="Write diff JSON to file (optional)")
    diff_cmd.add_argument("--verbose", action="store_true", default=False,
                          help="Show full added/removed/changed unit lists")

    args = parser.parse_args()

    if args.command == "scan":
        import os
        from bgi.pipeline import run_scan
        ai_key = args.ai_key or os.environ.get("DEEPSEEK_API_KEY")
        run_scan(
            args.path,
            language=args.lang,
            output=args.out,
            db=args.db,
            ai_key=ai_key,
            ai_model=args.ai_model,
            html=args.html,
            incremental=args.incremental,
            cache_file=args.cache,
            routes_output=args.routes,
        )

    elif args.command == "curate":
        import json
        import os
        from pathlib import Path
        from bgi.ai.curator import VocabularyCurator, candidates_to_dict
        from bgi.gate1.ai_fallback import make_deepseek_client

        ai_key = args.ai_key or os.environ.get("DEEPSEEK_API_KEY")
        ai_client = make_deepseek_client(ai_key) if ai_key else None
        curator = VocabularyCurator(
            enabled=bool(ai_key),
            client=ai_client,
            model=args.ai_model,
        )
        candidates = curator.curate(
            unresolved_log=Path(args.unresolved),
            sep_db=Path(args.db),
            graph=Path(args.graph),
        )
        result = candidates_to_dict(candidates)
        Path(args.out).write_text(json.dumps(result, indent=2))
        print(f"[BGI] Curator — {len(candidates)} candidate(s) written to {args.out}")
        for c in candidates:
            action = result["candidates"][candidates.index(c)]["action"]
            print(f"  [{action}] {c.token_name}  conf={c.confidence:.2f}  signals={c.signal_sources}")

    elif args.command == "diff":
        import json
        import os
        from pathlib import Path
        from bgi.gate1.scanner import scan_repository, scan_directory
        from bgi.gate1.ai_fallback import AIFallback
        from bgi.delta.diff import diff_scans, format_diff_report, serialize_diff

        ai = AIFallback(enabled=False)
        lang = args.lang.lower()

        def _scan(path: str) -> list:
            p = Path(path).resolve()
            if lang == "auto":
                return scan_repository(p, ai=ai)
            return scan_directory(p, language=lang, ai=ai)

        print(f"[BGI] Scanning before: {args.before}")
        fps_before = _scan(args.before)
        print(f"[BGI] Scanning after:  {args.after}")
        fps_after  = _scan(args.after)

        diff = diff_scans(fps_before, fps_after)
        print(format_diff_report(diff, verbose=args.verbose))

        if args.out:
            Path(args.out).write_text(json.dumps(serialize_diff(diff), indent=2))
            print(f"\n[BGI] Diff written to {args.out}")


if __name__ == "__main__":
    main()
