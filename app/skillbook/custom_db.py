"""
SkillBook Custom Database

Manages user-specific data in skillbook_custom.db:
- Favorites (bookmarks) per function name
- Comments (hierarchical) per function name
- Hashtags per function name

Schema:
    favorites: id, function_name, created_at
    comments:  id, function_name, parent_id, user_id, content, created_at
    hashtags:  id, function_name, tag, created_at
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=DELETE')
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

        CREATE TABLE IF NOT EXISTS hashtags (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            function_name TEXT NOT NULL,
            tag           TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            UNIQUE(function_name, tag)
        );

        CREATE INDEX IF NOT EXISTS idx_hashtags_func
            ON hashtags(function_name);

        CREATE INDEX IF NOT EXISTS idx_hashtags_tag
            ON hashtags(tag);
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


# ── Hashtags ───────────────────────────────────────────────────────────────

def get_hashtags(db_path: str, function_name: str) -> list:
    """Return list of tags for a function, ordered by created_at."""
    conn = _connect(db_path)
    rows = conn.execute(
        'SELECT tag FROM hashtags WHERE function_name = ? ORDER BY created_at ASC',
        (function_name,)
    ).fetchall()
    conn.close()
    return [r['tag'] for r in rows]


def add_hashtag(db_path: str, function_name: str, tag: str) -> bool:
    """Add a tag to a function. Returns True if added, False if already exists."""
    tag = tag.strip()
    if not tag:
        return False
    conn = _connect(db_path)
    try:
        conn.execute(
            'INSERT INTO hashtags (function_name, tag, created_at) VALUES (?, ?, ?)',
            (function_name, tag, datetime.utcnow().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def remove_hashtag(db_path: str, function_name: str, tag: str) -> bool:
    """Remove a tag from a function. Returns True if removed."""
    conn = _connect(db_path)
    cur = conn.execute(
        'DELETE FROM hashtags WHERE function_name = ? AND tag = ?',
        (function_name, tag)
    )
    conn.commit()
    removed = cur.rowcount > 0
    conn.close()
    return removed


def search_by_hashtag(db_path: str, tag: str) -> list:
    """Return function names whose tags match all space-separated terms (AND, case-insensitive)."""
    terms = [t for t in tag.lower().split() if t]
    if not terms:
        return []
    conn = _connect(db_path)
    # Each term must match at least one tag of the function (AND across terms)
    query = 'SELECT function_name FROM hashtags WHERE LOWER(tag) LIKE ?'
    base = f'SELECT function_name FROM hashtags WHERE LOWER(tag) LIKE ?'
    # Build: function_name IN (term1 matches) AND IN (term2 matches) ...
    subqueries = ' AND '.join(
        f'function_name IN (SELECT function_name FROM hashtags WHERE LOWER(tag) LIKE ?)'
        for _ in terms
    )
    sql = f'SELECT DISTINCT function_name FROM hashtags WHERE {subqueries} ORDER BY function_name'
    rows = conn.execute(sql, tuple(f'%{t}%' for t in terms)).fetchall()
    conn.close()
    return [r['function_name'] for r in rows]
