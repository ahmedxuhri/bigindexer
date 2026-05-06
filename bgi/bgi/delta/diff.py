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
