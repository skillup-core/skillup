"""
Skillup Group Management

Groups stored in the same account.db SQLite file.
Schema:
  groups            (id, name, description, image, image_small, image_mime, all_user, config, deleted, created_at, updated_at)
  group_admins      (group_id, user_id)
  group_users       (group_id, user_id)
  group_join_requests (group_id, user_id, requested_at)

Group IDs are UUIDs, never reused (deleted=1 rows are kept as tombstones).
"""

import base64
import json
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

from desktop.account import _get_connection


def init_group_db(db_path: str):
    """Create group tables if they don't exist."""
    import os
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = _get_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS groups (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                image       BLOB,
                image_small BLOB,
                image_mime  TEXT DEFAULT 'image/jpeg',
                all_user    INTEGER NOT NULL DEFAULT 0,
                config      TEXT NOT NULL DEFAULT '{}',
                deleted     INTEGER NOT NULL DEFAULT 0,
                created_at  INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_admins (
                group_id TEXT NOT NULL,
                user_id  TEXT NOT NULL,
                PRIMARY KEY (group_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS group_users (
                group_id TEXT NOT NULL,
                user_id  TEXT NOT NULL,
                PRIMARY KEY (group_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS group_join_requests (
                group_id     TEXT NOT NULL,
                user_id      TEXT NOT NULL,
                requested_at INTEGER NOT NULL,
                PRIMARY KEY (group_id, user_id)
            );
        """)
        # Migrate existing DB: add description column if missing
        cols = [row[1] for row in conn.execute("PRAGMA table_info(groups)").fetchall()]
        if 'description' not in cols:
            conn.execute("ALTER TABLE groups ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _group_row_to_dict(row) -> Dict[str, Any]:
    config = {}
    try:
        config = json.loads(row['config'] or '{}')
    except Exception:
        pass
    return {
        'id': row['id'],
        'name': row['name'],
        'description': row['description'] or '',
        'has_image': bool(row['image']),
        'image_mime': row['image_mime'] or 'image/jpeg',
        'all_user': bool(row['all_user']),
        'config': config,
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------

def create_group(db_path: str, creator_user_id: str, name: str,
                 description: str = '',
                 all_user: bool = False, config: Optional[dict] = None) -> Optional[str]:
    """
    Create a new group. Returns the new group_id (UUID) or None on failure.
    Creator is added to both group_admins and group_users.
    """
    group_id = str(uuid.uuid4())
    now = int(time.time())
    config_json = json.dumps(config or {'join_policy': 'free'})
    try:
        conn = _get_connection(db_path)
        try:
            conn.execute(
                "INSERT INTO groups (id, name, description, all_user, config, deleted, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (group_id, name, description, 1 if all_user else 0, config_json, now, now)
            )
            conn.execute(
                "INSERT INTO group_admins (group_id, user_id) VALUES (?, ?)",
                (group_id, creator_user_id)
            )
            conn.execute(
                "INSERT INTO group_users (group_id, user_id) VALUES (?, ?)",
                (group_id, creator_user_id)
            )
            conn.commit()
            return group_id
        finally:
            conn.close()
    except Exception:
        return None


def get_group(db_path: str, group_id: str) -> Optional[Dict[str, Any]]:
    """Return group info dict or None if not found / deleted."""
    try:
        conn = _get_connection(db_path)
        try:
            row = conn.execute(
                "SELECT * FROM groups WHERE id = ? AND deleted = 0", (group_id,)
            ).fetchone()
            if row is None:
                return None
            return _group_row_to_dict(row)
        finally:
            conn.close()
    except Exception:
        return None


def list_groups(db_path: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List active (non-deleted) groups.
    If user_id is given, only groups where user is a member (or all_user=1).
    """
    if not Path(db_path).exists():
        return []
    try:
        conn = _get_connection(db_path)
        try:
            if user_id:
                rows = conn.execute(
                    "SELECT g.* FROM groups g "
                    "WHERE g.deleted = 0 AND ("
                    "  g.all_user = 1 "
                    "  OR EXISTS (SELECT 1 FROM group_users gu WHERE gu.group_id = g.id AND gu.user_id = ?) "
                    ") ORDER BY g.name",
                    (user_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM groups WHERE deleted = 0 ORDER BY name"
                ).fetchall()
            return [_group_row_to_dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def update_group(db_path: str, group_id: str, admin_user_id: str,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 all_user: Optional[bool] = None,
                 config: Optional[dict] = None,
                 image: Optional[bytes] = None,
                 image_small: Optional[bytes] = None,
                 image_mime: Optional[str] = None) -> bool:
    """Update group fields. Only admins may call this."""
    if not _is_admin(db_path, group_id, admin_user_id):
        return False
    try:
        conn = _get_connection(db_path)
        try:
            updates = ['updated_at = ?']
            values = [int(time.time())]
            if name is not None:
                updates.append('name = ?')
                values.append(name)
            if description is not None:
                updates.append('description = ?')
                values.append(description)
            if all_user is not None:
                updates.append('all_user = ?')
                values.append(1 if all_user else 0)
            if config is not None:
                updates.append('config = ?')
                values.append(json.dumps(config))
            if image is not None:
                updates.append('image = ?')
                values.append(image)
            if image_small is not None:
                updates.append('image_small = ?')
                values.append(image_small)
            if image_mime is not None:
                updates.append('image_mime = ?')
                values.append(image_mime)
            values.append(group_id)
            conn.execute(
                f"UPDATE groups SET {', '.join(updates)} WHERE id = ? AND deleted = 0",
                values
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def delete_group(db_path: str, group_id: str, admin_user_id: str) -> bool:
    """Soft-delete a group (sets deleted=1). Only admins may call this."""
    if not _is_admin(db_path, group_id, admin_user_id):
        return False
    try:
        conn = _get_connection(db_path)
        try:
            conn.execute(
                "UPDATE groups SET deleted = 1, updated_at = ? WHERE id = ? AND deleted = 0",
                (int(time.time()), group_id)
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Membership helpers
# ---------------------------------------------------------------------------

def _is_admin(db_path: str, group_id: str, user_id: str) -> bool:
    try:
        conn = _get_connection(db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM group_admins WHERE group_id = ? AND user_id = ?",
                (group_id, user_id)
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def _is_member(db_path: str, group_id: str, user_id: str) -> bool:
    """Check membership (respects all_user flag)."""
    try:
        conn = _get_connection(db_path)
        try:
            grp = conn.execute(
                "SELECT all_user FROM groups WHERE id = ? AND deleted = 0", (group_id,)
            ).fetchone()
            if grp is None:
                return False
            if grp['all_user']:
                return True
            row = conn.execute(
                "SELECT 1 FROM group_users WHERE group_id = ? AND user_id = ?",
                (group_id, user_id)
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def get_group_members(db_path: str, group_id: str) -> List[Dict[str, Any]]:
    """
    Return list of members with is_admin flag.
    For all_user groups, reads from accounts table.
    """
    try:
        conn = _get_connection(db_path)
        try:
            grp = conn.execute(
                "SELECT all_user FROM groups WHERE id = ? AND deleted = 0", (group_id,)
            ).fetchone()
            if grp is None:
                return []

            if grp['all_user']:
                rows = conn.execute(
                    "SELECT a.id as user_id, a.name, a.photo_small, a.photo_mime, "
                    "  CASE WHEN ga.user_id IS NOT NULL THEN 1 ELSE 0 END as is_admin "
                    "FROM accounts a "
                    "LEFT JOIN group_admins ga ON ga.group_id = ? AND ga.user_id = a.id "
                    "WHERE a.activated = 1 ORDER BY a.id",
                    (group_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT gu.user_id, a.name, a.photo_small, a.photo_mime, "
                    "  CASE WHEN ga.user_id IS NOT NULL THEN 1 ELSE 0 END as is_admin "
                    "FROM group_users gu "
                    "LEFT JOIN accounts a ON a.id = gu.user_id "
                    "LEFT JOIN group_admins ga ON ga.group_id = ? AND ga.user_id = gu.user_id "
                    "WHERE gu.group_id = ? ORDER BY gu.user_id",
                    (group_id, group_id)
                ).fetchall()

            result = []
            for r in rows:
                avatar = None
                if r['photo_small']:
                    avatar = base64.b64encode(bytes(r['photo_small'])).decode('ascii')
                result.append({
                    'user_id': r['user_id'],
                    'display_name': r['name'] or r['user_id'],
                    'avatar_small': avatar,
                    'avatar_mime': r['photo_mime'] or 'image/jpeg',
                    'is_admin': bool(r['is_admin']),
                })
            return result
        finally:
            conn.close()
    except Exception:
        return []


def add_member(db_path: str, group_id: str, admin_user_id: str, target_user_id: str) -> Dict[str, Any]:
    """Admin adds a user to the group."""
    if not _is_admin(db_path, group_id, admin_user_id):
        return {'success': False, 'error': 'not_admin'}
    try:
        conn = _get_connection(db_path)
        try:
            grp = conn.execute(
                "SELECT id FROM groups WHERE id = ? AND deleted = 0", (group_id,)
            ).fetchone()
            if grp is None:
                return {'success': False, 'error': 'group_not_found'}
            conn.execute(
                "INSERT OR IGNORE INTO group_users (group_id, user_id) VALUES (?, ?)",
                (group_id, target_user_id)
            )
            # Remove any pending join request for this user
            conn.execute(
                "DELETE FROM group_join_requests WHERE group_id = ? AND user_id = ?",
                (group_id, target_user_id)
            )
            conn.commit()
            return {'success': True}
        finally:
            conn.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}


def remove_member(db_path: str, group_id: str, actor_user_id: str,
                  target_user_id: str) -> Dict[str, Any]:
    """
    Remove a user from the group.
    - Any member may remove themselves (self-leave).
    - Admins may remove any non-admin member.
    - Last admin cannot be removed.
    """
    is_self = actor_user_id == target_user_id
    is_admin_actor = _is_admin(db_path, group_id, actor_user_id)

    if not is_self and not is_admin_actor:
        return {'success': False, 'error': 'not_admin'}

    try:
        conn = _get_connection(db_path)
        try:
            grp = conn.execute(
                "SELECT id FROM groups WHERE id = ? AND deleted = 0", (group_id,)
            ).fetchone()
            if grp is None:
                return {'success': False, 'error': 'group_not_found'}

            # Check if target is admin
            target_is_admin = conn.execute(
                "SELECT 1 FROM group_admins WHERE group_id = ? AND user_id = ?",
                (group_id, target_user_id)
            ).fetchone() is not None

            # Non-admin actor cannot remove an admin
            if not is_admin_actor and target_is_admin:
                return {'success': False, 'error': 'cannot_remove_admin'}

            # Prevent removing the last admin
            if target_is_admin:
                admin_count = conn.execute(
                    "SELECT COUNT(*) FROM group_admins WHERE group_id = ?", (group_id,)
                ).fetchone()[0]
                if admin_count <= 1:
                    return {'success': False, 'error': 'last_admin'}

            conn.execute(
                "DELETE FROM group_users WHERE group_id = ? AND user_id = ?",
                (group_id, target_user_id)
            )
            conn.execute(
                "DELETE FROM group_admins WHERE group_id = ? AND user_id = ?",
                (group_id, target_user_id)
            )
            conn.commit()
            return {'success': True}
        finally:
            conn.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}


def grant_admin(db_path: str, group_id: str, admin_user_id: str,
                target_user_id: str) -> Dict[str, Any]:
    """Grant admin role to a group member."""
    if not _is_admin(db_path, group_id, admin_user_id):
        return {'success': False, 'error': 'not_admin'}
    if not _is_member(db_path, group_id, target_user_id):
        return {'success': False, 'error': 'not_member'}
    try:
        conn = _get_connection(db_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO group_admins (group_id, user_id) VALUES (?, ?)",
                (group_id, target_user_id)
            )
            conn.commit()
            return {'success': True}
        finally:
            conn.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}


def revoke_admin(db_path: str, group_id: str, admin_user_id: str,
                 target_user_id: str) -> Dict[str, Any]:
    """Revoke admin role from a group member. Last admin cannot be revoked."""
    if not _is_admin(db_path, group_id, admin_user_id):
        return {'success': False, 'error': 'not_admin'}
    try:
        conn = _get_connection(db_path)
        try:
            admin_count = conn.execute(
                "SELECT COUNT(*) FROM group_admins WHERE group_id = ?", (group_id,)
            ).fetchone()[0]
            if admin_count <= 1:
                return {'success': False, 'error': 'last_admin'}
            conn.execute(
                "DELETE FROM group_admins WHERE group_id = ? AND user_id = ?",
                (group_id, target_user_id)
            )
            conn.commit()
            return {'success': True}
        finally:
            conn.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Join requests
# ---------------------------------------------------------------------------

def request_join(db_path: str, group_id: str, user_id: str) -> Dict[str, Any]:
    """
    User requests to join a group.
    - free policy: added immediately.
    - approve policy: request queued for admin review.
    """
    grp = get_group(db_path, group_id)
    if grp is None:
        return {'success': False, 'error': 'group_not_found'}
    if _is_member(db_path, group_id, user_id):
        return {'success': False, 'error': 'already_member'}

    policy = grp.get('config', {}).get('join_policy', 'free')
    try:
        conn = _get_connection(db_path)
        try:
            if policy == 'free':
                conn.execute(
                    "INSERT OR IGNORE INTO group_users (group_id, user_id) VALUES (?, ?)",
                    (group_id, user_id)
                )
                conn.commit()
                return {'success': True, 'joined': True}
            else:
                # approve: queue request
                now = int(time.time())
                conn.execute(
                    "INSERT OR IGNORE INTO group_join_requests (group_id, user_id, requested_at) "
                    "VALUES (?, ?, ?)",
                    (group_id, user_id, now)
                )
                conn.commit()
                return {'success': True, 'joined': False, 'pending': True}
        finally:
            conn.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}


def list_join_requests(db_path: str, group_id: str) -> List[Dict[str, Any]]:
    """Return pending join requests for a group."""
    try:
        conn = _get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT r.user_id, r.requested_at, a.name, a.photo_small, a.photo_mime "
                "FROM group_join_requests r "
                "LEFT JOIN accounts a ON a.id = r.user_id "
                "WHERE r.group_id = ? ORDER BY r.requested_at",
                (group_id,)
            ).fetchall()
            result = []
            for r in rows:
                avatar = None
                if r['photo_small']:
                    avatar = base64.b64encode(bytes(r['photo_small'])).decode('ascii')
                result.append({
                    'user_id': r['user_id'],
                    'display_name': r['name'] or r['user_id'],
                    'avatar_small': avatar,
                    'avatar_mime': r['photo_mime'] or 'image/jpeg',
                    'requested_at': r['requested_at'],
                })
            return result
        finally:
            conn.close()
    except Exception:
        return []


def list_all_pending_join_requests(db_path: str, admin_user_id: str) -> List[Dict[str, Any]]:
    """
    Return all pending join requests across all groups where admin_user_id is admin.
    Used at startup to notify the admin.
    """
    try:
        conn = _get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT r.group_id, r.user_id, r.requested_at, "
                "  g.name as group_name, a.name as user_name, "
                "  a.photo_small, a.photo_mime "
                "FROM group_join_requests r "
                "JOIN groups g ON g.id = r.group_id AND g.deleted = 0 "
                "JOIN group_admins ga ON ga.group_id = r.group_id AND ga.user_id = ? "
                "LEFT JOIN accounts a ON a.id = r.user_id "
                "ORDER BY r.requested_at",
                (admin_user_id,)
            ).fetchall()
            result = []
            for r in rows:
                avatar = None
                if r['photo_small']:
                    avatar = base64.b64encode(bytes(r['photo_small'])).decode('ascii')
                result.append({
                    'group_id': r['group_id'],
                    'group_name': r['group_name'],
                    'user_id': r['user_id'],
                    'display_name': r['user_name'] or r['user_id'],
                    'avatar_small': avatar,
                    'avatar_mime': r['photo_mime'] or 'image/jpeg',
                    'requested_at': r['requested_at'],
                })
            return result
        finally:
            conn.close()
    except Exception:
        return []


def approve_join_request(db_path: str, group_id: str, admin_user_id: str,
                         target_user_id: str) -> Dict[str, Any]:
    """Approve a pending join request."""
    if not _is_admin(db_path, group_id, admin_user_id):
        return {'success': False, 'error': 'not_admin'}
    try:
        conn = _get_connection(db_path)
        try:
            req = conn.execute(
                "SELECT 1 FROM group_join_requests WHERE group_id = ? AND user_id = ?",
                (group_id, target_user_id)
            ).fetchone()
            if req is None:
                return {'success': False, 'error': 'request_not_found'}
            conn.execute(
                "INSERT OR IGNORE INTO group_users (group_id, user_id) VALUES (?, ?)",
                (group_id, target_user_id)
            )
            conn.execute(
                "DELETE FROM group_join_requests WHERE group_id = ? AND user_id = ?",
                (group_id, target_user_id)
            )
            conn.commit()
            return {'success': True}
        finally:
            conn.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}


def reject_join_request(db_path: str, group_id: str, admin_user_id: str,
                        target_user_id: str) -> Dict[str, Any]:
    """Reject (delete) a pending join request."""
    if not _is_admin(db_path, group_id, admin_user_id):
        return {'success': False, 'error': 'not_admin'}
    try:
        conn = _get_connection(db_path)
        try:
            conn.execute(
                "DELETE FROM group_join_requests WHERE group_id = ? AND user_id = ?",
                (group_id, target_user_id)
            )
            conn.commit()
            return {'success': True}
        finally:
            conn.close()
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_group_image(db_path: str, group_id: str, size: str = 'small'):
    """Return (bytes, mime) for group image, or (None, None)."""
    col = 'image_small' if size == 'small' else 'image'
    try:
        conn = _get_connection(db_path)
        try:
            row = conn.execute(
                f"SELECT {col}, image_mime FROM groups WHERE id = ? AND deleted = 0",
                (group_id,)
            ).fetchone()
            if row and row[0]:
                return bytes(row[0]), row['image_mime'] or 'image/jpeg'
            return None, None
        finally:
            conn.close()
    except Exception:
        return None, None
