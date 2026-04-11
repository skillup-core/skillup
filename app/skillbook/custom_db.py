"""
SkillBook Custom Database

Manages user-specific data in skillbook_custom.db:
- Favorites (bookmarks) per function name
- Comments (hierarchical) per function name

Schema:
    favorites: id, function_name, created_at
    comments:  id, function_name, parent_id, user_id, content, created_at
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db(db_path: str):
    """Initialize custom database schema (create tables if not exists)."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS favorites (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            function_name TEXT NOT NULL UNIQUE,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS comments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            function_name TEXT NOT NULL,
            parent_id     INTEGER REFERENCES comments(id) ON DELETE CASCADE,
            user_id       TEXT NOT NULL,
            content       TEXT NOT NULL,
            created_at    TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_favorites_func
            ON favorites(function_name);

        CREATE INDEX IF NOT EXISTS idx_comments_func
            ON comments(function_name);

        CREATE INDEX IF NOT EXISTS idx_comments_parent
            ON comments(parent_id);
    ''')
    conn.commit()
    conn.close()


# ── Favorites ──────────────────────────────────────────────────────────────

def get_favorites(db_path: str) -> list:
    """Return list of favorite function names (ordered by created_at desc)."""
    conn = _connect(db_path)
    rows = conn.execute(
        'SELECT function_name, created_at FROM favorites ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return [{'name': r['function_name'], 'created_at': r['created_at']} for r in rows]


def is_favorite(db_path: str, function_name: str) -> bool:
    conn = _connect(db_path)
    row = conn.execute(
        'SELECT id FROM favorites WHERE function_name = ?', (function_name,)
    ).fetchone()
    conn.close()
    return row is not None


def add_favorite(db_path: str, function_name: str) -> bool:
    """Add function to favorites. Returns True if added, False if already exists."""
    conn = _connect(db_path)
    try:
        conn.execute(
            'INSERT INTO favorites (function_name, created_at) VALUES (?, ?)',
            (function_name, datetime.utcnow().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def remove_favorite(db_path: str, function_name: str) -> bool:
    """Remove function from favorites. Returns True if removed."""
    conn = _connect(db_path)
    cur = conn.execute(
        'DELETE FROM favorites WHERE function_name = ?', (function_name,)
    )
    conn.commit()
    removed = cur.rowcount > 0
    conn.close()
    return removed


# ── Comments ───────────────────────────────────────────────────────────────

def get_comments(db_path: str, function_name: str) -> list:
    """
    Return all comments for a function as a flat list ordered by created_at.
    Each comment: {id, parent_id, user_id, content, created_at}
    """
    conn = _connect(db_path)
    rows = conn.execute(
        '''SELECT id, parent_id, user_id, content, created_at
           FROM comments
           WHERE function_name = ?
           ORDER BY created_at ASC''',
        (function_name,)
    ).fetchall()
    conn.close()
    return [
        {
            'id': r['id'],
            'parent_id': r['parent_id'],
            'user_id': r['user_id'],
            'content': r['content'],
            'created_at': r['created_at'],
        }
        for r in rows
    ]


def add_comment(db_path: str, function_name: str, user_id: str,
                content: str, parent_id: int = None) -> dict:
    """Add a comment. Returns the new comment dict."""
    conn = _connect(db_path)
    now = datetime.utcnow().isoformat()
    cur = conn.execute(
        '''INSERT INTO comments (function_name, parent_id, user_id, content, created_at)
           VALUES (?, ?, ?, ?, ?)''',
        (function_name, parent_id, user_id, content, now)
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {
        'id': new_id,
        'parent_id': parent_id,
        'user_id': user_id,
        'content': content,
        'created_at': now,
    }


def update_comment(db_path: str, comment_id: int, user_id: str, content: str) -> bool:
    """Update a comment's content (only if owned by user_id). Returns True if updated."""
    conn = _connect(db_path)
    cur = conn.execute(
        'UPDATE comments SET content = ? WHERE id = ? AND user_id = ?',
        (content, comment_id, user_id)
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_comment(db_path: str, comment_id: int, user_id: str) -> bool:
    """Delete a comment (only if owned by user_id). Returns True if deleted."""
    conn = _connect(db_path)
    cur = conn.execute(
        'DELETE FROM comments WHERE id = ? AND user_id = ?',
        (comment_id, user_id)
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
