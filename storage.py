"""Application persistence using SQLite."""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional


def _resolve_db_path() -> Path:
    preferred = Path("cache")
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        base = preferred
    except OSError:
        base = Path("/tmp/keywatch_cache")
        base.mkdir(parents=True, exist_ok=True)
    return base / "app_state.db"


DB_PATH = _resolve_db_path()
RETENTION_DAYS = 45


def _ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    _purge_stale(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            up_votes INTEGER NOT NULL DEFAULT 0,
            down_votes INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS votes (
            doc_id TEXT NOT NULL,
            token TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('up', 'down')),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (doc_id, token),
            FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            author TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()


def _purge_stale(conn: sqlite3.Connection, retention_days: int = RETENTION_DAYS) -> None:
    cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat(timespec="seconds")
    conn.execute(
        "DELETE FROM documents WHERE updated_at IS NULL OR updated_at < ?",
        (cutoff,),
    )
    conn.commit()


def _touch_document(conn: sqlite3.Connection, doc_id: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO documents (doc_id, up_votes, down_votes, updated_at)
        VALUES (?, 0, 0, ?)
        """,
        (doc_id, datetime.utcnow().isoformat(timespec="seconds")),
    )


def get_vote_record(doc_id: str, token: Optional[str] = None) -> Dict[str, Optional[str]]:
    with _ensure_db() as conn:
        _touch_document(conn, doc_id)
        row = conn.execute(
            "SELECT up_votes, down_votes FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        user_vote = None
        if token:
            vote_row = conn.execute(
                "SELECT direction FROM votes WHERE doc_id = ? AND token = ?",
                (doc_id, token),
            ).fetchone()
            if vote_row:
                user_vote = vote_row["direction"]
    up_votes = row["up_votes"] if row else 0
    down_votes = row["down_votes"] if row else 0
    return {
        "up": up_votes,
        "down": down_votes,
        "score": up_votes - down_votes,
        "user_vote": user_vote,
    }


def toggle_vote(doc_id: str, token: str, direction: str) -> Dict[str, Optional[str]]:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _ensure_db() as conn:
        _touch_document(conn, doc_id)
        row = conn.execute(
            "SELECT up_votes, down_votes FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        up_votes = row["up_votes"] if row else 0
        down_votes = row["down_votes"] if row else 0

        prev_row = conn.execute(
            "SELECT direction FROM votes WHERE doc_id = ? AND token = ?",
            (doc_id, token),
        ).fetchone()
        previous_direction = prev_row["direction"] if prev_row else None
        current_direction: Optional[str]

        if previous_direction == direction:
            # Undo vote
            conn.execute(
                "DELETE FROM votes WHERE doc_id = ? AND token = ?",
                (doc_id, token),
            )
            if direction == "up":
                up_votes = max(up_votes - 1, 0)
            else:
                down_votes = max(down_votes - 1, 0)
            current_direction = None
        else:
            if previous_direction:
                if previous_direction == "up":
                    up_votes = max(up_votes - 1, 0)
                else:
                    down_votes = max(down_votes - 1, 0)
                conn.execute(
                    "UPDATE votes SET direction = ?, updated_at = ? WHERE doc_id = ? AND token = ?",
                    (direction, now, doc_id, token),
                )
            else:
                conn.execute(
                    "INSERT INTO votes (doc_id, token, direction, updated_at) VALUES (?, ?, ?, ?)",
                    (doc_id, token, direction, now),
                )
            if direction == "up":
                up_votes += 1
            else:
                down_votes += 1
            current_direction = direction

        conn.execute(
            "UPDATE documents SET up_votes = ?, down_votes = ?, updated_at = ? WHERE doc_id = ?",
            (up_votes, down_votes, now, doc_id),
        )

    return {
        "up": up_votes,
        "down": down_votes,
        "score": up_votes - down_votes,
        "direction": current_direction,
        "previous_direction": previous_direction,
    }


def add_comment(doc_id: str, author: str, text: str) -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _ensure_db() as conn:
        _touch_document(conn, doc_id)
        conn.execute(
            "INSERT INTO comments (doc_id, author, text, created_at) VALUES (?, ?, ?, ?)",
            (doc_id, author, text, now),
        )
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM comments WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()["c"]
        conn.execute(
            "UPDATE documents SET updated_at = ? WHERE doc_id = ?",
            (now, doc_id),
        )
    return count


def get_comment_count(doc_id: str) -> int:
    with _ensure_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM comments WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        return count["c"] if count else 0
