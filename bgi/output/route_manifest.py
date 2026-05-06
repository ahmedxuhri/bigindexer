"""
BGI Route Manifest — collect all ROUTE-tagged units across all languages
and emit a structured JSON suitable for API documentation or AI agent consumption.

Output schema (per entry):
  {
    "unit_id":    "src/routes/users.ts::GET:/users",
    "method":     "GET",           // null if not detectable
    "path":       "/users",        // null if not detectable
    "file":       "src/routes/users.ts",
    "language":   "typescript",
    "tokens":     ["ROUTE", "ASYNC", "FETCH"],
    "confidence": 0.95,
    "line_start": 12,
    "line_end":   24
  }
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from bgi.core.cov import COV
from bgi.core.fingerprint import COVFingerprint


# Patterns to extract HTTP method and path from unit_id last segment
# Matches: GET:/users  POST:/users/:id  DELETE:<dynamic>
_ROUTE_SEGMENT = re.compile(
    r"^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|ALL|USE):(/.+|<dynamic>)$",
    re.IGNORECASE,
)


def _parse_route_segment(unit_id: str) -> tuple[str | None, str | None]:
    """
    Extract (method, path) from unit_id if the last segment is a route name.
    Returns (None, None) if the unit was detected via decorator/heritage (no inline name).
    """
    last = unit_id.rsplit("::", 1)[-1]
    m = _ROUTE_SEGMENT.match(last)
    if m:
        return m.group(1).upper(), m.group(2)
    return None, None


def _file_from_unit_id(unit_id: str) -> str:
    """Extract the file path portion (everything before the first ::)."""
    return unit_id.split("::")[0]


def build_route_manifest(
    fingerprints: list[COVFingerprint],
) -> list[dict]:
    """
    Filter fingerprints to ROUTE-tagged units and return structured manifest entries.
    Sorted by file then unit_id for deterministic output.
    """
    entries = []
    for fp in fingerprints:
        if COV.ROUTE not in fp.tokens:
            continue

        method, path = _parse_route_segment(fp.unit_id)
        entry = {
            "unit_id":    fp.unit_id,
            "method":     method,
            "path":       path,
            "file":       _file_from_unit_id(fp.unit_id),
            "language":   fp.language,
            "tokens":     [t.value for t in fp.tokens],
            "confidence": round(fp.confidence, 4),
            "line_start": fp.line_range[0] if fp.line_range else None,
            "line_end":   fp.line_range[1] if fp.line_range else None,
        }
        entries.append(entry)

    entries.sort(key=lambda e: (e["file"], e["unit_id"]))
    return entries


def write_route_manifest(
    fingerprints: list[COVFingerprint],
    output_path: str,
) -> list[dict]:
    """Build route manifest and write it to a JSON file. Returns the entries."""
    entries = build_route_manifest(fingerprints)
    Path(output_path).write_text(json.dumps(entries, indent=2))
    return entries
