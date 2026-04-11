"""
Skillup Account Management

Handles user account data stored in SQLite.
Designed for NFS-shared usage: concurrent reads are allowed,
writes are serialized with exclusive locking.

Schema is extensible - new fields can be added via ALTER TABLE.
"""

import os
import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, Any


# Schema version for future migrations
SCHEMA_VERSION = 1

# Default DB path (relative to skillup root)
DEFAULT_ACCOUNT_DB_RELPATH = 'desktop/data/account.db'


def get_default_account_db_path() -> str:
    """Return default account.db path (desktop/data/account.db under skillup root)"""
    skillup_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(skillup_root, DEFAULT_ACCOUNT_DB_RELPATH)


def _get_connection(db_path: str) -> sqlite3.Connection:
    """
    Open SQLite connection suitable for NFS-shared use.
    - DELETE journal mode (default): no .wal/.shm files, NFS-safe
    - Timeout for write lock contention
    """
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    """Create tables if they don't exist. Schema is forward-compatible."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_info (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id            TEXT PRIMARY KEY,          -- login id ($USER)
            name          TEXT NOT NULL,             -- display name (default: id)
            photo         BLOB,                      -- 320x320 image binary (NULL = use default)
            photo_small   BLOB,                      -- 64x64 image binary (NULL = derive from photo)
            photo_mime    TEXT DEFAULT 'image/jpeg', -- MIME type of photo
            activated     INTEGER NOT NULL DEFAULT 1, -- 1 = active, 0 = deactivated
            created_at    INTEGER NOT NULL,          -- Unix timestamp
            updated_at    INTEGER NOT NULL           -- Unix timestamp
            -- Future fields can be added with ALTER TABLE
        );
    """)

    # Insert schema version if not present
    conn.execute(
        "INSERT OR IGNORE INTO schema_info (key, value) VALUES ('version', ?)",
        (str(SCHEMA_VERSION),)
    )

    # Migration: add activated column if it doesn't exist (forward-compat)
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    if 'activated' not in existing_cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN activated INTEGER NOT NULL DEFAULT 1")

    conn.commit()


def init_db(db_path: str):
    """Initialize database, creating it if necessary."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = _get_connection(db_path)
    try:
        # Revert WAL mode if previously set, use default DELETE journal
        conn.execute('PRAGMA journal_mode=DELETE')
        _ensure_schema(conn)
    finally:
        conn.close()


def get_account(db_path: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get account info for user_id.
    Returns dict with id, name, has_photo, has_photo_small, created_at, updated_at.
    Returns None if no record exists (caller should use defaults).
    Photo binary is NOT returned here - use get_account_photo() for that.
    """
    try:
        conn = _get_connection(db_path)
        try:
            row = conn.execute(
                "SELECT id, name, photo IS NOT NULL as has_photo, "
                "photo_small IS NOT NULL as has_photo_small, "
                "photo_mime, activated, created_at, updated_at "
                "FROM accounts WHERE id = ?",
                (user_id,)
            ).fetchone()

            if row is None:
                return None

            return {
                'id': row['id'],
                'name': row['name'],
                'has_photo': bool(row['has_photo']),
                'has_photo_small': bool(row['has_photo_small']),
                'photo_mime': row['photo_mime'] or 'image/jpeg',
                'activated': bool(row['activated']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            }
        finally:
            conn.close()
    except Exception:
        return None


def get_account_photo(db_path: str, user_id: str, size: str = 'small') -> Optional[bytes]:
    """
    Get photo binary for user.
    size: 'full' (320x320) or 'small' (64x64)
    Returns None if no photo stored.
    """
    col = 'photo_small' if size == 'small' else 'photo'
    try:
        conn = _get_connection(db_path)
        try:
            row = conn.execute(
                f"SELECT {col}, photo_mime FROM accounts WHERE id = ?",
                (user_id,)
            ).fetchone()
            if row and row[0]:
                return bytes(row[0]), row['photo_mime'] or 'image/jpeg'
            return None, None
        finally:
            conn.close()
    except Exception:
        return None, None


def upsert_account(db_path: str, user_id: str, name: Optional[str] = None,
                   photo: Optional[bytes] = None, photo_small: Optional[bytes] = None,
                   photo_mime: Optional[str] = None) -> bool:
    """
    Insert or update account record.
    Only provided fields are updated (None = keep existing).
    Returns True on success.
    """
    try:
        conn = _get_connection(db_path)
        try:
            now = int(time.time())

            # Check if account exists
            existing = conn.execute(
                "SELECT id FROM accounts WHERE id = ?", (user_id,)
            ).fetchone()

            if existing is None:
                # Insert new account
                conn.execute(
                    "INSERT INTO accounts (id, name, photo, photo_small, photo_mime, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        name if name is not None else user_id,
                        photo,
                        photo_small,
                        photo_mime or 'image/jpeg',
                        now,
                        now
                    )
                )
            else:
                # Build UPDATE statement with only provided fields
                updates = ['updated_at = ?']
                values = [now]

                if name is not None:
                    updates.append('name = ?')
                    values.append(name)
                if photo is not None:
                    updates.append('photo = ?')
                    values.append(photo)
                if photo_small is not None:
                    updates.append('photo_small = ?')
                    values.append(photo_small)
                if photo_mime is not None:
                    updates.append('photo_mime = ?')
                    values.append(photo_mime)

                values.append(user_id)
                conn.execute(
                    f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?",
                    values
                )

            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        return False


def count_activated_users(db_path: str) -> int:
    """
    Return the number of accounts where activated=1.
    Returns -2 on error (DB not found, read failure, etc.).
    """
    if not Path(db_path).exists():
        return -2
    try:
        conn = _get_connection(db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM accounts WHERE activated=1"
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
    except Exception:
        return -2


def clear_account_photo(db_path: str, user_id: str) -> bool:
    """Remove photo from account (revert to default)."""
    try:
        conn = _get_connection(db_path)
        try:
            now = int(time.time())
            conn.execute(
                "UPDATE accounts SET photo = NULL, photo_small = NULL, updated_at = ? WHERE id = ?",
                (now, user_id)
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False
