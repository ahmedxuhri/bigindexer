#!/usr/bin/env python3
"""Score Gemini auto-model TWIN replication runs against rubric checklists.

This script scores rows with run_id suffix `mcp-twin-refresh-gemini-auto-r1` in
validation/runs.csv and fills:
- evidence_coverage_pct
- boundary_accuracy
- actionability
- hallucination_flags
- rework_needed
- executor
- notes
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from statistics import mean, median
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
RUNS_CSV = ROOT / "validation" / "runs.csv"

TARGET_SUFFIX = "mcp-twin-refresh-gemini-auto-r1"


def _norm(text: str) -> str:
    return text.lower()


def _has_any(text: str, *patterns: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE | re.MULTILINE) for p in patterns)


def _has_all(text: str, *patterns: str) -> bool:
    return all(re.search(p, text, re.IGNORECASE | re.MULTILINE) for p in patterns)


def _safe_not_direct_edit(text: str, unsafe: str, explicit_safe: str) -> bool:
    if re.search(explicit_safe, text, re.IGNORECASE | re.MULTILINE):
        return True
    return not re.search(unsafe, text, re.IGNORECASE | re.MULTILINE)


def _extract_assistant_text(path: Path) -> str:
    chunks: list[str] = []
    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "message" and obj.get("role") == "assistant":
            content = obj.get("content")
            if isinstance(content, str):
                chunks.append(content)
    return _norm(" ".join(chunks))


def _checklist(repo: str, prompt_id: str) -> list[Callable[[str], bool]]:
    c: list[Callable[[str], bool]] = []

    if repo == "fastapi" and prompt_id == "p01":
        c = [
            lambda t: _has_any(t, r"fastapi/routing\.py", r"\bapiroute\b", r"request dispatch"),
            lambda t: _has_any(t, r"fastapi/dependencies", r"dependency injection", r"solve_dependencies"),
            lambda t: _has_any(t, r"fastapi/openapi", r"\bopenapi\b"),
            lambda t: _has_any(t, r"fastapi/applications\.py", r"class fastapi", r"\bfastapi class\b"),
            lambda t: _has_any(t, r"\basgi\b", r"\bstarlette\b"),
            lambda t: _has_any(t, r"fastapi/responses\.py", r"fastapi/datastructures\.py", r"\bdatastructures\b"),
            lambda t: _has_any(t, r"\btests/", r"\btest suite\b", r"\btests\b"),
        ]
    elif repo == "django" and prompt_id == "p01":
        c = [
            lambda t: _has_any(t, r"\bmtv\b", r"\bmvt\b", r"model[- ]template[- ]view"),
            lambda t: _has_any(t, r"django/db/", r"\borm\b"),
            lambda t: _has_any(t, r"django/urls/", r"url routing", r"url resolver"),
            lambda t: _has_any(t, r"django/middleware/", r"\bmiddleware\b"),
            lambda t: _has_any(t, r"django/contrib/admin/", r"\badmin\b"),
            lambda t: _has_any(t, r"django/forms/", r"\bforms\b"),
            lambda t: _has_any(t, r"django/dispatch/", r"\bsignal"),
        ]
    elif repo == "pydantic" and prompt_id == "p01":
        c = [
            lambda t: _has_any(t, r"\brust\b", r"pydantic-core", r"\bsrc/"),
            lambda t: _has_any(t, r"python/pydantic_core", r"python wrapper", r"\bbindings\b"),
            lambda t: _has_any(t, r"pydantic_core_init\.pyi", r"type stub", r"\.pyi"),
            lambda t: _has_any(t, r"schemavalidator", r"schemaserializer", r"getcoreschema"),
            lambda t: _has_any(t, r"\bbenches/", r"\bbenchmark"),
            lambda t: _has_any(t, r"\bpyo3\b"),
        ]
    elif repo == "prometheus" and prompt_id == "p01":
        c = [
            lambda t: _has_any(t, r"cmd/prometheus/main\.go", r"\bmain\.go\b"),
            lambda t: _has_any(t, r"\btsdb\b"),
            lambda t: _has_any(t, r"\bscrape\b"),
            lambda t: _has_any(t, r"\brule\b"),
            lambda t: _has_any(t, r"\bweb\b", r"\bhttp\b"),
            lambda t: _has_any(t, r"model/labels/", r"\blabel"),
            lambda t: _has_any(t, r"\bdiscovery\b"),
        ]
    elif repo == "nextjs" and prompt_id == "p01":
        c = [
            lambda t: _has_any(t, r"\bmonorepo\b", r"\bpackages/"),
            lambda t: _has_any(t, r"packages/next/src/"),
            lambda t: _has_any(t, r"packages/next/src/server/"),
            lambda t: _has_any(t, r"packages/next/src/build/"),
            lambda t: _has_any(t, r"packages/next/src/client/"),
            lambda t: _has_any(t, r"\bcrates/", r"\bturbopack\b", r"\bswc\b", r"\brust\b"),
            lambda t: _has_all(t, r"\bclient\b", r"\bserver\b"),
        ]
    elif repo == "fastapi" and prompt_id == "p02":
        c = [
            lambda t: _has_all(t, r"routing", r"dependenc"),
            lambda t: _has_any(t, r"applications\.py", r"integration hub"),
            lambda t: _has_any(t, r"\basgi\b"),
            lambda t: _has_any(t, r"\btests/?", r"\btest"),
            lambda t: _has_all(t, r"openapi", r"routing"),
        ]
    elif repo == "django" and prompt_id == "p02":
        c = [
            lambda t: _has_all(t, r"\borm\b", r"\bview"),
            lambda t: _has_any(t, r"url resolver", r"django/urls/", r"routing boundary"),
            lambda t: _has_any(t, r"\bmiddleware\b"),
            lambda t: _has_all(t, r"\badmin\b", r"\borm\b"),
            lambda t: _has_any(t, r"\bcontrib\b", r"contrib apps"),
        ]
    elif repo == "pydantic" and prompt_id == "p02":
        c = [
            lambda t: _has_any(t, r"\brust\b", r"pydantic.core") and _has_any(t, r"\bpython\b"),
            lambda t: _has_any(t, r"schemavalidator", r"entry point"),
            lambda t: _has_any(t, r"\.pyi", r"type stub"),
            lambda t: _has_any(t, r"\bbenches/", r"\bbenchmark"),
            lambda t: _has_any(t, r"\berror\b", r"\bboundary\b"),
        ]
    elif repo == "prometheus" and prompt_id == "p02":
        c = [
            lambda t: _has_all(t, r"\bscrape", r"\btsdb"),
            lambda t: _has_any(t, r"\btsdb\b") and _has_any(t, r"\bweb\b", r"\bsystem\b", r"\bnetwork\b"),
            lambda t: _has_any(t, r"\brules engine\b", r"\brules/"),
            lambda t: _has_any(t, r"\bappend\b"),
            lambda t: _has_any(t, r"remote read", r"remote write"),
        ]
    elif repo == "nextjs" and prompt_id == "p02":
        c = [
            lambda t: _has_any(t, r"router-server", r"render server", r"process boundary", r"next-server\.ts"),
            lambda t: _has_any(t, r"\bswc\b", r"\bturbopack\b", r"\bnapi\b", r"\brust\b"),
            lambda t: _has_any(t, r"build.*runtime", r"manifest", r"chunk"),
            lambda t: _has_any(t, r"webpack", r"turbopack", r"rspack"),
            lambda t: _has_any(t, r"\brsc\b", r"app-render", r"client boundary"),
            lambda t: _has_any(t, r"incremental cache", r"\bincremental\b", r"server lib"),
            lambda t: _has_any(t, r"\bheader", r"request metadata", r"protocol boundary"),
            lambda t: _has_any(t, r"packages/next/src/server/next-server\.ts", r"high-coupling hotspot"),
        ]
    elif repo == "fastapi" and prompt_id == "p03":
        c = [
            lambda t: _has_any(t, r"get_request_handler", r"http request"),
            lambda t: _has_any(t, r"websocket"),
            lambda t: _has_any(t, r"recursive", r"calls itself"),
            lambda t: _has_any(t, r"solveddependency", r"contract"),
            lambda t: _has_any(t, r"no direct unit tests", r"integration tests"),
            lambda t: _has_any(t, r"all routes", r"100% of http traffic"),
        ]
    elif repo == "django" and prompt_id == "p03":
        c = [
            lambda t: _has_any(t, r"middleware chain", r"\bmiddleware\b"),
            lambda t: _has_any(t, r"every http request", r"every request"),
            lambda t: _has_any(t, r"exception handler", r"exception wrapping"),
            lambda t: _has_any(t, r"test runner", r"\btests\b"),
            lambda t: _has_any(t, r"process_request", r"process_response"),
        ]
    elif repo == "pydantic" and prompt_id == "p03":
        c = [
            lambda t: _has_any(t, r"all python validation", r"all validation calls"),
            lambda t: _has_any(t, r"\bpyo3\b", r"\bpython.*rust boundary"),
            lambda t: _has_any(t, r"\bbenches/", r"\bbenchmark"),
            lambda t: _has_any(t, r"type stub", r"\.pyi"),
            lambda t: _has_any(t, r"downstream pydantic", r"pydantic v2"),
        ]
    elif repo == "prometheus" and prompt_id == "p03":
        c = [
            lambda t: _has_any(t, r"\bapi\b", r"\brules?\b"),
            lambda t: _has_any(t, r"querier interface", r"storage backends", r"storage interface", r"\binterface\b"),
            lambda t: _has_any(t, r"remote read", r"remote storage"),
            lambda t: _has_any(t, r"federation"),
            lambda t: _has_any(t, r"chunk iterators", r"series set", r"seriesset", r"\bseries\b"),
        ]
    elif repo == "nextjs" and prompt_id == "p03":
        c = [
            lambda t: _has_all(t, r"next-server", r"next-dev-server"),
            lambda t: _has_any(t, r"requestlifecycleopts", r"type consumers", r"server types"),
            lambda t: _has_any(t, r"\bbuild\b", r"app-render", r"client components", r"incremental cache"),
            lambda t: _has_any(t, r"signature", r"api change", r"high-risk"),
            lambda t: _has_any(t, r"\btests?\b", r"typecheck", r"\bbuild checks?\b"),
        ]
    elif repo == "fastapi" and prompt_id == "p04":
        c = [
            lambda t: _has_any(t, r"@app\.middleware\(\"http\"\)", r"\basgi middleware"),
            lambda t: _has_any(t, r"build_middleware_stack", r"user_middleware"),
            lambda t: _has_any(t, r"time-to-first-byte", r"streaming caveat"),
            lambda t: _has_any(t, r"```", r"fastapi/middleware", r"specific file"),
            lambda t: _safe_not_direct_edit(
                t,
                r"(modify|edit|change).{0,40}routing\.py",
                r"(do not|don't|avoid).{0,40}routing\.py",
            ),
        ]
    elif repo == "django" and prompt_id == "p04":
        c = [
            lambda t: _has_any(t, r"\bmiddleware\b", r"\bsignal"),
            lambda t: _has_any(t, r"\bmiddleware insertion", r"\bmiddleware order", r"\bsettings\.py\b"),
            lambda t: _has_any(t, r"\borm\b", r"\bmodel\b", r"\bdatabase\b"),
            lambda t: _safe_not_direct_edit(
                t,
                r"(modify|edit|change).{0,40}get_response",
                r"(do not|don't|avoid).{0,40}get_response",
            ),
            lambda t: _has_any(t, r"checklist", r"\bstep 1\b", r"implementation guidance", r"file:"),
        ]
    elif repo == "pydantic" and prompt_id == "p04":
        c = [
            lambda t: _has_any(t, r"@validator", r"__get_validators__", r"aftervalidator", r"beforevalidator"),
            lambda t: _has_any(t, r"python side", r"not rust", r"python, not rust"),
            lambda t: _has_any(t, r"schema compilation", r"core schema", r"model_rebuild"),
            lambda t: _safe_not_direct_edit(
                t,
                r"(modify|edit|change).{0,40}(rust|pydantic-core|src/)",
                r"(do not|don't|avoid).{0,40}(rust|pydantic-core|src/)",
            ),
            lambda t: _has_any(t, r"example", r"implementation pattern", r"code"),
        ]
    elif repo == "prometheus" and prompt_id == "p04":
        c = [
            lambda t: _has_any(t, r"web/api/v1/api\.go"),
            lambda t: _has_any(t, r"tsdb\.head", r"tsdb\.db", r"\btsdb\b"),
            lambda t: _has_any(t, r"/api/v1/labels", r"labels endpoint"),
            lambda t: _has_any(t, r"\bseries\b", r"query path"),
            lambda t: _safe_not_direct_edit(
                t,
                r"(modify|edit|change).{0,40}(storage layer|storage/)",
                r"(do not|don't|avoid).{0,40}(storage layer|storage/)",
            ),
        ]
    elif repo == "nextjs" and prompt_id == "p04":
        c = [
            lambda t: _has_any(t, r"router-server\.ts", r"outer server handler", r"insertion point"),
            lambda t: _has_any(t, r"server-generated", r"do not trust client", r"not trusting client"),
            lambda t: _has_any(t, r"internal.*header", r"anti-forgery", r"hardening"),
            lambda t: _has_any(t, r"per-request", r"request metadata", r"propagation"),
            lambda t: _has_any(t, r"headerssent", r"\botel\b", r"opentelemetry", r"safety guard", r"guard"),
        ]

    if not c:
        raise ValueError(f"No checklist for {repo}/{prompt_id}")
    return c


def _score_one(repo: str, prompt_id: str, text: str) -> tuple[float, float, int, int, str]:
    checks = _checklist(repo, prompt_id)
    hits = sum(1 for fn in checks if fn(text))
    total = len(checks)
    evidence = round((hits / total) * 100.0, 1)

    if prompt_id in {"p02", "p03"}:
        boundary = 1.0 if hits >= max(2, total // 2) else 0.0
    elif prompt_id == "p04":
        boundary = 1.0 if hits >= 3 else 0.0
    else:
        boundary = 1.0 if hits >= max(3, total // 2) else 0.0

    actionable_markers = _has_any(
        text,
        r"actionability checklist",
        r"\bchecklist\b",
        r"\bstep 1\b",
        r"safest implementation path",
        r"implementation guidance",
    )
    if prompt_id == "p04":
        actionability = 5 if hits >= 4 else (4 if hits >= 3 else 3)
    else:
        if hits >= max(4, int(total * 0.7)):
            actionability = 5 if actionable_markers else 4
        elif hits >= max(3, total // 2):
            actionability = 4
        else:
            actionability = 3

    hallucinations = 0
    rework_needed = "no" if actionability >= 4 else "yes"
    return evidence, boundary, actionability, hallucinations, rework_needed


def main() -> None:
    with RUNS_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    scored_rows = []
    for row in rows:
        if TARGET_SUFFIX not in row["run_id"]:
            continue
        out_file = ROOT / row["output_file"]
        text = _extract_assistant_text(out_file)
        if not text.strip():
            continue
        evidence, boundary, actionability, hallucinations, rework = _score_one(
            row["repo_slug"], row["prompt_id"], text
        )
        row["evidence_coverage_pct"] = f"{evidence:.1f}"
        row["boundary_accuracy"] = f"{boundary:.1f}"
        row["actionability"] = str(actionability)
        row["hallucination_flags"] = str(hallucinations)
        row["rework_needed"] = rework
        row["executor"] = "auto_rubric_v2"
        row["notes"] = "gemini_auto_twin_replication_scored"
        scored_rows.append(row)

    with RUNS_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    if not scored_rows:
        print("No Gemini auto rows found for scoring.")
        return

    ev = [float(r["evidence_coverage_pct"]) for r in scored_rows]
    ba = [float(r["boundary_accuracy"]) for r in scored_rows]
    ac = [float(r["actionability"]) for r in scored_rows]
    lat = [float(r["latency_sec"]) for r in scored_rows if (r.get("latency_sec") or "").strip()]
    print(
        "Scored Gemini rows:",
        len(scored_rows),
        f"| evidence_mean={mean(ev):.2f}",
        f"| boundary_mean={mean(ba):.2f}",
        f"| actionability_mean={mean(ac):.2f}",
        f"| median_latency={median(lat):.2f}s",
    )


if __name__ == "__main__":
    main()
