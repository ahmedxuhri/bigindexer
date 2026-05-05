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
                      choices=["python", "typescript", "tsx", "ts", "javascript", "jsx", "js"],
                      help="Language to scan (default: python)")
    scan.add_argument("--out", default="bgi-graph.json", help="Output file")
    scan.add_argument("--db", default="bgi-sep.db", help="SEP SQLite database path")
    scan.add_argument("--ai-key", default=None,
                      help="AI API key (enables AI Position 1 + 3). Also reads DEEPSEEK_API_KEY env var.")
    scan.add_argument("--ai-model", default="deepseek-v4-flash",
                      help="AI model name (default: deepseek-v4-flash)")

    curate = sub.add_parser("curate", help="Analyze unresolved patterns and propose COV extension tokens")
    curate.add_argument("--unresolved", default="bgi-unresolved.jsonl", help="AIFallback log path")
    curate.add_argument("--db", default="bgi-sep.db", help="SEP database path")
    curate.add_argument("--graph", default="bgi-graph.json", help="Graph JSON path")
    curate.add_argument("--out", default="cov-extension-candidates.json", help="Output file")

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
        )

    elif args.command == "curate":
        import json
        from pathlib import Path
        from bgi.ai.curator import VocabularyCurator, candidates_to_dict
        curator = VocabularyCurator(enabled=False)
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


if __name__ == "__main__":
    main()
