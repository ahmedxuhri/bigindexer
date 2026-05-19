"""
AI Position 3 — Architecture Narrator.

Consumes the fully assembled BGI graph and produces two outputs:
  1. bigindexer.md  — structured markdown for AI agent consumption
  2. A plain-text architecture summary for humans (logged to stdout or file)

Design:
  - Heuristic pass always runs: produces a deterministic, rule-based markdown context with no API cost.
  - AI pass (when enabled): sends heuristic draft + graph context to an LLM (DeepSeek by default,
    any OpenAI-compatible provider works) to enrich cluster names, add architectural intent,
    and flag notable relationships.
  - Output is written to <output_dir>/bigindexer.md alongside the JSON graph.

bigindexer.md format:
  # BGI Architecture — <root>
  ## Clusters
  ### <cluster_name>  [HARD|SOFT] [CROSS-FILE]
  **Role:** <inferred role from dominant COV tokens>
  **Files:** ...
  **Units:** ...
  **Key relationships:** ...
  ## Seam Units
  ## Resurrection Forecasts (if any)
  ## Stats

Quick start (with DeepSeek):
    from bgi.ai.narrator import ArchitectureNarrator
    from bgi.gate1.ai_fallback import make_deepseek_client

    narrator = ArchitectureNarrator(
        enabled=True,
        client=make_deepseek_client("sk-..."),
    )
    result = narrator.narrate(graph, root="my_service")
    Path("bigindexer.md").write_text(result.agents_md)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# ── Role inference from dominant COV tokens ───────────────────────────────────

# Maps sets of dominant tokens → a human-readable architectural role.
# Matched in priority order (first match wins).
_ROLE_RULES: list[tuple[set[str], str]] = [
    ({"COV.AUTHENTICATE", "COV.AUTHORIZE"},       "Authentication & Authorization"),
    ({"COV.AUTHENTICATE"},                        "Authentication"),
    ({"COV.AUTHORIZE"},                           "Authorization"),
    ({"COV.ROUTE"},                               "API Routing Layer"),
    ({"COV.PERSIST", "COV.FETCH"},                "Data Access / Repository"),
    ({"COV.PERSIST"},                             "Data Writer"),
    ({"COV.FETCH"},                               "Data Reader"),
    ({"COV.EMIT", "COV.SUBSCRIBE"},               "Event Bus / Pub-Sub"),
    ({"COV.EMIT"},                                "Event Publisher"),
    ({"COV.SUBSCRIBE"},                           "Event Consumer"),
    ({"COV.CONTRACT"},                            "Interface / Contract Definition"),
    ({"COV.TEST"},                                "Test Suite"),
    ({"COV.INIT", "COV.TEARDOWN"},                "Lifecycle Manager"),
    ({"COV.VALIDATE", "COV.INTAKE"},              "Input Validation Layer"),
    ({"COV.VALIDATE"},                            "Validator"),
    ({"COV.TRANSFORM"},                           "Data Transformer"),
    ({"COV.DELEGATE"},                            "Orchestrator / Service Delegate"),
    ({"COV.RECOVER"},                             "Error Recovery"),
    ({"COV.LOG"},                                 "Observability / Logging"),
    ({"COV.MEASURE"},                             "Metrics / Instrumentation"),
    ({"COV.INTAKE", "COV.OUTPUT"},                "Request Handler"),
    ({"COV.INTAKE"},                              "Input Handler"),
    ({"COV.OUTPUT"},                              "Output Producer"),
]


def _infer_role(dominant_tokens: list[str]) -> str:
    """
    Infer architectural role from dominant tokens.

    Special case: when COV.TEST is the most prevalent token (position 0),
    the cluster is a test surface regardless of what other tokens it carries
    (tests routinely call routes, fetch data, mutate state — that does not
    make them an API Routing Layer).
    """
    if dominant_tokens and dominant_tokens[0] == "COV.TEST":
        return "Test Suite"
    token_set = set(dominant_tokens)
    for required, role in _ROLE_RULES:
        if required.issubset(token_set):
            return role
    return "General Logic"


def _is_test_cluster(cluster: dict, name: str) -> bool:
    """Heuristic: top dominant token is TEST, or the cluster name/files look test-shaped."""
    tokens = cluster.get("dominant_tokens", [])
    if tokens and tokens[0] == "COV.TEST":
        return True
    lowered_name = name.lower()
    if "test" in lowered_name or "benchmark" in lowered_name:
        return True
    files = cluster.get("files", [])
    if files and all("test" in f.lower() or "benchmark" in f.lower() for f in files):
        return True
    return False


# ── Cluster name heuristic ────────────────────────────────────────────────────

def _cluster_name(cluster: dict) -> str:
    """
    Derive a readable cluster name from member IDs.
    Prefers the most common class name, falls back to file name.
    """
    class_votes: dict[str, int] = {}
    for member in cluster["members"]:
        parts = member.split("::")
        if len(parts) == 3:
            cls = parts[1]
            class_votes[cls] = class_votes.get(cls, 0) + 1

    if class_votes:
        return max(class_votes, key=class_votes.__getitem__)

    # Fall back to file stem
    files = cluster.get("files", [])
    if files:
        return Path(files[0]).stem.replace("_", " ").title()

    return cluster["id"][:30]


# ── Cross-cluster relationship discovery ──────────────────────────────────────

def _cross_cluster_edges(edges: list[dict], unit_to_cluster: dict[str, str]) -> list[dict]:
    """Find edges that cross cluster boundaries (excluding same-token lifecycle noise)."""
    # These pairs are intra-component lifecycle — filter when they appear cross-cluster
    _LIFECYCLE_PAIRS = {("COV.INIT", "COV.TEARDOWN"), ("COV.INIT", "COV.DEFER")}

    cross = []
    seen = set()
    for e in edges:
        src_c = unit_to_cluster.get(e["source"])
        tgt_c = unit_to_cluster.get(e["target"])
        if src_c and tgt_c and src_c != tgt_c:
            pair = (e["key"], e["lock"])
            if pair in _LIFECYCLE_PAIRS:
                continue
            key = (src_c, tgt_c, e["key"], e["lock"])
            if key not in seen:
                seen.add(key)
                cross.append({
                    "from_cluster": src_c,
                    "to_cluster":   tgt_c,
                    "key":   e["key"],
                    "lock":  e["lock"],
                    "type":  e["type"],
                })
    return cross


def _aggregate_cross_edges(cross_edges: list[dict],
                            cluster_names: dict[str, str]) -> list[dict]:
    """Collapse cross-cluster edges into name-level traffic.

    The raw cross-edge list often includes:
      - many edges between cluster IDs that derive the same human name
        (BGI fragments a single class into several IDs)
      - many edges with the same (key, lock) pair between two name pairs

    Both are noise for a reader. We collapse to one row per
    (src_name, tgt_name, key, lock), drop self-pairs (src_name == tgt_name),
    and attach a count so the size is visible.
    """
    aggregated: dict[tuple[str, str, str, str], dict] = {}
    for ce in cross_edges:
        src_name = cluster_names.get(ce["from_cluster"], ce["from_cluster"])
        tgt_name = cluster_names.get(ce["to_cluster"], ce["to_cluster"])
        if src_name == tgt_name:
            continue
        bucket = aggregated.setdefault(
            (src_name, tgt_name, ce["key"], ce["lock"]),
            {"src_name": src_name, "tgt_name": tgt_name,
             "key": ce["key"], "lock": ce["lock"],
             "count": 0, "best_type": ce["type"]},
        )
        bucket["count"] += 1
        # Prefer HARD over PREDICTED for the displayed type
        if bucket["best_type"] != "HARD" and ce["type"] == "HARD":
            bucket["best_type"] = "HARD"
    return sorted(aggregated.values(),
                  key=lambda b: (-(1 if b["best_type"] == "HARD" else 0), -b["count"]))

_UNIT_PREVIEW_CAP = 5


def _architecture_glance(graph: dict, cross_edges: list[dict],
                          cluster_names: dict[str, str]) -> str:
    """Two-to-three sentence executive summary derived from the graph."""
    clusters = graph.get("clusters", [])
    cross_file = [c for c in clusters if c.get("is_cross_file")]
    sized = sorted(clusters, key=lambda c: -len(c.get("members", [])))

    if not clusters:
        return "_No clusters detected. Repo may be empty or scan parameters too strict._"

    # Deduplicate by name when picking "largest behavioral surfaces" — the
    # cluster list often fragments one component into several IDs that share
    # a name, and we don't want the same name showing up three times.
    largest_names: list[str] = []
    seen: set[str] = set()
    for c in sized:
        n = cluster_names.get(c["id"], c["id"])
        if n not in seen:
            largest_names.append(n)
            seen.add(n)
        if len(largest_names) >= 3:
            break

    parts: list[str] = []
    parts.append(
        f"This codebase fingerprints into **{len(clusters)} behavioral clusters** "
        f"({len(cross_file)} cross-file)."
    )
    if largest_names:
        parts.append(
            "Largest behavioral surfaces: "
            + ", ".join(f"`{n}`" for n in largest_names) + "."
        )

    aggregated = _aggregate_cross_edges(cross_edges, cluster_names)
    if aggregated:
        top_pairs: list[tuple[str, str]] = []
        seen_pair: set[tuple[str, str]] = set()
        for b in aggregated:
            pair = (b["src_name"], b["tgt_name"])
            if pair in seen_pair:
                continue
            seen_pair.add(pair)
            top_pairs.append(pair)
            if len(top_pairs) >= 3:
                break
        if top_pairs:
            formatted = ", ".join(f"`{a}` ↔ `{b}`" for a, b in top_pairs)
            parts.append(f"Notable cross-component coupling: {formatted}.")
    return " ".join(parts)


def _format_cluster_section(c: dict, name: str, role: str, seam_ids: set[str]) -> list[str]:
    """One cluster's markdown block. Caps unit list, drops internal jargon."""
    badges: list[str] = []
    if c.get("is_hard"):
        badges.append("HARD")
    if c.get("is_cross_file"):
        badges.append("CROSS-FILE")
    badge_str = "  `" + "` `".join(badges) + "`" if badges else ""

    members = c.get("members", [])
    files = c.get("files", [])
    files_display = ", ".join(f"`{f}`" for f in files[:6])
    if len(files) > 6:
        files_display += f", _and {len(files) - 6} more_"

    lines = [
        f"### {name}{badge_str}",
        "",
        f"**Role:** {role}",
        f"**Files** ({len(files)}): {files_display}",
        f"**Units:** {len(members)}",
    ]

    preview_count = min(len(members), _UNIT_PREVIEW_CAP)
    if preview_count:
        lines.append("")
        for m in members[:preview_count]:
            seam_tag = " ⚡ seam" if m in seam_ids else ""
            lines.append(f"- `{m}`{seam_tag}")
        if len(members) > preview_count:
            lines.append(f"- _…and {len(members) - preview_count} more_")

    tokens = c.get("dominant_tokens", [])
    if tokens:
        lines += [
            "",
            f"**Dominant tokens:** {', '.join(t.split('.')[-1] for t in tokens[:5])}",
        ]
    lines.append("")
    return lines


# ── Heuristic markdown generator ─────────────────────────────────────────────

def _build_agents_md(graph: dict, root: str, cross_edges: list[dict], cluster_names: dict[str, str]) -> str:
    stats = graph.get("stats", {})
    clusters = graph.get("clusters", [])
    seam_ids = {u["id"] for u in graph.get("units", []) if u.get("is_seam")}
    forecasts = graph.get("resurrection_forecasts", [])
    sep = stats.get("sep", {})

    # Sort: cross-file first, then by member count desc, then by id for stability
    sorted_clusters = sorted(
        clusters,
        key=lambda c: (
            0 if c.get("is_cross_file") else 1,
            -len(c.get("members", [])),
            c.get("id", ""),
        ),
    )

    # Split into production vs test surfaces so the marketing-facing sections lead
    production: list[dict] = []
    test_surfaces: list[dict] = []
    for c in sorted_clusters:
        if _is_test_cluster(c, cluster_names.get(c["id"], "")):
            test_surfaces.append(c)
        else:
            production.append(c)

    lines: list[str] = []

    lines += [
        f"# BGI Architecture — `{root}`",
        "",
        "<!-- Generated by BGI Architecture Narrator (Position 3) -->",
        "<!-- Consume this file to understand system structure before editing code. -->",
        "",
        "## Architecture at a glance",
        "",
        _architecture_glance(graph, cross_edges, cluster_names),
        "",
        "## Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Code units fingerprinted | {stats.get('units', 0)} |",
        f"| Edges detected | {stats.get('edges', 0)} (HARD: {stats.get('hard', 0)}, PREDICTED: {stats.get('predicted', 0)}) |",
        f"| Clusters | {stats.get('clusters', 0)} ({stats.get('hard_clusters', 0)} hard) |",
        f"| Seam units | {stats.get('seam_units', 0)} |",
        f"| Suspended (unresolved) | {sep.get('pending', 0)} |",
        f"| Intentional boundaries | {sep.get('intentional_boundary', 0)} |",
        "",
    ]

    # Cross-cluster relationships — surfaced early since they describe the architecture
    aggregated_cross = _aggregate_cross_edges(cross_edges, cluster_names)
    if aggregated_cross:
        lines += ["## Cross-cluster coupling", ""]
        for b in aggregated_cross[:30]:
            key = b["key"].split(".")[-1]
            lock = b["lock"].split(".")[-1]
            count_suffix = f" ×{b['count']}" if b["count"] > 1 else ""
            lines.append(
                f"- `{b['src_name']}` → `{b['tgt_name']}` via "
                f"**{key}↔{lock}** [{b['best_type']}]{count_suffix}"
            )
        if len(aggregated_cross) > 30:
            lines.append(f"- _…and {len(aggregated_cross) - 30} more cross-cluster pairs_")
        lines += [""]

    # Production clusters
    lines += ["## Clusters", ""]
    if production:
        for c in production:
            cid = c["id"]
            name = cluster_names.get(cid, cid)
            role = _infer_role(c.get("dominant_tokens", []))
            lines += _format_cluster_section(c, name, role, seam_ids)
    else:
        lines += ["_No production clusters above the size threshold._", ""]

    # Test surfaces — separate section so they don't dominate
    if test_surfaces:
        lines += [
            "## Test surfaces",
            "",
            f"_{len(test_surfaces)} test/benchmark cluster(s); summarized below._",
            "",
        ]
        for c in test_surfaces[:10]:
            cid = c["id"]
            name = cluster_names.get(cid, cid)
            files = c.get("files", [])
            files_display = ", ".join(f"`{f}`" for f in files[:3])
            if len(files) > 3:
                files_display += f", _and {len(files) - 3} more_"
            lines.append(
                f"- **{name}** — {len(c.get('members', []))} units in {files_display}"
            )
        if len(test_surfaces) > 10:
            lines.append(f"- _…and {len(test_surfaces) - 10} more test clusters_")
        lines += [""]

    # Seam units
    if seam_ids:
        lines += ["## Seam Units", ""]
        lines += ["These units sit at cluster boundaries — edit with care.", ""]
        for uid in sorted(seam_ids):
            lines.append(f"- `{uid}`")
        lines += [""]

    # Resurrection forecasts
    if forecasts:
        lines += ["## Unresolved References (Resurrection Forecasts)", ""]
        lines += [
            "These outward tokens have no matching lock in the current codebase.",
            "Either the provider module is not yet scanned, or this is an intentional boundary.",
            "",
        ]
        for f in forecasts:
            tok = f["token"].split(".")[-1]
            lock = f["predicted_lock_token"].split(".")[-1]
            boundary_tag = " 🚧 **INTENTIONAL BOUNDARY**" if f["is_boundary"] else ""
            lines += [
                f"### {tok} → {lock} (predicted){boundary_tag}",
                "",
                f"**Confidence:** {f['confidence']:.2f}  **Source:** {f['source']}",
                f"**Predicted module:** `{f['predicted_module']}`",
                f"**Reasoning:** {f['reasoning']}",
                "",
                "**Affected units:**",
            ]
            for uid in f["member_ids"]:
                lines.append(f"- `{uid}`")
            lines += [""]

    # Stats footer
    lines += [
        "---",
        "",
        "_This file was auto-generated by BGI. Do not edit manually._",
        "_Re-run `bgi scan` to refresh._",
    ]

    return "\n".join(lines) + "\n"


# ── Narrator ──────────────────────────────────────────────────────────────────

@dataclass
class NarratorResult:
    agents_md: str
    cluster_names: dict[str, str]   # cluster_id → human name
    cross_edges: list[dict]
    ai_enhanced: bool


class ArchitectureNarrator:
    """
    AI Position 3 — Architecture Narrator.

    Uses an OpenAI-compatible client (DeepSeek by default) to enrich
    heuristic cluster names with real domain context.

    Usage:
        from bgi.gate1.ai_fallback import make_deepseek_client
        narrator = ArchitectureNarrator(
            enabled=True,
            client=make_deepseek_client("sk-..."),
        )
        result = narrator.narrate(graph, root="my_service")
        Path("agents.md").write_text(result.agents_md)
    """

    def __init__(
        self,
        enabled: bool = False,
        client=None,
        model: str = "deepseek-v4-flash",
    ):
        self.enabled = enabled
        self.client = client
        self.model = model

    def narrate(self, graph: dict, root: str = ".") -> NarratorResult:
        clusters = graph.get("clusters", [])
        edges = graph.get("edges", [])
        units = graph.get("units", [])

        # Build unit→cluster map
        unit_to_cluster = {u["id"]: u.get("cluster") for u in units if u.get("cluster")}

        # Heuristic cluster names
        cluster_names = {c["id"]: _cluster_name(c) for c in clusters}

        # Cross-cluster edges
        cross_edges = _cross_cluster_edges(edges, unit_to_cluster)

        # Heuristic markdown
        md = _build_agents_md(graph, root, cross_edges, cluster_names)

        ai_enhanced = False
        if self.enabled and self.client is not None:
            try:
                md, cluster_names = self._ai_enhance(graph, md, cluster_names, root)
                ai_enhanced = True
            except Exception as exc:
                md += f"\n<!-- AI enhancement failed: {exc} -->\n"

        return NarratorResult(
            agents_md=md,
            cluster_names=cluster_names,
            cross_edges=cross_edges,
            ai_enhanced=ai_enhanced,
        )

    def _ai_enhance(
        self,
        graph: dict,
        heuristic_md: str,
        cluster_names: dict[str, str],
        root: str,
    ) -> tuple[str, dict[str, str]]:
        """
        Send heuristic agents.md to claude-haiku for enrichment.
        Returns (enhanced_md, updated_cluster_names).
        """
        clusters = graph.get("clusters", [])

        cluster_summary = "\n".join(
            f"- id={c['id']} name={cluster_names[c['id']]} "
            f"role={_infer_role(c['dominant_tokens'])} "
            f"tokens={c['dominant_tokens'][:4]} "
            f"members={c['members'][:3]}"
            for c in clusters
        )

        prompt = (
            "You are reviewing an auto-generated architecture document for a codebase. "
            "Below is the heuristic-generated agents.md and cluster metadata. "
            "Your tasks:\n"
            "1. Suggest better cluster names (short, domain-specific noun phrases like 'Auth Gateway', 'Payment Engine')\n"
            "2. Identify any architectural concerns (missing boundaries, suspicious cross-cluster edges, etc.)\n"
            "3. Return a JSON object with:\n"
            '   {"cluster_names": {"<cluster_id>": "<better_name>", ...}, '
            '"concerns": ["<concern1>", ...]}\n\n'
            f"Cluster metadata:\n{cluster_summary}\n\n"
            f"Current agents.md (truncated):\n{heuristic_md[:2000]}\n\n"
            "Reply with ONLY the JSON object. Keep concerns brief (max 3 items, max 100 chars each)."
        )

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        # Extract first complete JSON object in case there's preamble text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in response: {raw[:100]!r}")
        raw = match.group(0)

        import json
        parsed = json.loads(raw)

        # Merge AI names into cluster_names
        for cid, name in parsed.get("cluster_names", {}).items():
            if cid in cluster_names and name.strip():
                cluster_names[cid] = name.strip()

        # Rebuild md with updated names + append concerns
        md = _build_agents_md(graph, root,
                               _cross_cluster_edges(graph.get("edges", []),
                                                    {u["id"]: u.get("cluster")
                                                     for u in graph.get("units", [])
                                                     if u.get("cluster")}),
                               cluster_names)

        concerns = parsed.get("concerns", [])
        if concerns:
            concern_block = "\n## Architectural Concerns (AI)\n\n" + "\n".join(f"- {c}" for c in concerns) + "\n"
            md = md.rstrip("\n") + "\n" + concern_block

        return md, cluster_names
