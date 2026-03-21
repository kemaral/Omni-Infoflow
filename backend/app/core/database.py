"""
Deduplication Database
=======================
SQLite-backed storage that prevents the same content from being processed
twice.  Three independent fingerprint columns allow flexible matching:

- ``source_uri_hash`` : catches same-URL refetches
- ``content_hash``    : catches same-body reposts on different URLs
- ``external_id``     : catches known identifiers (RSS guid, DOI, …)
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Default DB path
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_DB_PATH = _DATA_DIR / "db.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_items (
    id              TEXT PRIMARY KEY,
    source_type     TEXT,
    source_uri      TEXT,
    source_uri_hash TEXT,
    content_hash    TEXT,
    external_id     TEXT,
    title           TEXT,
    status          TEXT DEFAULT 'completed',
    created_at      TEXT,
    updated_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_source_uri_hash ON processed_items(source_uri_hash);
CREATE INDEX IF NOT EXISTS idx_content_hash    ON processed_items(content_hash);
CREATE INDEX IF NOT EXISTS idx_external_id     ON processed_items(external_id);
"""


class DedupDatabase:
    """Lightweight persistent store for processed-item fingerprints.

    Usage::

        db = DedupDatabase()
        db.init()

        if db.is_duplicate(source_uri="https://...", content="..."):
            skip()

        db.mark_processed(item_id="abc", source_uri="https://...", ...)
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else _DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    # -- lifecycle ----------------------------------------------------------

    def init(self) -> None:
        """Create the database file and schema if they don't exist."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- hashing helpers ----------------------------------------------------

    @staticmethod
    def hash_uri(uri: str) -> str:
        return hashlib.sha256(uri.encode()).hexdigest()

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    # -- deduplication API --------------------------------------------------

    def is_duplicate(
        self,
        *,
        source_uri: str | None = None,
        content: str | None = None,
        external_id: str | None = None,
    ) -> bool:
        """Return ``True`` if ANY of the provided fingerprints already exist.

        Callers can pass one, two, or all three fingerprints; the check is
        an OR across all provided values.
        """
        self._ensure_connected()
        assert self._conn is not None

        clauses: list[str] = []
        params: list[str] = []

        if source_uri:
            clauses.append("source_uri_hash = ?")
            params.append(self.hash_uri(source_uri))

        if content:
            clauses.append("content_hash = ?")
            params.append(self.hash_content(content))

        if external_id:
            clauses.append("external_id = ?")
            params.append(external_id)

        if not clauses:
            return False

        query = f"SELECT 1 FROM processed_items WHERE {' OR '.join(clauses)} LIMIT 1"
        row = self._conn.execute(query, params).fetchone()
        return row is not None

    def mark_processed(
        self,
        *,
        item_id: str,
        source_type: str = "",
        source_uri: str = "",
        content: str = "",
        external_id: str | None = None,
        title: str | None = None,
        status: str = "completed",
    ) -> None:
        """Record an item as processed so future runs skip it."""
        self._ensure_connected()
        assert self._conn is not None

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO processed_items
                (id, source_type, source_uri, source_uri_hash,
                 content_hash, external_id, title, status,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                source_type,
                source_uri,
                self.hash_uri(source_uri) if source_uri else None,
                self.hash_content(content) if content else None,
                external_id,
                title,
                status,
                now,
                now,
            ),
        )
        self._conn.commit()

    # -- query helpers (for API / dashboard) --------------------------------

    def recent_items(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recently processed items."""
        self._ensure_connected()
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT * FROM processed_items ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        self._ensure_connected()
        assert self._conn is not None
        row = self._conn.execute("SELECT COUNT(*) FROM processed_items").fetchone()
        return row[0] if row else 0

    # -- internals ----------------------------------------------------------

    def _ensure_connected(self) -> None:
        if self._conn is None:
            raise RuntimeError(
                "Database not initialised. Call db.init() first."
            )
