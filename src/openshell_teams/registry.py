"""Agent registry: which agents exist, who created whom, their sandbox and state.
Capacity is reserved atomically; request IDs are scoped to (team, caller)."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class LimitReached(Exception):
    pass


class RequestIdReused(Exception):
    pass


class Registry:
    def __init__(self, path: Path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS teams (team TEXT PRIMARY KEY, max_workers INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS agents (
                name TEXT PRIMARY KEY, team TEXT NOT NULL, role TEXT NOT NULL, parent TEXT,
                caller TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL,
                counts INTEGER NOT NULL, state TEXT NOT NULL, sandbox_id TEXT, generation TEXT,
                grant_hash TEXT, created_at REAL NOT NULL,
                UNIQUE (team, caller, request_id));
        """)

    def add_team(self, team: str, *, max_workers: int) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO teams VALUES (?, ?)", (team, max_workers))

    def reserve(self, team, *, caller, request_id, digest, name, role, parent, counts=True) -> dict:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT * FROM agents WHERE team=? AND caller=? AND request_id=?",
                    (team, caller, request_id)).fetchone()
                if row:
                    if row["digest"] != digest:
                        raise RequestIdReused(request_id)
                    self._db.execute("COMMIT")
                    return {**dict(row), "retry": True}
                if counts:
                    (limit,) = self._db.execute("SELECT max_workers FROM teams WHERE team=?", (team,)).fetchone()
                    (used,) = self._db.execute(
                        "SELECT COUNT(*) FROM agents WHERE team=? AND counts=1 AND state != 'stopped'",
                        (team,)).fetchone()
                    if used >= limit:
                        raise LimitReached(f"team {team} has {used} of {limit} workers")
                self._db.execute(
                    "INSERT INTO agents (name, team, role, parent, caller, request_id, digest, counts, state, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?)",
                    (name, team, role, parent, caller, request_id, digest, int(counts), time.time()))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            return {**self.get(name), "retry": False}

    def update(self, name: str, **fields) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._db.execute(f"UPDATE agents SET {cols} WHERE name=?", (*fields.values(), name))

    def get(self, name: str) -> dict | None:
        row = self._db.execute("SELECT * FROM agents WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def by_sandbox(self, sandbox_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM agents WHERE sandbox_id=?", (sandbox_id,)).fetchone()
        return dict(row) if row else None

    def children(self, name: str) -> list[str]:
        return [r["name"] for r in self._db.execute(
            "SELECT name FROM agents WHERE parent=? AND state != 'stopped' ORDER BY created_at", (name,))]

    def is_stopping(self, name: str) -> bool:
        row = self.get(name)
        return bool(row and row["state"] in ("stopping", "stopped"))

    def begin_stop(self, name: str) -> list[str]:
        """Mark `name` and its descendants stopping; return the stop order, children first."""
        order: list[str] = []

        def visit(n):
            for child in self.children(n):
                visit(child)
            order.append(n)

        visit(name)
        for n in order:
            self.update(n, state="stopping")
        return order
