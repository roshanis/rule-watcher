"""Storage helpers for AI updates."""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Mapping

DB_FILENAME = "ai_updates.db"
RETENTION_DAYS = 14
MAX_ITEMS = 100


def _db_path() -> Path:
    preferred = Path("cache")
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        cache_dir = preferred
    except OSError:
        cache_dir = Path("/tmp/keywatch_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / DB_FILENAME


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            UNIQUE(source, external_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_items_published
        ON ai_items(published_at DESC)
        """
    )
    conn.commit()


def save_items(items: Iterable[Mapping[str, str]]) -> int:
    """Persist items, enforcing retention and cap. Returns inserted/updated count."""
    items = list(items)
    if not items:
        purge_expired()
        return 0

    now = datetime.utcnow().isoformat(timespec="seconds")
    with _connect() as conn:
        _init(conn)
        inserted = 0
        for item in items:
            conn.execute(
                """
                INSERT INTO ai_items (source, external_id, title, url, published_at, fetched_at)
                VALUES (:source, :external_id, :title, :url, :published_at, :fetched_at)
                ON CONFLICT(source, external_id) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    published_at = excluded.published_at,
                    fetched_at = excluded.fetched_at
                """,
                {
                    "source": item.get("source", "unknown"),
                    "external_id": item.get("external_id", item.get("url", "")),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "published_at": item.get("published_at"),
                    "fetched_at": item.get("fetched_at", now),
                },
            )
            inserted += 1

        _purge_old(conn, RETENTION_DAYS)
        _enforce_cap(conn, MAX_ITEMS)
        conn.commit()
        return inserted


def _purge_old(conn: sqlite3.Connection, retention_days: int) -> None:
    cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat(timespec="seconds")
    conn.execute(
        """
        DELETE FROM ai_items
        WHERE COALESCE(published_at, fetched_at) < ?
        """,
        (cutoff,),
    )


def _enforce_cap(conn: sqlite3.Connection, limit: int) -> None:
    conn.execute(
        """
        DELETE FROM ai_items
        WHERE id NOT IN (
            SELECT id FROM ai_items
            ORDER BY
                COALESCE(published_at, fetched_at) DESC,
                id DESC
            LIMIT ?
        )
        """,
        (limit,),
    )


def get_recent_items(limit: int = MAX_ITEMS) -> List[Mapping[str, str]]:
    with _connect() as conn:
        _init(conn)
        rows = conn.execute(
            """
            SELECT source, external_id, title, url, published_at, fetched_at
            FROM ai_items
            ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def purge_expired(retention_days: int = RETENTION_DAYS, limit: int = MAX_ITEMS) -> None:
    with _connect() as conn:
        _init(conn)
        _purge_old(conn, retention_days)
        _enforce_cap(conn, limit)
        conn.commit()
