"""
WorkHub SQLite database - connection, schema, CRUD.
One connection per call (thread-safe by default, NFS-safe with journal_mode=DELETE).
"""

import json
import os
import re
import sqlite3
import sys
import threading
import uuid
import zlib
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()

_IMG_RE = re.compile(r'!\[[^\]]*\]\(data:image/[^)]+\)')
_MENTION_RE = re.compile(r'@\[([^|]*)\|([^\]]*)\]')
_DOC_LINK_RE = re.compile(r'\[\[(\d+)\|([^\]]*)\]\]')
_DOC_LINK_ID_RE = re.compile(r'\[\[(\d+)\|')

_HIST_COMPRESS_THRESHOLD = 100  # bytes; below this, compression overhead isn't worth it


def _compress_body(body: str) -> bytes:
    """Compress history body. Returns bytes with a 1-byte prefix: 0x01=zlib, 0x00=plain."""
    raw = body.encode('utf-8')
    if len(raw) < _HIST_COMPRESS_THRESHOLD:
        return b'\x00' + raw
    comp = zlib.compress(raw)
    if len(comp) < len(raw):
        return b'\x01' + comp
    return b'\x00' + raw


def _decompress_body(data) -> str:
    """Decompress history body. Handles legacy plain-text str rows transparently."""
    if isinstance(data, str):
        return data  # legacy row stored as TEXT before compression was added
    if not data:
        return ''
    if data[:1] == b'\x01':
        return zlib.decompress(data[1:]).decode('utf-8')
    return data[1:].decode('utf-8')  # b'\x00' prefix = stored plain


def _fts_body(body: str) -> str:
    """Extract indexable text from body and strip embedded image data URLs."""
    try:
        obj = json.loads(body)
        # Collect all string leaf values (works for note, command, todo, checklist)
        def _collect(v):
            if isinstance(v, str):
                return v
            if isinstance(v, list):
                return ' '.join(_collect(i) for i in v)
            if isinstance(v, dict):
                return ' '.join(_collect(v2) for v2 in v.values())
            return ''
        body = _collect(obj)
    except (ValueError, TypeError):
        pass
    body = _MENTION_RE.sub(lambda m: m.group(2), body)
    body = _DOC_LINK_RE.sub(lambda m: m.group(2), body)
    return _IMG_RE.sub('', body)


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def _access_cond(user_id: str, group_ids: list, alias: str = 'w',
                 channel_ids: list = None) -> tuple:
    """Returns (WHERE fragment, params list) for access control.

    Public docs (channel_id IS NULL): visibility-based check as before.
    Channel docs: user must be a member of the channel (channel_id IN channel_ids).
    """
    a = alias + '.'
    if group_ids:
        ph = ','.join('?' * len(group_ids))
        pub_cond = (
            f"({a}owner_id = ? OR {a}visibility = 'all' "
            f"OR ({a}visibility = 'group' AND {a}group_id IN ({ph})))"
        )
        pub_params = [user_id] + list(group_ids)
    else:
        pub_cond = f"({a}owner_id = ? OR {a}visibility = 'all')"
        pub_params = [user_id]

    pub_full = f"({a}channel_id IS NULL AND {pub_cond})"

    if channel_ids:
        ch_ph = ','.join('?' * len(channel_ids))
        cond = f"({pub_full} OR {a}channel_id IN ({ch_ph}))"
        params = pub_params + list(channel_ids)
    else:
        cond = pub_full
        params = pub_params

    return cond, params


def init_db(db_path: str, current_user_id: str = '') -> bool:
    """Create/migrate schema. Returns True if FTS5 is available."""
    with _lock:
        conn = _connect(db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS works (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    title            TEXT NOT NULL DEFAULT '',
                    template         TEXT NOT NULL,
                    body             TEXT NOT NULL DEFAULT '',
                    tags             TEXT NOT NULL DEFAULT '',
                    owner_id         TEXT NOT NULL DEFAULT '',
                    visibility       TEXT NOT NULL DEFAULT 'all',
                    group_id         TEXT,
                    owner_write_only INTEGER NOT NULL DEFAULT 1,
                    channel_id       TEXT,
                    version          INTEGER NOT NULL DEFAULT 1,
                    created_at       TEXT NOT NULL,
                    updated_at       TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS channels (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    admin_id   TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS channel_members (
                    channel_id  TEXT NOT NULL,
                    member_type TEXT NOT NULL,
                    member_id   TEXT NOT NULL,
                    PRIMARY KEY (channel_id, member_type, member_id)
                );
            """)

            # Migrate: add columns if missing
            existing = {row[1] for row in conn.execute("PRAGMA table_info(works)")}
            migrations = [
                ('owner_id',         "ALTER TABLE works ADD COLUMN owner_id TEXT NOT NULL DEFAULT ''"),
                ('visibility',       "ALTER TABLE works ADD COLUMN visibility TEXT NOT NULL DEFAULT 'me'"),
                ('group_id',         "ALTER TABLE works ADD COLUMN group_id TEXT"),
                ('owner_write_only', "ALTER TABLE works ADD COLUMN owner_write_only INTEGER NOT NULL DEFAULT 1"),
                ('channel_id',       "ALTER TABLE works ADD COLUMN channel_id TEXT"),
                ('version',          "ALTER TABLE works ADD COLUMN version INTEGER NOT NULL DEFAULT 1"),
            ]
            for col, sql in migrations:
                if col not in existing:
                    conn.execute(sql)

            # Backfill: rows with empty owner_id become owned by current user
            if current_user_id:
                conn.execute(
                    "UPDATE works SET owner_id = ? WHERE owner_id = ''",
                    (current_user_id,)
                )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS works_history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_id    INTEGER NOT NULL,
                    body       TEXT NOT NULL DEFAULT '',
                    saved_by   TEXT NOT NULL DEFAULT '',
                    edited_at  TEXT NOT NULL,
                    title      TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS work_links (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_id    INTEGER NOT NULL,
                    linked_id  INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(work_id, linked_id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_work_links_work_id "
                "ON work_links(work_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_work_links_linked_id "
                "ON work_links(linked_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_works_history_work_id "
                "ON works_history(work_id, id DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_works_channel_id "
                "ON works(channel_id)"
            )
            # Migrate: add title column if missing
            hist_cols = {row[1] for row in conn.execute("PRAGMA table_info(works_history)")}
            if 'title' not in hist_cols:
                conn.execute("ALTER TABLE works_history ADD COLUMN title TEXT NOT NULL DEFAULT ''")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_action_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL,
                    action     TEXT NOT NULL,
                    work_id    INTEGER,
                    work_title TEXT NOT NULL DEFAULT '',
                    work_type  TEXT NOT NULL DEFAULT '',
                    detail     TEXT NOT NULL DEFAULT '',
                    history_id INTEGER,
                    acted_at   TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_action_log_user "
                "ON user_action_log(user_id, id DESC)"
            )
            conn.commit()

            fts5_ok = False
            try:
                # Migrate: drop old content-based FTS5 and its triggers if present.
                # Old table had content='works' in its DDL; new standalone table does not.
                old = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='works_fts'"
                ).fetchone()
                if old and old['sql'] and 'content=' in old['sql']:
                    conn.executescript("""
                        DROP TRIGGER IF EXISTS works_ai;
                        DROP TRIGGER IF EXISTS works_ad;
                        DROP TRIGGER IF EXISTS works_au;
                        DROP TABLE IF EXISTS works_fts;
                    """)

                # Standalone FTS5: Python manages index updates via _fts_body() to strip images.
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5("
                    "title, body, tags, tokenize='unicode61')"
                )

                # Rebuild index when table was just created (or dropped and recreated above).
                fts_count = conn.execute("SELECT COUNT(*) FROM works_fts").fetchone()[0]
                if fts_count == 0:
                    rows = conn.execute("SELECT id, title, body, tags FROM works").fetchall()
                    if rows:
                        conn.executemany(
                            "INSERT INTO works_fts(rowid, title, body, tags) VALUES (?, ?, ?, ?)",
                            [(r['id'], r['title'], _fts_body(r['body']), r['tags']) for r in rows]
                        )

                conn.commit()
                fts5_ok = True
            except sqlite3.OperationalError:
                pass

            conn.commit()
        finally:
            conn.close()
    try:
        os.chmod(db_path, 0o666)
    except OSError:
        pass
    return fts5_ok


_WORK_SELECT = (
    "SELECT w.id, w.title, w.template, w.tags, "
    "w.owner_id, w.visibility, w.group_id, w.owner_write_only, w.channel_id, w.created_at, w.updated_at "
    "FROM works w "
)


def work_list(db_path: str, user_id: str, group_ids: list, limit: int = 50,
              channel_id: str = None, channel_ids: list = None) -> list:
    if channel_ids is None:
        channel_ids = []
    with _lock:
        conn = _connect(db_path)
        try:
            if channel_id is not None:
                # Private channel: verify membership then filter by channel
                if channel_id not in channel_ids:
                    return []
                sql = (
                    _WORK_SELECT +
                    "WHERE w.channel_id=? ORDER BY w.updated_at DESC LIMIT ?"
                )
                rows = conn.execute(sql, [channel_id, limit]).fetchall()
            else:
                # Public channel: visibility-based access, channel_id IS NULL
                pub_cond, pub_params = _access_cond(user_id, group_ids)
                # pub_cond already includes channel_id IS NULL
                sql = (
                    _WORK_SELECT +
                    f"WHERE {pub_cond} ORDER BY w.updated_at DESC LIMIT ?"
                )
                rows = conn.execute(sql, pub_params + [limit]).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def work_list_my(db_path: str, user_id: str, limit: int = 50) -> list:
    with _lock:
        conn = _connect(db_path)
        try:
            sql = (
                _WORK_SELECT +
                "WHERE w.owner_id = ? ORDER BY w.updated_at DESC LIMIT ?"
            )
            rows = conn.execute(sql, [user_id, limit]).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def work_get(db_path: str, work_id: int, user_id: str, group_ids: list,
             channel_ids: list = None) -> tuple:
    """Returns (item_dict, None) or (None, error_string)."""
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    with _lock:
        conn = _connect(db_path)
        try:
            exists = conn.execute("SELECT id FROM works WHERE id=?", (work_id,)).fetchone()
            if not exists:
                return None, 'not_found'
            sql = f"SELECT * FROM works w WHERE w.id=? AND {cond}"
            row = conn.execute(sql, [work_id] + params).fetchone()
            if row is None:
                return None, 'forbidden'
            return dict(row), None
        finally:
            conn.close()


def work_get_titles(db_path: str, ids: list, user_id: str, group_ids: list,
                    channel_ids: list = None) -> list:
    """Return [{id, title, template}] for each accessible id. Missing/forbidden ids are omitted."""
    if not ids:
        return []
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    placeholders = ','.join('?' for _ in ids)
    sql = f"SELECT w.id, w.title, w.template FROM works w WHERE w.id IN ({placeholders}) AND {cond}"
    with _lock:
        conn = _connect(db_path)
        try:
            rows = conn.execute(sql, list(ids) + params).fetchall()
            return [{'id': r['id'], 'title': r['title'], 'template': r['template']} for r in rows]
        finally:
            conn.close()


def work_create(db_path: str, template: str, owner_id: str,
                title: str = '', body: str = '', tags: str = '',
                history_body: str = '', action_history_limit: int = 200,
                channel_id: str = None) -> tuple:
    now = _now()
    with _lock:
        conn = _connect(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO works "
                "(title, template, body, tags, owner_id, visibility, group_id, channel_id, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'all', NULL, ?, 1, ?, ?)",
                (title, template, body, tags, owner_id, channel_id, now, now)
            )
            new_id = cur.lastrowid
            try:
                conn.execute(
                    "INSERT INTO works_fts(rowid, title, body, tags) VALUES (?, ?, ?, ?)",
                    (new_id, title, _fts_body(body), tags)
                )
            except sqlite3.OperationalError:
                pass
            if history_body:
                conn.execute(
                    "INSERT INTO works_history(work_id, body, saved_by, edited_at, title) VALUES (?, ?, ?, ?, ?)",
                    (new_id, _compress_body(history_body), owner_id, now, title)
                )
            _log_action(conn, owner_id, 'create', new_id, title, template,
                        action_history_limit=action_history_limit)
            conn.commit()
            return new_id, now
        finally:
            conn.close()


def work_save(db_path: str, work_id: int, user_id: str, group_ids: list,
              title: str, body: str, tags: str,
              visibility: str, group_id, version: int,
              owner_write_only: int = 1,
              skip_body: bool = False,
              history_body: str = '', history_title: str = '',
              autosave_count: int = 10,
              action_history_limit: int = 200,
              channel_ids: list = None) -> dict:
    if channel_ids is None:
        channel_ids = []
    now = _now()
    with _lock:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT owner_id, visibility, group_id, owner_write_only, channel_id, version, body, tags, template FROM works WHERE id=?",
                (work_id,)
            ).fetchone()
            if row is None:
                return {'success': False, 'error': 'not_found'}

            is_owner = (row['owner_id'] == user_id)
            row_channel_id = row['channel_id']
            if row_channel_id:
                # Channel doc: access via channel membership
                has_access = is_owner or row_channel_id in channel_ids
            else:
                has_access = (
                    is_owner
                    or row['visibility'] == 'all'
                    or (row['visibility'] == 'group' and row['group_id'] in group_ids)
                )
            if not has_access:
                return {'success': False, 'error': 'forbidden'}

            # Non-owner cannot edit if owner_write_only=1
            if not is_owner and row['owner_write_only'] == 1:
                return {'success': False, 'error': 'forbidden'}

            # Only owner can change sharing settings
            if is_owner:
                if row_channel_id:
                    # Channel doc: visibility/group_id are fixed; only owner_write_only changes
                    new_visibility = row['visibility']
                    new_group_id = row['group_id']
                    new_owner_write_only = 1 if owner_write_only else 0
                else:
                    new_visibility = visibility if visibility in ('me', 'group', 'all') else row['visibility']
                    new_group_id = group_id if new_visibility == 'group' else None
                    # Validate group membership
                    if new_visibility == 'group':
                        if not new_group_id or new_group_id not in group_ids:
                            return {'success': False, 'error': 'invalid_group'}
                    # visibility='me' always forces owner_write_only=1
                    if new_visibility == 'me':
                        new_owner_write_only = 1
                    else:
                        new_owner_write_only = 1 if owner_write_only else 0
            else:
                new_visibility = row['visibility']
                new_group_id = row['group_id']
                new_owner_write_only = row['owner_write_only']

            if skip_body:
                # body를 건드리지 않고 title/tags만 저장. 버전 체크 없음.
                conn.execute(
                    "UPDATE works SET title=?, tags=?, visibility=?, group_id=?, "
                    "owner_write_only=?, updated_at=?, version=version+1 WHERE id=?",
                    (title, tags, new_visibility, new_group_id, new_owner_write_only, now, work_id)
                )
                updated = conn.execute(
                    "SELECT version, body FROM works WHERE id=?", (work_id,)
                ).fetchone()
                new_version = updated['version']
                current_body = updated['body'] or ''
                try:
                    conn.execute("DELETE FROM works_fts WHERE rowid=?", (work_id,))
                    conn.execute(
                        "INSERT INTO works_fts(rowid, title, body, tags) VALUES (?, ?, ?, ?)",
                        (work_id, title, _fts_body(current_body), tags)
                    )
                except sqlite3.OperationalError:
                    pass
                if history_body:
                    hcur = conn.execute(
                        "INSERT INTO works_history(work_id, body, saved_by, edited_at, title) VALUES (?, ?, ?, ?, ?)",
                        (work_id, _compress_body(history_body), user_id, now, history_title or title)
                    )
                    conn.execute(
                        "DELETE FROM works_history WHERE work_id=? AND id NOT IN ("
                        "SELECT id FROM works_history WHERE work_id=? ORDER BY id DESC LIMIT ?)",
                        (work_id, work_id, autosave_count)
                    )
                    _log_action(conn, user_id, 'edit', work_id, history_title or title,
                                row['template'] if row else '',
                                history_id=hcur.lastrowid,
                                action_history_limit=action_history_limit)
                if row and tags != (row['tags'] or ''):
                    _log_action(conn, user_id, 'tag', work_id, title, row['template'] or '',
                                action_history_limit=action_history_limit)
                if is_owner and row and (
                    new_visibility != row['visibility']
                    or new_group_id != row['group_id']
                    or new_owner_write_only != row['owner_write_only']
                ):
                    _log_action(conn, user_id, 'share', work_id, title, row['template'] or '',
                                detail=new_visibility,
                                action_history_limit=action_history_limit)
                conn.commit()
                return {'success': True, 'version': new_version, 'updated_at': now}

            cur = conn.execute(
                "UPDATE works SET title=?, body=?, tags=?, visibility=?, group_id=?, "
                "owner_write_only=?, updated_at=?, version=version+1 WHERE id=? AND version=?",
                (title, body, tags, new_visibility, new_group_id, new_owner_write_only, now, work_id, version)
            )
            if cur.rowcount == 0:
                server_row = conn.execute("SELECT * FROM works WHERE id=?", (work_id,)).fetchone()
                return {
                    'success': False,
                    'error': 'conflict',
                    'server_item': dict(server_row) if server_row else None,
                }

            try:
                conn.execute("DELETE FROM works_fts WHERE rowid=?", (work_id,))
                conn.execute(
                    "INSERT INTO works_fts(rowid, title, body, tags) VALUES (?, ?, ?, ?)",
                    (work_id, title, _fts_body(body), tags)
                )
            except sqlite3.OperationalError:
                pass

            if history_body:
                hcur = conn.execute(
                    "INSERT INTO works_history(work_id, body, saved_by, edited_at, title) VALUES (?, ?, ?, ?, ?)",
                    (work_id, _compress_body(history_body), user_id, now, history_title or title)
                )
                conn.execute(
                    "DELETE FROM works_history WHERE work_id=? AND id NOT IN ("
                    "  SELECT id FROM works_history WHERE work_id=? ORDER BY id DESC LIMIT ?"
                    ")",
                    (work_id, work_id, autosave_count)
                )
                _log_action(conn, user_id, 'edit', work_id, history_title or title,
                            row['template'] if row else '',
                            history_id=hcur.lastrowid,
                            action_history_limit=action_history_limit)

            if row and tags != (row['tags'] or ''):
                _log_action(conn, user_id, 'tag', work_id, title, row['template'] or '',
                            action_history_limit=action_history_limit)
            if is_owner and row and (
                new_visibility != row['visibility']
                or new_group_id != row['group_id']
                or new_owner_write_only != row['owner_write_only']
            ):
                _log_action(conn, user_id, 'share', work_id, title, row['template'] or '',
                            detail=new_visibility,
                            action_history_limit=action_history_limit)
            conn.commit()
            return {'success': True, 'version': version + 1, 'updated_at': now, 'prev_body': row['body'] if row else ''}
        finally:
            conn.close()


def _make_copy_title(title: str) -> str:
    import re
    # Strip trailing copy suffix: " (사본)" or " (사본N)" where N >= 2
    base = re.sub(r'\s*\(사본(\d+)?\)\s*$', '', title).rstrip()
    m = re.search(r'\s*\(사본(\d+)?\)\s*$', title)
    if not m:
        return base + ' (사본)'
    n = int(m.group(1)) if m.group(1) else 1
    return base + f' (사본{n + 1})'


def work_copy(db_path: str, work_id: int, user_id: str, group_ids: list,
              action_history_limit: int = 200, channel_ids: list = None) -> dict:
    """Copy a document the caller can access. Returns {success, id, updated_at} or {success, error}."""
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    now = _now()
    with _lock:
        conn = _connect(db_path)
        try:
            sql = f"SELECT w.* FROM works w WHERE w.id=? AND {cond}"
            row = conn.execute(sql, [work_id] + params).fetchone()
            if row is None:
                exists = conn.execute("SELECT id FROM works WHERE id=?", (work_id,)).fetchone()
                return {'success': False, 'error': 'not_found' if not exists else 'forbidden'}
            new_title = _make_copy_title(row['title'] or '')
            cur = conn.execute(
                "INSERT INTO works "
                "(title, template, body, tags, owner_id, visibility, group_id, channel_id, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'me', NULL, NULL, 1, ?, ?)",
                (new_title, row['template'], row['body'], row['tags'], user_id, now, now)
            )
            new_id = cur.lastrowid
            try:
                conn.execute(
                    "INSERT INTO works_fts(rowid, title, body, tags) VALUES (?, ?, ?, ?)",
                    (new_id, new_title, _fts_body(row['body']), row['tags'])
                )
            except sqlite3.OperationalError:
                pass
            _log_action(conn, user_id, 'copy', new_id, new_title, row['template'] or '',
                        detail=str(work_id), action_history_limit=action_history_limit)
            conn.commit()
            return {'success': True, 'id': new_id, 'updated_at': now, 'template': row['template'],
                    'title': new_title, 'body': row['body'], 'tags': row['tags']}
        finally:
            conn.close()


def work_delete(db_path: str, work_id: int, user_id: str,
                action_history_limit: int = 200) -> dict:
    with _lock:
        conn = _connect(db_path)
        try:
            row = conn.execute("SELECT owner_id, title, template FROM works WHERE id=?", (work_id,)).fetchone()
            if row is None:
                return {'success': False, 'error': 'not_found'}
            if row['owner_id'] != user_id:
                return {'success': False, 'error': 'forbidden'}
            work_title = row['title'] or ''
            work_type = row['template'] or ''
            conn.execute("DELETE FROM works WHERE id=?", (work_id,))
            conn.execute("DELETE FROM works_history WHERE work_id=?", (work_id,))
            conn.execute(
                "DELETE FROM work_links WHERE work_id=? OR linked_id=?",
                (work_id, work_id)
            )
            try:
                conn.execute("DELETE FROM works_fts WHERE rowid=?", (work_id,))
            except sqlite3.OperationalError:
                pass
            _log_action(conn, user_id, 'delete', work_id, work_title, work_type,
                        action_history_limit=action_history_limit)
            conn.commit()
            return {'success': True}
        finally:
            conn.close()


def work_history_save(db_path: str, work_id: int, body: str, saved_by: str,
                      edited_at: str, autosave_count: int = 10, title: str = '',
                      action_history_limit: int = 200) -> dict:
    """Save a history entry for work_id and trim to autosave_count entries.

    Also logs an 'edit' action_log entry and returns history_id in the response.
    """
    with _lock:
        conn = _connect(db_path)
        try:
            work_row = conn.execute(
                "SELECT id, template FROM works WHERE id=?", (work_id,)
            ).fetchone()
            if not work_row:
                return {'success': False, 'error': 'not_found'}
            cur = conn.execute(
                "INSERT INTO works_history(work_id, body, saved_by, edited_at, title) VALUES (?, ?, ?, ?, ?)",
                (work_id, _compress_body(body), saved_by, edited_at, title)
            )
            history_id = cur.lastrowid
            # Trim to autosave_count: keep the newest N entries
            conn.execute(
                "DELETE FROM works_history WHERE work_id=? AND id NOT IN ("
                "  SELECT id FROM works_history WHERE work_id=? ORDER BY id DESC LIMIT ?"
                ")",
                (work_id, work_id, autosave_count)
            )
            # Log edit action (history_save is only called when body changed)
            _log_action(conn, saved_by, 'edit', work_id, title, work_row['template'] or '',
                        history_id=history_id, action_history_limit=action_history_limit)
            conn.commit()
            return {'success': True, 'history_id': history_id}
        finally:
            conn.close()


def work_history_list(db_path: str, work_id: int, user_id: str, group_ids: list,
                      channel_ids: list = None) -> tuple:
    """Returns (list_of_entries, None) or (None, error_string)."""
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    with _lock:
        conn = _connect(db_path)
        try:
            sql = f"SELECT w.id FROM works w WHERE w.id=? AND {cond}"
            row = conn.execute(sql, [work_id] + params).fetchone()
            if row is None:
                exists = conn.execute("SELECT id FROM works WHERE id=?", (work_id,)).fetchone()
                return None, ('not_found' if not exists else 'forbidden')
            rows = conn.execute(
                "SELECT id, saved_by, edited_at FROM works_history "
                "WHERE work_id=? ORDER BY id DESC",
                (work_id,)
            ).fetchall()
            return [dict(r) for r in rows], None
        finally:
            conn.close()


def work_history_get(db_path: str, history_id: int, user_id: str, group_ids: list,
                     channel_ids: list = None) -> tuple:
    """Returns (entry_dict_with_body, None) or (None, error_string)."""
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    with _lock:
        conn = _connect(db_path)
        try:
            h = conn.execute(
                "SELECT h.id, h.work_id, h.body, h.saved_by, h.edited_at, h.title "
                "FROM works_history h WHERE h.id=?",
                (history_id,)
            ).fetchone()
            if h is None:
                return None, 'not_found'
            sql = f"SELECT w.id FROM works w WHERE w.id=? AND {cond}"
            row = conn.execute(sql, [h['work_id']] + params).fetchone()
            if row is None:
                return None, 'forbidden'
            entry = dict(h)
            entry['body'] = _decompress_body(entry['body'])
            return entry, None
        finally:
            conn.close()


def tag_list(db_path: str, user_id: str, group_ids: list,
             channel_ids: list = None) -> list:
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    with _lock:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                f"SELECT w.tags FROM works w WHERE {cond} AND w.tags != ''",
                params
            ).fetchall()
        finally:
            conn.close()
    freq: dict = {}
    for row in rows:
        for tag in row['tags'].split(','):
            tag = tag.strip()
            if tag:
                freq[tag] = freq.get(tag, 0) + 1
    return sorted(freq.keys(), key=lambda t: -freq[t])


def extract_doc_link_ids(body: str) -> set:
    """Extract set of integer ids referenced by [[id|...]] tokens in body."""
    return {int(m) for m in _DOC_LINK_ID_RE.findall(body)}


def sync_inline_links(db_path: str, work_id: int, prev_body: str, new_body: str,
                      user_id: str, group_ids: list,
                      action_history_limit: int = 200) -> None:
    """Add/remove work_links rows derived from [[id|...]] body diff.

    Only adds/removes ids that changed between prev_body and new_body.
    Manual dialog links (not in either body) are left untouched.
    """
    prev_ids = extract_doc_link_ids(prev_body)
    new_ids = extract_doc_link_ids(new_body)
    to_add = new_ids - prev_ids
    to_remove = prev_ids - new_ids
    if not to_add and not to_remove:
        return
    for linked_id in to_add:
        if linked_id != work_id:
            link_add(db_path, work_id, linked_id, user_id, group_ids,
                     action_history_limit=action_history_limit)
    for linked_id in to_remove:
        link_remove(db_path, work_id, linked_id, user_id, group_ids,
                    action_history_limit=action_history_limit)


# -----------------------------------------------------------------------
# Document links
# -----------------------------------------------------------------------

def link_list(db_path: str, work_id: int, user_id: str, group_ids: list,
              channel_ids: list = None) -> tuple:
    """Returns (list_of_linked_items, None) or (None, error_string).

    Each item includes id, title, template, owner_id, visibility fields.
    Only returns linked documents the caller can access.
    """
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    with _lock:
        conn = _connect(db_path)
        try:
            # Verify the source document exists and is accessible
            src = conn.execute(f"SELECT w.id FROM works w WHERE w.id=? AND {cond}", [work_id] + params).fetchone()
            if src is None:
                exists = conn.execute("SELECT id FROM works WHERE id=?", (work_id,)).fetchone()
                return None, ('not_found' if not exists else 'forbidden')

            # Fetch all partner IDs from both directions
            link_rows = conn.execute(
                "SELECT work_id, linked_id FROM work_links WHERE work_id=? OR linked_id=?",
                (work_id, work_id)
            ).fetchall()
            partner_ids = []
            for lr in link_rows:
                pid = lr['linked_id'] if lr['work_id'] == work_id else lr['work_id']
                partner_ids.append(pid)

            if not partner_ids:
                return [], None

            # Fetch accessible partner documents
            ph = ','.join('?' * len(partner_ids))
            sql = (
                f"SELECT w.id, w.title, w.template, w.owner_id, w.visibility, w.group_id "
                f"FROM works w WHERE w.id IN ({ph}) AND {cond} "
                f"ORDER BY w.updated_at DESC"
            )
            rows = conn.execute(sql, partner_ids + params).fetchall()
            return [dict(r) for r in rows], None
        finally:
            conn.close()


def link_add(db_path: str, work_id: int, linked_id: int,
             user_id: str, group_ids: list,
             action_history_limit: int = 200,
             channel_ids: list = None) -> dict:
    """Create a bidirectional link between work_id and linked_id."""
    if work_id == linked_id:
        return {'success': False, 'error': 'self_link'}
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    now = _now()
    # Normalise so smaller id is always work_id
    a, b = (work_id, linked_id) if work_id < linked_id else (linked_id, work_id)
    with _lock:
        conn = _connect(db_path)
        try:
            # Both documents must exist and be accessible
            for wid in (work_id, linked_id):
                row = conn.execute(f"SELECT w.id FROM works w WHERE w.id=? AND {cond}", [wid] + params).fetchone()
                if row is None:
                    exists = conn.execute("SELECT id FROM works WHERE id=?", (wid,)).fetchone()
                    return {'success': False, 'error': 'not_found' if not exists else 'forbidden'}
            try:
                conn.execute(
                    "INSERT INTO work_links(work_id, linked_id, created_at) VALUES (?, ?, ?)",
                    (a, b, now)
                )
            except sqlite3.IntegrityError:
                return {'success': False, 'error': 'already_linked'}
            # Fetch titles for logging
            src_row = conn.execute("SELECT title, template FROM works WHERE id=?", (work_id,)).fetchone()
            lnk_row = conn.execute("SELECT title FROM works WHERE id=?", (linked_id,)).fetchone()
            src_title = src_row['title'] if src_row else ''
            src_type = src_row['template'] if src_row else ''
            linked_title = lnk_row['title'] if lnk_row else ''
            _log_action(conn, user_id, 'link_add', work_id, src_title, src_type,
                        detail=linked_title, action_history_limit=action_history_limit)
            conn.commit()
            return {'success': True}
        finally:
            conn.close()


def link_remove(db_path: str, work_id: int, linked_id: int,
                user_id: str, group_ids: list,
                action_history_limit: int = 200,
                channel_ids: list = None) -> dict:
    """Remove the link between work_id and linked_id."""
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    a, b = (work_id, linked_id) if work_id < linked_id else (linked_id, work_id)
    with _lock:
        conn = _connect(db_path)
        try:
            # Caller must have access to the source document
            src = conn.execute(
                f"SELECT w.id, w.title, w.template FROM works w WHERE w.id=? AND {cond}",
                [work_id] + params
            ).fetchone()
            if src is None:
                return {'success': False, 'error': 'forbidden'}
            lnk_row = conn.execute("SELECT title FROM works WHERE id=?", (linked_id,)).fetchone()
            linked_title = lnk_row['title'] if lnk_row else ''
            cur = conn.execute(
                "DELETE FROM work_links WHERE work_id=? AND linked_id=?", (a, b)
            )
            if cur.rowcount == 0:
                return {'success': False, 'error': 'not_found'}
            _log_action(conn, user_id, 'link_remove', work_id, src['title'] or '', src['template'] or '',
                        detail=linked_title, action_history_limit=action_history_limit)
            conn.commit()
            return {'success': True}
        finally:
            conn.close()


def _log_action(conn: sqlite3.Connection, user_id: str, action: str,
                work_id, work_title: str, work_type: str,
                detail: str = '', history_id=None,
                action_history_limit: int = 200) -> None:
    """Insert a user_action_log row and trim excess entries. Must be called within an open transaction."""
    now = _now()
    conn.execute(
        "INSERT INTO user_action_log(user_id, action, work_id, work_title, work_type, detail, history_id, acted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, action, work_id, work_title or '', work_type or '', detail or '', history_id, now)
    )
    conn.execute(
        "DELETE FROM user_action_log WHERE user_id=? AND id NOT IN ("
        "  SELECT id FROM user_action_log WHERE user_id=? ORDER BY id DESC LIMIT ?"
        ")",
        (user_id, user_id, action_history_limit)
    )


def action_log_list(db_path: str, user_id: str, limit: int = 200) -> list:
    """Return user_action_log entries for user_id, newest first, up to limit.

    Each entry also has:
      diff_available  - True if action='edit' AND both this history row AND its predecessor
                        (the snapshot taken just before this edit) still exist.
      prev_history_id - The id of the predecessor works_history row (None if not available).
    """
    with _lock:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                "SELECT id, action, work_id, work_title, work_type, detail, history_id, acted_at "
                "FROM user_action_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
            result = []
            for r in rows:
                item = dict(r)
                diff_available = False
                prev_history_id = None
                if r['action'] == 'edit' and r['history_id'] and r['work_id']:
                    hist_ok = conn.execute(
                        "SELECT id FROM works_history WHERE id=?", (r['history_id'],)
                    ).fetchone()
                    if hist_ok:
                        prev_row = conn.execute(
                            "SELECT id FROM works_history WHERE work_id=? AND id < ? "
                            "ORDER BY id DESC LIMIT 1",
                            (r['work_id'], r['history_id'])
                        ).fetchone()
                        if prev_row:
                            prev_history_id = prev_row['id']
                            diff_available = True
                item['diff_available'] = diff_available
                item['prev_history_id'] = prev_history_id
                result.append(item)
            return result
        finally:
            conn.close()


def link_resolve(db_path: str, target_id: int, user_id: str, group_ids: list,
                 channel_ids: list = None) -> tuple:
    """Fetch minimal info about a document for link-add preview.

    Returns (item_dict, None) or (None, error_string).
    item_dict contains id, title, template, owner_id.
    """
    if channel_ids is None:
        channel_ids = []
    cond, params = _access_cond(user_id, group_ids, channel_ids=channel_ids)
    with _lock:
        conn = _connect(db_path)
        try:
            sql = f"SELECT w.id, w.title, w.template, w.owner_id FROM works w WHERE w.id=? AND {cond}"
            row = conn.execute(sql, [target_id] + params).fetchone()
            if row is None:
                exists = conn.execute("SELECT id FROM works WHERE id=?", (target_id,)).fetchone()
                return None, ('not_found' if not exists else 'forbidden')
            return dict(row), None
        finally:
            conn.close()


# -----------------------------------------------------------------------
# Channel management
# -----------------------------------------------------------------------

def get_user_channel_ids(db_path: str, user_id: str, group_ids: list,
                         group_names: list = None) -> list:
    """Return list of channel IDs the user can access (direct or via group membership).

    group_ids: UUIDs of groups the user belongs to.
    group_names: names of those same groups (for backward compat with records stored by name).
    """
    # Combine UUIDs and names so both old (name-stored) and new (UUID-stored) records match
    group_refs = list(group_ids)
    if group_names:
        for n in group_names:
            if n not in group_refs:
                group_refs.append(n)
    with _lock:
        conn = _connect(db_path)
        try:
            if group_refs:
                ph = ','.join('?' * len(group_refs))
                rows = conn.execute(
                    f"SELECT DISTINCT channel_id FROM channel_members "
                    f"WHERE (member_type='user' AND member_id=?) "
                    f"OR (member_type='group' AND member_id IN ({ph}))",
                    [user_id] + group_refs
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT channel_id FROM channel_members "
                    "WHERE member_type='user' AND member_id=?",
                    [user_id]
                ).fetchall()
            return [r['channel_id'] for r in rows]
        finally:
            conn.close()


def channel_list(db_path: str, user_id: str, group_ids: list,
                 group_names: list = None) -> list:
    """Return channels accessible to the user, with admin_id."""
    channel_ids = get_user_channel_ids(db_path, user_id, group_ids, group_names=group_names)
    if not channel_ids:
        return []
    ph = ','.join('?' * len(channel_ids))
    with _lock:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                f"SELECT id, name, admin_id, created_at FROM channels WHERE id IN ({ph}) ORDER BY name",
                channel_ids
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def channel_create(db_path: str, name: str, admin_id: str) -> dict:
    """Create a new channel. Creator becomes admin and first member."""
    channel_id = str(uuid.uuid4())
    now = _now()
    with _lock:
        conn = _connect(db_path)
        try:
            conn.execute(
                "INSERT INTO channels(id, name, admin_id, created_at) VALUES (?, ?, ?, ?)",
                (channel_id, name, admin_id, now)
            )
            conn.execute(
                "INSERT INTO channel_members(channel_id, member_type, member_id) VALUES (?, 'user', ?)",
                (channel_id, admin_id)
            )
            conn.commit()
            return {'success': True, 'id': channel_id}
        finally:
            conn.close()


def channel_get(db_path: str, channel_id: str, user_id: str, group_ids: list,
                group_names: list = None) -> dict:
    """Return channel info + member list. User must be a member."""
    channel_ids = get_user_channel_ids(db_path, user_id, group_ids, group_names=group_names)
    if channel_id not in channel_ids:
        return {'success': False, 'error': 'forbidden'}
    with _lock:
        conn = _connect(db_path)
        try:
            ch = conn.execute(
                "SELECT id, name, admin_id, created_at FROM channels WHERE id=?",
                (channel_id,)
            ).fetchone()
            if ch is None:
                return {'success': False, 'error': 'not_found'}
            members = conn.execute(
                "SELECT member_type, member_id FROM channel_members "
                "WHERE channel_id=? ORDER BY member_type, member_id",
                (channel_id,)
            ).fetchall()
            return {
                'success': True,
                'channel': dict(ch),
                'members': [dict(m) for m in members],
            }
        finally:
            conn.close()


def channel_update(db_path: str, channel_id: str, actor_id: str, name: str) -> dict:
    """Update channel name. Admin only."""
    with _lock:
        conn = _connect(db_path)
        try:
            ch = conn.execute("SELECT admin_id FROM channels WHERE id=?", (channel_id,)).fetchone()
            if ch is None:
                return {'success': False, 'error': 'not_found'}
            if ch['admin_id'] != actor_id:
                return {'success': False, 'error': 'not_admin'}
            conn.execute("UPDATE channels SET name=? WHERE id=?", (name, channel_id))
            conn.commit()
            return {'success': True}
        finally:
            conn.close()


def channel_member_add(db_path: str, channel_id: str, actor_id: str,
                       member_type: str, member_id: str) -> dict:
    """Add a user or group to a channel. Admin only."""
    if member_type not in ('user', 'group'):
        return {'success': False, 'error': 'invalid_type'}
    with _lock:
        conn = _connect(db_path)
        try:
            ch = conn.execute("SELECT admin_id FROM channels WHERE id=?", (channel_id,)).fetchone()
            if ch is None:
                return {'success': False, 'error': 'not_found'}
            if ch['admin_id'] != actor_id:
                return {'success': False, 'error': 'not_admin'}
            conn.execute(
                "INSERT OR IGNORE INTO channel_members(channel_id, member_type, member_id) "
                "VALUES (?, ?, ?)",
                (channel_id, member_type, member_id)
            )
            conn.commit()
            return {'success': True}
        finally:
            conn.close()


def channel_member_remove(db_path: str, channel_id: str, actor_id: str,
                          member_type: str, member_id: str) -> dict:
    """Remove a member from a channel. Admin only; admin cannot remove themselves."""
    with _lock:
        conn = _connect(db_path)
        try:
            ch = conn.execute("SELECT admin_id FROM channels WHERE id=?", (channel_id,)).fetchone()
            if ch is None:
                return {'success': False, 'error': 'not_found'}
            if ch['admin_id'] != actor_id:
                return {'success': False, 'error': 'not_admin'}
            if member_type == 'user' and member_id == actor_id:
                return {'success': False, 'error': 'cannot_remove_admin'}
            conn.execute(
                "DELETE FROM channel_members WHERE channel_id=? AND member_type=? AND member_id=?",
                (channel_id, member_type, member_id)
            )
            conn.commit()
            return {'success': True}
        finally:
            conn.close()


def channel_delete(db_path: str, channel_id: str, actor_id: str) -> dict:
    """Delete a channel and all its works. Admin only."""
    with _lock:
        conn = _connect(db_path)
        try:
            ch = conn.execute("SELECT admin_id FROM channels WHERE id=?", (channel_id,)).fetchone()
            if ch is None:
                return {'success': False, 'error': 'not_found'}
            if ch['admin_id'] != actor_id:
                return {'success': False, 'error': 'not_admin'}
            conn.execute("DELETE FROM works_history WHERE work_id IN "
                         "(SELECT id FROM works WHERE channel_id=?)", (channel_id,))
            conn.execute("DELETE FROM works WHERE channel_id=?", (channel_id,))
            conn.execute("DELETE FROM channel_members WHERE channel_id=?", (channel_id,))
            conn.execute("DELETE FROM channels WHERE id=?", (channel_id,))
            conn.commit()
            return {'success': True}
        finally:
            conn.close()


def channel_set_admin(db_path: str, channel_id: str, actor_id: str, new_admin_id: str) -> dict:
    """Transfer admin role to a channel member. Current admin only."""
    with _lock:
        conn = _connect(db_path)
        try:
            ch = conn.execute("SELECT admin_id FROM channels WHERE id=?", (channel_id,)).fetchone()
            if ch is None:
                return {'success': False, 'error': 'not_found'}
            if ch['admin_id'] != actor_id:
                return {'success': False, 'error': 'not_admin'}
            member = conn.execute(
                "SELECT 1 FROM channel_members WHERE channel_id=? AND member_type='user' AND member_id=?",
                (channel_id, new_admin_id)
            ).fetchone()
            if member is None:
                return {'success': False, 'error': 'not_member'}
            conn.execute("UPDATE channels SET admin_id=? WHERE id=?", (new_admin_id, channel_id))
            conn.commit()
            return {'success': True}
        finally:
            conn.close()
