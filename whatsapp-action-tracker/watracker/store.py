"""SQLite-backed task and outcome store.

Tasks are deduplicated on a stable ``uid`` derived from (chat, source
timestamp, normalized title) so the same export can be re-ingested safely
as the chat grows.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

DEFAULT_DB = Path.home() / ".watracker" / "watracker.db"

STATUSES = ("open", "in_progress", "blocked", "done", "cancelled")
OPEN_STATUSES = ("open", "in_progress", "blocked")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    assignee TEXT,
    requester TEXT,
    chat TEXT,
    due TEXT,
    priority TEXT DEFAULT 'normal',
    status TEXT DEFAULT 'open',
    kind TEXT DEFAULT 'action',
    confidence REAL DEFAULT 1.0,
    origin TEXT DEFAULT 'whatsapp',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    source_ts TEXT,
    source_sender TEXT,
    source_text TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT UNIQUE NOT NULL,
    text TEXT NOT NULL,
    chat TEXT,
    sender TEXT,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_chat ON tasks(chat);
"""


def _norm(text: str) -> str:
    return re.sub(r"\W+", "", (text or "").lower())


def make_uid(chat: str, source_ts: str, title: str) -> str:
    return hashlib.sha1(f"{chat}|{source_ts}|{_norm(title)}".encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else DEFAULT_DB
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def close(self):
        self.conn.close()

    # -- tasks -------------------------------------------------------------

    def add_task(
        self,
        title: str,
        *,
        assignee: Optional[str] = None,
        requester: Optional[str] = None,
        chat: str = "",
        due: Optional[date] = None,
        priority: str = "normal",
        kind: str = "action",
        confidence: float = 1.0,
        origin: str = "whatsapp",
        source_ts: Optional[datetime] = None,
        source_sender: Optional[str] = None,
        source_text: Optional[str] = None,
        uid: Optional[str] = None,
        status: str = "open",
        created_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> Optional[int]:
        """Insert a task; returns row id, or None if it already existed."""
        sts = source_ts.isoformat(timespec="seconds") if source_ts else ""
        uid = uid or make_uid(chat, sts, title)
        now = _now()
        try:
            cur = self.conn.execute(
                """INSERT INTO tasks (uid, title, assignee, requester, chat, due,
                       priority, status, kind, confidence, origin, created_at,
                       updated_at, completed_at, source_ts, source_sender, source_text)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid, title, assignee, requester, chat,
                    due.isoformat() if due else None,
                    priority, status, kind, confidence, origin,
                    created_at or now, now, completed_at, sts or None,
                    source_sender, source_text,
                ),
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def update_status(self, task_id: int, status: str, note_ts: Optional[str] = None) -> bool:
        if status not in STATUSES:
            raise ValueError(f"invalid status: {status}")
        completed = (note_ts or _now()) if status == "done" else None
        cur = self.conn.execute(
            "UPDATE tasks SET status=?, updated_at=?, completed_at=COALESCE(?, completed_at) WHERE id=?",
            (status, _now(), completed, task_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def set_fields(self, task_id: int, **fields) -> bool:
        allowed = {"title", "assignee", "due", "priority", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return False
        cols = ", ".join(f"{k}=?" for k in updates)
        cur = self.conn.execute(
            f"UPDATE tasks SET {cols}, updated_at=? WHERE id=?",
            (*updates.values(), _now(), task_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def tasks(
        self,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        chat: Optional[str] = None,
        open_only: bool = False,
    ) -> List[dict]:
        query = "SELECT * FROM tasks WHERE 1=1"
        args: list = []
        if open_only:
            query += f" AND status IN ({','.join('?' * len(OPEN_STATUSES))})"
            args.extend(OPEN_STATUSES)
        elif status:
            query += " AND status=?"
            args.append(status)
        if assignee:
            query += " AND LOWER(COALESCE(assignee,''))=LOWER(?)"
            args.append(assignee)
        if chat:
            query += " AND chat=?"
            args.append(chat)
        query += " ORDER BY COALESCE(due, '9999') ASC, priority DESC, id ASC"
        return [dict(r) for r in self.conn.execute(query, args)]

    def get(self, task_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def find_similar_open(self, title: str, threshold: float = 0.7) -> Optional[dict]:
        from .extractor import similarity

        for task in self.tasks(open_only=True):
            if similarity(title, task["title"]) >= threshold:
                return task
        return None

    # -- outcomes ----------------------------------------------------------

    def add_outcome(self, text: str, ts: datetime, chat: str = "", sender: Optional[str] = None) -> Optional[int]:
        uid = hashlib.sha1(f"{chat}|{ts.isoformat()}|{_norm(text)}".encode()).hexdigest()[:16]
        try:
            cur = self.conn.execute(
                "INSERT INTO outcomes (uid, text, chat, sender, ts) VALUES (?,?,?,?,?)",
                (uid, text, chat, sender, ts.isoformat(timespec="seconds")),
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def outcomes(self, since: Optional[str] = None, until: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM outcomes WHERE 1=1"
        args: list = []
        if since:
            query += " AND ts >= ?"
            args.append(since)
        if until:
            query += " AND ts <= ?"
            args.append(until)
        query += " ORDER BY ts ASC"
        return [dict(r) for r in self.conn.execute(query, args)]
