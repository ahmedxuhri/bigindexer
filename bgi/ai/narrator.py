"""
AI Position 3 — Architecture Narrator.

Consumes the fully assembled BGI graph and produces two outputs:
  1. agents.md  — structured markdown for AI agent consumption
  2. A plain-text architecture summary for humans (logged to stdout or file)

Design:
  - Heuristic pass always runs: produces a deterministic, rule-based agents.md with no API cost.
  - AI pass (when enabled): sends heuristic draft + graph context to an LLM (DeepSeek by default,
    any OpenAI-compatible provider works) to enrich cluster names, add architectural intent,
    and flag notable relationships.
  - Output is written to <output_dir>/agents.md alongside the JSON graph.

agents.md format:
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
    Path("agents.md").write_text(result.agents_md)
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
    token_set = set(dominant_tokens)
    for required, role in _ROLE_RULES:
        if required.issubset(token_set):
            return role
    return "General Logic"


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


# ── Heuristic markdown generator ─────────────────────────────────────────────

def _build_agents_md(graph: dict, root: str, cross_edges: list[dict], cluster_names: dict[str, str]) -> str:
    stats = graph.get("stats", {})
    clusters = graph.get("clusters", [])
    seam_ids = {u["id"] for u in graph.get("units", []) if u.get("is_seam")}
    forecasts = graph.get("resurrection_forecasts", [])
    sep = stats.get("sep", {})

    lines: list[str] = []

    lines += [
        f"# BGI Architecture — `{root}`",
        "",
        "<!-- Generated by BGI Architecture Narrator (Position 3) -->",
        "<!-- Consume this file to understand system structure before editing code. -->",
        "",
        "## Overview",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Code units fingerprinted | {stats.get('units', 0)} |",
        f"| Edges detected | {stats.get('edges', 0)} (HARD: {stats.get('hard', 0)}, PREDICTED: {stats.get('predicted', 0)}) |",
        f"| Clusters | {stats.get('clusters', 0)} ({stats.get('hard_clusters', 0)} hard) |",
        f"| Seam units | {stats.get('seam_units', 0)} |",
        f"| Suspended (unresolved) | {sep.get('pending', 0)} |",
        f"| Intentional boundaries | {sep.get('intentional_boundary', 0)} |",
        "",
    ]

    # Clusters
    lines += ["## Clusters", ""]
    for c in clusters:
        cid = c["id"]
        name = cluster_names.get(cid, cid)
        role = _infer_role(c["dominant_tokens"])
        badges = []
        if c.get("is_hard"):
            badges.append("HARD")
        if c.get("is_cross_file"):
            badges.append("CROSS-FILE")
        badge_str = "  `" + "` `".join(badges) + "`" if badges else ""

        lines += [
            f"### {name}{badge_str}",
            "",
            f"**Role:** {role}",
            f"**Probability:** {c['probability']:.2f}  **Radar range:** {c['radar_range']} lines",
            f"**Files:** {', '.join(f'`{f}`' for f in c['files'])}",
            "",
            "**Units:**",
        ]
        for m in c["members"]:
            seam_tag = " ⚡ seam" if m in seam_ids else ""
            lines.append(f"- `{m}`{seam_tag}")

        lines += ["", f"**Dominant tokens:** {', '.join(t.split('.')[1] for t in c['dominant_tokens'][:5])}", ""]

    # Cross-cluster relationships
    if cross_edges:
        lines += ["## Cross-Cluster Relationships", ""]
        for ce in cross_edges:
            src_name = cluster_names.get(ce["from_cluster"], ce["from_cluster"])
            tgt_name = cluster_names.get(ce["to_cluster"], ce["to_cluster"])
            key = ce["key"].split(".")[-1]
            lock = ce["lock"].split(".")[-1]
            lines.append(f"- `{src_name}` → `{tgt_name}` via **{key}↔{lock}** [{ce['type']}]")
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
        f"_Re-run `bgi scan` to refresh._",
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
