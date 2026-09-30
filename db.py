"""
SQLite helper for the Cross-Team Reuse Platform.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from werkzeug.security import generate_password_hash


DEMO_USERS = [
    ("demo", "demo123", "Demo User"),
]


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(connect(db_path)) as conn:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                uploaded_file TEXT,
                uploaded_function TEXT,
                existing_team TEXT,
                existing_file TEXT,
                existing_function TEXT,
                acceptance_score REAL,
                decision TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        user_count = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        if user_count == 0:
            for username, password, display_name in DEMO_USERS:
                conn.execute(
                    """
                    INSERT INTO users
                    (username, password_hash, display_name)
                    VALUES (?, ?, ?)
                    """,
                    (
                        username,
                        generate_password_hash(password),
                        display_name,
                    ),
                )

        conn.commit()


def get_user(db_path: Path, username: str):
    with closing(connect(db_path)) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()


def save_feedback(
    db_path: Path,
    username: str,
    uploaded_file: str,
    uploaded_function: str,
    existing_team: str,
    existing_file: str,
    existing_function: str,
    acceptance_score: float,
    decision: str,
) -> None:

    with closing(connect(db_path)) as conn:

        conn.execute(
            """
            INSERT INTO feedback (
                username,
                uploaded_file,
                uploaded_function,
                existing_team,
                existing_file,
                existing_function,
                acceptance_score,
                decision
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                uploaded_file,
                uploaded_function,
                existing_team,
                existing_file,
                existing_function,
                acceptance_score,
                decision,
            ),
        )

        conn.commit()