"""
CodeHub DB service - SQLite access for projects, members, stars.
"""

import sqlite3
import os
from typing import List, Optional, Dict


class CodeHubDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    owner_account TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    star_count  INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT NOT NULL,
                    last_deployed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS members (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    account     TEXT NOT NULL,
                    UNIQUE(project_id, account)
                );
                CREATE TABLE IF NOT EXISTS stars (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    account     TEXT NOT NULL,
                    UNIQUE(project_id, account)
                );
            """)
            # Migration: add last_deployed_at if not exists (for existing DBs)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
            if 'last_deployed_at' not in cols:
                conn.execute("ALTER TABLE projects ADD COLUMN last_deployed_at TEXT")

    # ── projects ────────────────────────────────────────────────────────────

    def create_project(self, name: str, owner_account: str, description: str,
                       members: List[str]) -> int:
        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO projects (name, owner_account, description, star_count, created_at)"
                " VALUES (?, ?, ?, 0, ?)",
                (name, owner_account, description, created_at)
            )
            project_id = cur.lastrowid
            for account in members:
                if account and account != owner_account:
                    conn.execute(
                        "INSERT OR IGNORE INTO members (project_id, account) VALUES (?, ?)",
                        (project_id, account)
                    )
        return project_id

    def get_project(self, project_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if row is None:
                return None
            return self._project_row(conn, row)

    def get_project_by_owner_name(self, owner_account: str, name: str) -> Optional[Dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE owner_account = ? AND name = ?",
                (owner_account, name)
            ).fetchone()
            if row is None:
                return None
            return self._project_row(conn, row)

    def list_projects(self, search: str = '', limit: int = 0,
                      offset: int = 0) -> Dict:
        with self._connect() as conn:
            if search:
                pattern = f'%{search}%'
                total = conn.execute(
                    "SELECT COUNT(*) FROM projects WHERE name LIKE ? OR description LIKE ?",
                    (pattern, pattern)
                ).fetchone()[0]
                pagination = f" LIMIT {limit} OFFSET {offset}" if limit else ""
                rows = conn.execute(
                    "SELECT * FROM projects WHERE name LIKE ? OR description LIKE ?"
                    " ORDER BY created_at DESC" + pagination,
                    (pattern, pattern)
                ).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
                pagination = f" LIMIT {limit} OFFSET {offset}" if limit else ""
                rows = conn.execute(
                    "SELECT * FROM projects ORDER BY created_at DESC" + pagination
                ).fetchall()
            return {'total': total, 'projects': [self._project_row(conn, r) for r in rows]}

    def list_projects_by_owner(self, account: str, search: str = '',
                               limit: int = 0, offset: int = 0) -> Dict:
        with self._connect() as conn:
            if search:
                pattern = f'%{search}%'
                total = conn.execute(
                    "SELECT COUNT(*) FROM projects WHERE owner_account = ?"
                    " AND (name LIKE ? OR description LIKE ?)",
                    (account, pattern, pattern)
                ).fetchone()[0]
                pagination = f" LIMIT {limit} OFFSET {offset}" if limit else ""
                rows = conn.execute(
                    "SELECT * FROM projects WHERE owner_account = ?"
                    " AND (name LIKE ? OR description LIKE ?)"
                    " ORDER BY created_at DESC" + pagination,
                    (account, pattern, pattern)
                ).fetchall()
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM projects WHERE owner_account = ?",
                    (account,)
                ).fetchone()[0]
                pagination = f" LIMIT {limit} OFFSET {offset}" if limit else ""
                rows = conn.execute(
                    "SELECT * FROM projects WHERE owner_account = ?"
                    " ORDER BY created_at DESC" + pagination,
                    (account,)
                ).fetchall()
            return {'total': total, 'projects': [self._project_row(conn, r) for r in rows]}

    def list_projects_by_member(self, account: str, search: str = '',
                                limit: int = 0, offset: int = 0) -> Dict:
        with self._connect() as conn:
            if search:
                pattern = f'%{search}%'
                total = conn.execute(
                    "SELECT COUNT(DISTINCT p.id) FROM projects p"
                    " JOIN members m ON m.project_id = p.id"
                    " WHERE m.account = ?"
                    " AND (p.name LIKE ? OR p.description LIKE ?)",
                    (account, pattern, pattern)
                ).fetchone()[0]
                pagination = f" LIMIT {limit} OFFSET {offset}" if limit else ""
                rows = conn.execute(
                    "SELECT p.* FROM projects p"
                    " JOIN members m ON m.project_id = p.id"
                    " WHERE m.account = ?"
                    " AND (p.name LIKE ? OR p.description LIKE ?)"
                    " ORDER BY p.created_at DESC" + pagination,
                    (account, pattern, pattern)
                ).fetchall()
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM members WHERE account = ?",
                    (account,)
                ).fetchone()[0]
                pagination = f" LIMIT {limit} OFFSET {offset}" if limit else ""
                rows = conn.execute(
                    "SELECT p.* FROM projects p"
                    " JOIN members m ON m.project_id = p.id"
                    " WHERE m.account = ?"
                    " ORDER BY p.created_at DESC" + pagination,
                    (account,)
                ).fetchall()
            return {'total': total, 'projects': [self._project_row(conn, r) for r in rows]}

    def _project_row(self, conn, row) -> Dict:
        project_id = row['id']
        members = [r['account'] for r in conn.execute(
            "SELECT account FROM members WHERE project_id = ?", (project_id,)
        ).fetchall()]
        return {
            'id': project_id,
            'name': row['name'],
            'owner_account': row['owner_account'],
            'description': row['description'],
            'star_count': row['star_count'],
            'created_at': row['created_at'],
            'last_deployed_at': row['last_deployed_at'],
            'members': members,
        }

    def update_description(self, project_id: int, description: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET description = ? WHERE id = ?",
                (description, project_id)
            )

    def update_last_deployed_at(self, project_id: int):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET last_deployed_at = ? WHERE id = ?",
                (now, project_id)
            )

    def transfer_owner(self, project_id: int, old_owner: str, new_owner: str):
        with self._connect() as conn:
            # Add old owner as member
            conn.execute(
                "INSERT OR IGNORE INTO members (project_id, account) VALUES (?, ?)",
                (project_id, old_owner)
            )
            # Remove new owner from members if present
            conn.execute(
                "DELETE FROM members WHERE project_id = ? AND account = ?",
                (project_id, new_owner)
            )
            conn.execute(
                "UPDATE projects SET owner_account = ? WHERE id = ?",
                (new_owner, project_id)
            )

    def delete_project(self, project_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    # ── members ─────────────────────────────────────────────────────────────

    def set_members(self, project_id: int, members: List[str]):
        with self._connect() as conn:
            conn.execute("DELETE FROM members WHERE project_id = ?", (project_id,))
            for account in members:
                if account:
                    conn.execute(
                        "INSERT OR IGNORE INTO members (project_id, account) VALUES (?, ?)",
                        (project_id, account)
                    )

    # ── stars ────────────────────────────────────────────────────────────────

    def toggle_star(self, project_id: int, account: str) -> bool:
        """Toggle star. Returns True if starred, False if unstarred."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM stars WHERE project_id = ? AND account = ?",
                (project_id, account)
            ).fetchone()
            if row:
                conn.execute(
                    "DELETE FROM stars WHERE project_id = ? AND account = ?",
                    (project_id, account)
                )
                conn.execute(
                    "UPDATE projects SET star_count = star_count - 1 WHERE id = ?",
                    (project_id,)
                )
                return False
            else:
                conn.execute(
                    "INSERT INTO stars (project_id, account) VALUES (?, ?)",
                    (project_id, account)
                )
                conn.execute(
                    "UPDATE projects SET star_count = star_count + 1 WHERE id = ?",
                    (project_id,)
                )
                return True

    def is_starred(self, project_id: int, account: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM stars WHERE project_id = ? AND account = ?",
                (project_id, account)
            ).fetchone()
            return row is not None

