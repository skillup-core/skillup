"""
Skilltalk DB layer — SQLite CRUD and cleanup.
All connections use PRAGMA journal_mode=DELETE (NFS-safe) and PRAGMA foreign_keys=ON.
"""

import base64
import os
import sqlite3
import threading
import time


_KEY = b'\x5f\x3a\x7c\x21\x9b\xe4\x12\x68\xd0\x4f\xa3\x85\x2e\x71\xc9\x56'


def _xor(data: bytes) -> bytes:
    key = _KEY
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _encode(text: str) -> str:
    return base64.b64encode(_xor(text.encode('utf-8'))).decode('ascii')


def _decode(encoded: str) -> str:
    try:
        return _xor(base64.b64decode(encoded.encode('ascii'))).decode('utf-8')
    except Exception:
        return encoded


def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), mode=0o777, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        os.chmod(db_path, 0o666)
    except OSError:
        pass
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str) -> None:
    conn = _connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chatroom (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            created_at   INTEGER NOT NULL,
            last_chat_at INTEGER,
            created_by   TEXT
        );

        CREATE TABLE IF NOT EXISTS chatroom_member (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chatroom_id INTEGER NOT NULL REFERENCES chatroom(id),
            uid         TEXT    NOT NULL,
            joined_at   INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chatroom_id INTEGER NOT NULL REFERENCES chatroom(id),
            sender_uid  TEXT    NOT NULL,
            sender_ip   TEXT    NOT NULL,
            contents    TEXT    NOT NULL,
            mimetype    TEXT    NOT NULL DEFAULT 'text/plain',
            created_at  INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_chat_chatroom
            ON chat(chatroom_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_chatroom_member_room
            ON chatroom_member(chatroom_id);
        CREATE INDEX IF NOT EXISTS idx_chatroom_member_uid
            ON chatroom_member(uid);
    """)
    conn.commit()
    conn.close()


class SkilltalkDB:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = _connect(db_path)

    def _execute(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def _commit(self):
        with self._lock:
            self._conn.commit()

    # ------------------------------------------------------------------
    # Chatroom
    # ------------------------------------------------------------------

    def get_rooms_for_uid(self, uid: str) -> list:
        with self._lock:
            rows = self._conn.execute("""
                SELECT cr.id, cr.name, cr.created_at, cr.last_chat_at,
                       COALESCE(cr.created_by, (
                           SELECT cm2.uid FROM chatroom_member cm2
                           WHERE cm2.chatroom_id = cr.id
                           ORDER BY cm2.joined_at ASC, cm2.id ASC
                           LIMIT 1
                       )) AS created_by
                FROM chatroom cr
                JOIN chatroom_member cm ON cm.chatroom_id = cr.id
                WHERE cm.uid = ?
                ORDER BY COALESCE(cr.last_chat_at, cr.created_at) DESC
            """, (uid,)).fetchall()
        return [dict(r) for r in rows]

    def create_room(self, name: str, member_uids: list, created_by: str = None) -> int:
        now = int(time.time())
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO chatroom (name, created_at, created_by) VALUES (?, ?, ?)",
                (name, now, created_by)
            )
            room_id = cur.lastrowid
            for uid in member_uids:
                self._conn.execute(
                    "INSERT INTO chatroom_member (chatroom_id, uid, joined_at) VALUES (?, ?, ?)",
                    (room_id, uid, now)
                )
            self._conn.commit()
        return room_id

    def get_room(self, room_id: int) -> dict:
        with self._lock:
            row = self._conn.execute("""
                SELECT id, name, created_at, last_chat_at,
                       COALESCE(created_by, (
                           SELECT cm.uid FROM chatroom_member cm
                           WHERE cm.chatroom_id = chatroom.id
                           ORDER BY cm.joined_at ASC, cm.id ASC
                           LIMIT 1
                       )) AS created_by
                FROM chatroom WHERE id = ?
            """, (room_id,)).fetchone()
        return dict(row) if row else None

    def delete_room(self, room_id: int) -> None:
        """Delete room and all its chats and members."""
        with self._lock:
            self._conn.execute("DELETE FROM chat WHERE chatroom_id = ?", (room_id,))
            self._conn.execute("DELETE FROM chatroom_member WHERE chatroom_id = ?", (room_id,))
            self._conn.execute("DELETE FROM chatroom WHERE id = ?", (room_id,))
            self._conn.commit()

    def get_room_members(self, room_id: int) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT uid FROM chatroom_member WHERE chatroom_id = ?",
                (room_id,)
            ).fetchall()
        return [r['uid'] for r in rows]

    def is_member(self, room_id: int, uid: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM chatroom_member WHERE chatroom_id = ? AND uid = ?",
                (room_id, uid)
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Chat messages
    # ------------------------------------------------------------------

    def insert_chat(self, room_id: int, sender_uid: str, sender_ip: str, contents: str, mimetype: str = 'text/plain') -> int:
        now = int(time.time())
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO chat (chatroom_id, sender_uid, sender_ip, contents, mimetype, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (room_id, sender_uid, sender_ip, _encode(contents), mimetype, now)
            )
            chat_id = cur.lastrowid
            self._conn.execute(
                "UPDATE chatroom SET last_chat_at = ? WHERE id = ?",
                (now, room_id)
            )
            self._conn.commit()
        return chat_id

    def get_chats(self, room_id: int, before_id: int = None, limit: int = 50) -> list:
        with self._lock:
            if before_id is not None:
                rows = self._conn.execute("""
                    SELECT id, chatroom_id, sender_uid, sender_ip, contents, mimetype, created_at
                    FROM chat
                    WHERE chatroom_id = ? AND id < ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (room_id, before_id, limit)).fetchall()
            else:
                rows = self._conn.execute("""
                    SELECT id, chatroom_id, sender_uid, sender_ip, contents, mimetype, created_at
                    FROM chat
                    WHERE chatroom_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (room_id, limit)).fetchall()
        result = [dict(r) for r in reversed(rows)]
        for r in result:
            r['contents'] = _decode(r['contents'])
        return result

    def get_chat_by_id(self, chat_id: int) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, chatroom_id, sender_uid, sender_ip, contents, mimetype, created_at FROM chat WHERE id = ?",
                (chat_id,)
            ).fetchone()
        if row is None:
            return None
        r = dict(row)
        r['contents'] = _decode(r['contents'])
        return r

    def delete_chat(self, chat_id: int, sender_uid: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM chat WHERE id = ? AND sender_uid = ?",
                (chat_id, sender_uid)
            )
            self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Member leave
    # ------------------------------------------------------------------

    def leave_room(self, room_id: int, uid: str) -> int:
        """Remove uid from room. Returns remaining member count."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM chatroom_member WHERE chatroom_id = ? AND uid = ?",
                (room_id, uid)
            )
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM chatroom_member WHERE chatroom_id = ?",
                (room_id,)
            ).fetchone()
            remaining = row['cnt']
            if remaining == 0:
                self._conn.execute("DELETE FROM chat WHERE chatroom_id = ?", (room_id,))
                self._conn.execute("DELETE FROM chatroom WHERE id = ?", (room_id,))
            self._conn.commit()
        return remaining

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, chatroom_retention_days: int = 30, chat_retention_days: int = 30) -> None:
        now = int(time.time())
        chat_cutoff = now - chat_retention_days * 86400
        room_cutoff = now - chatroom_retention_days * 86400
        with self._lock:
            self._conn.execute("DELETE FROM chat WHERE created_at < ?", (chat_cutoff,))
            self._conn.execute(
                "DELETE FROM chatroom WHERE (last_chat_at IS NOT NULL AND last_chat_at < ?) "
                "OR (last_chat_at IS NULL AND created_at < ?)",
                (room_cutoff, room_cutoff)
            )
            self._conn.execute(
                "DELETE FROM chatroom_member WHERE chatroom_id NOT IN (SELECT id FROM chatroom)"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
