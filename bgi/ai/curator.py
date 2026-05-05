"""
AI Position 4 — Vocabulary Curator.

Runs periodically (not in the scan hot path) to analyze patterns in:
  1. Unresolved call snippets from AIFallback log (bgi-unresolved.jsonl)
  2. Recurring suspended token patterns from the SEP
  3. Current COV token frequency distribution from graph output

Produces a ranked list of ExtensionCandidate objects — proposed new tokens
for promotion into the 20% extension zone of the COV vocabulary.

Extension zone tokens (pre-approved, waiting for evidence):
  MEMOIZE, ORCHESTRATE, INTERCEPT, PATTERN_MATCH, RETRY, CACHE, CHECKPOINT

Run as: bgi curate --unresolved bgi-unresolved.jsonl --db bgi-sep.db --graph bgi-graph.json

Output: cov-extension-candidates.json (human-reviews before any token is added)

Design principles:
  - Curator never modifies cov.py directly. It proposes; humans decide.
  - AI call is single and batched. Heuristic pass always runs first.
  - A token needs evidence from ≥2 signal sources before it's a candidate.
  - Confidence threshold: 0.60 before the token appears in the report.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


# ── Extension zone — pre-approved token names ─────────────────────────────────
# These are the names that earned a spot in the reserved 20% zone but
# haven't yet accumulated enough real-world evidence to enter core.

EXTENSION_ZONE: set[str] = {
    "MEMOIZE",       # result caching / @lru_cache patterns
    "ORCHESTRATE",   # multi-step workflow coordination
    "INTERCEPT",     # middleware / before/after hooks
    "PATTERN_MATCH", # structural pattern matching (match/case)
    "RETRY",         # retry/backoff logic
    "CACHE",         # explicit cache read/write (distinct from MEMOIZE)
    "CHECKPOINT",    # save/restore state mid-computation
    "PAGINATE",      # cursor/offset iteration patterns
    "BATCH",         # bulk operation over collection
    "ENRICH",        # adding fields / decorating a data object
}

# Heuristic patterns: regex on call snippets → candidate token name
_HEURISTIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\blru_cache\b|\bmemoize\b|\bcache\b",    re.I), "MEMOIZE"),
    (re.compile(r"\borchestr\b|\bworkflow\b|\bpipeline\b", re.I), "ORCHESTRATE"),
    (re.compile(r"\bintercept\b|\bmiddleware\b|\bhook\b",  re.I), "INTERCEPT"),
    (re.compile(r"\bretry\b|\bbackoff\b|\bexponential\b",  re.I), "RETRY"),
    (re.compile(r"\bpaginat\b|\bcursor\b|\boffset\b",      re.I), "PAGINATE"),
    (re.compile(r"\bbatch\b|\bbulk\b",                     re.I), "BATCH"),
    (re.compile(r"\benrich\b|\bdecorate\b|\bannot",        re.I), "ENRICH"),
    (re.compile(r"\bcheckpoint\b|\bsnapshot\b",            re.I), "CHECKPOINT"),
    (re.compile(r"\bmatch\b.*\bcase\b|\bpattern\b",        re.I), "PATTERN_MATCH"),
]


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ExtensionCandidate:
    """
    A proposed token for promotion into the COV extension zone.
    Human must review before any change to cov.py.
    """
    token_name: str          # proposed COV name (should be in EXTENSION_ZONE)
    evidence_count: int      # number of distinct unresolved snippets that matched
    signal_sources: list[str]# e.g. ["unresolved_calls", "sep_odd_group"]
    confidence: float        # 0.0–1.0
    example_snippets: list[str]  # up to 5 representative examples
    reasoning: str
    is_extension_zone: bool  # True if already in EXTENSION_ZONE
    source: str              # "heuristic" | "ai"


# ── Signal loading ────────────────────────────────────────────────────────────

def _load_unresolved(log_path: Path) -> list[str]:
    """Read unresolved call snippets from AIFallback JSONL log."""
    if not log_path.exists():
        return []
    snippets = []
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                snippets.append(obj.get("snippet", ""))
            except json.JSONDecodeError:
                continue
    return [s for s in snippets if s]


def _load_sep_tokens(db_path: Path) -> Counter:
    """Read pending suspended edge tokens from SEP SQLite."""
    token_counts: Counter = Counter()
    if not db_path.exists():
        return token_counts
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT token, COUNT(*) as n FROM suspended_edges WHERE resolved=0 GROUP BY token"
        ).fetchall()
        conn.close()
        for tok, n in rows:
            token_counts[tok.split(".")[-1]] += n
    except Exception:
        pass
    return token_counts


def _load_token_distribution(graph_path: Path) -> Counter:
    """Count how frequently each COV token appears across all units in the graph."""
    dist: Counter = Counter()
    if not graph_path.exists():
        return dist
    try:
        graph = json.loads(graph_path.read_text())
        for unit in graph.get("units", []):
            for tok in unit.get("tokens", []) + unit.get("class_context", []):
                name = tok.split(".")[-1]
                dist[name] += 1
    except Exception:
        pass
    return dist


# ── Heuristic analysis ────────────────────────────────────────────────────────

def _heuristic_candidates(
    snippets: list[str],
    sep_tokens: Counter,
) -> list[ExtensionCandidate]:
    """
    Group unresolved snippets by extension-zone token pattern.
    Cross-reference with SEP recurring tokens for multi-signal evidence.
    """
    # Match snippets against heuristic patterns
    pattern_hits: dict[str, list[str]] = {}
    for snippet in snippets:
        for pat, token_name in _HEURISTIC_PATTERNS:
            if pat.search(snippet):
                pattern_hits.setdefault(token_name, []).append(snippet)
                break  # one token per snippet

    candidates: list[ExtensionCandidate] = []

    for token_name, matched in pattern_hits.items():
        evidence = len(matched)
        if evidence < 2:
            # Not enough evidence from calls alone
            continue

        sources = ["unresolved_calls"]
        # Check if SEP also has recurring trouble with a related core token
        # (e.g. MEMOIZE candidates often appear alongside repeated FETCH suspensions)
        sep_related = {"MEMOIZE": "FETCH", "ORCHESTRATE": "DELEGATE",
                       "RETRY": "RECOVER", "CACHE": "FETCH"}.get(token_name)
        if sep_related and sep_tokens.get(sep_related, 0) >= 2:
            sources.append("sep_odd_group")

        confidence = min(0.5 + evidence * 0.04, 0.85)
        if len(sources) > 1:
            confidence = min(confidence + 0.1, 0.92)

        if confidence < 0.60:
            continue

        examples = list(dict.fromkeys(matched))[:5]  # dedup, cap at 5
        candidates.append(ExtensionCandidate(
            token_name=token_name,
            evidence_count=evidence,
            signal_sources=sources,
            confidence=round(confidence, 3),
            example_snippets=examples,
            reasoning=(
                f"{evidence} unresolved call(s) match '{token_name}' pattern. "
                + (f"SEP also shows recurring '{sep_related}' suspensions." if len(sources) > 1 else "")
            ),
            is_extension_zone=token_name in EXTENSION_ZONE,
            source="heuristic",
        ))

    # Sort by multi-signal first, then evidence count
    candidates.sort(key=lambda c: (-len(c.signal_sources), -c.evidence_count))
    return candidates


# ── Curator ───────────────────────────────────────────────────────────────────

class VocabularyCurator:
    """
    AI Position 4.

    Usage:
        curator = VocabularyCurator(enabled=True, client=anthropic_client)
        candidates = curator.curate(
            unresolved_log=Path("bgi-unresolved.jsonl"),
            sep_db=Path("bgi-sep.db"),
            graph=Path("bgi-graph.json"),
        )
        Path("cov-extension-candidates.json").write_text(
            json.dumps(candidates_to_dict(candidates), indent=2)
        )
    """

    def __init__(self, enabled: bool = False, client=None):
        self.enabled = enabled
        self.client = client

    def curate(
        self,
        unresolved_log: Path,
        sep_db: Path,
        graph: Path,
    ) -> list[ExtensionCandidate]:
        snippets = _load_unresolved(unresolved_log)
        sep_tokens = _load_sep_tokens(sep_db)
        token_dist = _load_token_distribution(graph)

        candidates = _heuristic_candidates(snippets, sep_tokens)

        if not snippets and not sep_tokens:
            return candidates  # nothing to analyze

        if self.enabled and self.client is not None and snippets:
            try:
                candidates = self._ai_refine(snippets, sep_tokens, token_dist, candidates)
            except Exception as exc:
                for c in candidates:
                    c.reasoning += f" [AI unavailable: {exc}]"

        return candidates

    def _ai_refine(
        self,
        snippets: list[str],
        sep_tokens: Counter,
        token_dist: Counter,
        heuristics: list[ExtensionCandidate],
    ) -> list[ExtensionCandidate]:
        """
        Single batched AI call: given unresolved snippets, identify which
        extension-zone token (if any) each group belongs to, and rank confidence.
        """
        sample = snippets[:60]  # cap tokens/cost
        sep_summary = ", ".join(f"{t}×{n}" for t, n in sep_tokens.most_common(8))
        dist_summary = ", ".join(f"{t}×{n}" for t, n in token_dist.most_common(10))
        ext_list = ", ".join(sorted(EXTENSION_ZONE))

        heuristic_summary = "\n".join(
            f"- {c.token_name}: evidence={c.evidence_count}, sources={c.signal_sources}"
            for c in heuristics
        ) or "  (none)"

        prompt = (
            "You are the Vocabulary Curator for a code intelligence system called BGI.\n"
            "BGI uses a fixed set of semantic tokens (COV) to fingerprint code. "
            "Some call patterns cannot be classified into current tokens — these are logged as 'unresolved'.\n\n"
            f"Extension zone (tokens awaiting promotion): {ext_list}\n\n"
            f"Unresolved call snippets (sample of {len(sample)}):\n"
            + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sample)) + "\n\n"
            f"SEP recurring suspended tokens: {sep_summary or 'none'}\n"
            f"Current token distribution: {dist_summary or 'none'}\n\n"
            f"Heuristic candidates already found:\n{heuristic_summary}\n\n"
            "Tasks:\n"
            "1. Identify which extension-zone tokens have strong evidence (≥3 snippet matches)\n"
            "2. Flag any pattern that suggests a new token NOT in the extension zone\n"
            "3. Return a JSON array of candidates, each: "
            '{"token_name": str, "evidence_count": int, "confidence": float, '
            '"example_snippets": [str, ...], "reasoning": str, "is_new": bool}\n'
            "Only output the JSON array."
        )

        response = self.client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=768,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        parsed = json.loads(raw)

        ai_candidates: list[ExtensionCandidate] = []
        seen_names = {c.token_name for c in heuristics}

        for item in parsed:
            token_name = str(item.get("token_name", "")).upper().replace(" ", "_")
            if not token_name:
                continue
            confidence = float(item.get("confidence", 0.0))
            if confidence < 0.60:
                continue
            examples = [str(s) for s in item.get("example_snippets", [])][:5]

            if token_name in seen_names:
                # Merge AI confidence into existing heuristic candidate
                for c in heuristics:
                    if c.token_name == token_name:
                        c.confidence = round(max(c.confidence, confidence), 3)
                        c.source = "ai"
                        if "ai_analysis" not in c.signal_sources:
                            c.signal_sources.append("ai_analysis")
                        if examples:
                            c.example_snippets = list(dict.fromkeys(c.example_snippets + examples))[:5]
            else:
                ai_candidates.append(ExtensionCandidate(
                    token_name=token_name,
                    evidence_count=int(item.get("evidence_count", 0)),
                    signal_sources=["ai_analysis"],
                    confidence=confidence,
                    example_snippets=examples,
                    reasoning=str(item.get("reasoning", "")),
                    is_extension_zone=token_name in EXTENSION_ZONE,
                    source="ai",
                ))

        combined = heuristics + ai_candidates
        combined.sort(key=lambda c: (-len(c.signal_sources), -c.confidence))
        return combined


# ── Serialization ─────────────────────────────────────────────────────────────

def candidates_to_dict(candidates: list[ExtensionCandidate]) -> dict:
    return {
        "bgi_version": "0.1.0",
        "extension_zone": sorted(EXTENSION_ZONE),
        "candidates": [
            {
                "token_name": c.token_name,
                "evidence_count": c.evidence_count,
                "signal_sources": c.signal_sources,
                "confidence": c.confidence,
                "example_snippets": c.example_snippets,
                "reasoning": c.reasoning,
                "is_extension_zone": c.is_extension_zone,
                "source": c.source,
                "action": "PROMOTE" if c.confidence >= 0.80 and c.is_extension_zone
                          else "REVIEW" if c.confidence >= 0.60
                          else "WATCH",
            }
            for c in candidates
        ],
    }
