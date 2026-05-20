"""
BGI Graph Diff — detect architectural changes between two scan snapshots.

Compares two sets of COVFingerprints (from two git SHAs, branches, or directories)
and reports:
  - Added/removed/changed units (fingerprint-level diff)
  - Added/removed routes
  - Token drift per file (tokens gained/lost)
  - Language composition changes

Usage:
    from bgi.delta.diff import diff_scans, format_diff_report
    result = diff_scans(fps_before, fps_after)
    print(format_diff_report(result))
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class UnitDiff:
    unit_id: str
    status: str           # "added" | "removed" | "changed"
    before: COVFingerprint | None
    after:  COVFingerprint | None

    @property
    def tokens_added(self) -> list[str]:
        if not self.after or not self.before:
            return [t.value for t in (self.after or self.before).tokens]
        b = set(self.before.tokens)
        return [t.value for t in self.after.tokens if t not in b]

    @property
    def tokens_removed(self) -> list[str]:
        if not self.before or not self.after:
            return []
        a = set(self.after.tokens)
        return [t.value for t in self.before.tokens if t not in a]


@dataclass
class RouteDiff:
    unit_id: str
    status: str           # "added" | "removed"
    language: str
    file: str


@dataclass
class ScanDiff:
    added_units:   list[UnitDiff]   = field(default_factory=list)
    removed_units: list[UnitDiff]   = field(default_factory=list)
    changed_units: list[UnitDiff]   = field(default_factory=list)
    route_diffs:   list[RouteDiff]  = field(default_factory=list)
    # language → (before_count, after_count)
    lang_counts:   dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def added_routes(self) -> list[RouteDiff]:
        return [r for r in self.route_diffs if r.status == "added"]

    @property
    def removed_routes(self) -> list[RouteDiff]:
        return [r for r in self.route_diffs if r.status == "removed"]

    @property
    def is_clean(self) -> bool:
        return not (self.added_units or self.removed_units or self.changed_units)


# ── Core diff logic ───────────────────────────────────────────────────────────

def diff_scans(
    before: list[COVFingerprint],
    after:  list[COVFingerprint],
) -> ScanDiff:
    """
    Compare two lists of COVFingerprints and return a ScanDiff.

    Units are matched by unit_id. A unit is "changed" if its token set differs
    (ignoring confidence/source changes — only semantic token changes matter).
    """
    before_map: dict[str, COVFingerprint] = {fp.unit_id: fp for fp in before}
    after_map:  dict[str, COVFingerprint] = {fp.unit_id: fp for fp in after}

    diff = ScanDiff()

    all_ids = set(before_map) | set(after_map)
    for uid in sorted(all_ids):
        b = before_map.get(uid)
        a = after_map.get(uid)

        if b is None:
            diff.added_units.append(UnitDiff(uid, "added", None, a))
        elif a is None:
            diff.removed_units.append(UnitDiff(uid, "removed", b, None))
        elif set(b.tokens) != set(a.tokens):
            diff.changed_units.append(UnitDiff(uid, "changed", b, a))

    # Route diff
    before_routes = {fp.unit_id for fp in before if COV.ROUTE in fp.tokens}
    after_routes  = {fp.unit_id for fp in after  if COV.ROUTE in fp.tokens}

    for uid in sorted(after_routes - before_routes):
        fp = after_map[uid]
        diff.route_diffs.append(RouteDiff(uid, "added", fp.language, uid.split("::")[0]))
    for uid in sorted(before_routes - after_routes):
        fp = before_map[uid]
        diff.route_diffs.append(RouteDiff(uid, "removed", fp.language, uid.split("::")[0]))

    # Language composition
    def _lang_counts(fps: list[COVFingerprint]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for fp in fps:
            counts[fp.language] = counts.get(fp.language, 0) + 1
        return counts

    bc = _lang_counts(before)
    ac = _lang_counts(after)
    for lang in sorted(set(bc) | set(ac)):
        diff.lang_counts[lang] = (bc.get(lang, 0), ac.get(lang, 0))

    return diff


# ── Formatting ────────────────────────────────────────────────────────────────

def format_diff_report(diff: ScanDiff, verbose: bool = False) -> str:
    lines = []

    # Summary
    lines.append("── BGI Diff Report ───────────────────────────────")
    lines.append(f"  Added units:   {len(diff.added_units)}")
    lines.append(f"  Removed units: {len(diff.removed_units)}")
    lines.append(f"  Changed units: {len(diff.changed_units)}")
    lines.append(f"  Route changes: +{len(diff.added_routes)} / -{len(diff.removed_routes)}")

    # Language composition
    if diff.lang_counts:
        lines.append("\n── Language composition ──────────────────────────")
        for lang, (b, a) in diff.lang_counts.items():
            delta = a - b
            sign  = "+" if delta >= 0 else ""
            lines.append(f"  {lang:12s}  {b:4d} → {a:4d}  ({sign}{delta})")

    # Route changes
    if diff.route_diffs:
        lines.append("\n── Route changes ─────────────────────────────────")
        for r in diff.route_diffs:
            prefix = "  +" if r.status == "added" else "  -"
            lines.append(f"{prefix} [{r.language}] {r.unit_id}")

    # Unit details (verbose or just first N)
    if verbose or diff.added_units:
        lines.append("\n── Added units ───────────────────────────────────")
        for u in diff.added_units[:50]:
            toks = ", ".join(t.value for t in (u.after or u.before).tokens)
            lines.append(f"  + {u.unit_id}  [{toks}]")
        if len(diff.added_units) > 50:
            lines.append(f"  … and {len(diff.added_units) - 50} more")

    if verbose or diff.removed_units:
        lines.append("\n── Removed units ─────────────────────────────────")
        for u in diff.removed_units[:50]:
            toks = ", ".join(t.value for t in (u.before or u.after).tokens)
            lines.append(f"  - {u.unit_id}  [{toks}]")
        if len(diff.removed_units) > 50:
            lines.append(f"  … and {len(diff.removed_units) - 50} more")

    if verbose or diff.changed_units:
        lines.append("\n── Changed units (token drift) ───────────────────")
        for u in diff.changed_units[:50]:
            added   = u.tokens_added
            removed = u.tokens_removed
            parts = []
            if added:   parts.append(f"+{','.join(added)}")
            if removed: parts.append(f"-{','.join(removed)}")
            lines.append(f"  ~ {u.unit_id}  {' '.join(parts)}")
        if len(diff.changed_units) > 50:
            lines.append(f"  … and {len(diff.changed_units) - 50} more")

    return "\n".join(lines)


def serialize_diff(diff: ScanDiff) -> dict:
    """Serialize ScanDiff to a JSON-compatible dict."""
    def _fp_tokens(fp: COVFingerprint | None) -> list[str]:
        return [t.value for t in fp.tokens] if fp else []

    return {
        "summary": {
            "added_units":    len(diff.added_units),
            "removed_units":  len(diff.removed_units),
            "changed_units":  len(diff.changed_units),
            "added_routes":   len(diff.added_routes),
            "removed_routes": len(diff.removed_routes),
        },
        "lang_counts": {
            lang: {"before": b, "after": a}
            for lang, (b, a) in diff.lang_counts.items()
        },
        "added_units": [
            {"unit_id": u.unit_id, "tokens": _fp_tokens(u.after)}
            for u in diff.added_units
        ],
        "removed_units": [
            {"unit_id": u.unit_id, "tokens": _fp_tokens(u.before)}
            for u in diff.removed_units
        ],
        "changed_units": [
            {
                "unit_id":        u.unit_id,
                "tokens_before":  _fp_tokens(u.before),
                "tokens_after":   _fp_tokens(u.after),
                "tokens_added":   u.tokens_added,
                "tokens_removed": u.tokens_removed,
            }
            for u in diff.changed_units
        ],
        "route_diffs": [
            {"unit_id": r.unit_id, "status": r.status, "language": r.language, "file": r.file}
            for r in diff.route_diffs
        ],
    }


# ── Markdown drift narration ─────────────────────────────────────────────────

# Drift verdict thresholds — keep these conservative, easy to defend.
_DRIFT_STABLE_THRESHOLD = 5      # changed_units below this = stable
_DRIFT_RESTRUCTURE_THRESHOLD = 200  # above this = restructure-class change


def _drift_verdict(diff: ScanDiff) -> tuple[str, str]:
    """One-line architectural verdict + one-line explanation."""
    total_units_after = sum(a for _, a in diff.lang_counts.values())
    total_changes = (len(diff.added_units) + len(diff.removed_units)
                     + len(diff.changed_units))

    if total_changes == 0:
        return ("Stable", "No fingerprint-level changes between the two scans.")
    if total_changes < _DRIFT_STABLE_THRESHOLD:
        return ("Stable",
                f"{total_changes} unit-level change(s); architecture intent unchanged.")
    if total_changes < _DRIFT_RESTRUCTURE_THRESHOLD:
        return ("Drifting",
                f"{total_changes} unit-level changes "
                f"({len(diff.added_units)} added, {len(diff.removed_units)} removed, "
                f"{len(diff.changed_units)} re-tokenized).")
    pct = (100 * total_changes / total_units_after) if total_units_after else 0
    return ("Restructured",
            f"{total_changes} unit-level changes ({pct:.0f}% of post-scan units). "
            f"Likely a refactor pass or a feature merge.")


def _aggregate_token_drift(diff: ScanDiff) -> dict[str, tuple[int, int]]:
    """Repo-wide token emission deltas.

    Returns {token: (gained, lost)} aggregated across added/removed/changed
    units. Useful as architectural signal: AUTHENTICATE rising = new auth
    surface; PERSIST falling = data layer being abstracted; etc.
    """
    gained: dict[str, int] = {}
    lost: dict[str, int] = {}
    for u in diff.added_units:
        for t in (u.after.tokens if u.after else ()):
            gained[t.value] = gained.get(t.value, 0) + 1
    for u in diff.removed_units:
        for t in (u.before.tokens if u.before else ()):
            lost[t.value] = lost.get(t.value, 0) + 1
    for u in diff.changed_units:
        for t in u.tokens_added:
            gained[t] = gained.get(t, 0) + 1
        for t in u.tokens_removed:
            lost[t] = lost.get(t, 0) + 1
    keys = set(gained) | set(lost)
    return {k: (gained.get(k, 0), lost.get(k, 0)) for k in keys}


def _file_churn(diff: ScanDiff) -> dict[str, int]:
    """Per-file change count: added + removed + changed units."""
    churn: dict[str, int] = {}
    for u in diff.added_units + diff.removed_units + diff.changed_units:
        f = u.unit_id.split("::", 1)[0]
        churn[f] = churn.get(f, 0) + 1
    return churn


def format_diff_markdown(diff: ScanDiff,
                          before_label: str = "before",
                          after_label: str = "after") -> str:
    """Architectural drift narration in markdown.

    Designed as a companion to bigindexer.md: same readability discipline
    (executive summary first, raw lists capped, internal jargon stripped).
    Suitable for PR comments, drift dashboards, or pasting into review docs.
    """
    verdict, explanation = _drift_verdict(diff)
    token_drift = _aggregate_token_drift(diff)
    churn = _file_churn(diff)

    lines: list[str] = [
        f"# BGI Architecture Drift — `{before_label}` → `{after_label}`",
        "",
        "<!-- Generated by `bgi diff --report`. -->",
        "",
        "## Verdict",
        "",
        f"**{verdict}.** {explanation}",
        "",
        "## Summary",
        "",
        "| Change | Count |",
        "|--------|------:|",
        f"| Added units | {len(diff.added_units)} |",
        f"| Removed units | {len(diff.removed_units)} |",
        f"| Re-tokenized units | {len(diff.changed_units)} |",
        f"| Routes added | {len(diff.added_routes)} |",
        f"| Routes removed | {len(diff.removed_routes)} |",
        "",
    ]

    # Architectural surface changes — routes are the most visible kind
    if diff.route_diffs:
        lines += [
            "## Architectural surface changes",
            "",
            "Routes are public-facing entry points; additions and removals "
            "indicate real API-surface drift.",
            "",
        ]
        added_routes = diff.added_routes
        removed_routes = diff.removed_routes
        if added_routes:
            lines.append(f"**Added ({len(added_routes)}):**")
            lines.append("")
            for r in added_routes[:15]:
                lines.append(f"- `+` `{r.unit_id}` _({r.language})_")
            if len(added_routes) > 15:
                lines.append(f"- _…and {len(added_routes) - 15} more_")
            lines.append("")
        if removed_routes:
            lines.append(f"**Removed ({len(removed_routes)}):**")
            lines.append("")
            for r in removed_routes[:15]:
                lines.append(f"- `-` `{r.unit_id}` _({r.language})_")
            if len(removed_routes) > 15:
                lines.append(f"- _…and {len(removed_routes) - 15} more_")
            lines.append("")

    # Token drift — architectural intent signal
    if token_drift:
        sorted_drift = sorted(
            token_drift.items(),
            key=lambda kv: -(kv[1][0] + kv[1][1]),
        )
        notable = [(t, g, l) for t, (g, l) in sorted_drift if (g + l) >= 2][:12]
        if notable:
            lines += [
                "## Token drift",
                "",
                "Repo-wide behavioral token deltas. Rising tokens indicate "
                "where new architectural intent is appearing; falling tokens "
                "indicate behavior being removed or abstracted away.",
                "",
                "| Token | Gained | Lost | Net |",
                "|-------|------:|-----:|----:|",
            ]
            for token, gained, lost in notable:
                tok_name = token.split(".")[-1]
                net = gained - lost
                sign = "+" if net > 0 else ""
                lines.append(f"| `{tok_name}` | +{gained} | -{lost} | {sign}{net} |")
            lines.append("")

    # File churn hotspots
    if churn:
        top_churn = sorted(churn.items(), key=lambda kv: -kv[1])[:10]
        if top_churn and top_churn[0][1] >= 2:
            lines += [
                "## Files with most behavioral churn",
                "",
            ]
            for f, n in top_churn:
                lines.append(f"- `{f}` — {n} unit change(s)")
            lines.append("")

    # Language composition (only when something actually shifted)
    shifted_langs = [
        (lang, b, a) for lang, (b, a) in diff.lang_counts.items() if b != a
    ]
    if shifted_langs:
        lines += [
            "## Language composition shifts",
            "",
            "| Language | Before | After | Δ |",
            "|----------|------:|------:|----:|",
        ]
        for lang, b, a in shifted_langs:
            delta = a - b
            sign = "+" if delta > 0 else ""
            lines.append(f"| {lang} | {b} | {a} | {sign}{delta} |")
        lines.append("")

    if diff.is_clean and not diff.route_diffs:
        lines += [
            "## Detail",
            "",
            "_No fingerprint-level differences. Architecture is identical "
            "between the two scans._",
            "",
        ]
    elif (not diff.added_units and not diff.removed_units
          and len(diff.changed_units) <= 30):
        # Small re-tokenization sets: list inline, they're readable
        lines += [
            "## Re-tokenized units",
            "",
        ]
        for u in diff.changed_units:
            added = ", ".join(t.split(".")[-1] for t in u.tokens_added)
            removed = ", ".join(t.split(".")[-1] for t in u.tokens_removed)
            parts = []
            if added:
                parts.append(f"`+{added}`")
            if removed:
                parts.append(f"`-{removed}`")
            lines.append(f"- `{u.unit_id}` — {' '.join(parts)}")
        lines.append("")

    lines += [
        "---",
        "",
        "_Generated by `bgi diff --report`. Re-run on any two scan roots._",
    ]

    return "\n".join(lines) + "\n"
