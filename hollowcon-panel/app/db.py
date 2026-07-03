"""Tiny SQLite data layer for proxy users/clients."""
from __future__ import annotations

import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Iterator, Optional

from .config import get_settings


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_settings().db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                auth_password TEXT NOT NULL,
                uuid TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                note TEXT DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        # Migration: add uuid column to pre-existing tables.
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "uuid" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN uuid TEXT NOT NULL DEFAULT ''")
        # Backfill UUIDs for any client missing one.
        for row in conn.execute("SELECT id FROM users WHERE uuid = '' OR uuid IS NULL").fetchall():
            conn.execute(
                "UPDATE users SET uuid = ? WHERE id = ?", (str(uuid.uuid4()), row["id"])
            )


def list_users() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_user(user_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_name(name: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None


def create_user(name: str, auth_password: str | None = None, note: str = "") -> dict:
    auth_password = auth_password or secrets.token_urlsafe(12)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO users (name, auth_password, uuid, enabled, note, created_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (name, auth_password, str(uuid.uuid4()), note, int(time.time())),
        )
        user_id = cur.lastrowid
    return get_user(user_id)  # type: ignore[return-value]


def toggle_user(user_id: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE users SET enabled = 1 - enabled WHERE id = ?", (user_id,)
        )


def delete_user(user_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def enabled_auth_passwords() -> list[str]:
    return [u["auth_password"] for u in list_users() if u["enabled"]]
