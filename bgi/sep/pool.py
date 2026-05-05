"""
SEP — Suspended Edge Pool.

Stores unresolved outward references from Gate 2 in SQLite.
Groups them into Odd Groups by COV pattern.
Resurrects edges when new fingerprints arrive that provide the missing lock.
Flags INTENTIONAL_BOUNDARY when edges remain suspended past the age threshold.

Flow:
  Gate 2 produces SuspendedEdge objects for every outward token with no current lock.
  SEP.ingest()  — writes them into the pool
  SEP.resurrect() — given new fingerprints, tries to resolve suspended edges
  SEP.odd_groups() — clusters suspended edges by token/pattern for AI Position 2
  SEP.scan_boundaries() — promotes stale suspended edges to INTENTIONAL_BOUNDARY
"""
from __future__ import annotations

import sqlite3
import json
import time
from dataclasses import dataclass
from pathlib import Path

from bgi.core.cov import COV, LOCK_MAP
from bgi.core.edges import BGIEdge
from bgi.core.fingerprint import COVFingerprint
from bgi.gate2.keylock import SuspendedEdge, _edge_confidence, _classify_edge, _directed


# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS suspended_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT    NOT NULL,
    token       TEXT    NOT NULL,
    raw_callee  TEXT    NOT NULL,
    ingested_at REAL    NOT NULL,   -- unix timestamp
    resolved    INTEGER NOT NULL DEFAULT 0,
    resolved_at REAL,
    boundary    INTEGER NOT NULL DEFAULT 0,
    scan_run    TEXT                -- identifier for the scan batch that produced this
);

CREATE INDEX IF NOT EXISTS idx_sep_token    ON suspended_edges (token, resolved);
CREATE INDEX IF NOT EXISTS idx_sep_source   ON suspended_edges (source_id);
CREATE INDEX IF NOT EXISTS idx_sep_boundary ON suspended_edges (boundary);
"""

# How many seconds before an unresolved edge is declared INTENTIONAL_BOUNDARY
DEFAULT_BOUNDARY_AGE = 60 * 60 * 24 * 7  # 7 days; set low in tests


# ── Odd Group ─────────────────────────────────────────────────────────────────

@dataclass
class OddGroup:
    """
    A cluster of suspended edges sharing the same COV token pattern.
    Handed to AI Position 2 (Resurrection Forecaster).
    """
    token: COV
    pattern: str          # dominant raw_callee pattern (e.g. ".fetch_user")
    member_ids: list[str] # source_ids in this group
    count: int
    oldest_age_s: float   # seconds since oldest member was ingested
    is_boundary: bool     # True if any member is already flagged


# ── Pool ──────────────────────────────────────────────────────────────────────

class SuspendedEdgePool:
    """
    SQLite-backed store for suspended edges.
    One pool per project (one .db file).
    """

    def __init__(self, db_path: str | Path = ":memory:"):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_DDL)
        self._conn.commit()

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest(
        self,
        suspended: list[SuspendedEdge],
        scan_run: str = "",
    ) -> int:
        """
        Write suspended edges from a Gate 2 scan into the pool.
        Skips duplicates (same source_id + token already pending).
        Returns number of new rows inserted.
        """
        now = time.time()
        inserted = 0
        cur = self._conn.cursor()

        for se in suspended:
            # Check for existing unresolved duplicate
            exists = cur.execute(
                "SELECT 1 FROM suspended_edges WHERE source_id=? AND token=? AND resolved=0",
                (se.source_id, str(se.token)),
            ).fetchone()
            if exists:
                continue

            cur.execute(
                """
                INSERT INTO suspended_edges (source_id, token, raw_callee, ingested_at, scan_run)
                VALUES (?, ?, ?, ?, ?)
                """,
                (se.source_id, str(se.token), se.raw_callee, now, scan_run),
            )
            inserted += 1

        self._conn.commit()
        return inserted

    # ── Resurrection ─────────────────────────────────────────────────────────

    def resurrect(
        self,
        new_fingerprints: list[COVFingerprint],
    ) -> list[BGIEdge]:
        """
        Given a fresh batch of fingerprints, attempt to resolve pending suspended edges.

        For each pending suspended edge:
          - Look for new fingerprints that contain a lock token for the suspended key token.
          - If found, create a BGIEdge and mark the suspended edge resolved.

        Returns list of newly resurrected BGIEdge objects.
        """
        if not new_fingerprints:
            return []

        # Build lock index from new fingerprints: lock_token → [fp]
        lock_index: dict[str, list[COVFingerprint]] = {}
        for fp in new_fingerprints:
            for tok in fp.all_tokens():
                lock_index.setdefault(str(tok), []).append(fp)

        cur = self._conn.cursor()
        pending = cur.execute(
            "SELECT id, source_id, token, raw_callee FROM suspended_edges WHERE resolved=0"
        ).fetchall()

        resurrected: list[BGIEdge] = []
        now = time.time()

        for row in pending:
            cov_token = _cov_from_str(row["token"])
            if cov_token is None:
                continue

            lock_candidates = LOCK_MAP.get(cov_token, set())
            for lock_tok in lock_candidates:
                partners = lock_index.get(str(lock_tok), [])
                for fp_b in partners:
                    # Build a minimal proxy fingerprint for confidence computation
                    proxy = _make_proxy(row["source_id"], cov_token)
                    confidence = _edge_confidence(proxy, fp_b)
                    edge_type = _classify_edge(confidence)
                    key_tok, lk_tok = _directed(cov_token, lock_tok)

                    if (cov_token, lock_tok) in {(key_tok, lk_tok)}:
                        source_id, target_id = row["source_id"], fp_b.unit_id
                    else:
                        source_id, target_id = fp_b.unit_id, row["source_id"]

                    resurrected.append(BGIEdge(
                        source_id=source_id,
                        target_id=target_id,
                        key_token=key_tok,
                        lock_token=lk_tok,
                        confidence=confidence,
                        edge_type=edge_type,
                        provenance=f"sep:resurrected:{row['source_id']}",
                    ))

                    cur.execute(
                        "UPDATE suspended_edges SET resolved=1, resolved_at=? WHERE id=?",
                        (now, row["id"]),
                    )
                    break  # take first match per suspended edge

        self._conn.commit()
        return resurrected

    # ── Odd Groups ────────────────────────────────────────────────────────────

    def odd_groups(self) -> list[OddGroup]:
        """
        Cluster pending (unresolved, non-boundary) suspended edges by COV token.
        Returns OddGroup list sorted by count descending.
        Handed to AI Position 2 for resurrection forecasting.
        """
        cur = self._conn.cursor()
        rows = cur.execute(
            """
            SELECT token, raw_callee, source_id, ingested_at, boundary
            FROM suspended_edges
            WHERE resolved=0
            ORDER BY token, ingested_at
            """
        ).fetchall()

        groups: dict[str, dict] = {}
        now = time.time()

        for row in rows:
            tok = row["token"]
            g = groups.setdefault(tok, {
                "token": tok,
                "pattern": row["raw_callee"],
                "member_ids": [],
                "oldest_age_s": 0.0,
                "any_boundary": False,
            })
            g["member_ids"].append(row["source_id"])
            age = now - row["ingested_at"]
            if age > g["oldest_age_s"]:
                g["oldest_age_s"] = age
            if row["boundary"]:
                g["any_boundary"] = True

        result = []
        for tok_str, g in groups.items():
            cov_token = _cov_from_str(tok_str)
            if cov_token is None:
                continue
            result.append(OddGroup(
                token=cov_token,
                pattern=g["pattern"],
                member_ids=g["member_ids"],
                count=len(g["member_ids"]),
                oldest_age_s=g["oldest_age_s"],
                is_boundary=g["any_boundary"],
            ))

        result.sort(key=lambda g: -g.count)
        return result

    # ── Boundary detection ────────────────────────────────────────────────────

    def scan_boundaries(
        self,
        max_age_s: float = DEFAULT_BOUNDARY_AGE,
    ) -> list[str]:
        """
        Promote suspended edges older than max_age_s to INTENTIONAL_BOUNDARY.
        Returns list of source_ids promoted.
        """
        cutoff = time.time() - max_age_s
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT id, source_id FROM suspended_edges WHERE resolved=0 AND boundary=0 AND ingested_at<?",
            (cutoff,),
        ).fetchall()

        promoted = []
        for row in rows:
            cur.execute("UPDATE suspended_edges SET boundary=1 WHERE id=?", (row["id"],))
            promoted.append(row["source_id"])

        self._conn.commit()
        return promoted

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        cur = self._conn.cursor()
        total    = cur.execute("SELECT COUNT(*) FROM suspended_edges").fetchone()[0]
        pending  = cur.execute("SELECT COUNT(*) FROM suspended_edges WHERE resolved=0 AND boundary=0").fetchone()[0]
        resolved = cur.execute("SELECT COUNT(*) FROM suspended_edges WHERE resolved=1").fetchone()[0]
        boundary = cur.execute("SELECT COUNT(*) FROM suspended_edges WHERE boundary=1").fetchone()[0]
        return {
            "total": total,
            "pending": pending,
            "resolved": resolved,
            "intentional_boundary": boundary,
        }

    def close(self):
        self._conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cov_from_str(s: str) -> COV | None:
    """Parse 'COV.TOKEN' or 'TOKEN' → COV enum member."""
    name = s.split(".")[-1]
    try:
        return COV[name]
    except KeyError:
        return None


def _make_proxy(unit_id: str, token: COV) -> COVFingerprint:
    """Minimal stand-in fingerprint for confidence computation."""
    from bgi.core.fingerprint import COVFingerprint
    return COVFingerprint(
        unit_id=unit_id,
        tokens=[token],
        class_context=[],
        confidence=0.75,
        source=unit_id.split("::")[0],
        language="python",
        line_range=(0, 0),
    )
