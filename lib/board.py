"""
Board system: common SQLite CRUD and path resolution for all boards.
"""

import json
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional


# skillup-full/ directory (parent of lib/)
_SKILLUP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP_DIR = os.path.join(_SKILLUP_DIR, 'app')
_DESKTOP_DIR = os.path.join(_SKILLUP_DIR, 'desktop')
_FALLBACK_BOARD_DIR = os.path.join(_SKILLUP_DIR, 'desktop', 'data', 'board')


def _read_desktop_board_dir() -> str:
    """Read general.board_dir from [desktop] section of the default config file."""
    try:
        from lib.config import _get_default_config_path, _expand_config_value
        path = _get_default_config_path()
        if not path or not os.path.exists(path):
            return ''
        ini_dir = os.path.dirname(os.path.abspath(path))
        in_desktop = False
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith(';'):
                    continue
                if line.startswith('[') and line.endswith(']'):
                    in_desktop = (line[1:-1].strip() == 'desktop')
                    continue
                if in_desktop and line.startswith('general.board_dir'):
                    _, val = line.split('=', 1)
                    return _expand_config_value(val.strip(), ini_dir)
    except Exception:
        pass
    return ''


def get_board_dir(config: Dict[str, Any]) -> str:
    board_dir = config.get('general.board_dir') or ''
    if not board_dir:
        board_dir = _read_desktop_board_dir()
    return board_dir or _FALLBACK_BOARD_DIR


def resolve_form_path(path: str) -> str:
    """Resolve a form path to an absolute path.

    If path is already absolute, return as-is.
    Otherwise resolve relative to skillup-full/ root.
    """
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.join(_SKILLUP_DIR, path)


def is_under_system_dir(path: str) -> bool:
    """Return True if path resides under app/ or desktop/."""
    p = os.path.realpath(path)
    return p.startswith(os.path.realpath(_APP_DIR) + os.sep) or \
           p.startswith(os.path.realpath(_DESKTOP_DIR) + os.sep)


def is_system_board(detail_path: str, list_path: str) -> bool:
    """Return True if both form files reside under app/ or desktop/."""
    return is_under_system_dir(detail_path) and is_under_system_dir(list_path)


def get_db_path(board_dir: str, system: bool) -> str:
    sub = 'system' if system else 'user'
    return os.path.join(board_dir, sub, 'board.db')


def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    _migrate_schema(conn)
    return conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    try:
        conn.execute('ALTER TABLE posts ADD COLUMN row_id INTEGER')
        conn.commit()
    except sqlite3.OperationalError:
        pass


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            record_id  TEXT PRIMARY KEY,
            form_id    TEXT NOT NULL,
            data       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            row_id     INTEGER
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
            form_id UNINDEXED,
            data,
            content='posts',
            content_rowid='rowid'
        );

        CREATE TRIGGER IF NOT EXISTS posts_ai AFTER INSERT ON posts BEGIN
            INSERT INTO posts_fts(rowid, form_id, data)
            VALUES (new.rowid, new.form_id, new.data);
        END;

        CREATE TRIGGER IF NOT EXISTS posts_ad AFTER DELETE ON posts BEGIN
            INSERT INTO posts_fts(posts_fts, rowid, form_id, data)
            VALUES ('delete', old.rowid, old.form_id, old.data);
        END;

        CREATE TRIGGER IF NOT EXISTS posts_au AFTER UPDATE ON posts BEGIN
            INSERT INTO posts_fts(posts_fts, rowid, form_id, data)
            VALUES ('delete', old.rowid, old.form_id, old.data);
            INSERT INTO posts_fts(rowid, form_id, data)
            VALUES (new.rowid, new.form_id, new.data);
        END;
    """)
    conn.commit()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def post_record(db_path: str, form_id: str, data: Dict[str, Any]) -> str:
    """Insert a new record; returns the new record_id."""
    record_id = str(uuid.uuid4())
    now = _now_iso()
    with _connect(db_path) as conn:
        row = conn.execute(
            'SELECT COALESCE(MAX(row_id), 0) + 1 FROM posts WHERE form_id=?',
            (form_id,)
        ).fetchone()
        row_id = row[0]
        conn.execute(
            'INSERT INTO posts (record_id, form_id, data, created_at, updated_at, row_id) VALUES (?,?,?,?,?,?)',
            (record_id, form_id, json.dumps(data, ensure_ascii=False), now, now, row_id)
        )
    return record_id


def modify_record(db_path: str, record_id: str, data: Dict[str, Any]) -> bool:
    """Update an existing record; returns True if a row was updated."""
    now = _now_iso()
    with _connect(db_path) as conn:
        cur = conn.execute(
            'UPDATE posts SET data=?, updated_at=? WHERE record_id=?',
            (json.dumps(data, ensure_ascii=False), now, record_id)
        )
        return cur.rowcount > 0


def delete_record(db_path: str, record_id: str) -> bool:
    """Delete a record; returns True if a row was deleted."""
    with _connect(db_path) as conn:
        cur = conn.execute('DELETE FROM posts WHERE record_id=?', (record_id,))
        return cur.rowcount > 0


def list_records(db_path: str, form_id: str) -> List[Dict[str, Any]]:
    """Return all records for form_id ordered by created_at desc."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            'SELECT record_id, data, created_at, updated_at, row_id FROM posts WHERE form_id=? ORDER BY created_at DESC',
            (form_id,)
        ).fetchall()
    result = []
    for row in rows:
        entry = json.loads(row['data'])
        entry['@record_id'] = row['record_id']
        entry['@created_at'] = row['created_at']
        entry['@updated_at'] = row['updated_at']
        entry['@row_id'] = row['row_id']
        result.append(entry)
    return result


def get_record(db_path: str, record_id: str) -> Optional[Dict[str, Any]]:
    """Return a single record by record_id, or None."""
    with _connect(db_path) as conn:
        row = conn.execute(
            'SELECT record_id, data, created_at, updated_at, row_id FROM posts WHERE record_id=?',
            (record_id,)
        ).fetchone()
    if row is None:
        return None
    entry = json.loads(row['data'])
    entry['@record_id'] = row['record_id']
    entry['@created_at'] = row['created_at']
    entry['@updated_at'] = row['updated_at']
    entry['@row_id'] = row['row_id']
    return entry


def search_records(db_path: str, form_id: str, query: str) -> List[Dict[str, Any]]:
    """FTS5 full-text search within a form's records."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT p.record_id, p.data, p.created_at, p.updated_at, p.row_id
               FROM posts_fts f
               JOIN posts p ON p.rowid = f.rowid
               WHERE f.form_id = ? AND posts_fts MATCH ?
               ORDER BY p.created_at DESC""",
            (form_id, query)
        ).fetchall()
    result = []
    for row in rows:
        entry = json.loads(row['data'])
        entry['@record_id'] = row['record_id']
        entry['@created_at'] = row['created_at']
        entry['@updated_at'] = row['updated_at']
        entry['@row_id'] = row['row_id']
        result.append(entry)
    return result


def read_form_id(form_path: str) -> Optional[str]:
    """Read formId from a form JSON file."""
    try:
        with open(form_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        return (schema.get('docProps') or {}).get('formId')
    except Exception:
        return None
